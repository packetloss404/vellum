"""Tests for the day-3 computed dossier status endpoint.

The status is DERIVED - no new column on ``dossiers``. These tests pin the
precedence rules:

  delivered > running > waiting_plan_approval > waiting_input > stuck > idle

and exercise the 404 behavior for missing dossiers. The ``fresh_db`` fixture
(see ``conftest.py``) points VELLUM_DB_PATH at a throwaway SQLite file and
re-inits the schema before each test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_tool_hooks():
    """``vellum.agent.telemetry`` registers itself into
    ``handlers.TOOL_HOOKS`` at import time. This module imports
    ``vellum.main`` (transitively via ``_client()``) which pulls telemetry
    in. Snapshot + restore so we do not leak the hook into the shared
    process state used by ``test_runtime_hooks.py``'s sentinel test."""
    from vellum.tools import handlers

    saved_hooks = list(handlers.TOOL_HOOKS)
    try:
        yield
    finally:
        handlers.TOOL_HOOKS.clear()
        handlers.TOOL_HOOKS.extend(saved_hooks)


def _mk_dossier(title: str = "status test"):
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement="observe status",
            dossier_type=m.DossierType.investigation,
        )
    )


def _client():
    from vellum.main import create_app

    return TestClient(create_app())


# ---------- storage layer ----------


def test_get_dossier_status_not_found(fresh_db):
    from vellum import storage

    result = storage.get_dossier_status("dos_does_not_exist")
    assert result["status"] == "not_found"


def test_status_idle_for_new_dossier(fresh_db):
    from vellum import storage

    d = _mk_dossier()
    result = storage.get_dossier_status(d.id)
    assert result["status"] == "idle"
    assert result["dossier_id"] == d.id
    assert result["delivered"] is False
    assert result["unresolved_plan_approval_id"] is None
    assert result["open_needs_input_count"] == 0
    assert result["open_decision_point_count"] == 0
    assert result["last_stuck_at"] is None


def test_status_waiting_plan_approval(fresh_db):
    from vellum import models as m, storage

    d = _mk_dossier()
    # Draft (but do not approve) a plan.
    storage.update_investigation_plan(
        d.id,
        m.InvestigationPlanUpdate(
            items=[
                m.InvestigationPlanItem(question="q1"),
                m.InvestigationPlanItem(question="q2"),
            ],
            rationale="initial plan",
            approve=False,
        ),
    )
    # Create a plan-approval decision point (title-based fallback).
    dp = storage.add_decision_point(
        d.id,
        m.DecisionPointCreate(
            title="Plan approval: please approve the draft plan",
            options=[
                m.DecisionOption(label="approve"),
                m.DecisionOption(label="revise"),
            ],
        ),
    )

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "waiting_plan_approval"
    assert result["unresolved_plan_approval_id"] == dp.id


def test_status_waiting_input_needs_input(fresh_db):
    from vellum import models as m, storage

    d = _mk_dossier()
    storage.add_needs_input(
        d.id,
        m.NeedsInputCreate(question="what is the budget?"),
    )

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "waiting_input"
    assert result["open_needs_input_count"] == 1


def test_status_waiting_input_non_plan_decision(fresh_db):
    """An unresolved decision_point that is NOT a plan-approval gate counts
    as waiting_input, not waiting_plan_approval."""
    from vellum import models as m, storage

    d = _mk_dossier()
    storage.add_decision_point(
        d.id,
        m.DecisionPointCreate(
            title="Which vendor to choose",
            options=[
                m.DecisionOption(label="A"),
                m.DecisionOption(label="B"),
            ],
        ),
    )

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "waiting_input"
    assert result["open_decision_point_count"] == 1
    assert result["unresolved_plan_approval_id"] is None


def test_status_stuck_recent(fresh_db):
    from vellum import models as m, storage

    d = _mk_dossier()
    storage.append_investigation_log(
        d.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.stuck_declared,
            payload={"reason": "loop"},
            summary="agent stuck in loop",
        ),
    )

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "stuck"
    assert result["last_stuck_at"] is not None


def test_status_stuck_ignored_if_before_last_visit(fresh_db):
    """If the user has visited the dossier AFTER the stuck was declared, the
    stuck is considered seen/cleared and status falls through to idle."""
    from vellum import models as m, storage

    d = _mk_dossier()
    storage.append_investigation_log(
        d.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.stuck_declared,
            payload={},
            summary="stuck",
        ),
    )
    # User visits the dossier AFTER the stuck entry.
    storage.mark_dossier_visited(d.id)

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "idle"


def test_status_delivered(fresh_db):
    from vellum import models as m, storage

    d = _mk_dossier()
    storage.update_dossier(
        d.id,
        m.DossierUpdate(status=m.DossierStatus.delivered),
    )

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "delivered"
    assert result["delivered"] is True


def test_status_running_via_orchestrator(fresh_db, monkeypatch):
    from vellum import storage
    from vellum.agent import orchestrator as orch_mod

    d = _mk_dossier()

    def _fake_list_active(_self):
        return [
            {"dossier_id": d.id, "started_at": "2026-01-01T00:00:00+00:00", "status": "running"}
        ]

    monkeypatch.setattr(orch_mod.AgentOrchestrator, "list_active", _fake_list_active)

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "running"


def test_status_precedence_running_beats_waiting_input(fresh_db, monkeypatch):
    """Precedence: when the orchestrator reports running AND there are open
    needs_input, running must win."""
    from vellum import models as m, storage
    from vellum.agent import orchestrator as orch_mod

    d = _mk_dossier()
    storage.add_needs_input(
        d.id, m.NeedsInputCreate(question="blocks everything")
    )

    def _fake_list_active(_self):
        return [
            {"dossier_id": d.id, "started_at": "2026-01-01T00:00:00+00:00", "status": "running"}
        ]

    monkeypatch.setattr(orch_mod.AgentOrchestrator, "list_active", _fake_list_active)

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "running"


def test_status_precedence_delivered_beats_everything(fresh_db, monkeypatch):
    from vellum import models as m, storage
    from vellum.agent import orchestrator as orch_mod

    d = _mk_dossier()
    storage.add_needs_input(d.id, m.NeedsInputCreate(question="?"))
    storage.update_dossier(
        d.id, m.DossierUpdate(status=m.DossierStatus.delivered)
    )

    def _fake_list_active(_self):
        return [
            {"dossier_id": d.id, "started_at": "2026-01-01T00:00:00+00:00", "status": "running"}
        ]

    monkeypatch.setattr(orch_mod.AgentOrchestrator, "list_active", _fake_list_active)

    result = storage.get_dossier_status(d.id)
    assert result["status"] == "delivered"


# ---------- HTTP route ----------


def test_route_404_for_missing_dossier(fresh_db):
    client = _client()
    resp = client.get("/api/dossiers/dos_missing/status")
    assert resp.status_code == 404


def test_route_returns_status_dict(fresh_db):
    client = _client()
    d = _mk_dossier()
    resp = client.get(f"/api/dossiers/{d.id}/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dossier_id"] == d.id
    assert body["status"] == "idle"
    assert "status_detail" in body
    assert body["open_needs_input_count"] == 0
    assert body["open_decision_point_count"] == 0
    assert body["delivered"] is False
