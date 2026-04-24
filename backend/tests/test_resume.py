"""Day-3 resume + lifecycle tests.

Exercises the three Day-3 additions:

  - ``POST /api/dossiers/{id}/resume`` — open a fresh work_session with
    ``trigger=resume`` and fire ``ORCHESTRATOR.start`` (mocked here; we
    never hit the real LLM).
  - ``GET /api/dossiers/{id}/resume-state`` — read-only snapshot for
    the UI to decide whether to offer a resume action.
  - ``lifecycle.reconcile_at_startup`` enrichments: the report now
    carries ``recovered_dossier_ids`` and
    ``active_sessions_before_reconcile``.

HTTP tests use FastAPI's ``TestClient`` against a freshly-provisioned
SQLite DB (see ``conftest.py::fresh_db``). ``ORCHESTRATOR.start`` is
monkeypatched module-wide to a no-op coroutine so the agent runtime
never runs.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient


# ---------- test helpers ----------


def _mk_dossier(title: str = "Resume test dossier") -> Any:
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement="Exercise the Day-3 resume path.",
            dossier_type=m.DossierType.investigation,
        )
    )


def _patch_orchestrator_start(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace ``ORCHESTRATOR.start`` with a recording no-op.

    Returns a dict into which every call is appended, so tests can
    assert the orchestrator was (or wasn't) asked to start the dossier.
    """
    from vellum.agent import orchestrator as orch_mod

    calls: dict[str, list[dict]] = {"started": []}

    async def _fake_start(
        dossier_id: str,
        max_turns: int = 200,
        model: Optional[str] = None,
        expected_session_id: Optional[str] = None,
    ) -> dict:
        calls["started"].append(
            {
                "dossier_id": dossier_id,
                "max_turns": max_turns,
                "model": model,
                "expected_session_id": expected_session_id,
            }
        )
        return {"status": "started", "dossier_id": dossier_id}

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _fake_start)
    return calls


@pytest.fixture
def client(fresh_db, monkeypatch):
    """FastAPI TestClient against the fresh_db sqlite file.

    ``fresh_db`` already points ``VELLUM_DB_PATH`` at a throwaway file
    and runs ``init_db`` on it. We only need to build the app on top.
    Lifespan hooks (including ``reconcile_at_startup``) run on enter /
    exit — that's fine, they're idempotent and return immediately on
    an empty DB.

    Importing ``vellum.main`` triggers ``vellum.agent.telemetry`` which
    appends ``log_tool_call`` to ``handlers.TOOL_HOOKS`` as a side
    effect. The sentinel in ``test_runtime_hooks`` captures and
    restores ``TOOL_HOOKS`` to whatever it sees at first test entry,
    so it's order-sensitive to this append. To keep the full suite
    deterministic, snapshot TOOL_HOOKS before ``create_app`` and
    restore it afterward.
    """
    # Snapshot TOOL_HOOKS before the first import-time mutation.
    try:
        from vellum.tools import handlers as _handlers_before
        _saved_hooks = list(_handlers_before.TOOL_HOOKS)
    except Exception:
        _saved_hooks = None

    from vellum.main import create_app

    app = create_app()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if _saved_hooks is not None:
            from vellum.tools import handlers as _handlers_after
            _handlers_after.TOOL_HOOKS.clear()
            _handlers_after.TOOL_HOOKS.extend(_saved_hooks)


# ---------- POST /resume ----------


def test_resume_missing_dossier_returns_404(client, monkeypatch):
    calls = _patch_orchestrator_start(monkeypatch)
    resp = client.post("/api/dossiers/dos_does_not_exist/resume")
    assert resp.status_code == 404, resp.text
    # Must NOT have asked the orchestrator to start anything.
    assert calls["started"] == []


def test_resume_idle_dossier_starts_session(client, monkeypatch):
    calls = _patch_orchestrator_start(monkeypatch)
    dossier = _mk_dossier()

    resp = client.post(f"/api/dossiers/{dossier.id}/resume")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["dossier_id"] == dossier.id
    assert body["status"] == "started"
    assert body["work_session_id"].startswith("ws_"), body

    # Orchestrator was asked to start this dossier, exactly once.
    assert len(calls["started"]) == 1
    assert calls["started"][0]["dossier_id"] == dossier.id

    # The new session is active and carries trigger=resume.
    from vellum import models as m, storage

    active = storage.get_active_work_session(dossier.id)
    assert active is not None
    assert active.id == body["work_session_id"]
    assert active.trigger == m.WorkSessionTrigger.resume


