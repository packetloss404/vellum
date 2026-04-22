"""Tests for the ``--auto-resolve`` feature of ``scripts/day2_smoke.py``.

The auto-resolve flag simulates a user for the canned credit-card-debt
demo problem: approves plan_approval decision points and answers
needs_input with keyword-matched canned facts. These tests exercise the
pure-helpers (``_pick_auto_answer``) and the storage-integrated helper
(``_auto_resolve_round`` / ``_auto_resolve_loop``) without making any
live LLM calls - the orchestrator kickoff is monkeypatched to a no-op.

Run::

    cd backend && ./.venv/Scripts/python.exe -m pytest \\
        tests/test_day2_smoke_auto_resolve.py -v
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


# ---------- script loader ----------


def _load_day2_script():
    """Import scripts/day2_smoke.py by path (it's not in a package)."""
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "day2_smoke.py"
    if not script_path.exists():
        pytest.fail(f"scripts/day2_smoke.py missing at {script_path}")
    spec = importlib.util.spec_from_file_location(
        "_day2_smoke_for_auto_resolve_tests", str(script_path)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_day2_smoke_for_auto_resolve_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------- _pick_auto_answer rule-matching tests ----------


def test_pick_auto_answer_matches_state_question():
    day2 = _load_day2_script()
    ans = day2._pick_auto_answer("What state was the decedent domiciled in?")
    assert ans is not None
    assert "Arizona" in ans


def test_pick_auto_answer_matches_multi_keyword():
    day2 = _load_day2_script()
    ans = day2._pick_auto_answer("What state? Was probate opened?")
    assert ans is not None
    # Must include fragments from BOTH the jurisdictional rule and the
    # estate/probate rule.
    assert "Arizona" in ans
    assert "No probate" in ans


def test_pick_auto_answer_no_match_returns_none():
    day2 = _load_day2_script()
    assert day2._pick_auto_answer("What is the capital of France?") is None


def test_pick_auto_answer_empty_string_returns_none():
    day2 = _load_day2_script()
    assert day2._pick_auto_answer("") is None


def test_pick_auto_answer_case_insensitive():
    day2 = _load_day2_script()
    ans = day2._pick_auto_answer("STATE of domicile?")
    assert ans is not None
    assert "Arizona" in ans


def test_pick_auto_answer_cosigner_variant():
    day2 = _load_day2_script()
    ans = day2._pick_auto_answer("Is your friend a co-signer on any account?")
    assert ans is not None
    assert "co-signer" in ans.lower() or "cosigner" in ans.lower()


def test_title_matches_plan_approval():
    day2 = _load_day2_script()
    assert day2._title_matches_plan_approval("Approve plan before proceeding")
    assert day2._title_matches_plan_approval("Approve the plan")
    assert not day2._title_matches_plan_approval("Which creditor to call first?")


# ---------- auto-resolve loop tests (storage-integrated, no LLM) ----------


@pytest.fixture
def _day2(monkeypatch):
    """Load the script and stub out ORCHESTRATOR.start to a no-op so
    ``_auto_resolve_loop`` can kick the agent without triggering any live
    work."""
    day2 = _load_day2_script()

    async def _fake_run_agent(dossier_id, max_turns, model):
        # Pretend the agent ran and ended its turn waiting on the user -
        # the loop condition for continuing. Tests that want the loop
        # to actually advance will override this per-test.
        return {"reason": "ended_turn", "turns": 1, "session_id": "ws_fake"}

    monkeypatch.setattr(day2, "_run_agent", _fake_run_agent)
    return day2


def test_auto_resolve_loop_resolves_plan_approval(_day2, fresh_db):
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="plan-approval test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    # Draft a plan (unapproved).
    storage.update_investigation_plan(
        dossier.id,
        m.InvestigationPlanUpdate(
            items=[
                m.InvestigationPlanItem(question="Q1"),
                m.InvestigationPlanItem(question="Q2"),
            ],
            rationale="test plan",
            approve=False,
        ),
    )
    # Add a plan-approval DP.
    dp = storage.add_decision_point(
        dossier.id,
        m.DecisionPointCreate(
            title="Approve plan before starting sub-investigations",
            options=[
                m.DecisionOption(label="Approve", recommended=True),
                m.DecisionOption(label="Revise"),
            ],
            kind="plan_approval",
        ),
    )

    dps, nis, skipped = _day2._auto_resolve_round(dossier.id)
    assert dps == 1
    assert nis == 0
    assert skipped == 0

    # DP is resolved with "Approve".
    dp_after = [
        d for d in storage.list_decision_points(dossier.id) if d.id == dp.id
    ][0]
    assert dp_after.resolved_at is not None
    assert dp_after.chosen == "Approve"

    # And plan.approved_at is stamped via the auto-approve hook.
    d_after = storage.get_dossier(dossier.id)
    assert d_after is not None
    assert d_after.investigation_plan is not None
    assert d_after.investigation_plan.approved_at is not None


def test_auto_resolve_loop_resolves_needs_input(_day2, fresh_db):
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="needs-input test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    ni = storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What state is the decedent's domicile?"),
    )

    dps, nis, skipped = _day2._auto_resolve_round(dossier.id)
    assert dps == 0
    assert nis == 1
    assert skipped == 0

    ni_after = [
        n for n in storage.list_needs_input(dossier.id) if n.id == ni.id
    ][0]
    assert ni_after.answered_at is not None
    assert ni_after.answer is not None
    assert "Arizona" in ni_after.answer


