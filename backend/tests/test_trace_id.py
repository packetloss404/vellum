"""Tests for Phase 4A: trace_id propagation from work_session to turns to telemetry."""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

import pytest

from vellum import models as m
from vellum import storage


def _mk_dossier():
    return storage.create_dossier(
        m.DossierCreate(
            title="trace test dossier",
            problem_statement="test trace_id propagation",
            dossier_type=m.DossierType.investigation,
        )
    )


# ---------- work_session.trace_id ----------


def test_start_work_session_generates_trace_id(fresh_db):
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    assert session.trace_id, "trace_id must be non-empty on new sessions"
    assert len(session.trace_id) == 32, "trace_id should be uuid4 hex (32 chars)"


def test_each_session_gets_unique_trace_id(fresh_db):
    dossier = _mk_dossier()
    session1 = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    storage.end_work_session(session1.id)
    session2 = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    assert session1.trace_id != session2.trace_id


def test_get_work_session_returns_trace_id(fresh_db):
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    fetched = storage.get_work_session(session.id)
    assert fetched is not None
    assert fetched.trace_id == session.trace_id


def test_pre_phase4a_rows_have_empty_trace_id(fresh_db):
    """Existing DBs migrated via _REQUIRED_COLUMNS get default '' for trace_id."""
    from vellum import db as _db

    dossier = _mk_dossier()
    with _db.connect() as conn:
        # Simulate a pre-Phase-4A insert without trace_id.
        conn.execute(
            "INSERT INTO work_sessions (id, dossier_id, started_at, trigger, token_budget_used) "
            "VALUES (?, ?, ?, ?, 0)",
            ("ws_old", dossier.id, m.utc_now().isoformat(), "manual"),
        )

    fetched = storage.get_work_session("ws_old")
    assert fetched is not None
    assert fetched.trace_id == ""


# ---------- trace_id on agent_turns ----------


def test_agent_turn_inherits_trace_id_from_session(fresh_db):
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
        )
    )

    assert turn.trace_id == session.trace_id


def test_list_turns_for_trace_matches_session(fresh_db):
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    for i in range(3):
        storage.create_agent_turn(
            m.AgentTurnCreate(
                dossier_id=dossier.id,
                work_session_id=session.id,
                trace_id=session.trace_id,
                turn_index=i + 1,
                model="claude-3-5-sonnet",
            )
        )

    turns = storage.list_agent_turns_for_trace(session.trace_id)
    assert len(turns) == 3


# ---------- trace_id in telemetry ----------


def test_telemetry_log_includes_trace_id(fresh_db, tmp_path: Path, monkeypatch):
    log_path = tmp_path / "tool_calls.log"
    monkeypatch.setenv("VELLUM_TOOL_LOG_PATH", str(log_path))
    from vellum.agent import telemetry as t
    telemetry = importlib.reload(t)

    telemetry.log_tool_call(
        dossier_id="dos_x",
        tool_name="upsert_section",
        args={"title": "test"},
        result={"ok": True},
        trace_id="abc123def456",
    )

    for h in logging.getLogger("vellum.agent.telemetry").handlers:
        h.flush()

    raw = log_path.read_text(encoding="utf-8").strip()
    record = json.loads(raw.splitlines()[-1])
    assert record["trace_id"] == "abc123def456"


def test_telemetry_log_trace_id_defaults_empty(fresh_db, tmp_path: Path, monkeypatch):
    log_path = tmp_path / "tool_calls.log"
    monkeypatch.setenv("VELLUM_TOOL_LOG_PATH", str(log_path))
    from vellum.agent import telemetry as t
    telemetry = importlib.reload(t)

    telemetry.log_tool_call(
        dossier_id="dos_x",
        tool_name="upsert_section",
        args={},
        result=None,
    )

    for h in logging.getLogger("vellum.agent.telemetry").handlers:
        h.flush()

    raw = log_path.read_text(encoding="utf-8").strip()
    record = json.loads(raw.splitlines()[-1])
    assert record["trace_id"] == ""


# ---------- trace_id flows parent → sub ----------


def test_sub_turns_share_parent_trace_id(fresh_db):
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="sub scope"),
        session.id,
    )

    parent_turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            trace_id=session.trace_id,
            turn_index=1,
            model="claude-3-5-sonnet",
        )
    )

    sub_turn = storage.create_agent_turn(
        m.AgentTurnCreate(
            dossier_id=dossier.id,
            work_session_id=session.id,
            sub_investigation_id=sub.id,
            trace_id=session.trace_id,
            turn_index=2,
            model="claude-3-5-sonnet",
        )
    )

    assert parent_turn.trace_id == session.trace_id
    assert sub_turn.trace_id == session.trace_id

    # Both show up when filtering by trace.
    all_turns = storage.list_agent_turns_for_trace(session.trace_id)
    assert len(all_turns) == 2
