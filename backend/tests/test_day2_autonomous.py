"""Day-2 autonomous-agent smoke test.

Two tests live here:

1. ``test_autonomous_run`` - the gated LIVE test. Requires an explicit
   ANTHROPIC_API_KEY *and* ``VELLUM_RUN_AUTONOMOUS_TESTS=1`` in the env.
   If either is missing it SKIPS. This is a pure smoke check that the
   agent loop works end-to-end on the credit-card-debt demo problem and
   doesn't spiral. Thresholds are deliberately soft so a bad day on the
   upstream API doesn't fail a deliverable check the agent itself didn't
   cause - the substance-bar is enforced by ``scripts/day2_smoke.py``,
   not this test.

2. ``test_digest_shape`` / ``test_parse_args`` - structural tests for the
   runnable script's pure helpers. These are NOT gated on any env var and
   run on every test-collection so the script's public surface cannot
   silently regress.

Run the structural tests::

    cd backend && ./.venv/Scripts/python.exe -m pytest \\
        tests/test_day2_autonomous.py -v

The gated test should SKIP in that run.

To actually run the live test (makes real API calls; not for CI)::

    VELLUM_RUN_AUTONOMOUS_TESTS=1 ANTHROPIC_API_KEY=replace-me \\
        ./.venv/Scripts/python.exe -m pytest tests/test_day2_autonomous.py -v
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest


# ---------- script loader ----------


def _load_day2_script():
    """Import scripts/day2_smoke.py by path, for the structural tests.

    The script lives outside any package, so we do a direct spec-based
    import. The script itself inserts ``backend/`` onto sys.path for its
    own runtime imports, which is fine to trigger here: it's a no-op if
    the module-level imports (``vellum.storage`` etc.) are already
    importable, and safe otherwise.
    """
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "day2_smoke.py"
    if not script_path.exists():
        pytest.fail(f"scripts/day2_smoke.py missing at {script_path}")
    spec = importlib.util.spec_from_file_location(
        "_day2_smoke_for_tests", str(script_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_day2_smoke_for_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------- structural tests (always run) ----------


def test_parse_args_defaults():
    day2 = _load_day2_script()

    ns = day2.parse_args([])
    assert ns.max_turns == 200
    assert ns.model is None
    assert ns.dossier_id is None
    # Default problem should mention the demo scenario so we don't
    # accidentally regress the default target.
    assert "credit card" in ns.problem.lower()


def test_parse_args_overrides():
    day2 = _load_day2_script()

    ns = day2.parse_args(
        [
            "--problem",
            "a different hard problem",
            "--max-turns",
            "50",
            "--model",
            "claude-sonnet-4-6",
            "--dossier-id",
            "dos_abc",
            "--title",
            "custom title",
        ]
    )
    assert ns.problem == "a different hard problem"
    assert ns.max_turns == 50
    assert ns.model == "claude-sonnet-4-6"
    assert ns.dossier_id == "dos_abc"
    assert ns.title == "custom title"


def test_digest_shape_all_pass():
    day2 = _load_day2_script()

    stats = day2.DigestStats(
        dossier_id="dos_xyz",
        title="Credit card debt demo",
        status="delivered",
        turns=47,
        duration_s=65.5,
        sub_investigations=4,
        sub_delivered=2,
        sources=25,
        artifacts=2,
        considered_rejected=3,
        sections=7,
        debrief_what_i_did="Investigated FDCPA + state law + creditor patterns.",
        debrief_what_i_found="No personal liability absent co-signer.",
        debrief_do_next="Draft verification letter.",
        debrief_left_open="Confirm state = Texas community-property rules.",
    )
    rendered = day2.format_digest(stats)

    # Structural: header + every required line is present.
    assert rendered.startswith("=== Vellum Day-2 Digest ===")
    assert "Dossier: dos_xyz" in rendered
    assert "Title: Credit card debt demo" in rendered
    assert "Status: delivered" in rendered
    assert "Turns: 47" in rendered
    assert "Duration: 01:05" in rendered
    assert "Sub-investigations: 4" in rendered
    assert "(of which delivered: 2)" in rendered
    assert "Sources consulted: 25" in rendered
    assert "Artifacts: 2" in rendered
    assert "Considered-and-rejected: 3" in rendered
    assert "Sections: 7" in rendered
    assert "What I did:    Investigated FDCPA + state law + creditor patterns." in rendered
    assert "What I found:  No personal liability absent co-signer." in rendered
    assert "Do next:       Draft verification letter." in rendered
    assert "Left open:     Confirm state = Texas community-property rules." in rendered
    assert "sub >= 3:      PASS" in rendered
    assert "sources >= 20: PASS" in rendered
    assert "artifacts >= 1: PASS" in rendered


def test_digest_shape_all_fail():
    day2 = _load_day2_script()

    stats = day2.DigestStats(
        dossier_id="dos_thin",
        title="thin run",
        status="turn_limit",
        turns=12,
        duration_s=30.0,
        sub_investigations=1,
        sources=3,
        artifacts=0,
    )
    rendered = day2.format_digest(stats)
    assert "sub >= 3:      FAIL" in rendered
    assert "sources >= 20: FAIL" in rendered
    assert "artifacts >= 1: FAIL" in rendered
    # Empty debrief fields should still render their labels cleanly.
    assert "What I did:    " in rendered
    assert "What I found:  " in rendered
    assert "Do next:       " in rendered
    assert "Left open:     " in rendered


def test_parse_debrief_note_roundtrip():
    day2 = _load_day2_script()

    note = (
        "what i did: investigated FDCPA\n"
        "what i found: no liability without cosigner\n"
        "do next: draft verification letter\n"
        "left open: confirm state law"
    )
    parsed = day2._parse_debrief_note(note)
    assert parsed["what_i_did"] == "investigated FDCPA"
    assert parsed["what_i_found"] == "no liability without cosigner"
    assert parsed["do_next"] == "draft verification letter"
    assert parsed["left_open"] == "confirm state law"


# ---------- LIVE test, gated ----------


_GATED_REASON = (
    "requires live API key (ANTHROPIC_API_KEY) and explicit opt-in "
    "(VELLUM_RUN_AUTONOMOUS_TESTS=1). Not for CI."
)


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY")
    or not os.environ.get("VELLUM_RUN_AUTONOMOUS_TESTS"),
    reason=_GATED_REASON,
)
def test_autonomous_run():
    """Live run. SKIPPED unless both env vars are set.

    Runs the agent with a small max_turns cap (<= 50) to verify the plumbing
    only - not to exercise the full-hour substance bar. Real full-bar
    checks belong to ``scripts/day2_smoke.py``, which is what Day-2 is
    graded on.

    Asserts SOFT thresholds: the agent either produced a visible trail
    (>=1 sub-investigation and >=3 source-bearing events) OR ended cleanly
    as ``stuck``/``ended_turn``. Either path proves the loop plumbing
    works without hanging.
    """
    # Use a throwaway DB so a live run doesn't pollute the dev DB.
    tmp = Path(tempfile.gettempdir()) / f"vellum_day2_test_{int(time.time())}.db"
    os.environ["VELLUM_DB_PATH"] = str(tmp)

    # Defer vellum imports until after we've set the DB path - config.py
    # reads VELLUM_DB_PATH at import time.
    from vellum import db, models as m, storage
    from vellum.agent.orchestrator import ORCHESTRATOR

    db.init_db()

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="Day-2 autonomous smoke (test DB)",
            problem_statement=(
                "Credit card debt negotiation - renegotiating a deceased "
                "parent's credit card debts when there's no estate. Friend's "
                "mother passed with ~$40k across 3 accounts, no estate, no "
                "co-signer. What percentage should they open at?"
            ),
            dossier_type=m.DossierType.investigation,
        )
    )

    import asyncio

    async def _drive() -> dict:
        start_run = getattr(ORCHESTRATOR, "start_run", None)
        if callable(start_run):
            return await start_run(dossier.id, max_turns=50)  # type: ignore[misc]
        await ORCHESTRATOR.start(dossier.id, max_turns=50)
        task = ORCHESTRATOR._tasks.get(dossier.id)  # type: ignore[attr-defined]
        assert task is not None, "orchestrator start() did not register task"
        result = await task
        return {
            "reason": getattr(result, "reason", "unknown"),
            "turns": getattr(result, "turns", 0),
            "session_id": getattr(result, "session_id", ""),
            "error": getattr(result, "error", None),
        }

    run_result = asyncio.run(_drive())

    full = storage.get_dossier_full(dossier.id)
    assert full is not None, "dossier vanished mid-run"

    sub_types = {"finding", "evidence", "open_question", "decision_needed"}
    subs = [
        s for s in full.sections
        if (s.type.value if hasattr(s.type, "value") else str(s.type)) in sub_types
    ]
    total_sources = sum(len(s.sources or []) for s in full.sections)
    artifacts = [
        s for s in full.sections
        if (s.type.value if hasattr(s.type, "value") else str(s.type)) == "recommendation"
    ]

    digest_lines = [
        f"reason={run_result.get('reason')}",
        f"turns={run_result.get('turns')}",
        f"sections={len(full.sections)}",
        f"subs={len(subs)}",
        f"sources={total_sources}",
        f"artifacts={len(artifacts)}",
        f"ruled_out={len(full.ruled_out)}",
        f"reasoning={len(full.reasoning_trail)}",
        f"needs_input={len(full.needs_input)}",
    ]
    print("\n[day2-test DIGEST]", "  ".join(digest_lines))

    # SOFT asserts - the agent can rationally deliver, get stuck, or hit
    # the 50-turn cap. We fail only on clear plumbing breaks.
    assert run_result.get("reason") in {
        "ended_turn", "turn_limit", "stuck", "error"
    }, f"unexpected reason: {run_result}"

    # If the agent errored before doing any work, something structural
    # broke (import? model name? schema?) - fail loudly.
    if run_result.get("reason") == "error" and len(full.sections) == 0:
        pytest.fail(
            f"agent errored with zero sections drafted: {run_result.get('error')}"
        )

    # At least one sub-investigation OR a clean early end.
    if run_result.get("reason") == "ended_turn" and len(full.sections) == 0:
        # Model chose to end the turn without any tool calls. That's a
        # real-API hiccup we accept - don't fail on it, but flag it.
        print("[day2-test] agent ended turn with no tool calls (API hiccup?)")
    else:
        assert len(subs) >= 1, (
            f"expected >=1 sub-investigation; got {len(subs)}. digest={digest_lines}"
        )

    # >=3 source-bearing events OR the agent got stuck / delivered cleanly.
    if run_result.get("reason") not in {"stuck", "ended_turn"}:
        assert total_sources + len(full.reasoning_trail) >= 3, (
            f"expected >=3 investigation-log entries; got "
            f"sources={total_sources} reasoning={len(full.reasoning_trail)}"
        )

    # >=1 artifact OR explicit "no artifacts drafted yet" note.
    if len(artifacts) == 0:
        # Accept either reasoning_trail mention or decision_point mention.
        deferred_artifact_markers = [
            "no artifact" in (e.note or "").lower()
            or "deferred" in (e.note or "").lower()
            for e in full.reasoning_trail
        ]
        if not any(deferred_artifact_markers):
            print(
                "[day2-test] WARNING: no artifact drafted and no explicit "
                "deferral note. (Soft-pass at 50 turns; hard-check lives in "
                "scripts/day2_smoke.py at 200 turns.)"
            )

    # Debrief is currently derived (not yet written by the agent). Assert
    # the derived four-tuple is non-empty.
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "scripts"))
    try:
        day2 = _load_day2_script()
        stats = day2.read_stats_from_storage(dossier.id)
    finally:
        # no-op path cleanup; test-isolation handled by pytest
        pass
    assert stats.debrief_what_i_did, "derived debrief 'what I did' was empty"
    assert stats.debrief_what_i_found, "derived debrief 'what I found' was empty"
    assert stats.debrief_do_next, "derived debrief 'do next' was empty"
    assert stats.debrief_left_open, "derived debrief 'left open' was empty"
