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

Calibration rationale (day 5)
-----------------------------
The thresholds and exemptions here are tuned against a realistic 40-turn
demo run (3-6 sub-investigations, 30-80 source logs, 3+ artifacts). The
goal: don't trip on healthy iteration, but still catch genuine spins fast.

* ``_EXEMPT_FROM_LOOP`` — some tools are by-design iterative. An agent will
  legitimately call ``update_debrief`` and ``update_investigation_plan``
  several times with near-identical args as the investigation matures.
  Treating those as loops was producing false alarms, so they're skipped
  from the exact-args loop detector.
* ``_EXEMPT_FROM_NO_PROGRESS`` — source-reading bursts are work, not spin.
  ``log_source_consulted`` and ``web_search`` routinely fire 10-30 times
  during a research phase before the agent returns to drafting a section.
  The same-tool-no-progress heuristic was originally meant for synthesis
  tools stuck in a loop; exempting reading tools keeps it honest. (Note:
  args differ per call for these anyway, so the exact-args loop detector
  still catches true repeats.)
* ``_REVISION_STALL_THRESHOLD`` was 3, raised to 5 (config-driven). A
  finding section revised 4-5 times as evidence accumulates is good, not
  stall. Any storage mutation that indicates progress — a needs_input
  resolve, a new artifact, or a spawned sub-investigation — resets the
  per-section revision counter, via ``mark_progress`` (called from the
  relevant storage-mutating handlers).
* ``_SESSION_BUDGET_MULTIPLIER`` was 10, raised to 15 (config-driven). A
  40-turn session with cached prompts + ~30k input avg could legitimately
  brush 300k; 450k gives day-5 comfort without giving up the sanity bound.

All numbers are still SOFT signals. We detect and report; the runtime
surfaces a decision_point; the agent and user decide whether to continue.
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
    # Escalation tier (1 = heads-up, 2 = decision_point, 3+ = forced-recommended
    # decision_point). Default 2 matches pre-tier behavior; callers set
    # explicitly via ``_assign_tier_and_emit``.
    tier: int = 2


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

    # Phase 2: progress-forcing. Counts turns since the last turn that
    # emitted at least one "progress" tool call. Reset to 0 when a progress
    # tool is observed; incremented on every end-of-turn where it wasn't.
    turns_since_progress: int = 0
    no_progress_reported: bool = False

    # Phase 3 part C: stuck-escalation tier tracking. Every surfaced signal
    # bumps this counter; the signal's ``tier`` is ``min(count, 3)``. The
    # runtime uses tier to decide whether to emit a heads-up-only note
    # (tier 1), a standard decision_point (tier 2), or a forced-recommended
    # decision_point (tier 3+).
    stuck_escalation_count: int = 0


_STATE_LOCK = threading.Lock()
_SESSION_STATE: dict[str, _SessionState] = {}

# Upsert tools that count as revisions against the same section.
_UPSERT_TOOL_NAMES = {"upsert_section"}
# Tools whose purpose is ITERATIVE refinement — calling them repeatedly with
# near-identical args is expected, not loop behavior. Exempted from the
# exact-args loop detector.
_EXEMPT_FROM_LOOP: set = {"update_debrief", "update_investigation_plan"}
# Tools whose purpose is source-reading / research; calling them many times
# in a research burst is WORK, not spin. Exempted from the
# same_tool_no_progress heuristic. Args usually differ per call anyway, so
# the exact-args loop detector still catches true repeats.
_EXEMPT_FROM_NO_PROGRESS: set = {"log_source_consulted", "web_search"}
# Tools beyond needs_input whose execution counts as "analytic progress"
# for the revision-stall counter: a new artifact or a new sub-investigation
# within the same session means the agent is moving forward, so any
# accumulated upsert-counts are reset.
_PROGRESS_MUTATION_TOOL_NAMES = {"add_artifact", "spawn_sub_investigation"}
# Threshold for revision stall — strictly more than this many revisions on
# the same section without progress fires the signal. Overridable via
# ``VELLUM_STUCK_REVISION_STALL_THRESHOLD``. Default raised from 3 → 5
# (day 5): real findings legitimately revise 4-5 times as evidence lands.
_REVISION_STALL_THRESHOLD = config.STUCK_REVISION_STALL_THRESHOLD
# Session budget sanity bound: N x SECTION_TOKEN_BUDGET. Overridable via
# ``VELLUM_STUCK_SESSION_BUDGET_MULT``. Default raised from 10 → 15
# (day 5) to cover realistic 40-turn cached-prompt runs.
_SESSION_BUDGET_MULTIPLIER = config.STUCK_SESSION_BUDGET_MULT
# v2: same_tool_no_progress threshold — same tool name (any args) called
# this many times in a session without creating any new section fires.
_SAME_TOOL_NO_PROGRESS_THRESHOLD = 8

