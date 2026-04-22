"""Stuck detection for Vellum's agent.

Watches for signs the agent is spinning — repeated tool calls, revisions
without progress, approaching budget — and surfaces a clean signal to the
runtime. The runtime decides what to do with the signal (it will call the
`check_stuck` handler to surface a decision_point to the user).

Per Ian's directive: budgets are SOFT signals, not hard caps. We detect and
report; we never terminate the agent mid-thought.

v2 (day 2): every surfaced StuckSignal also emits an investigation_log entry
of type ``stuck_declared``. The v1 ``check_stuck`` tool call continues to
fire separately for backwards compatibility; the investigation_log emission
is additive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from vellum import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal type
# ---------------------------------------------------------------------------


@dataclass
class StuckSignal:
    kind: str                       # "loop" | "section_budget" | "session_budget" | "revision_stall"
    detail: str                     # short human-readable explanation
    summary_of_attempts: str        # ready to feed into check_stuck tool's `summary_of_attempts`
    options_for_user: list[dict]    # [{"label": ..., "implications": ..., "recommended": bool}, ...]


# ---------------------------------------------------------------------------
# Per-session tracking state
# ---------------------------------------------------------------------------


@dataclass
class _SessionState:
    # tool-call loop tracking
    tool_call_counts: Counter = field(default_factory=Counter)     # (tool_name, args_hash) -> count
    tool_call_examples: dict = field(default_factory=dict)         # (tool_name, args_hash) -> (tool_name, args)
    loop_reported: set = field(default_factory=set)                # (tool_name, args_hash) already reported

    # token budgets
    section_tokens: Counter = field(default_factory=Counter)       # section_id -> input tokens (this session)
    session_tokens: int = 0
    section_budget_reported: set = field(default_factory=set)      # section_ids already reported
    session_budget_reported: bool = False

    # revision stall (upsert_section calls per section, reset on needs_input resolution)
    upsert_counts_since_resolve: Counter = field(default_factory=Counter)  # section_id -> count
    revision_stall_reported: set = field(default_factory=set)              # section_ids already reported

    # v2: same_tool_no_progress — soft-loop heuristic that catches an agent
    # repeatedly calling the same tool (any args) without producing a new
    # section. Track total sections created, and the baseline snapshot of
    # that count at each tool's first call.
    tool_name_counts: Counter = field(default_factory=Counter)             # tool_name -> count (any args)
    sections_created: int = 0                                              # running total this session
    tool_name_first_sections_snapshot: dict = field(default_factory=dict)  # tool_name -> sections_created at first call
    same_tool_no_progress_reported: set = field(default_factory=set)       # tool_names already reported

    # Investigation-log emission side: dedupe by (kind, key) so we never
    # write two stuck_declared entries for the same underlying signal.
    investigation_log_emitted: set = field(default_factory=set)


_STATE_LOCK = threading.Lock()
_SESSION_STATE: dict[str, _SessionState] = {}

# Upsert tools that count as revisions against the same section.
_UPSERT_TOOL_NAMES = {"upsert_section"}
# Threshold for revision stall — per spec, strictly more than 3 revisions.
_REVISION_STALL_THRESHOLD = 3
# Session budget hard-coded sanity bound: 10x SECTION_TOKEN_BUDGET.
_SESSION_BUDGET_MULTIPLIER = 10
# v2: same_tool_no_progress threshold — same tool name (any args) called
# this many times in a session without creating any new section fires.
_SAME_TOOL_NO_PROGRESS_THRESHOLD = 8


def _state(session_id: str) -> _SessionState:
    s = _SESSION_STATE.get(session_id)
    if s is None:
        s = _SessionState()
        _SESSION_STATE[session_id] = s
    return s


def _hash_args(args: dict) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except TypeError:
        blob = repr(sorted(args.items(), key=lambda kv: str(kv[0])))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _pretty_args(args: dict, max_len: int = 120) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        blob = str(args)
    if len(blob) > max_len:
        return blob[: max_len - 1] + "…"
    return blob


def _emit_investigation_log(session_id: str, signal: StuckSignal) -> None:
    """Append a ``stuck_declared`` entry to the investigation_log for this
    signal. Best-effort: if storage isn't usable (e.g. no work_session row,
    no DB schema) we log and continue, because detecting the stuck state
    is the primary job — the log write is a secondary surface.

    Callers are expected to invoke this at most once per surfaced signal
    (i.e. right before the first ``return signal`` for that signal). The
    per-signal dedup sets (``loop_reported`` et al.) guarantee that.
    """
    # Import lazily to avoid pulling storage/models into module import time
    # (stuck.py is imported from runtime.py, which imports storage itself —
    # the lazy import keeps the one-way dependency explicit).
    try:
        from vellum import models as m
        from vellum import storage
    except Exception:  # pragma: no cover — should never fail in real use
        logger.warning("stuck: could not import storage for investigation_log emit", exc_info=True)
        return
    try:
        ws = storage.get_work_session(session_id)
        if ws is None:
            raise ValueError(f"work_session {session_id} not found")
        storage.append_investigation_log(
            ws.dossier_id,
            m.InvestigationLogAppend(
                entry_type=m.InvestigationLogEntryType.stuck_declared,
                summary=f"[stuck:{signal.kind}] {signal.detail}",
                payload={
                    "kind": signal.kind,
                    "summary_of_attempts": signal.summary_of_attempts,
                    "options": signal.options_for_user,
                },
            ),
            work_session_id=session_id,
        )
    except Exception:
        # Best-effort: a missing work_session row (e.g. self-test using an
        # untracked session id) or a DB error must not prevent the signal
        # from reaching the runtime.
        logger.debug(
            "stuck: investigation_log emit failed for %s/%s", signal.kind, session_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_tool_call(session_id: str, tool_name: str, args: dict) -> Optional[StuckSignal]:
    """Record a tool call; return a loop StuckSignal when the threshold is
    newly crossed for a given (tool_name, args_hash), or a
    same_tool_no_progress StuckSignal when the soft-loop threshold is newly
    crossed for a tool name (any args) without section creation.

    Also bumps per-section counters when args contains section_id or
    after_section_id — so check_revision_stall can use them.
    """
    args = args or {}
    args_hash = _hash_args(args)
    key = (tool_name, args_hash)
    signal: Optional[StuckSignal] = None

    with _STATE_LOCK:
        st = _state(session_id)
        st.tool_call_counts[key] += 1
        st.tool_call_examples.setdefault(key, (tool_name, args))
        count = st.tool_call_counts[key]

        # v2: by-tool-name count (any args) and baseline snapshot of
        # sections_created at the tool's FIRST call — feeds the
        # same_tool_no_progress heuristic.
        st.tool_name_counts[tool_name] += 1
        st.tool_name_first_sections_snapshot.setdefault(tool_name, st.sections_created)
        tool_count = st.tool_name_counts[tool_name]

        # Track section creations: upsert_section with no section_id means a
        # new section was just created. This is how we detect "analytic
        # progress" for same_tool_no_progress.
        if tool_name in _UPSERT_TOOL_NAMES and not args.get("section_id"):
            st.sections_created += 1

        # Bump revision-stall counter on upsert_section calls.
        if tool_name in _UPSERT_TOOL_NAMES:
            section_id = args.get("section_id") or args.get("after_section_id")
            if section_id:
                st.upsert_counts_since_resolve[section_id] += 1

        if count >= config.LOOP_DETECTION_THRESHOLD and key not in st.loop_reported:
            st.loop_reported.add(key)
            pretty = _pretty_args(args)
            detail = (
                f"Tool `{tool_name}` has been called {count} times with the same arguments "
                f"({pretty}) in this session."
            )
            summary = (
                f"I've called `{tool_name}` {count} times with args `{pretty}` and "
                f"I don't seem to be getting new information each time. I may be stuck."
            )
            options = [
                {
                    "label": "Try different arguments or phrasing",
                    "implications": (
                        "I'll reformulate the call (different keywords, narrower/broader scope) "
                        "and try once more before escalating."
                    ),
                    "recommended": True,
                },
                {
                    "label": "Switch to a different tool or source",
                    "implications": (
                        "I'll stop retrying this tool and use an alternative pathway to make progress."
                    ),
                    "recommended": False,
                },
                {
                    "label": "Mark what I have as provisional and move on",
                    "implications": (
                        "I'll record the best result so far as provisional and continue to the "
                        "next open question, flagging this for later follow-up."
                    ),
                    "recommended": False,
                },
            ]
            signal = StuckSignal(
                kind="loop",
                detail=detail,
                summary_of_attempts=summary,
                options_for_user=options,
            )

        # same_tool_no_progress: same tool name called >= threshold times AND
        # no new section created since its first call. Strict "no new section
        # in that span" — if even one section has been created since the
        # first call, we assume the agent is making progress and skip.
        # Checked only if no higher-priority loop signal already fired.
        if (
            signal is None
            and tool_count >= _SAME_TOOL_NO_PROGRESS_THRESHOLD
            and tool_name not in st.same_tool_no_progress_reported
        ):
            baseline = st.tool_name_first_sections_snapshot.get(tool_name, 0)
            if st.sections_created == baseline:
                st.same_tool_no_progress_reported.add(tool_name)
                detail = (
                    f"Tool `{tool_name}` has been called {tool_count} times in this "
                    f"session without producing any new section — the agent may be "
                    f"spinning without making analytic progress."
                )
                summary = (
                    f"I've called `{tool_name}` {tool_count} times in this session and "
                    f"haven't produced a new section since I started. I may be researching "
                    f"without synthesizing — worth pausing to check."
                )
                options = [
                    {
                        "label": "Let me keep going — I'm close",
                        "implications": (
                            "I'll continue with the same approach; the heuristic is advisory, "
                            "not a hard stop."
                        ),
                        "recommended": False,
                    },
                    {
                        "label": "Pause for your direction",
                        "implications": (
                            "I'll hand off with a summary of what I've looked at so far and "
                            "wait for you to steer me toward a section to draft."
                        ),
                        "recommended": True,
                    },
                ]
                signal = StuckSignal(
                    kind="same_tool_no_progress",
                    detail=detail,
                    summary_of_attempts=summary,
                    options_for_user=options,
                )

    if signal is not None:
        _emit_investigation_log(session_id, signal)
    return signal


def record_input_tokens(session_id: str, section_id: Optional[str], tokens: int) -> None:
    """Accumulate input-token usage, optionally scoped to a section.

    Intended to be called once per model turn with the prompt-token count,
    tagged with the section currently being worked on (if any). If no
    section is active, still accumulates to the session-wide total.
    """
    if tokens <= 0:
        return
    with _STATE_LOCK:
        st = _state(session_id)
        st.session_tokens += tokens
        if section_id:
            st.section_tokens[section_id] += tokens


def check_section_budget(dossier_id: str, session_id: str) -> Optional[StuckSignal]:
    """If any section's accumulated input tokens in THIS session exceed
    config.SECTION_TOKEN_BUDGET, return StuckSignal(kind='section_budget').
    """
    signal: Optional[StuckSignal] = None
    with _STATE_LOCK:
        st = _state(session_id)
        budget = config.SECTION_TOKEN_BUDGET
        for section_id, used in st.section_tokens.items():
            if used > budget and section_id not in st.section_budget_reported:
                st.section_budget_reported.add(section_id)
                detail = (
                    f"Section `{section_id}` has consumed {used} input tokens in this session, "
                    f"exceeding the soft budget of {budget}."
                )
                summary = (
                    f"I've spent {used} input tokens working on section `{section_id}` "
                    f"(soft budget is {budget}). I may be over-investing here relative to its scope."
                )
                options = [
                    {
                        "label": "Accept the current draft and move on",
                        "implications": (
                            "I'll treat the section as good-enough for now and move to other open work."
                        ),
                        "recommended": True,
                    },
                    {
                        "label": "Narrow the scope of this section",
                        "implications": (
                            "I'll trim the section's aims (e.g. split into sub-sections or drop a "
                            "branch) so I stop spending tokens on tangents."
                        ),
                        "recommended": False,
                    },
                    {
                        "label": "Keep going — this section is worth the cost",
                        "implications": (
                            "I'll continue; the soft budget is advisory, not a hard cap. I'll "
                            "check in again if I burn another full budget."
                        ),
                        "recommended": False,
                    },
                ]
                signal = StuckSignal(
                    kind="section_budget",
                    detail=detail,
                    summary_of_attempts=summary,
                    options_for_user=options,
                )
                break
    if signal is not None:
        _emit_investigation_log(session_id, signal)
    return signal


def check_revision_stall(dossier_id: str, session_id: str) -> Optional[StuckSignal]:
    """If the same section_id has been the target of upsert_section more than
    _REVISION_STALL_THRESHOLD times in this session AND no needs_input has
    been resolved in that window, return StuckSignal(kind='revision_stall').
    """
    signal: Optional[StuckSignal] = None
    with _STATE_LOCK:
        st = _state(session_id)
        for section_id, count in st.upsert_counts_since_resolve.items():
            if count > _REVISION_STALL_THRESHOLD and section_id not in st.revision_stall_reported:
                st.revision_stall_reported.add(section_id)
                detail = (
                    f"Section `{section_id}` has been rewritten {count} times in this session "
                    f"without any intervening needs_input resolution — the draft isn't converging."
                )
                summary = (
                    f"I've rewritten section `{section_id}` {count} times without converging. "
                    f"I may not have enough information, or the framing may be wrong."
                )
                options = [
                    {
                        "label": "Pick the current version and move on",
                        "implications": (
                            "I'll freeze the latest draft as provisional and stop revising. "
                            "You can push back on it later."
                        ),
                        "recommended": True,
                    },
                    {
                        "label": "Pause and ask you for more context",
                        "implications": (
                            "I'll raise a needs_input with the specific ambiguity blocking me "
                            "rather than keep rewriting blind."
                        ),
                        "recommended": False,
                    },
                    {
                        "label": "Split this section into two",
                        "implications": (
                            "I'll factor the section into smaller pieces if the scope is the "
                            "problem, and revise those independently."
                        ),
                        "recommended": False,
                    },
                ]
                signal = StuckSignal(
                    kind="revision_stall",
                    detail=detail,
                    summary_of_attempts=summary,
                    options_for_user=options,
                )
                break
    if signal is not None:
        _emit_investigation_log(session_id, signal)
    return signal


def check_session_budget(session_id: str) -> Optional[StuckSignal]:
    """Session-wide token ceiling — _SESSION_BUDGET_MULTIPLIER x
    SECTION_TOKEN_BUDGET as a hard-coded sanity bound. Soft signal only.
    """
    signal: Optional[StuckSignal] = None
    with _STATE_LOCK:
        st = _state(session_id)
        ceiling = _SESSION_BUDGET_MULTIPLIER * config.SECTION_TOKEN_BUDGET
        if st.session_tokens > ceiling and not st.session_budget_reported:
            st.session_budget_reported = True
            used = st.session_tokens
            detail = (
                f"Session `{session_id}` has consumed {used} input tokens, exceeding the "
                f"sanity ceiling of {ceiling} (10x section budget)."
            )
            summary = (
                f"I've used {used} input tokens in this work session (sanity ceiling "
                f"is {ceiling}). That's a lot for one sitting — worth checking whether "
                f"I'm still making real progress."
            )
            options = [
                {
                    "label": "Wrap up — deliver what I have and end the session",
                    "implications": (
                        "I'll summarize open items, mark provisional pieces clearly, and end "
                        "the work session so you can review before spending more."
                    ),
                    "recommended": True,
                },
                {
                    "label": "Keep going — the work is clearly progressing",
                    "implications": (
                        "I'll continue; the ceiling is advisory. I'll check in again after "
                        "significant additional progress."
                    ),
                    "recommended": False,
                },
                {
                    "label": "Pause and let me take over",
                    "implications": (
                        "I'll hand off with a summary of what's done, what's provisional, and "
                        "the specific next step I'd take."
                    ),
                    "recommended": False,
                },
            ]
            signal = StuckSignal(
                kind="session_budget",
                detail=detail,
                summary_of_attempts=summary,
                options_for_user=options,
            )
    if signal is not None:
        _emit_investigation_log(session_id, signal)
    return signal


def check_stuck_state(dossier_id: str, session_id: str) -> Optional[StuckSignal]:
    """Composite check — runtime calls this each turn. Returns the first
    signal found from any sub-check. Priority: loop signals are emitted
    inline from record_tool_call, so here we focus on the standing-state
    checks in order of specificity (revision_stall -> section_budget ->
    session_budget).
    """
    for check in (check_revision_stall, check_section_budget):
        sig = check(dossier_id, session_id)
        if sig is not None:
            return sig
    return check_session_budget(session_id)


def mark_needs_input_resolved(session_id: str) -> None:
    """Called when the user answers a needs_input. Resets the
    'section-being-revised-without-progress' counter for revision_stall,
    because the block has been unblocked.
    """
    with _STATE_LOCK:
        st = _state(session_id)
        st.upsert_counts_since_resolve.clear()
        st.revision_stall_reported.clear()


def reset_session(session_id: str) -> None:
    """Clear all internal tracking for this session. Called on
    end_work_session / run() exit.
    """
    with _STATE_LOCK:
        _SESSION_STATE.pop(session_id, None)


# ---------------------------------------------------------------------------
# Structural self-test
# ---------------------------------------------------------------------------


def _run_self_test() -> None:
    sid = "sess_selftest"
    did = "dos_selftest"

    # Start fresh.
    reset_session(sid)

    # 1+2. Loop fires exactly once at threshold, not on subsequent identical calls.
    signals = []
    for _ in range(config.LOOP_DETECTION_THRESHOLD + 1):
        sig = record_tool_call(sid, "web_search", {"q": "FDCPA heirs Texas"})
        if sig is not None:
            signals.append(sig)
    assert len(signals) == 1, f"expected exactly one loop signal, got {len(signals)}"
    assert signals[0].kind == "loop"
    assert signals[0].options_for_user, "options_for_user must be non-empty"
    for opt in signals[0].options_for_user:
        assert "label" in opt and "implications" in opt, "option must have label + implications"

    # 3. Different tool calls alternately do NOT fire a loop signal.
    reset_session(sid)
    for i in range(10):
        tool = "web_search" if i % 2 == 0 else "get_url"
        args = {"q": f"query-{i}"} if tool == "web_search" else {"url": f"https://x/{i}"}
        assert record_tool_call(sid, tool, args) is None, "no loop should fire on varied calls"

    # 4. Section budget: exceed via record_input_tokens.
    reset_session(sid)
    record_input_tokens(sid, "sec_alpha", config.SECTION_TOKEN_BUDGET + 1)
    sig = check_section_budget(did, sid)
    assert sig is not None and sig.kind == "section_budget", "section_budget should fire"
    # Does not re-fire for the same section.
    assert check_section_budget(did, sid) is None, "section_budget should not re-fire"

    # 5. Revision stall: 4 upserts on same section -> fires.
    reset_session(sid)
    for _ in range(4):
        record_tool_call(sid, "upsert_section", {"section_id": "sec_open"})
    sig = check_revision_stall(did, sid)
    assert sig is not None and sig.kind == "revision_stall", "revision_stall should fire"

    # 6. After mark_needs_input_resolved, the stall counter resets — more
    # upserts within the reset window (up to threshold) should NOT fire again.
    mark_needs_input_resolved(sid)
    for _ in range(_REVISION_STALL_THRESHOLD):  # 3 more — at threshold, not past it
        record_tool_call(sid, "upsert_section", {"section_id": "sec_open"})
    assert check_revision_stall(did, sid) is None, (
        "revision_stall must not fire immediately after needs_input resolution"
    )

    # 7. reset_session clears state — next identical batch does not trip loop.
    reset_session(sid)
    trip = [
        record_tool_call(sid, "web_search", {"q": "reset-check"})
        for _ in range(config.LOOP_DETECTION_THRESHOLD - 1)
    ]
    assert all(s is None for s in trip), "after reset, under-threshold calls must not signal"

    # Composite check smoke test.
    reset_session(sid)
    record_input_tokens(sid, "sec_beta", config.SECTION_TOKEN_BUDGET + 1)
    composite = check_stuck_state(did, sid)
    assert composite is not None and composite.kind == "section_budget"

    # Session budget smoke test.
    reset_session(sid)
    record_input_tokens(sid, None, _SESSION_BUDGET_MULTIPLIER * config.SECTION_TOKEN_BUDGET + 1)
    sig = check_session_budget(sid)
    assert sig is not None and sig.kind == "session_budget"

    reset_session(sid)
    print("all stuck checks OK")


if __name__ == "__main__":
    _run_self_test()
