"""Tests for the telemetry module: tool-call logging + session stats.

The module targets the Day-2 merged schema (investigation_log,
sub_investigations, artifacts). In this worktree those tables do not
ship with schema.sql yet — the runtime-hooks / storage agents are
landing them in parallel. The tests use the worktree's v1 schema for
the "happy path" (change_log is always present) and, for the tests
that specifically exercise investigation_log / sub_investigations /
artifact counting, create stub tables via raw SQL against the same
throwaway DB. This lets the tests document the intended behaviour now
without forking schema.sql.
"""
from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# conftest.py owns the VELLUM_DB_PATH / init_db setup via the `fresh_db` fixture.


# ---------- helpers ----------


def _stub_v2_tables(conn) -> None:
    """Create the Day-2 tables (investigation_log, sub_investigations,
    artifacts) inside the throwaway DB. Mirrors the columns session_stats
    actually queries. These CREATE statements are intentionally
    worktree-local — when the real schema merges, the CREATE IF NOT EXISTS
    is a no-op."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS investigation_log (
            id TEXT PRIMARY KEY,
            dossier_id TEXT NOT NULL,
            work_session_id TEXT,
            sub_investigation_id TEXT,
            entry_type TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sub_investigations (
            id TEXT PRIMARY KEY,
            dossier_id TEXT NOT NULL,
            parent_section_id TEXT,
            scope TEXT NOT NULL,
            questions TEXT NOT NULL DEFAULT '[]',
            state TEXT NOT NULL DEFAULT 'running',
            return_summary TEXT,
            findings_section_ids TEXT NOT NULL DEFAULT '[]',
            findings_artifact_ids TEXT NOT NULL DEFAULT '[]',
            started_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            dossier_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            intended_use TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'draft',
            kind_note TEXT,
            supersedes TEXT,
            last_updated TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def _mk_dossier():
    from vellum import models as m, storage
    return storage.create_dossier(
        m.DossierCreate(
            title="telemetry test dossier",
            problem_statement="observe the agent",
            dossier_type=m.DossierType.investigation,
        )
    )


def _reload_telemetry():
    """Fresh import so _build_logger picks up env var changes (notably
    VELLUM_TOOL_LOG_PATH) set by a specific test."""
    from vellum.agent import telemetry as t
    importlib.reload(t)
    return t


# ---------- log_tool_call ----------


def test_log_tool_call_writes_json_line(fresh_db, tmp_path: Path, monkeypatch):
    log_path = tmp_path / "tool_calls.log"
    monkeypatch.setenv("VELLUM_TOOL_LOG_PATH", str(log_path))
    telemetry = _reload_telemetry()

    telemetry.log_tool_call(
        dossier_id="dos_x",
        tool_name="upsert_section",
        args={"title": "Finding 1", "content": "short body"},
        result={"section_id": "sec_1", "state": "confident"},
    )

    # Flush file handlers so the line is on disk before we read it.
    for h in logging.getLogger("vellum.agent.telemetry").handlers:
        h.flush()

    raw = log_path.read_text(encoding="utf-8").strip()
    assert raw, "expected a log line written to VELLUM_TOOL_LOG_PATH"
    record = json.loads(raw.splitlines()[-1])
    assert record["dossier_id"] == "dos_x"
    assert record["tool_name"] == "upsert_section"
    assert record["args_preview"]["title"] == "Finding 1"
    assert record["result_preview"]["section_id"] == "sec_1"
    assert "ts" in record
    assert "duration_ms" in record and record["duration_ms"] is None


def test_log_tool_call_truncates_long_strings(fresh_db, tmp_path: Path, monkeypatch):
    log_path = tmp_path / "tool_calls.log"
    monkeypatch.setenv("VELLUM_TOOL_LOG_PATH", str(log_path))
    telemetry = _reload_telemetry()

    long_title = "t" * 400
    long_content = "c" * 400
    long_result = "r" * 400

    telemetry.log_tool_call(
        dossier_id="dos_x",
        tool_name="upsert_section",
        args={"title": long_title, "content": long_content},
        result=long_result,
    )
    for h in logging.getLogger("vellum.agent.telemetry").handlers:
        h.flush()

    record = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])

    # title (non-verbose key) truncates to 200-char default + suffix.
    assert record["args_preview"]["title"].startswith("t" * 200)
    assert "…" in record["args_preview"]["title"]
    assert len(record["args_preview"]["title"]) < 400

    # content (verbose key) truncates harder — to 120 chars + suffix.
    assert record["args_preview"]["content"].startswith("c" * 120)
    assert len(record["args_preview"]["content"]) < len(record["args_preview"]["title"])

    # top-level string result truncates at default 200.
    assert record["result_preview"].startswith("r" * 200)
    assert "…" in record["result_preview"]


def test_log_tool_call_never_raises(fresh_db, tmp_path: Path, monkeypatch):
    """A badly-typed arg must not take out an agent turn."""
    telemetry = _reload_telemetry()

    class NotSerialisable:
        def __repr__(self) -> str:
            return "<weird>"

    # default=str in json.dumps handles this — confirm it doesn't raise.
    telemetry.log_tool_call(
        dossier_id="dos_x",
        tool_name="weird_tool",
        args={"weird": NotSerialisable()},
        result=None,
    )


# ---------- session_stats ----------


def test_session_stats_returns_none_for_missing_session(fresh_db):
    telemetry = _reload_telemetry()
    assert telemetry.session_stats("ws_does_not_exist") is None


def test_session_stats_counts_artifacts_sources_subs(fresh_db):
    """Full happy-path against the merged-shape schema (stubbed here)."""
    from vellum import db as _db
    from vellum import models as m, storage

    telemetry = _reload_telemetry()

    # 1. Create a dossier and a work_session.
    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    # 2. Stub the merged-shape tables and populate them within the
    # session's active window.
    with _db.connect() as conn:
        _stub_v2_tables(conn)

        # 3 source_consulted entries for this session
        for i in range(3):
            conn.execute(
                "INSERT INTO investigation_log "
                "(id, dossier_id, work_session_id, entry_type, payload, summary, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"ilg_src_{i}",
                    dossier.id,
                    session.id,
                    "source_consulted",
                    "{}",
                    f"source {i}",
                    m.utc_now().isoformat(),
                ),
            )

        # 2 sub_investigations started inside the session window
        for i in range(2):
            conn.execute(
                "INSERT INTO sub_investigations "
                "(id, dossier_id, scope, state, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"sub_{i}",
                    dossier.id,
                    f"scope {i}",
                    "running",
                    m.utc_now().isoformat(),
                ),
            )

        # 1 artifact row (content) plus the matching change_log artifact_added entry.
        conn.execute(
            "INSERT INTO artifacts "
            "(id, dossier_id, kind, title, content, intended_use, state, "
            "last_updated, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "art_1",
                dossier.id,
                "letter",
                "Demand letter",
                "body",
                "send",
                "draft",
                m.utc_now().isoformat(),
                m.utc_now().isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO change_log "
            "(id, dossier_id, work_session_id, kind, change_note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                m.new_id("chg"),
                dossier.id,
                session.id,
                "artifact_added",
                "Added artifact: Demand letter",
                m.utc_now().isoformat(),
            ),
        )

    # Also write a real section via storage (so change_log picks up section_created).
    storage.upsert_section(
        dossier.id,
        m.SectionUpsert(
            type=m.SectionType.finding,
            title="Seeded finding",
            state=m.SectionState.confident,
            change_note="seeded from test",
        ),
        work_session_id=session.id,
    )

    # 3. Burn some tokens so the aggregate shows up.
    storage.increment_session_tokens(session.id, 1234)

    stats = telemetry.session_stats(session.id)

    assert stats is not None
    assert stats["session_id"] == session.id
    assert stats["dossier_id"] == dossier.id
    assert stats["source_count"] == 3
    assert stats["sub_investigation_count"] == 2
    assert stats["artifact_count"] == 1
    assert stats["tokens_used"] == 1234
    # tool_counts merges change_log.kind + investigation_log.entry_type
    assert stats["tool_counts"].get("artifact_added") == 1
    assert stats["tool_counts"].get("section_created") == 1
    assert stats["tool_counts"].get("source_consulted") == 3
    # duration_seconds is non-negative (session still open — measured vs now).
    assert stats["duration_seconds"] >= 0.0


def test_session_stats_handles_missing_v2_tables(fresh_db):
    """Pre-merge: investigation_log / sub_investigations / artifacts don't
    exist. session_stats must still return a sensible shape with zero
    counts instead of blowing up on OperationalError."""
    from vellum import models as m, storage

    telemetry = _reload_telemetry()

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    # Touch change_log via a real section upsert so at least the v1 counts
    # populate.
    storage.upsert_section(
        dossier.id,
        m.SectionUpsert(
            type=m.SectionType.finding,
            title="Pre-merge finding",
            state=m.SectionState.confident,
            change_note="only v1 tables",
        ),
        work_session_id=session.id,
    )

    stats = telemetry.session_stats(session.id)

    assert stats is not None
    assert stats["source_count"] == 0
    assert stats["sub_investigation_count"] == 0
    assert stats["artifact_count"] == 0
    assert "section_created" in stats["tool_counts"]


# ---------- hook registration ----------


def test_hook_registers_into_tool_hooks_when_present(fresh_db, monkeypatch):
    """If handlers.TOOL_HOOKS exists at import time, log_tool_call gets
    appended to it. If it doesn't, the import still succeeds cleanly."""
    from vellum.tools import handlers

    # Simulate the merged state: ensure TOOL_HOOKS is a real list on the module.
    monkeypatch.setattr(handlers, "TOOL_HOOKS", [], raising=False)

    telemetry = _reload_telemetry()

    assert telemetry.log_tool_call in handlers.TOOL_HOOKS


# ---------- HTTP route smoke test ----------


def test_stats_route_returns_200(fresh_db):
    """GET /api/work-sessions/{id}/stats returns the stats dict."""
    from vellum import models as m, storage
    from vellum.main import create_app

    _reload_telemetry()  # wire the hook to whatever TOOL_HOOKS shape exists

    # create_app() calls db.init_db() again against the same VELLUM_DB_PATH
    # — idempotent via CREATE TABLE IF NOT EXISTS.
    app = create_app()
    client = TestClient(app)

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    resp = client.get(f"/api/work-sessions/{session.id}/stats")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert payload["session_id"] == session.id
    assert payload["dossier_id"] == dossier.id
    assert "tool_counts" in payload
    assert "source_count" in payload
    assert "sub_investigation_count" in payload
    assert "artifact_count" in payload
    assert "tokens_used" in payload
    assert "duration_seconds" in payload


def test_stats_route_404_for_missing_session(fresh_db):
    from vellum.main import create_app

    _reload_telemetry()

    app = create_app()
    client = TestClient(app)

    resp = client.get("/api/work-sessions/ws_nonexistent/stats")
    assert resp.status_code == 404