def test_resume_with_active_session_returns_409(client, monkeypatch):
    calls = _patch_orchestrator_start(monkeypatch)
    dossier = _mk_dossier()

    # Open a session by hand — simulate "the agent is already working".
    from vellum import models as m, storage

    active = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    resp = client.post(f"/api/dossiers/{dossier.id}/resume")
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["active_work_session_id"] == active.id
    assert body["dossier_id"] == dossier.id

    # Orchestrator must not have been called — the conflict was caught
    # at the storage layer before any start attempt.
    assert calls["started"] == []

    # And the existing session is untouched (still active).
    still_active = storage.get_active_work_session(dossier.id)
    assert still_active is not None
    assert still_active.id == active.id
    assert still_active.ended_at is None


def test_start_work_session_rejects_duplicate_active_session(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    active = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    with pytest.raises(storage.ActiveWorkSessionExists) as excinfo:
        storage.start_work_session(dossier.id, m.WorkSessionTrigger.resume)

    assert excinfo.value.session.id == active.id
    sessions = storage.list_work_sessions(dossier.id)
    assert [s for s in sessions if s.ended_at is None] == [active]


def test_resume_closes_new_session_if_orchestrator_race(client, monkeypatch):
    """If the orchestrator reports AgentAlreadyRunning (e.g. raced a
    concurrent start we didn't see), the route must close the session
    it just created and still return 409.
    """
    from vellum.agent import orchestrator as orch_mod

    dossier = _mk_dossier()

    calls: list[str] = []

    async def _always_conflict(dossier_id: str, **_kw: Any) -> dict:
        calls.append(dossier_id)
        raise orch_mod.AgentAlreadyRunning(dossier_id)

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _always_conflict)

    resp = client.post(f"/api/dossiers/{dossier.id}/resume")
    assert resp.status_code == 409, resp.text
    assert calls == [dossier.id]

    # Critically: the session the route opened must have been closed,
    # so a later reconcile_at_startup doesn't think there's an orphan.
    from vellum import storage

    active = storage.get_active_work_session(dossier.id)
    assert active is None, "resume must clean up its own session on conflict"


# ---------- GET /resume-state ----------


def test_resume_state_missing_dossier_returns_404(client):
    resp = client.get("/api/dossiers/dos_missing/resume-state")
    assert resp.status_code == 404


def test_resume_state_shapes(client, monkeypatch):
    from vellum import models as m, storage

    # 1. Empty dossier: no plan, no sessions, nothing open.
    dossier = _mk_dossier("no plan yet")
    resp = client.get(f"/api/dossiers/{dossier.id}/resume-state")
    assert resp.status_code == 200, resp.text
    state = resp.json()
    assert state == {
        "dossier_id": dossier.id,
        "has_plan": False,
        "plan_approved": False,
        "active_work_session_id": None,
        "last_session_ended_at": None,
        "last_visited_at": None,
        "open_needs_input_count": 0,
        "open_decision_point_count": 0,
        "delivered": False,
        "wake_at": None,
        "wake_pending": False,
        "wake_reason": None,
    }

    # 2. Plan drafted but not approved.
    storage.update_investigation_plan(
        dossier.id,
        m.InvestigationPlanUpdate(items=[], rationale="first draft", approve=False),
    )
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["has_plan"] is True
    assert state["plan_approved"] is False

    # 3. Plan approved.
    storage.update_investigation_plan(
        dossier.id,
        m.InvestigationPlanUpdate(items=[], rationale="good to go", approve=True),
    )
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["has_plan"] is True
    assert state["plan_approved"] is True

    # 4. Open needs_input + open decision_point.
    storage.add_needs_input(
        dossier.id,
        m.NeedsInputCreate(question="which API key?"),
    )
    storage.add_decision_point(
        dossier.id,
        m.DecisionPointCreate(
            title="pick stack",
            options=[
                m.DecisionOption(label="A", implications="fast"),
                m.DecisionOption(label="B", implications="safe"),
            ],
            recommendation="A",
        ),
    )
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["open_needs_input_count"] == 1
    assert state["open_decision_point_count"] == 1

    # 5. Active session surfaces its id.
    session = storage.start_work_session(
        dossier.id, m.WorkSessionTrigger.manual
    )
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["active_work_session_id"] == session.id
    # last_session_ended_at is still None — nothing has ended yet.
    assert state["last_session_ended_at"] is None

    # 6. Visit is read-only for session lifecycle: it updates last_visited_at
    # but must not close the active agent session.
    visit = client.post(f"/api/dossiers/{dossier.id}/visit")
    assert visit.status_code == 200, visit.text
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["last_visited_at"] is not None
    assert state["active_work_session_id"] == session.id

    # 7. End session: active clears, last_session_ended_at populates.
    storage.end_work_session(session.id)
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["active_work_session_id"] is None
    assert state["last_session_ended_at"] is not None

    # 8. Visit updates last_visited_at and must NOT revive the plan /
    # counts (read-only contract on visit).
    client.post(f"/api/dossiers/{dossier.id}/visit")
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["last_visited_at"] is not None
    assert state["has_plan"] is True
    assert state["plan_approved"] is True

    # 9. Delivered dossier surfaces delivered=True.
    storage.update_dossier(
        dossier.id, m.DossierUpdate(status=m.DossierStatus.delivered)
    )
    state = client.get(f"/api/dossiers/{dossier.id}/resume-state").json()
    assert state["delivered"] is True