# Phase 2: progress-forcing. A turn that calls any tool in this set counts
# as "progress" — the agent moved the investigation state in a way that's
# not just refining prose. Tools NOT in this set (upsert_section,
# update_section_state, append_reasoning, log_source_consulted,
# update_debrief, update_investigation_plan, update_artifact, reorder_sections)
# can all be called in loops without advancing the case, so they don't
# reset the counter. declare_stuck / check_stuck are included — declaring
# stuck IS an action, and excluding them would produce the absurd state
# where the agent's stuck declaration trips another stuck signal.
_PROGRESS_TOOL_NAMES: set = {
    "flag_needs_input",
    "flag_decision_point",
    "spawn_sub_investigation",
    "complete_sub_investigation",
    "mark_considered_and_rejected",
    "mark_ruled_out",
    "add_artifact",
    "schedule_wake",
    "mark_investigation_delivered",
    "update_working_theory",
    "declare_stuck",
    "check_stuck",
    "request_user_paste",
    "summarize_session",
    "record_premise_challenge",
    "update_sub_investigation",
}


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


def _assign_tier_and_emit(session_id: str, signal: StuckSignal) -> StuckSignal:
    """Stamp a tier onto ``signal`` based on how many stuck signals have
    been surfaced in this session so far, emit the investigation_log entry,
    and return the (mutated) signal.

    Tier policy (see Phase 3 part C):
      * 1st signal in session -> tier 1 (heads-up; runtime suppresses
        decision_point and just appends a reasoning note).
      * 2nd signal            -> tier 2 (standard decision_point).
      * 3rd and beyond        -> tier 3 (decision_point with the FIRST
        option's ``recommended`` forced True; others forced False).

    This is the single place tier assignment happens; every caller that
    previously did ``_emit_investigation_log(...); return signal`` now does
    ``return _assign_tier_and_emit(...)``.
    """
    with _STATE_LOCK:
        st = _state(session_id)
        st.stuck_escalation_count += 1
        tier = min(st.stuck_escalation_count, 3)
    signal.tier = tier
    if tier >= 3 and signal.options_for_user:
        for i, opt in enumerate(signal.options_for_user):
            opt["recommended"] = (i == 0)
    _emit_investigation_log(session_id, signal)
    return signal


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

        # Day 5: any storage mutation that represents ANALYTIC PROGRESS
        # (new artifact, spawned sub-investigation) resets the
        # revision-stall counters — the agent is clearly moving forward.
        if tool_name in _PROGRESS_MUTATION_TOOL_NAMES:
            st.upsert_counts_since_resolve.clear()
            st.revision_stall_reported.clear()

        # Day 5: exempt iterative-by-design tools from the exact-args loop
        # detector. update_debrief / update_investigation_plan are designed
        # to be called repeatedly with similar args as the run matures.
        if tool_name in _EXEMPT_FROM_LOOP:
            loop_detection_enabled = False
        else:
            loop_detection_enabled = True

        if loop_detection_enabled and count >= config.LOOP_DETECTION_THRESHOLD and key not in st.loop_reported:
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
        # Day 5: source-reading tools (log_source_consulted, web_search) are
        # exempt — reading many sources is WORK, not spin.
        if (
            signal is None
            and tool_name not in _EXEMPT_FROM_NO_PROGRESS
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
        return _assign_tier_and_emit(session_id, signal)
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
        return _assign_tier_and_emit(session_id, signal)
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
        return _assign_tier_and_emit(session_id, signal)
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
        return _assign_tier_and_emit(session_id, signal)
    return signal


def check_stuck_state(dossier_id: str, session_id: str) -> Optional[StuckSignal]:
    """Composite check — runtime calls this each turn. Returns the first
    signal found from any sub-check. Priority: loop signals are emitted
    inline from record_tool_call, so here we focus on the standing-state
    checks in order of specificity (no_progress -> revision_stall ->
    section_budget -> session_budget). no_progress runs first because it's
    the one that catches "nothing is advancing" before any of the narrower
    checks have a chance to trip.
    """
    sig = check_no_progress(session_id)
    if sig is not None:
        return sig
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


def record_turn_end(session_id: str, tool_names_this_turn: list[str]) -> None:
    """Increment turns_since_progress, or reset if a progress tool fired.

    Called once per agent turn after all tool dispatches for the turn are
    complete. The counter feeds check_no_progress(). Idempotent for empty
    lists (still increments — a turn with no tool calls is NOT progress).
    """
    tool_set = set(tool_names_this_turn)
    with _STATE_LOCK:
        st = _state(session_id)
        if tool_set & _PROGRESS_TOOL_NAMES:
            st.turns_since_progress = 0
            st.no_progress_reported = False
        else:
            st.turns_since_progress += 1


def check_no_progress(session_id: str) -> Optional[StuckSignal]:
    """Fire a soft signal when the agent has gone too many turns without a
    progress-tool call. Threshold reads from the ``progress_forcing_turns``
    setting; 0 disables the check entirely.
    """
    # Lazy import — storage isn't available at module-import time because
    # stuck.py is imported from runtime.py which imports storage itself.
    try:
        from vellum import storage as _storage
        threshold = int(_storage.get_setting("progress_forcing_turns", 5) or 0)
    except Exception:
        threshold = 5
    if threshold <= 0:
        return None
    signal: Optional[StuckSignal] = None
    with _STATE_LOCK:
        st = _state(session_id)
        if st.turns_since_progress < threshold or st.no_progress_reported:
            return None
        st.no_progress_reported = True
        count = st.turns_since_progress
        detail = (
            f"The last {count} turns have not produced a progress action "
            f"(decision point, sub-investigation, artifact, theory update, "
            f"needs_input, etc.). The investigation may be stuck refining "
            f"without advancing."
        )
        summary = (
            f"I've spent {count} turns editing sections / reading / logging "
            f"without actually moving the investigation forward. A turn "
            f"should reduce uncertainty, eliminate an option, request "
            f"missing input, or update the working theory — I haven't done "
            f"any of those in a while. Worth pausing to choose a direction."
        )
        options = [
            {
                "label": "Update the working theory with what you know",
                "implications": (
                    "Force a `update_working_theory` call that names the "
                    "current belief and what would change it. This is the "
                    "lowest-cost way to turn a stall into a concrete move."
                ),
                "recommended": True,
            },
            {
                "label": "Spawn a focused sub-investigation",
                "implications": (
                    "Pick the single most load-bearing open question and "
                    "spawn a scoped sub with it as its goal."
                ),
                "recommended": False,
            },
            {
                "label": "Pause and ask the user for direction",
                "implications": (
                    "Surface a flag_decision_point with 2–3 concrete paths "
                    "forward and let the user pick."
                ),
                "recommended": False,
            },
        ]
        signal = StuckSignal(
            kind="no_progress",
            detail=detail,
            summary_of_attempts=summary,
            options_for_user=options,
        )
    if signal is not None:
        return _assign_tier_and_emit(session_id, signal)
    return signal


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

    # 5. Revision stall: (_REVISION_STALL_THRESHOLD + 1) upserts on same
    # section -> fires. Use distinct args to avoid also tripping the
    # exact-args loop signal.
    reset_session(sid)
    for i in range(_REVISION_STALL_THRESHOLD + 1):
        record_tool_call(sid, "upsert_section", {"section_id": "sec_open", "i": i})
    sig = check_revision_stall(did, sid)
    assert sig is not None and sig.kind == "revision_stall", "revision_stall should fire"

    # 6. After mark_needs_input_resolved, the stall counter resets — more
    # upserts within the reset window (up to threshold) should NOT fire again.
    mark_needs_input_resolved(sid)
    for i in range(_REVISION_STALL_THRESHOLD):  # at threshold, not past it
        record_tool_call(sid, "upsert_section", {"section_id": "sec_open", "j": i})
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

    # Tier escalation: first signal -> tier=1, second -> 2, third -> 3.
    reset_session(sid)
    # Tier 1: trip any signal. Use the exact-args loop path (easy to fire).
    sig1 = None
    for _ in range(config.LOOP_DETECTION_THRESHOLD):
        sig1 = record_tool_call(sid, "web_search", {"q": "tier1"})
        if sig1 is not None:
            break
    assert sig1 is not None and sig1.tier == 1, f"expected tier 1, got {getattr(sig1, 'tier', None)}"

    # Tier 2: trip another distinct signal.
    sig2 = None
    for _ in range(config.LOOP_DETECTION_THRESHOLD):
        sig2 = record_tool_call(sid, "get_url", {"url": "https://x"})
        if sig2 is not None:
            break
    assert sig2 is not None and sig2.tier == 2

    # Tier 3+: trip a third signal; confirm recommended=True on first option.
    record_input_tokens(sid, "sec_t3", config.SECTION_TOKEN_BUDGET + 1)
    sig3 = check_section_budget(did, sid)
    assert sig3 is not None and sig3.tier == 3
    assert sig3.options_for_user[0]["recommended"] is True
    assert all(o["recommended"] is False for o in sig3.options_for_user[1:])
    print("tier escalation 1 -> 2 -> 3 OK")


if __name__ == "__main__":
    _run_self_test()
