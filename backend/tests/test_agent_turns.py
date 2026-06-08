"""Tests for Phase 4A: agent_turns CRUD and cost aggregation."""
from __future__ import annotations

import pytest

from vellum import models as m
from vellum import storage


def _mk_dossier():
    return storage.create_dossier(
        m.DossierCreate(
            title="turn test dossier",
            problem_statement="test per-turn cost rows",
            dossier_type=m.DossierType.investigation,
        )
    )


def _mk_session(dossier_id: str) -> m.WorkSession:
    return storage.start_work_session(dossier_id, m.WorkSessionTrigger.manual)


# ---------- CRUD ----------


def test_create_agent_turn_and_read_back(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)

    turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
            input_tokens=500,
            output_tokens=100,
            cache_creation_input_tokens=50,
            cache_read_input_tokens=200,
            cost_usd=0.012,
            duration_ms=3200,
            tool_calls_count=3,
            stop_reason="tool_use",
        )
    )

    assert turn.id.startswith("agt_")
    assert turn.dossier_id == dossier.id
    assert turn.work_session_id == session.id
    assert turn.trace_id == session.trace_id
    assert turn.turn_index == 1
    assert turn.model == "claude-3-5-sonnet"
    assert turn.input_tokens == 500
    assert turn.output_tokens == 100
    assert turn.cost_usd == 0.012
    assert turn.duration_ms == 3200
    assert turn.tool_calls_count == 3
    assert turn.stop_reason == "tool_use"
    assert turn.created_at is not None


def test_create_agent_turn_with_sub_investigation_id(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="test sub"),
        session.id,
    )

    turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            sub_investigation_id=sub.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
            input_tokens=300,
            output_tokens=50,
            cost_usd=0.005,
            duration_ms=1500,
            tool_calls_count=1,
            stop_reason="end_turn",
        )
    )

    assert turn.sub_investigation_id == sub.id


def test_create_agent_turn_with_notes(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)

    turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
            cost_usd=0.0,
            notes="compaction triggered before this turn",
        )
    )

    assert turn.notes == "compaction triggered before this turn"


# ---------- List queries ----------


def test_list_turns_for_dossier(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)

    for i in range(3):
        storage.create_agent_turn(
            m.AgentTurnCreate(
                dossier_id=dossier.id,
                work_session_id=session.id,
                trace_id=session.trace_id,
                turn_index=i + 1,
                model="claude-3-5-sonnet",
                cost_usd=0.01 * (i + 1),
            )
        )

    turns = storage.list_agent_turns_for_dossier(dossier.id)
    assert len(turns) == 3
    # Ordered by created_at DESC — newest first.
    assert turns[0].turn_index == 3
    assert turns[2].turn_index == 1


def test_list_turns_for_dossier_respects_limit(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)

    for i in range(5):
        storage.create_agent_turn(
            m.AgentTurnCreate(
                dossier_id=dossier.id,
                work_session_id=session.id,
                trace_id=session.trace_id,
                turn_index=i + 1,
                model="claude-3-5-sonnet",
            )
        )

    turns = storage.list_agent_turns_for_dossier(dossier.id, limit=2)
    assert len(turns) == 2


def test_list_turns_for_session(fresh_db):
    dossier = _mk_dossier()
    session1 = _mk_session(dossier.id)
    storage.end_work_session(session1.id)
    session2 = _mk_session(dossier.id)

    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session1.id,
            trace_id=session1.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
        )
    )
    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session2.id,
            trace_id=session2.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
        )
    )

    turns1 = storage.list_agent_turns_for_session(session1.id)
    turns2 = storage.list_agent_turns_for_session(session2.id)
    assert len(turns1) == 1
    assert len(turns2) == 1
    assert turns1[0].work_session_id == session1.id
    assert turns2[0].work_session_id == session2.id


def test_list_turns_for_trace(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)
    trace_id = session.trace_id

    for i in range(2):
        storage.create_agent_turn(
            m.AgentTurnCreate(
                dossier_id=dossier.id,
                work_session_id=session.id,
                trace_id=trace_id,
                turn_index=i + 1,
                model="claude-3-5-sonnet",
            )
        )

    turns = storage.list_agent_turns_for_trace(trace_id)
    assert len(turns) == 2
    assert all(t.trace_id == trace_id for t in turns)


# ---------- Cost aggregation ----------


def test_cost_summary_aggregates_by_model(fresh_db):
    dossier = _mk_dossier()
    session = _mk_session(dossier.id)

    for _ in range(2):
        storage.create_agent_turn(
            m.AgentTurnCreate(
                dossier_id=dossier.id,
                work_session_id=session.id,
                trace_id=session.trace_id,
                turn_index=1,
                model="claude-3-5-sonnet",
                input_tokens=500,
                output_tokens=100,
                cache_creation_input_tokens=50,
                cache_read_input_tokens=200,
                cost_usd=0.01,
                duration_ms=2000,
                tool_calls_count=2,
            )
        )

    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=3,
            model="claude-3-haiku",
            input_tokens=200,
            output_tokens=30,
            cost_usd=0.002,
            duration_ms=800,
            tool_calls_count=1,
        )
    )

    summary = storage.get_turn_cost_summary_for_dossier(dossier.id)
    assert len(summary) == 2

    sonnet_row = next(r for r in summary if r["model"] == "claude-3-5-sonnet")
    assert sonnet_row["turn_count"] == 2
    assert sonnet_row["total_input_tokens"] == 1000
    assert sonnet_row["total_output_tokens"] == 200
    assert sonnet_row["total_cache_creation_input_tokens"] == 100
    assert sonnet_row["total_cache_read_input_tokens"] == 400
    assert sonnet_row["total_cost_usd"] == pytest.approx(0.02, abs=1e-6)
    assert sonnet_row["total_duration_ms"] == 4000
    assert sonnet_row["total_tool_calls"] == 4

    haiku_row = next(r for r in summary if r["model"] == "claude-3-haiku")
    assert haiku_row["turn_count"] == 1
    assert haiku_row["total_input_tokens"] == 200
    assert haiku_row["total_cost_usd"] == pytest.approx(0.002, abs=1e-6)


def test_cost_summary_empty_for_no_turns(fresh_db):
    dossier = _mk_dossier()
    summary = storage.get_turn_cost_summary_for_dossier(dossier.id)
    assert summary == []


# ---------- API route smoke tests ----------


def test_turns_route_returns_turns(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    client = TestClient(app)

    dossier = _mk_dossier()
    session = _mk_session(dossier.id)
    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
            cost_usd=0.01,
        )
    )

    resp = client.get(f"/api/dossiers/{dossier.id}/turns")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["model"] == "claude-3-5-sonnet"


def test_turns_summary_route(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    client = TestClient(app)

    dossier = _mk_dossier()
    session = _mk_session(dossier.id)
    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
            cost_usd=0.01,
        )
    )

    resp = client.get(f"/api/dossiers/{dossier.id}/turns/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["model"] == "claude-3-5-sonnet"
    assert data[0]["turn_count"] == 1


def test_turns_by_trace_route(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    client = TestClient(app)

    dossier = _mk_dossier()
    session = _mk_session(dossier.id)
    storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
        )
    )

    resp = client.get(f"/api/dossiers/{dossier.id}/turns/by-trace/{session.trace_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_turns_route_404_for_missing_dossier(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/dossiers/dos_nonexistent/turns")
    assert resp.status_code == 404
