"""Vellum Day-2 autonomous smoke test / deliverable script.

What this does
--------------
Drives a single real agent run against the Anthropic API on a hard problem
(default: the demo credit-card-debt negotiation problem), prints a live
progress line every 30s, and on exit emits a DIGEST summarizing the
substance bar the agent cleared (sub-investigations, sources consulted,
artifacts drafted, considered-and-rejected).

This is the Day-2 deliverable check: we want to show the agent can work
autonomously for ~1 hour on a hard problem, spawn 2-3+ sub-investigations,
consult 20+ sources, produce multiple artifacts, without spiraling.

Cost warning
------------
THIS MAKES REAL CLAUDE API CALLS AGAINST A LIVE KEY. Budget expectation:

  Conservative estimate: $8-$20 per full run (max_turns=200, opus-4.7)
  Shorter smoke run (max_turns=50): $2-$6

Assumption: ~200 turns * ~30k input tokens (cached) + ~3k output tokens at
claude-opus-4-7 list prices, with Anthropic's web_search billed separately
per query. Actual cost depends heavily on how much the agent spends in
tool loops and cache-hit rate. Watch your Anthropic dashboard; abort with
Ctrl-C if the estimate slips. Partial state is saved - the dossier and
any work the agent did up to the cancellation are preserved on disk.

Prerequisites
-------------
- ``ANTHROPIC_API_KEY`` set in the environment (or in ``backend/.env``).
- Backend venv with ``anthropic`` + ``pydantic`` + ``python-dotenv`` etc.
- A writable SQLite DB (defaults to ``backend/vellum.db``; override with
  ``VELLUM_DB_PATH``).

How to run
----------
From the repo root, with the backend venv active::

    ./backend/.venv/Scripts/python.exe scripts/day2_smoke.py
    ./backend/.venv/Scripts/python.exe scripts/day2_smoke.py --max-turns 50
    ./backend/.venv/Scripts/python.exe scripts/day2_smoke.py \
        --problem "Your own hard problem here" --max-turns 100
    ./backend/.venv/Scripts/python.exe scripts/day2_smoke.py \
        --dossier-id dos_abc123  # resume an existing dossier
    ./backend/.venv/Scripts/python.exe scripts/day2_smoke.py --auto-resolve

--auto-resolve
--------------
The agent typically stalls after drafting a plan and flagging needs_input
(the plan-approval decision point is a hard gate; missing facts block
sub-investigations). ``--auto-resolve`` simulates a user for the canned
credit-card-debt demo problem:

  - auto-approves any unresolved plan_approval decision points ("Approve",
    which flips ``plan.approved_at`` via the storage auto-approve hook);
  - answers any unresolved needs_input questions whose text matches a set
    of keyword heuristics, using canned facts tuned to the demo problem
    (state of decedent, estate status, account relationship, prior
    creditor contact, amounts/creditors, who is asking).

After each resolve round the orchestrator is kicked again. The loop caps
at 3 iterations; if the agent keeps surfacing unresolved questions the
harness can't answer, the loop exits and the digest reports whatever
state was reached.

WARNING: the canned matchers are tuned for the credit-card-debt demo
problem. On other problems, keyword matches will typically not fire and
the loop will stall after the first agent turn. Use ``--auto-resolve``
only against the demo problem (or problems you've extended the matcher
for).

Digest semantics
----------------
The final digest reports three substance-bar checks:
  - sub >= 3:      at least three sub-investigations (sections) created
  - sources >= 20: at least twenty source citations across all sections
  - artifacts >= 1: at least one recommendation-type section drafted

Exit code is 0 iff all three substance-bar checks pass; 1 otherwise.

DO NOT run this in CI. It is a manual deliverable-verification tool.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Make ``vellum`` importable whether we run from repo root or elsewhere.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


DEFAULT_PROBLEM = (
    "Credit card debt negotiation - renegotiating a deceased parent's "
    "credit card debts when there's no estate. My friend's mother passed "
    "away with ~$40k credit card debt across 3 accounts. No estate, no "
    "probate, no co-signer. Friend wants to know what percentage to open "
    "negotiations at. Push back on the premise if warranted."
)


# ---------- stats snapshot ----------


@dataclass
class DigestStats:
    """Everything the digest needs in one bag. Pure data - no I/O."""

    dossier_id: str = ""
    title: str = ""
    status: str = "running"  # delivered | stuck | turn_limit | error | running | cancelled
    turns: int = 0
    duration_s: float = 0.0
    sub_investigations: int = 0
    sub_delivered: int = 0
    sources: int = 0
    artifacts: int = 0
    considered_rejected: int = 0
    sections: int = 0
    debrief_what_i_did: str = ""
    debrief_what_i_found: str = ""
    debrief_do_next: str = ""
    debrief_left_open: str = ""
    recent_log: list[str] = field(default_factory=list)

    # Substance bar
    @property
    def sub_pass(self) -> bool:
        return self.sub_investigations >= 3

    @property
    def sources_pass(self) -> bool:
        return self.sources >= 20

    @property
    def artifacts_pass(self) -> bool:
        return self.artifacts >= 1

    @property
    def all_pass(self) -> bool:
        return self.sub_pass and self.sources_pass and self.artifacts_pass


# ---------- stats readers ----------


def read_stats_from_storage(dossier_id: str) -> DigestStats:
    """Compute a fresh DigestStats by reading the dossier + children.

    v2 primitives (all first-class in storage):
      - sub_investigations: storage.list_sub_investigations
      - source_consulted:   investigation_log entries with entry_type=source_consulted
      - artifacts:          storage.list_artifacts
      - considered_and_rejected: storage.list_considered_and_rejected
      - debrief:            dossier.debrief (Debrief model)
      - investigation_plan: dossier.investigation_plan (InvestigationPlan model)
    """
    from vellum import storage
    from vellum import models as m

    stats = DigestStats(dossier_id=dossier_id)
    dossier = storage.get_dossier(dossier_id)
    if dossier is None:
        stats.status = "error"
        return stats
    stats.title = dossier.title

    full = storage.get_dossier_full(dossier_id)
    if full is None:
        return stats

    stats.sections = len(full.sections)
    stats.artifacts = len(full.artifacts)
    stats.sub_investigations = len(full.sub_investigations)
    stats.sub_delivered = sum(
        1 for s in full.sub_investigations
        if (s.state.value if hasattr(s.state, "value") else str(s.state)) == "delivered"
    )
    stats.considered_rejected = len(full.considered_and_rejected)

    # source_consulted count from investigation_log
    try:
        counts = storage.count_investigation_log_by_type(dossier_id)
        stats.sources = counts.get("source_consulted", 0)
    except Exception:
        stats.sources = 0

    # Debrief: direct from dossier.debrief; fall back to derivation if null.
    if dossier.debrief is not None:
        stats.debrief_what_i_did = dossier.debrief.what_i_did or ""
        stats.debrief_what_i_found = dossier.debrief.what_i_found or ""
        stats.debrief_do_next = dossier.debrief.what_you_should_do_next or ""
        stats.debrief_left_open = dossier.debrief.what_i_couldnt_figure_out or ""
    else:
        stats.debrief_what_i_did, stats.debrief_what_i_found, \
            stats.debrief_do_next, stats.debrief_left_open = \
            _derive_debrief(full)

    # Most recent investigation-log entries (newest 3, summary line).
    try:
        recent = storage.list_investigation_log(dossier_id, limit=3)
        stats.recent_log = [f"{e.entry_type.value}: {e.summary}" for e in recent]
    except Exception:
        stats.recent_log = []

    return stats


def _parse_debrief_note(note: str) -> dict[str, str]:
    """Parse a debrief note with 'key: value' lines or similar free-form text."""
    out: dict[str, str] = {}
    mapping = {
        "what i did": "what_i_did",
        "what_i_did": "what_i_did",
        "what i found": "what_i_found",
        "what_i_found": "what_i_found",
        "do next": "do_next",
        "do_next": "do_next",
        "left open": "left_open",
        "left_open": "left_open",
    }
    for raw_line in note.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        key = k.strip().lower().lstrip("-* ").rstrip()
        v = v.strip()
        if key in mapping and v:
            out[mapping[key]] = v
    return out


def _derive_debrief(full: Any) -> tuple[str, str, str, str]:
    """Best-effort four-tuple when no explicit debrief entry was written."""
    # What I did: count of changes.
    did = f"{len(full.sections)} sections, {len(full.reasoning_trail)} reasoning notes"
    # What I found: pick the first confident finding, else first section.
    found = ""
    for s in full.sections:
        t = s.type.value if hasattr(s.type, "value") else str(s.type)
        state = s.state.value if hasattr(s.state, "value") else str(s.state)
        if t in ("finding", "summary") and state == "confident":
            found = s.title
            break
    if not found and full.sections:
        found = full.sections[0].title
    # Do next: first open needs_input or provisional section.
    do_next = ""
    for ni in full.needs_input:
        if ni.answered_at is None:
            do_next = f"answer: {ni.question}"
            break
    if not do_next:
        for s in full.sections:
            state = s.state.value if hasattr(s.state, "value") else str(s.state)
            if state in ("provisional", "blocked"):
                do_next = f"firm up: {s.title}"
                break
    if not do_next:
        do_next = "no explicit next-step recorded"
    # Left open: provisional/blocked sections count.
    n_open = 0
    for s in full.sections:
        state = s.state.value if hasattr(s.state, "value") else str(s.state)
        if state in ("provisional", "blocked"):
            n_open += 1
    left_open = f"{n_open} provisional/blocked sections, {len([ni for ni in full.needs_input if ni.answered_at is None])} open questions"
    return did, found, do_next, left_open


# ---------- digest formatter ----------


def format_digest(stats: DigestStats) -> str:
    """Render the DigestStats as the canonical text block.

    Pure function on the stats dict - no I/O. Exercised by a structural
    test so the shape can't silently regress.
    """
    def tick(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    duration_min = int(stats.duration_s // 60)
    duration_sec = int(stats.duration_s % 60)
    lines = [
        "=== Vellum Day-2 Digest ===",
        f"Dossier: {stats.dossier_id}  Title: {stats.title}",
        f"Status: {stats.status}",
        f"Turns: {stats.turns}  Duration: {duration_min:02d}:{duration_sec:02d}",
        f"Sub-investigations: {stats.sub_investigations}   "
        f"(of which delivered: {stats.sub_delivered})",
        f"Sources consulted: {stats.sources}",
        f"Artifacts: {stats.artifacts}",
        f"Considered-and-rejected: {stats.considered_rejected}",
        f"Sections: {stats.sections}",
        "Debrief:",
        f"  What I did:    {stats.debrief_what_i_did}",
        f"  What I found:  {stats.debrief_what_i_found}",
        f"  Do next:       {stats.debrief_do_next}",
        f"  Left open:     {stats.debrief_left_open}",
        "Substance bar:",
        f"  sub >= 3:      {tick(stats.sub_pass)}",
        f"  sources >= 20: {tick(stats.sources_pass)}",
        f"  artifacts >= 1: {tick(stats.artifacts_pass)}",
    ]
    return "\n".join(lines)


# ---------- argparse ----------


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="day2_smoke",
        description="Day-2 autonomous smoke test for the Vellum agent.",
    )
    ap.add_argument(
        "--problem",
        default=DEFAULT_PROBLEM,
        help="The problem statement. Defaults to the credit-card-debt demo.",
    )
    ap.add_argument(
        "--max-turns",
        type=int,
        default=200,
        help="Cap on agent turns. Default 200 (about 1 hour of work).",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="Anthropic model name. Default from VELLUM_MODEL / config.py.",
    )
    ap.add_argument(
        "--dossier-id",
        default=None,
        help="Resume an existing dossier instead of creating a new one.",
    )
    ap.add_argument(
        "--title",
        default="Credit card debt negotiation - deceased parent, no estate",
        help="Title for a newly-created dossier.",
    )
    ap.add_argument(
        "--auto-resolve",
        action="store_true",
        default=False,
        help=(
            "After each agent turn ends waiting on the user, auto-approve "
            "plan-approval decision points and answer needs_input with a "
            "canned set of facts tuned to the credit-card-debt demo problem, "
            "then kick the agent again. Caps at 3 rounds. On non-demo "
            "problems the canned matchers will likely not fire and the "
            "loop will stall after the first agent turn."
        ),
    )
    return ap.parse_args(argv)


# ---------- dossier setup ----------


def create_or_resume_dossier(
    problem: str,
    dossier_id: Optional[str],
    title: str,
) -> tuple[str, str, bool]:
    """Return (dossier_id, title, created_new)."""
    from vellum import models as m, storage

    if dossier_id:
        d = storage.get_dossier(dossier_id)
        if d is None:
            raise SystemExit(f"dossier {dossier_id} not found")
        print(f"[day2-smoke] resuming dossier {d.id} - {d.title}")
        return d.id, d.title, False

    d = storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement=problem,
            out_of_scope=[],
            dossier_type=m.DossierType.investigation,
        )
    )
    print(f"[day2-smoke] created dossier {d.id} - {d.title}")
    return d.id, d.title, True


# ---------- progress ticker ----------


async def _progress_ticker(
    dossier_id: str,
    stop: asyncio.Event,
    interval_s: float = 30.0,
) -> None:
    """Every ``interval_s`` seconds, read stats and print a one-line update."""
    t0 = time.time()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
            return
        except asyncio.TimeoutError:
            pass

        stats = read_stats_from_storage(dossier_id)
        elapsed = int(time.time() - t0)
        line = (
            f"[day2-smoke {elapsed:>4}s] "
            f"subs={stats.sub_investigations} "
            f"sources={stats.sources} "
            f"artifacts={stats.artifacts} "
            f"ruled_out={stats.considered_rejected} "
            f"sections={stats.sections}"
        )
        print(line, flush=True)
        for entry in stats.recent_log:
            print(f"    - {entry[:120]}", flush=True)


# ---------- orchestrator integration ----------


async def _run_agent(
    dossier_id: str,
    max_turns: int,
    model: Optional[str],
) -> dict:
    """Kick off the agent and await its RunResult.

    The brief describes ``ORCHESTRATOR.start_run(dossier_id)`` as an
    awaitable that returns the run result. The actual orchestrator API
    today is ``start()`` (returns a descriptor) + an internal
    ``asyncio.Task`` we can observe. This wrapper prefers
    ``start_run`` if it ever exists, else uses the current ``start`` +
    task-await shape.
    """
    from vellum.agent.orchestrator import ORCHESTRATOR

    start_run = getattr(ORCHESTRATOR, "start_run", None)
    if callable(start_run):
        # Future shape: single-call kick-and-await.
        return await start_run(dossier_id, max_turns=max_turns, model=model)  # type: ignore[misc]

    # Current shape: start() launches a task; we then await that task.
    await ORCHESTRATOR.start(dossier_id, max_turns=max_turns, model=model)
    # Reach into the tracking map. This is an internal API, but we own
    # the instance and need the task handle for a clean await.
    task = ORCHESTRATOR._tasks.get(dossier_id)  # type: ignore[attr-defined]
    if task is None:
        return {"reason": "error", "error": "task missing after start()"}
    try:
        result = await task
    except asyncio.CancelledError:
        return {"reason": "cancelled"}
    # RunResult is a dataclass; convert to a plain dict for the caller.
    if hasattr(result, "__dict__"):
        return {
            "reason": getattr(result, "reason", "unknown"),
            "turns": getattr(result, "turns", 0),
            "session_id": getattr(result, "session_id", ""),
            "error": getattr(result, "error", None),
        }
    return {"reason": "unknown", "result": repr(result)}


# ---------- auto-resolve (simulated user) ----------


# Canned facts for the credit-card-debt demo problem. Each entry is a short
# natural-language answer that will be returned when a needs_input question's
# lowercased text contains one of the listed keywords. A single question may
# match multiple categories, in which case the fragments are concatenated.
_AUTO_ANSWER_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("state", "jurisdiction", "domicile"),
        (
            "Decedent was domiciled in Arizona. The heir (my friend) lives "
            "in California. Decedent was unmarried at time of death."
        ),
    ),
    (
        ("estate", "probate", "assets"),
        (
            "No probate has been opened. The decedent had no titled assets "
            "(no house, no car in her name). Cash balances in a single "
            "checking account (~$2,400) passed to my friend as joint owner "
            "outside probate."
        ),
    ),
    (
        (
            "cosigner", "co-signer", "joint", "authorized user",
            "account holder", "relationship",
        ),
        (
            "My friend is not a co-signer or authorized user on any of the "
            "three credit card accounts. The accounts were solely in the "
            "decedent's name."
        ),
    ),
    (
        ("contact", "collector", "called", "calls", "spoken", "talked", "engagement"),
        (
            "Two calls from a Capital One collections rep, to my friend "
            "personally. No payments made. Nothing in writing. No verbal "
            "acknowledgment of the debt."
        ),
    ),
    (
        (
            "amount", "balance", "creditor", "which", "three accounts",
            "chase", "capital one", "discover",
        ),
        (
            "Chase ~$8k, Capital One ~$7k, Discover ~$3k. All accounts were "
            "active in the month before death. No payments since the last "
            "statement prior to death (~2 months ago)."
        ),
    ),
    (
        ("who", "yourself", "your friend", "asking"),
        (
            "I'm asking on behalf of my friend. My friend wants to understand "
            "their legal exposure first, and only then consider negotiation "
            "if there is any exposure at all."
        ),
    ),
]


def _pick_auto_answer(question_text: str) -> Optional[str]:
    """Return a canned answer for a needs_input question, or None.

    Substring match on the lowercased question text. If multiple categories
    match, the canned fragments are concatenated (whitespace-separated) so
    a compound question like "What state? Was probate opened?" picks up
    both the jurisdictional and estate fragments.
    """
    if not question_text:
        return None
    lc = question_text.lower()
    matched: list[str] = []
    for keywords, answer in _AUTO_ANSWER_RULES:
        for kw in keywords:
            if kw in lc:
                if answer not in matched:
                    matched.append(answer)
                break
    if not matched:
        return None
    return " ".join(matched)


_PLAN_APPROVAL_TITLE_PATTERNS = ("approve plan", "approve the plan", "plan approval")


def _title_matches_plan_approval(title: str) -> bool:
    """Fallback heuristic: if ``kind`` isn't set but the title looks like
    a plan-approval ask, treat it as one. Defensive - all new DPs should
    carry ``kind`` today, but storage/back-compat DPs might not.
    """
    if not title:
        return False
    lc = title.lower()
    return any(p in lc for p in _PLAN_APPROVAL_TITLE_PATTERNS)


def _auto_resolve_round(
    dossier_id: str,
    work_session_id: Optional[str] = None,
) -> tuple[int, int, int]:
    """Resolve all resolvable plan-approval DPs and needs_input in one pass.

    Returns ``(dps_resolved, ni_resolved, ni_skipped)``. A skipped ni is one
    we couldn't find a canned answer for - the caller should treat any
    ``ni_skipped > 0`` and ``dps_resolved == 0 and ni_resolved == 0`` as
    ``nothing could be resolved``.
    """
    from vellum import storage

    dps_resolved = 0
    ni_resolved = 0
    ni_skipped = 0

    for dp in storage.list_decision_points(dossier_id, open_only=True):
        if dp.kind == "plan_approval" or _title_matches_plan_approval(dp.title):
            storage.resolve_decision_point(
                dossier_id, dp.id, chosen="Approve",
                work_session_id=work_session_id,
            )
            dps_resolved += 1

    for ni in storage.list_needs_input(dossier_id, open_only=True):
        answer = _pick_auto_answer(ni.question)
        if answer is None:
            ni_skipped += 1
            continue
        storage.resolve_needs_input(
            dossier_id, ni.id, answer=answer,
            work_session_id=work_session_id,
        )
        ni_resolved += 1

    return dps_resolved, ni_resolved, ni_skipped


async def _auto_resolve_loop(
    dossier_id: str,
    max_turns: int,
    model: Optional[str],
    max_rounds: int = 3,
) -> dict:
    """Drive plan-approve + needs_input-answer rounds, kicking the agent
    between each. Returns the final run_result dict.

    Terminates when:
      - the agent ends with a reason other than ``ended_turn`` (stuck,
        delivered, turn_limit, error), OR
      - a resolve round finds nothing to resolve, OR
      - ``max_rounds`` iterations have elapsed.
    """
    rounds = 0
    last_result: dict = {"reason": "error", "turns": 0, "session_id": ""}
    while rounds < max_rounds:
        rounds += 1
        dps, nis, skipped = _auto_resolve_round(dossier_id)
        print(
            f"[day2-smoke] auto-resolve round {rounds}: "
            f"plan_dps={dps} needs_input_answered={nis} "
            f"needs_input_skipped={skipped}",
            flush=True,
        )
        if dps == 0 and nis == 0:
            # Nothing we could simulate. Give up and let the digest
            # report whatever state the dossier is in.
            print(
                "[day2-smoke] auto-resolve: nothing to resolve - stopping.",
                flush=True,
            )
            break
        # Kick the agent again.
        last_result = await _run_agent(dossier_id, max_turns, model)
        if last_result.get("reason") != "ended_turn":
            print(
                f"[day2-smoke] auto-resolve: agent finished with reason="
                f"{last_result.get('reason')} - stopping.",
                flush=True,
            )
            return last_result
    if rounds >= max_rounds:
        print(
            f"[day2-smoke] auto-resolve: hit max_rounds={max_rounds} cap.",
            flush=True,
        )
    return last_result


# ---------- main ----------


async def _amain(args: argparse.Namespace) -> int:
    from vellum import db

    db.init_db()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[day2-smoke] ERROR: ANTHROPIC_API_KEY not set. This script makes "
            "real API calls and cannot run without a key.",
            file=sys.stderr,
        )
        return 2

    dossier_id, title, _created = create_or_resume_dossier(
        problem=args.problem,
        dossier_id=args.dossier_id,
        title=args.title,
    )

    print(
        f"[day2-smoke] starting agent: max_turns={args.max_turns} "
        f"model={args.model or os.environ.get('VELLUM_MODEL', 'default')}",
        flush=True,
    )

    stop_event = asyncio.Event()
    t0 = time.time()

    ticker = asyncio.create_task(_progress_ticker(dossier_id, stop_event))
    run_task = asyncio.create_task(
        _run_agent(dossier_id, args.max_turns, args.model)
    )

    # Ctrl-C handling: request cancellation of the run_task; the agent
    # runtime closes its work_session in a ``finally`` block, so partial
    # state is preserved.
    loop = asyncio.get_running_loop()
    cancelled_by_user = {"flag": False}

    def _sigint(*_: Any) -> None:
        if cancelled_by_user["flag"]:
            return
        cancelled_by_user["flag"] = True
        print(
            "\n[day2-smoke] Ctrl-C received - cancelling agent; partial "
            "dossier state will be preserved.",
            flush=True,
        )
        run_task.cancel()

    prev_handler: Any = signal.SIG_DFL
    try:
        prev_handler = signal.getsignal(signal.SIGINT)
        # loop.add_signal_handler isn't available on Windows.
        if sys.platform == "win32":
            signal.signal(signal.SIGINT, _sigint)
        else:
            loop.add_signal_handler(signal.SIGINT, _sigint)
    except (NotImplementedError, RuntimeError):
        signal.signal(signal.SIGINT, _sigint)

    run_result: dict = {"reason": "error"}
    try:
        try:
            run_result = await run_task
        except asyncio.CancelledError:
            run_result = {"reason": "cancelled"}

        # --auto-resolve: if the agent ended a turn still waiting on the
        # user, simulate a user for the canned demo problem and kick the
        # agent again, up to 3 rounds. Only runs if the initial run didn't
        # already finish with a terminal reason and wasn't user-cancelled.
        if (
            getattr(args, "auto_resolve", False)
            and not cancelled_by_user["flag"]
            and run_result.get("reason") == "ended_turn"
        ):
            try:
                resolved = await _auto_resolve_loop(
                    dossier_id, args.max_turns, args.model, max_rounds=3,
                )
            except asyncio.CancelledError:
                resolved = {"reason": "cancelled"}
            # Keep the resolved result if auto-resolve did any work;
            # otherwise fall back to the original run_result.
            if resolved and resolved.get("reason"):
                run_result = resolved
    finally:
        stop_event.set()
        try:
            await ticker
        except Exception:
            pass
        try:
            if sys.platform == "win32":
                signal.signal(signal.SIGINT, prev_handler)
        except Exception:
            pass

    duration_s = time.time() - t0

    # Read final stats and overwrite with the real turn count + status.
    stats = read_stats_from_storage(dossier_id)
    stats.dossier_id = dossier_id
    stats.title = title
    stats.turns = int(run_result.get("turns", 0) or 0)
    stats.duration_s = duration_s
    reason = run_result.get("reason", "error")
    if cancelled_by_user["flag"] or reason == "cancelled":
        stats.status = "cancelled"
    elif reason == "ended_turn":
        # The brief uses "delivered" for a clean finish; map it here.
        stats.status = "delivered"
    else:
        stats.status = reason

    error_msg = run_result.get("error") if isinstance(run_result, dict) else None
    print()
    print(format_digest(stats), flush=True)
    if error_msg:
        print(f"\nError: {error_msg}", flush=True)
    return 0 if stats.all_pass else 1


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_amain(args))
    except KeyboardInterrupt:
        # Fallback if a KeyboardInterrupt escapes the asyncio handler.
        print("[day2-smoke] aborted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