def test_auto_resolve_round_skips_unanswerable_question(_day2, fresh_db):
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="skip test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What is the capital of France?"),
    )
    dps, nis, skipped = _day2._auto_resolve_round(dossier.id)
    assert dps == 0
    assert nis == 0
    assert skipped == 1


def test_auto_resolve_iteration_cap_of_3(_day2, fresh_db, monkeypatch):
    """If every round has something to resolve, cap at 3 iterations.

    Simulate an agent that, on every kick, ends its turn having added a
    fresh needs_input that we CAN answer. The loop should resolve, kick,
    resolve, kick, resolve, kick -> then hit the cap and stop.
    """
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="cap test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    # Seed one answerable ni so the first round does something.
    storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What state is the decedent domiciled in?"),
    )

    kick_count = {"n": 0}

    async def _fake_run_agent(dossier_id, max_turns, model):
        # Each fake "agent turn" adds another answerable question and
        # ends the turn waiting on the user.
        kick_count["n"] += 1
        storage.add_needs_input(
            dossier_id,
            m.NeedsInputCreate(
                question=f"Round {kick_count['n']}: what state again?"
            ),
        )
        return {"reason": "ended_turn", "turns": kick_count["n"], "session_id": "ws"}

    monkeypatch.setattr(_day2, "_run_agent", _fake_run_agent)

    asyncio.run(_day2._auto_resolve_loop(dossier.id, max_turns=10, model=None, max_rounds=3))

    # The loop kicks the agent once per round that had something to
    # resolve. With max_rounds=3 and every round producing a new
    # answerable question, we expect exactly 3 kicks.
    assert kick_count["n"] == 3

    # All needs_input on the dossier should be answered.
    remaining = storage.list_needs_input(dossier.id, open_only=True)
    # After the final round's resolve phase, every ni from rounds 1-3 is
    # resolved; the fake agent added one after each resolve (total 3 new
    # plus the seed = 4). But the LAST fake kick adds one AFTER the loop
    # exits the resolve step... let's just check the cap behavior: kicks
    # are capped at 3.
    assert len(remaining) <= 1  # at most the last-kick's unresolved ni


def test_auto_resolve_loop_stops_when_nothing_to_resolve(_day2, fresh_db):
    """If a round finds no plan_approval DPs and no matching needs_input,
    the loop exits immediately without calling the agent."""
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="nothing-to-do test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    # An unresolvable question (no keywords match).
    storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What is the capital of France?"),
    )

    kicked = {"n": 0}

    async def _fake_run_agent(dossier_id, max_turns, model):
        kicked["n"] += 1
        return {"reason": "ended_turn", "turns": 1, "session_id": "ws"}

    # Swap in the counter.
    import types
    _day2._run_agent = _fake_run_agent  # type: ignore[assignment]

    asyncio.run(_day2._auto_resolve_loop(dossier.id, max_turns=10, model=None, max_rounds=3))

    # No kicks - loop should have bailed on round 1 when the skip count
    # was non-zero and the resolve count was zero.
    assert kicked["n"] == 0


def test_auto_resolve_loop_stops_on_non_ended_turn_reason(_day2, fresh_db, monkeypatch):
    """If the agent comes back with reason != ended_turn (e.g. delivered,
    stuck, turn_limit, error), the loop stops even if there's still
    stuff to resolve in later rounds.
    """
    from vellum import models as m, storage

    dossier = storage.create_dossier(
        m.DossierCreate(
            title="delivered test",
            problem_statement="stub",
            dossier_type=m.DossierType.investigation,
        )
    )
    storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="What state was the decedent domiciled in?"),
    )

    kicks = {"n": 0}

    async def _fake_run_agent(dossier_id, max_turns, model):
        kicks["n"] += 1
        return {"reason": "delivered", "turns": 5, "session_id": "ws"}

    monkeypatch.setattr(_day2, "_run_agent", _fake_run_agent)

    result = asyncio.run(
        _day2._auto_resolve_loop(dossier.id, max_turns=10, model=None, max_rounds=3)
    )
    # Exactly one kick (first round resolved the ni and kicked; agent
    # came back delivered so we stop).
    assert kicks["n"] == 1
    assert result["reason"] == "delivered"