# ---------- lifecycle.reconcile_at_startup enrichments ----------


def test_reconcile_reports_recovered_dossier_ids_and_active_before(
    fresh_db, caplog
):
    """The Day-3 enrichments must be populated and the log summary must
    mention the titles we recovered (up to 5)."""
    from vellum import lifecycle
    from vellum import models as m, storage

    # Three dossiers, each with an orphan work_session.
    d1 = storage.create_dossier(
        m.DossierCreate(
            title="Alpha investigation",
            problem_statement="p1",
            dossier_type=m.DossierType.investigation,
        )
    )
    d2 = storage.create_dossier(
        m.DossierCreate(
            title="Beta investigation",
            problem_statement="p2",
            dossier_type=m.DossierType.investigation,
        )
    )
    d3 = storage.create_dossier(
        m.DossierCreate(
            title="Gamma investigation",
            problem_statement="p3",
            dossier_type=m.DossierType.investigation,
        )
    )

    storage.start_work_session(d1.id, m.WorkSessionTrigger.manual)
    storage.start_work_session(d2.id, m.WorkSessionTrigger.manual)
    storage.start_work_session(d3.id, m.WorkSessionTrigger.manual)

    import logging

    caplog.set_level(logging.INFO, logger="vellum.lifecycle")
    report = lifecycle.reconcile_at_startup()

    # 3 orphan sessions, 3 distinct dossiers.
    assert report.active_sessions_before_reconcile == 3
    assert report.recovered_work_sessions == 3
    assert set(report.recovered_dossier_ids) == {d1.id, d2.id, d3.id}
    assert len(report.recovered_dossier_ids) == 3  # de-duped

    # Log summary must mention at least one title so the one-liner is
    # actually useful.
    summary = "\n".join(
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "vellum.lifecycle"
    )
    assert "Alpha investigation" in summary or "Beta investigation" in summary \
        or "Gamma investigation" in summary, summary
    assert "active_before=3" in summary

    # Second call: nothing to recover.
    report2 = lifecycle.reconcile_at_startup()
    assert report2.active_sessions_before_reconcile == 0
    assert report2.recovered_work_sessions == 0
    assert report2.recovered_dossier_ids == []


def test_reconcile_log_summary_caps_at_five_titles(fresh_db, caplog):
    """Summary should carry at most 5 titles + a '+N more' suffix."""
    from vellum import lifecycle
    from vellum import models as m, storage

    ids = []
    for i in range(7):
        d = storage.create_dossier(
            m.DossierCreate(
                title=f"Dossier {i:02d}",
                problem_statement="p",
                dossier_type=m.DossierType.investigation,
            )
        )
        storage.start_work_session(d.id, m.WorkSessionTrigger.manual)
        ids.append(d.id)

    import logging

    caplog.set_level(logging.INFO, logger="vellum.lifecycle")
    report = lifecycle.reconcile_at_startup()
    assert len(report.recovered_dossier_ids) == 7

    summary = "\n".join(
        rec.getMessage()
        for rec in caplog.records
        if rec.name == "vellum.lifecycle"
    )
    # 7 dossiers → 5 shown, 2 more suffix.
    assert "+2 more" in summary, summary
