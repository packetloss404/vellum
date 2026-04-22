"""Day 3: plan-approval gate tests.

Covers:
- `storage.approve_investigation_plan` — idempotent, no-op on null plan.
- `resolve_decision_point` auto-approves plan when kind=plan_approval + an
  approving chosen string.
- Redirect / non-approve chosen strings do NOT approve.
- kind=generic never auto-approves (backward compat).
- `build_state_snapshot` surfaces the three plan states: missing / drafted /
  approved.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Point VELLUM_DB_PATH at a throwaway file and reinit schema."""
    tmp = Path(tempfile.mkdtemp()) / "vellum_test.db"
    monkeypatch.setenv("VELLUM_DB_PATH", str(tmp))

    import importlib
    from vellum import config, db, storage
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(storage)

    db.init_db()
    yield storage, db
    try:
        tmp.unlink()
    except OSError:
        pass


def _make_dossier(storage):
    from vellum import models as m
    return storage.create_dossier(
        m.DossierCreate(
            title="Plan approval test",
            problem_statement="Test plan gate",
            dossier_type=m.DossierType.investigation,
        )
    )


def _draft_plan(storage, dossier_id: str, session_id: str | None = None):
    from vellum import models as m
    return storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(
            items=[
                m.InvestigationPlanItem(question="Q1", rationale="why1"),
                m.InvestigationPlanItem(question="Q2", rationale="why2"),
            ],
            rationale="starter plan",
            approve=False,
        ),
        session_id,
    )


# ---------- approve_investigation_plan ----------


def test_approve_investigation_plan_sets_approved_at_once(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)

    pre = storage.get_dossier(dossier.id)
    assert pre.investigation_plan is not None
    assert pre.investigation_plan.approved_at is None

    updated = storage.approve_investigation_plan(dossier.id, session.id)
    assert updated is not None
    assert updated.investigation_plan is not None
    first_approved = updated.investigation_plan.approved_at
    assert first_approved is not None


def test_approve_investigation_plan_is_idempotent(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)

    first = storage.approve_investigation_plan(dossier.id, session.id)
    first_ts = first.investigation_plan.approved_at
    second = storage.approve_investigation_plan(dossier.id, session.id)
    # approved_at unchanged by second call.
    assert second.investigation_plan.approved_at == first_ts


def test_approve_investigation_plan_noop_on_null_plan(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)

    result = storage.approve_investigation_plan(dossier.id, session.id)
    assert result is not None
    assert result.investigation_plan is None


# ---------- resolve_decision_point auto-approve ----------


def _plan_approval_dp(storage, dossier_id: str, session_id: str):
    from vellum import models as m
    return storage.add_decision_point(
        dossier_id,
        m.DecisionPointCreate(
            title="Approve starter plan?",
            options=[
                m.DecisionOption(label="Approve"),
                m.DecisionOption(label="Redirect"),
            ],
            kind="plan_approval",
        ),
        session_id,
    )


def test_resolve_plan_approval_with_approve_auto_approves(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)
    dp = _plan_approval_dp(storage, dossier.id, session.id)

    resolved = storage.resolve_decision_point(
        dossier.id, dp.id, "Approve", session.id
    )
    assert resolved is not None
    assert resolved.resolved_at is not None

    refreshed = storage.get_dossier(dossier.id)
    assert refreshed.investigation_plan.approved_at is not None


def test_resolve_plan_approval_with_redirect_does_not_approve(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)
    dp = _plan_approval_dp(storage, dossier.id, session.id)

    storage.resolve_decision_point(dossier.id, dp.id, "Redirect", session.id)
    refreshed = storage.get_dossier(dossier.id)
    assert refreshed.investigation_plan.approved_at is None


def test_generic_kind_never_auto_approves(fresh_db):
    storage, _ = fresh_db
    from vellum import models as m
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)

    # A generic decision point — even when chosen is "Approve" — must not touch
    # the plan's approved_at (backward compat for legacy/unrelated DPs).
    dp = storage.add_decision_point(
        dossier.id,
        m.DecisionPointCreate(
            title="Some unrelated choice",
            options=[m.DecisionOption(label="Approve"), m.DecisionOption(label="Skip")],
            # kind defaults to "generic"
        ),
        session.id,
    )
    assert dp.kind == "generic"

    storage.resolve_decision_point(dossier.id, dp.id, "Approve", session.id)
    refreshed = storage.get_dossier(dossier.id)
    assert refreshed.investigation_plan.approved_at is None


def test_resolve_plan_approval_case_insensitive_yes(fresh_db):
    storage, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)
    dp = _plan_approval_dp(storage, dossier.id, session.id)

    storage.resolve_decision_point(dossier.id, dp.id, "yes", session.id)
    refreshed = storage.get_dossier(dossier.id)
    assert refreshed.investigation_plan.approved_at is not None


# ---------- build_state_snapshot plan-status surfacing ----------


def test_state_snapshot_no_plan(fresh_db):
    storage, _ = fresh_db
    from vellum.agent.prompt import build_state_snapshot
    dossier = _make_dossier(storage)

    full = storage.get_dossier_full(dossier.id)
    snap = build_state_snapshot(full)
    assert "No plan yet" in snap
    assert "draft one" in snap.lower()


def test_state_snapshot_drafted_not_approved(fresh_db):
    storage, _ = fresh_db
    from vellum.agent.prompt import build_state_snapshot
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)

    full = storage.get_dossier_full(dossier.id)
    snap = build_state_snapshot(full)
    assert "PLAN DRAFTED" in snap
    assert "awaiting user approval" in snap
    assert "flag_decision_point" in snap
    assert "kind=plan_approval" in snap


def test_state_snapshot_approved(fresh_db):
    storage, _ = fresh_db
    from vellum.agent.prompt import build_state_snapshot
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id)
    storage.approve_investigation_plan(dossier.id, session.id)

    full = storage.get_dossier_full(dossier.id)
    snap = build_state_snapshot(full)
    assert "PLAN APPROVED" in snap
    assert "Proceed with substantive work" in snap
