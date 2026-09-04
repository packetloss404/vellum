"""Durable, versioned autonomous-research lifecycle and progress reporting."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import timedelta
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .. import models as m
from ..db import connect
from ._helpers import _dt, _dt_str, _row_get

_LIVE = ("queued", "running", "pause_requested", "waiting_for_user", "blocked_sleep", "paused", "cap_reached", "quarantined")
_TERMINAL = ("completed", "failed", "cancelled", "superseded")


def _normalise_citation(value: str) -> str:
    raw = (value or "").strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        return ""
    host = (parts.hostname or "").casefold().removeprefix("www.")
    try:
        parsed_port = parts.port
    except ValueError:
        return ""
    default_port = (parts.scheme.casefold() == "http" and parsed_port == 80) or (parts.scheme.casefold() == "https" and parsed_port == 443)
    port = f":{parsed_port}" if parsed_port and not default_port else ""
    path = parts.path.rstrip("/") or "/"
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if k.casefold() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}
                       and not k.casefold().startswith("utm_")])
    return urlunsplit((parts.scheme.casefold(), host + port, path, query, ""))


def _run_from_row(row) -> m.ResearchRun:
    return m.ResearchRun(
        id=row["id"], dossier_id=row["dossier_id"],
        policy_snapshot=m.ResearchPolicy.model_validate_json(row["policy_snapshot"]),
        depth=m.ResearchDepth(row["depth"]), strategy_version=row["strategy_version"],
        status=m.ResearchRunStatus(row["status"]), initiated_by=row["initiated_by"],
        state_version=int(row["state_version"]), started_at=_dt(row["started_at"]),
        updated_at=_dt(row["updated_at"]), ended_at=_dt(row["ended_at"]),
        stop_reason=row["stop_reason"], completion_reason=row["completion_reason"],
        sessions_started=int(row["sessions_started"] or 0), cost_usd=float(row["cost_usd"] or 0),
    )


def _active_run_row(conn, dossier_id: str):
    marks = ",".join("?" for _ in _LIVE)
    return conn.execute(f"SELECT * FROM research_runs WHERE dossier_id=? AND status IN ({marks}) ORDER BY started_at DESC LIMIT 1", (dossier_id, *_LIVE)).fetchone()


def get_active_research_run(dossier_id: str) -> Optional[m.ResearchRun]:
    with connect() as conn:
        row = _active_run_row(conn, dossier_id)
    return _run_from_row(row) if row else None


def get_research_run(run_id: str) -> Optional[m.ResearchRun]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
    return _run_from_row(row) if row else None


def list_research_runs(dossier_id: str) -> list[m.ResearchRun]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM research_runs WHERE dossier_id=? ORDER BY started_at DESC", (dossier_id,)).fetchall()
    return [_run_from_row(row) for row in rows]


def _append_event(conn, run_row, event_type: str, payload: Optional[dict] = None,
                  work_session_id: Optional[str] = None, *, notify: bool = False) -> str:
    event_id = m.new_id("rev"); now_s = _dt_str(m.utc_now())
    conn.execute("INSERT INTO research_run_events (id,run_id,work_session_id,event_type,payload,transition_version,created_at) VALUES (?,?,?,?,?,?,?)",
                 (event_id, run_row["id"], work_session_id, event_type, json.dumps(payload or {}, separators=(",", ":")), int(run_row["state_version"]), now_s))
    if notify:
        conn.execute("INSERT OR IGNORE INTO notifications (id,dossier_id,run_id,event_id,event_type,payload,is_read,created_at) VALUES (?,?,?,?,?,?,0,?)",
                     (m.new_id("not"), run_row["dossier_id"], run_row["id"], event_id, event_type, json.dumps(payload or {}, separators=(",", ":")), now_s))
    return event_id


def _transition(conn, run_id: str, status: str, *, stop_reason: Optional[str] = None,
                completion_reason: Optional[str] = None, event_type: Optional[str] = None,
                payload: Optional[dict] = None, work_session_id: Optional[str] = None,
                notify: bool = False, expected_version: Optional[int] = None):
    row = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
    if row is None or (expected_version is not None and int(row["state_version"]) != expected_version):
        return None
    if row["status"] == status and row["stop_reason"] == stop_reason and row["completion_reason"] == completion_reason:
        return row
    version = int(row["state_version"]) + 1; now_s = _dt_str(m.utc_now())
    ended_at = now_s if status in _TERMINAL else None
    cur = conn.execute("UPDATE research_runs SET status=?,state_version=?,updated_at=?,ended_at=?,stop_reason=?,completion_reason=? WHERE id=? AND state_version=?",
                       (status, version, now_s, ended_at, stop_reason, completion_reason, run_id, int(row["state_version"])))
    if not cur.rowcount:
        return None
    updated = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
    _append_event(conn, updated, event_type or status, payload, work_session_id, notify=notify)
    return updated


def update_research_policy(dossier_id: str, policy: m.ResearchPolicy) -> Optional[m.ResearchPolicy]:
    with connect() as conn:
        cur = conn.execute("UPDATE dossiers SET research_policy=?,updated_at=? WHERE id=?", (policy.model_dump_json(), _dt_str(m.utc_now()), dossier_id))
    return policy if cur.rowcount else None


def _setting_tx(conn, key: str, default=None):
    row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else default


def _schedule_wake_tx(conn, dossier_id: str, run_id: str, reason: str, due_at, expected_version: int) -> str:
    now_s = _dt_str(m.utc_now()); due_s = _dt_str(due_at); wake_id = m.new_id("rwk")
    conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE run_id=? AND state IN ('pending','leased')", (now_s, run_id))
    conn.execute("INSERT INTO research_wakes (id,dossier_id,run_id,reason,due_at,state,expected_run_version,created_at,updated_at) VALUES (?,?,?,?,?,'pending',?,?,?)",
                 (wake_id, dossier_id, run_id, reason, due_s, expected_version, now_s, now_s))
    pending = int(due_at <= m.utc_now())
    conn.execute("UPDATE dossiers SET wake_at=?,wake_pending=?,wake_reason=? WHERE id=?", (None if pending else due_s, pending, reason, dossier_id))
    return wake_id


def _create_run(conn, dossier, policy: m.ResearchPolicy, *, initiated_by: str, idempotency_key: Optional[str]) -> str:
    now = m.utc_now(); now_s = _dt_str(now); run_id = m.new_id("rrn")
    enabled = policy.model_copy(update={"autonomy_enabled": True})
    conn.execute("INSERT INTO research_runs (id,dossier_id,policy_snapshot,depth,strategy_version,status,initiated_by,state_version,started_at,updated_at,start_idempotency_key) VALUES (?,?,?,?,?,'queued',?,1,?,?,?)",
                 (run_id, dossier["id"], enabled.model_dump_json(), enabled.depth.value, "v1", initiated_by, now_s, now_s, idempotency_key))
    run = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
    _append_event(conn, run, "run_started", {"initiated_by": initiated_by})
    conn.execute("UPDATE dossiers SET research_policy=?,research_started_at=?,research_stop_reason=NULL,updated_at=? WHERE id=?", (enabled.model_dump_json(), now_s, now_s, dossier["id"]))
    _schedule_wake_tx(conn, dossier["id"], run_id, m.WakeReason.autonomous_continue.value, now, int(run["state_version"]))
    return run_id


def start_autonomous_research(dossier_id: str, policy: Optional[m.ResearchPolicy] = None, *,
                              idempotency_key: Optional[str] = None, initiated_by: str = "user") -> Optional[m.ResearchProgress]:
    """Start once; retries return the same run and never reset its budget."""
    with connect() as conn:
        if not conn.in_transaction: conn.execute("BEGIN IMMEDIATE")
        dossier = conn.execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,)).fetchone()
        if dossier is None: return None
        if dossier["status"] == m.DossierStatus.delivered.value: raise ValueError("delivered dossiers cannot start autonomous research")
        if _row_get(dossier, "quarantined_at"): raise ValueError("quarantined dossiers must be explicitly cleared before research starts")
        if not bool(_setting_tx(conn, "sleep_mode_enabled", True)): raise ValueError("sleep mode must be enabled before autonomous research can start")
        if idempotency_key:
            replay = conn.execute("SELECT id FROM research_runs WHERE dossier_id=? AND start_idempotency_key=?", (dossier_id, idempotency_key)).fetchone()
            if replay: return get_research_progress(dossier_id, run_id=replay["id"])
        active = _active_run_row(conn, dossier_id)
        if active:
            if active["status"] in ("queued", "running", "waiting_for_user"): return get_research_progress(dossier_id)
            raise ValueError("a paused research run already exists; resume it or explicitly restart")
        if conn.execute("SELECT 1 FROM research_runs WHERE dossier_id=? LIMIT 1", (dossier_id,)).fetchone():
            raise ValueError("research has run before; use explicit restart to create a new run")
        current = m.ResearchPolicy.model_validate_json(dossier["research_policy"]) if dossier["research_policy"] else m.ResearchPolicy()
        _create_run(conn, dossier, policy or current, initiated_by=initiated_by, idempotency_key=idempotency_key)
    return get_research_progress(dossier_id)


def restart_autonomous_research(dossier_id: str, policy: Optional[m.ResearchPolicy] = None, *,
                                idempotency_key: Optional[str] = None, initiated_by: str = "user") -> Optional[m.ResearchProgress]:
    with connect() as conn:
        if not conn.in_transaction: conn.execute("BEGIN IMMEDIATE")
        dossier = conn.execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,)).fetchone()
        if dossier is None: return None
        if dossier["status"] == "delivered": raise ValueError("delivered dossiers cannot restart research")
        if not bool(_setting_tx(conn, "sleep_mode_enabled", True)): raise ValueError("sleep mode must be enabled before research restarts")
        if idempotency_key:
            replay = conn.execute("SELECT id FROM research_runs WHERE dossier_id=? AND start_idempotency_key=?", (dossier_id, idempotency_key)).fetchone()
            if replay: return get_research_progress(dossier_id, run_id=replay["id"])
        if conn.execute("SELECT 1 FROM work_sessions WHERE dossier_id=? AND ended_at IS NULL", (dossier_id,)).fetchone():
            raise ValueError("cannot restart research while a work session is active")
        active = _active_run_row(conn, dossier_id)
        if active:
            _transition(conn, active["id"], "superseded", completion_reason="explicit_restart", event_type="run_superseded")
            conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE run_id=? AND state IN ('pending','leased')", (_dt_str(m.utc_now()), active["id"]))
        current = m.ResearchPolicy.model_validate_json(dossier["research_policy"]) if dossier["research_policy"] else m.ResearchPolicy()
        conn.execute("UPDATE dossiers SET quarantined_at=NULL,quarantine_reason=NULL,consecutive_error_count=0 WHERE id=?", (dossier_id,))
        _create_run(conn, dossier, policy or current, initiated_by=initiated_by, idempotency_key=idempotency_key)
    return get_research_progress(dossier_id)


def pause_autonomous_research(dossier_id: str, reason: str = "paused_by_user") -> Optional[m.ResearchProgress]:
    with connect() as conn:
        if not conn.in_transaction: conn.execute("BEGIN IMMEDIATE")
        dossier = conn.execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,)).fetchone()
        if dossier is None: return None
        active = _active_run_row(conn, dossier_id)
        policy = (m.ResearchPolicy.model_validate_json(dossier["research_policy"]) if dossier["research_policy"] else m.ResearchPolicy()).model_copy(update={"autonomy_enabled": False})
        now_s = _dt_str(m.utc_now())
        conn.execute("UPDATE dossiers SET research_policy=?,research_stop_reason=?,updated_at=? WHERE id=?", (policy.model_dump_json(), reason, now_s, dossier_id))
        if active:
            target = "pause_requested" if active["status"] == "running" else "paused"
            _transition(conn, active["id"], target, stop_reason=reason, event_type=target)
            conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE run_id=? AND state IN ('pending','leased')", (now_s, active["id"]))
        conn.execute("UPDATE dossiers SET wake_at=NULL,wake_pending=0 WHERE id=? AND wake_reason=?", (dossier_id, m.WakeReason.autonomous_continue.value))
    return get_research_progress(dossier_id)


def resume_autonomous_research(dossier_id: str, run_id: str) -> Optional[m.ResearchProgress]:
    with connect() as conn:
        if not conn.in_transaction: conn.execute("BEGIN IMMEDIATE")
        dossier = conn.execute("SELECT * FROM dossiers WHERE id=?", (dossier_id,)).fetchone()
        run = conn.execute("SELECT * FROM research_runs WHERE id=? AND dossier_id=?", (run_id, dossier_id)).fetchone()
        if dossier is None or run is None: return None
        if dossier["status"] == "delivered" or _row_get(dossier, "quarantined_at"): raise ValueError("delivered or quarantined dossiers cannot resume research")
        if conn.execute("SELECT 1 FROM work_sessions WHERE dossier_id=? AND ended_at IS NULL", (dossier_id,)).fetchone():
            raise ValueError("cannot resume research while a work session is active")
        if run["status"] not in ("paused", "cap_reached", "blocked_sleep", "pause_requested"): raise ValueError(f"research run in {run['status']} cannot be resumed")
        if not bool(_setting_tx(conn, "sleep_mode_enabled", True)): raise ValueError("sleep mode must be enabled before research resumes")
        updated = _transition(conn, run_id, "queued", event_type="run_resumed")
        policy = m.ResearchPolicy.model_validate_json(run["policy_snapshot"]).model_copy(update={"autonomy_enabled": True})
        conn.execute("UPDATE dossiers SET research_policy=?,research_stop_reason=NULL,updated_at=? WHERE id=?", (policy.model_dump_json(), _dt_str(m.utc_now()), dossier_id))
        _schedule_wake_tx(conn, dossier_id, run_id, m.WakeReason.autonomous_continue.value, m.utc_now(), int(updated["state_version"]))
    return get_research_progress(dossier_id)


def set_research_stop_reason(dossier_id: str, reason: Optional[str]) -> None:
    with connect() as conn:
        conn.execute("UPDATE dossiers SET research_stop_reason=?,updated_at=? WHERE id=?", (reason, _dt_str(m.utc_now()), dossier_id))


def schedule_research_wake(dossier_id: str, run_id: str, reason: m.WakeReason, due_at=None) -> str:
    with connect() as conn:
        run = conn.execute("SELECT * FROM research_runs WHERE id=? AND dossier_id=?", (run_id, dossier_id)).fetchone()
        if run is None: raise ValueError("research run not found")
        if run["status"] not in ("queued", "running"):
            raise ValueError(f"research run in {run['status']} cannot be scheduled")
        return _schedule_wake_tx(conn, dossier_id, run_id, reason.value, due_at or m.utc_now(), int(run["state_version"]))


def resume_waiting_research_run(dossier_id: str, run_id: str, reason: m.WakeReason) -> None:
    with connect() as conn:
        _resume_waiting_research_run_tx(conn, dossier_id, reason)


def _resume_waiting_research_run_tx(conn, dossier_id: str, reason: m.WakeReason) -> bool:
    """Resume a waiting run inside the caller's answer/decision transaction."""
    run = _active_run_row(conn, dossier_id)
    if not run or run["status"] != "waiting_for_user": return False
    open_needs = conn.execute("SELECT 1 FROM needs_input WHERE dossier_id=? AND answered_at IS NULL LIMIT 1", (dossier_id,)).fetchone()
    open_decisions = conn.execute("SELECT 1 FROM decision_points WHERE dossier_id=? AND resolved_at IS NULL LIMIT 1", (dossier_id,)).fetchone()
    if open_needs or open_decisions:
        return True
    if not bool(_setting_tx(conn, "sleep_mode_enabled", True)):
        _transition(conn, run["id"], "blocked_sleep", stop_reason="sleep_mode_disabled", event_type="user_blocker_resolved_sleep_blocked", payload={"reason": reason.value})
        return True
    updated = _transition(conn, run["id"], "queued", event_type="user_blocker_resolved", payload={"reason": reason.value})
    _schedule_wake_tx(conn, dossier_id, run["id"], reason.value, m.utc_now(), int(updated["state_version"]))
    return True


def lease_due_research_wakes(owner: str, *, limit: int = 20, lease_seconds: int = 60) -> list[dict]:
    now = m.utc_now(); now_s = _dt_str(now); expires = _dt_str(now + timedelta(seconds=lease_seconds)); leased=[]
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE research_wakes SET state='pending',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE state='leased' AND lease_expires_at<=?", (now_s, now_s))
        rows = conn.execute("SELECT w.*,r.status AS run_status,r.state_version,r.policy_snapshot,d.quarantined_at,d.status AS dossier_status FROM research_wakes w JOIN research_runs r ON r.id=w.run_id JOIN dossiers d ON d.id=w.dossier_id WHERE w.state='pending' AND w.due_at<=? ORDER BY w.due_at,w.id LIMIT ?", (now_s, limit)).fetchall()
        for row in rows:
            if row["run_status"] not in ("queued", "running") or row["quarantined_at"] or row["dossier_status"] == "delivered":
                conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE id=?", (now_s, row["id"]))
                if row["quarantined_at"] and row["run_status"] != "quarantined": _transition(conn, row["run_id"], "quarantined", stop_reason="dossier_quarantined", event_type="run_quarantined", notify=True)
                continue
            policy = m.ResearchPolicy.model_validate_json(row["policy_snapshot"])
            current = conn.execute("SELECT sessions_started,cost_usd FROM research_runs WHERE id=?", (row["run_id"],)).fetchone()
            cap_reason = None
            if int(current["sessions_started"] or 0) >= policy.max_sessions: cap_reason = "session_cap_reached"
            elif float(current["cost_usd"] or 0) >= policy.max_cost_usd: cap_reason = "cost_cap_reached"
            if cap_reason:
                conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE id=?", (now_s, row["id"]))
                _transition(conn, row["run_id"], "cap_reached", stop_reason=cap_reason, event_type="run_cap_reached", payload={"reason":cap_reason}, notify=True)
                continue
            if int(row["expected_run_version"] or 0) != int(row["state_version"]):
                conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE id=?", (now_s, row["id"])); continue
            cur = conn.execute("UPDATE research_wakes SET state='leased',lease_owner=?,lease_expires_at=?,attempt_count=attempt_count+1,updated_at=? WHERE id=? AND state='pending'", (owner, expires, now_s, row["id"]))
            if cur.rowcount:
                item=dict(row); item["lease_owner"]=owner; item["lease_expires_at"]=expires; leased.append(item)
    return leased


def claim_research_wake_session(wake_id: str, owner: str) -> str:
    """Atomically validate a leased wake and create exactly one run session.

    Called by the orchestrator's session_factory only after process capacity
    has been accepted. Pause/restart/version changes therefore win cleanly and
    no capacity retry can consume a session from the run budget.
    """
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT w.*,r.status AS run_status,r.state_version,r.policy_snapshot,r.sessions_started,r.cost_usd,"
            "d.status AS dossier_status,d.quarantined_at FROM research_wakes w "
            "JOIN research_runs r ON r.id=w.run_id JOIN dossiers d ON d.id=w.dossier_id "
            "WHERE w.id=?", (wake_id,),
        ).fetchone()
        if row is None or row["state"] != "leased" or row["lease_owner"] != owner:
            raise ValueError("research wake lease is no longer valid")
        if row["run_status"] not in ("queued", "running") or row["dossier_status"] == "delivered" or row["quarantined_at"]:
            raise ValueError("research run is no longer launchable")
        if int(row["expected_run_version"] or 0) != int(row["state_version"]):
            raise ValueError("research wake generation is stale")
        existing = conn.execute("SELECT id FROM work_sessions WHERE dossier_id=? AND ended_at IS NULL", (row["dossier_id"],)).fetchone()
        if existing:
            raise ValueError("work session already active")
        policy = m.ResearchPolicy.model_validate_json(row["policy_snapshot"])
        if int(row["sessions_started"] or 0) >= policy.max_sessions or float(row["cost_usd"] or 0) >= policy.max_cost_usd:
            raise ValueError("research run cap reached")
        session_id = m.new_id("ws")
        try:
            conn.execute(
                "INSERT INTO work_sessions (id,dossier_id,started_at,trigger,token_budget_used,trace_id,research_run_id,wake_id,max_turns_snapshot,launched_at,launch_state) "
                "VALUES (?,?,?,'autonomous',0,?,?,?,?,?,'launched')",
                (session_id, row["dossier_id"], now_s, uuid.uuid4().hex, row["run_id"], wake_id, policy.max_turns_per_session, now_s),
            )
        except sqlite3.IntegrityError as exc:
            duplicate = conn.execute("SELECT id FROM work_sessions WHERE wake_id=?", (wake_id,)).fetchone()
            if duplicate: return duplicate["id"]
            raise exc
        conn.execute("UPDATE research_wakes SET state='consumed',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?", (now_s, wake_id))
        conn.execute("UPDATE dossiers SET wake_at=NULL,wake_pending=0 WHERE id=?", (row["dossier_id"],))
        conn.execute("UPDATE research_runs SET status='running',sessions_started=sessions_started+1,state_version=state_version+1,updated_at=? WHERE id=?", (now_s, row["run_id"]))
        updated = conn.execute("SELECT * FROM research_runs WHERE id=?", (row["run_id"],)).fetchone()
        _append_event(conn, updated, "session_started", {"wake_id": wake_id}, session_id)
        return session_id


def release_research_wake(wake_id: str, owner: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE research_wakes SET state='pending',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND state='leased' AND lease_owner=?", (_dt_str(m.utc_now()), wake_id, owner))


def consume_research_wake(wake_id: str, owner: str) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE research_wakes SET state='consumed',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND state='leased' AND lease_owner=?", (_dt_str(m.utc_now()), wake_id, owner))
        if cur.rowcount:
            row = conn.execute("SELECT dossier_id FROM research_wakes WHERE id=?", (wake_id,)).fetchone()
            conn.execute("UPDATE dossiers SET wake_at=NULL,wake_pending=0 WHERE id=?", (row["dossier_id"],))
    return bool(cur.rowcount)


def mark_run_session_launched(run_id: str, session_id: str) -> None:
    with connect() as conn:
        run = conn.execute("SELECT * FROM research_runs WHERE id=?", (run_id,)).fetchone()
        if not run: return
        now_s=_dt_str(m.utc_now())
        conn.execute("UPDATE research_runs SET status='running',sessions_started=sessions_started+1,state_version=state_version+1,updated_at=? WHERE id=?", (now_s,run_id))
        updated=conn.execute("SELECT * FROM research_runs WHERE id=?",(run_id,)).fetchone(); _append_event(conn,updated,"session_started",{},session_id)


def sync_run_cost_from_session(session_id: str) -> None:
    with connect() as conn:
        session=conn.execute("SELECT research_run_id FROM work_sessions WHERE id=?",(session_id,)).fetchone()
        if not session or not session["research_run_id"]: return
        total=conn.execute("SELECT COALESCE(SUM(cost_usd),0) n FROM work_sessions WHERE research_run_id=?",(session["research_run_id"],)).fetchone()["n"]
        conn.execute("UPDATE research_runs SET cost_usd=?,updated_at=? WHERE id=?",(float(total or 0),_dt_str(m.utc_now()),session["research_run_id"]))


def transition_run_after_session(dossier_id: str, session_id: str, status: str, reason: Optional[str] = None, *, notify: bool = False) -> None:
    with connect() as conn:
        session=conn.execute("SELECT dossier_id,research_run_id FROM work_sessions WHERE id=?",(session_id,)).fetchone()
        if not session or session["dossier_id"] != dossier_id or not session["research_run_id"]: return
        run=conn.execute("SELECT * FROM research_runs WHERE id=? AND dossier_id=?",(session["research_run_id"],dossier_id)).fetchone()
        if not run: return
        _transition(conn,run["id"],status,stop_reason=reason,completion_reason=reason if status=="completed" else None,event_type=f"run_{status}",work_session_id=session_id,notify=notify)
        policy=m.ResearchPolicy.model_validate_json(run["policy_snapshot"]); enabled=status not in ("paused","cap_reached","completed","failed","quarantined","cancelled")
        conn.execute("UPDATE dossiers SET research_policy=?,research_stop_reason=?,updated_at=? WHERE id=?",(policy.model_copy(update={"autonomy_enabled":enabled}).model_dump_json(),reason,_dt_str(m.utc_now()),dossier_id))


def sync_runs_for_sleep_mode(enabled: bool) -> None:
    with connect() as conn:
        if not enabled:
            for row in conn.execute("SELECT * FROM research_runs WHERE status IN ('queued','running')").fetchall():
                _transition(conn,row["id"],"blocked_sleep",stop_reason="sleep_mode_disabled",event_type="sleep_suspended")
                conn.execute("UPDATE research_wakes SET state='cancelled',updated_at=? WHERE run_id=? AND state IN ('pending','leased')",(_dt_str(m.utc_now()),row["id"]))
        else:
            for row in conn.execute("SELECT * FROM research_runs WHERE status='blocked_sleep'").fetchall():
                updated=_transition(conn,row["id"],"queued",event_type="sleep_resumed")
                _schedule_wake_tx(conn,row["dossier_id"],row["id"],m.WakeReason.autonomous_continue.value,m.utc_now(),int(updated["state_version"]))


def get_research_evidence(run_id: str) -> dict:
    with connect() as conn:
        sources=[dict(r) for r in conn.execute("SELECT DISTINCT s.* FROM evidence_sources s JOIN evidence_observations o ON o.source_id=s.id WHERE o.run_id=? ORDER BY s.created_at",(run_id,)).fetchall()]
        observations=[dict(r) for r in conn.execute("SELECT * FROM evidence_observations WHERE run_id=? ORDER BY created_at",(run_id,)).fetchall()]
        claims=[dict(r) for r in conn.execute("SELECT * FROM research_claims WHERE run_id=? ORDER BY created_at",(run_id,)).fetchall()]
        links=[dict(r) for r in conn.execute("SELECT ce.* FROM claim_evidence ce JOIN research_claims c ON c.id=ce.claim_id WHERE c.run_id=? ORDER BY ce.created_at",(run_id,)).fetchall()]
    return {"run_id":run_id,"sources":sources,"observations":observations,"claims":claims,"claim_evidence":links}


def list_notifications(*, unread_only: bool = True) -> list[dict]:
    with connect() as conn:
        rows=conn.execute(f"SELECT * FROM notifications {'WHERE is_read=0' if unread_only else ''} ORDER BY created_at DESC").fetchall()
    return [{**dict(r),"payload":json.loads(r["payload"] or "{}"),"is_read":bool(r["is_read"])} for r in rows]


def mark_notification_read(notification_id: str) -> bool:
    with connect() as conn: cur=conn.execute("UPDATE notifications SET is_read=1 WHERE id=?",(notification_id,))
    return bool(cur.rowcount)


def get_research_progress(dossier_id: str, run_id: Optional[str] = None) -> Optional[m.ResearchProgress]:
    with connect() as conn:
        dossier=conn.execute("SELECT * FROM dossiers WHERE id=?",(dossier_id,)).fetchone()
        if dossier is None: return None
        active_run=_active_run_row(conn,dossier_id)
        if run_id is not None:
            run=conn.execute("SELECT * FROM research_runs WHERE id=? AND dossier_id=?",(run_id,dossier_id)).fetchone()
            if run is None: return None
        else:
            run=active_run or conn.execute("SELECT * FROM research_runs WHERE dossier_id=? ORDER BY started_at DESC LIMIT 1",(dossier_id,)).fetchone()
        active_for_view = active_run if active_run and run and active_run["id"] == run["id"] else None
        if run:
            policy=m.ResearchPolicy.model_validate_json(run["policy_snapshot"]); started_at=_dt(run["started_at"]); stop_reason=run["stop_reason"]
            sessions_used=int(run["sessions_started"] or 0); cost_usd=float(run["cost_usd"] or 0); run_id=run["id"]; run_version=int(run["state_version"])
        else:
            policy=m.ResearchPolicy.model_validate_json(dossier["research_policy"]) if dossier["research_policy"] else m.ResearchPolicy(); started_at=_dt(_row_get(dossier,"research_started_at")); stop_reason=_row_get(dossier,"research_stop_reason")
            sessions_used=0; cost_usd=0.0; run_id=None; run_version=None
        citations=set();domains=set();primary=set();linked=set();limited=set();contradictory=set(); source_count=0
        if run_id:
            evidence_rows=conn.execute(
                "SELECT s.id,s.canonical_url,s.domain,s.model_source_type,s.authority_status,o.limitations "
                "FROM evidence_sources s JOIN evidence_observations o ON o.source_id=s.id "
                "WHERE o.run_id=? AND o.provenance IN ('cited','consulted','user_provided')",
                (run_id,),
            ).fetchall()
            source_count=len(evidence_rows)
            for row in evidence_rows:
                citations.add(row["id"])
                if row["domain"]: domains.add(row["domain"].casefold().removeprefix("www."))
                # This is source qualification, not truth verification. A
                # model-declared primary source counts only when a deterministic
                # official-domain classifier independently qualified it.
                if row["model_source_type"]=="primary" and row["authority_status"]=="government_domain": primary.add(row["id"])
                if row["limitations"]: limited.add(row["id"])
            linked={r["source_id"] for r in conn.execute(
                "SELECT DISTINCT o.source_id FROM evidence_observations o JOIN claim_evidence ce ON ce.observation_id=o.id "
                "JOIN research_claims c ON c.id=ce.claim_id WHERE o.run_id=? AND o.provenance IN ('cited','consulted','user_provided') AND c.section_id IS NOT NULL",
                (run_id,),
            ).fetchall()}
            contradictory={r["source_id"] for r in conn.execute(
                "SELECT DISTINCT o.source_id FROM evidence_observations o JOIN claim_evidence ce ON ce.observation_id=o.id "
                "WHERE o.run_id=? AND o.provenance IN ('cited','consulted','user_provided') AND ce.relation IN ('contradicts','refutes')", (run_id,),
            ).fetchall()}
        else:
            # Explicit compatibility fallback for dossiers that have not yet
            # entered the versioned-run lifecycle. These lifetime/model-claimed
            # metrics never satisfy an active run's completion gate.
            source_rows=conn.execute("SELECT payload FROM investigation_log WHERE dossier_id=? AND entry_type='source_consulted' ORDER BY created_at",(dossier_id,)).fetchall(); source_count=len(source_rows)
            for row in source_rows:
                try: payload=json.loads(row["payload"] or "{}")
                except (TypeError,json.JSONDecodeError): payload={}
                citation=_normalise_citation(str(payload.get("citation") or ""))
                if not citation: continue
                citations.add(citation); domain=(urlsplit(citation).hostname or "").casefold().removeprefix("www.")
                if domain: domains.add(domain)
                if payload.get("supports_section_ids") or payload.get("contradicts_section_ids"): linked.add(citation)
                if payload.get("limitations"): limited.add(citation)
                if payload.get("contradicts_section_ids"): contradictory.add(citation)
        plan=conn.execute("SELECT COUNT(*) total,SUM(status='completed') completed,SUM(status='abandoned') abandoned FROM plan_items WHERE dossier_id=?",(dossier_id,)).fetchone()
        open_needs=int(conn.execute("SELECT COUNT(*) n FROM needs_input WHERE dossier_id=? AND answered_at IS NULL",(dossier_id,)).fetchone()["n"]); open_dps=int(conn.execute("SELECT COUNT(*) n FROM decision_points WHERE dossier_id=? AND resolved_at IS NULL",(dossier_id,)).fetchone()["n"])
        active_row=conn.execute("SELECT id FROM work_sessions WHERE dossier_id=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",(dossier_id,)).fetchone()
        wake=conn.execute("SELECT due_at FROM research_wakes WHERE run_id=? AND state IN ('pending','leased') ORDER BY due_at LIMIT 1",(active_for_view["id"],)).fetchone() if active_for_view else None
        total=int(plan["total"] or 0);completed=int(plan["completed"] or 0);abandoned=int(plan["abandoned"] or 0)
        material_total=material_supported=0
        if run_id:
            material=conn.execute(
                "SELECT COUNT(*) total,SUM(CASE WHEN EXISTS (SELECT 1 FROM claim_evidence ce JOIN evidence_observations eo ON eo.id=ce.observation_id WHERE ce.claim_id=c.id AND ce.relation IN ('supports','context') AND eo.run_id=? AND eo.provenance IN ('cited','consulted','user_provided')) THEN 1 ELSE 0 END) supported "
                "FROM research_claims c WHERE c.run_id=? AND c.status='active' AND c.materiality='material'",
                (run_id,run_id),
            ).fetchone()
            material_total=int(material["total"] or 0); material_supported=int(material["supported"] or 0)
        checks=[m.ResearchCompletionCheck(key="sources",label="Qualified sources",passed=len(citations)>=policy.target_source_count,current=len(citations),target=policy.target_source_count),m.ResearchCompletionCheck(key="primary_sources",label="Qualified primary sources",passed=len(primary)>=policy.min_primary_sources,current=len(primary),target=policy.min_primary_sources,detail="Official-domain qualification; not truth verification"),m.ResearchCompletionCheck(key="material_claims",label="Material claims have evidence",passed=material_total>0 and material_supported==material_total,current=material_supported,target=material_total,detail="Coverage check only; not truth verification"),m.ResearchCompletionCheck(key="plan",label="Research plan completed",passed=total>0 and completed==total,current=completed,target=total,detail=f"{abandoned} abandoned" if abandoned else ""),m.ResearchCompletionCheck(key="blockers",label="No open user blockers",passed=(open_needs+open_dps)==0,current=open_needs+open_dps,target=0)]
        report=m.ResearchCompletionReport(ready=all(c.passed for c in checks),checks=checks,completed_plan_items=completed,abandoned_plan_items=abandoned,total_plan_items=total)
        if dossier["status"]=="delivered": status="delivered"
        elif not run: status="manual"
        else: status=run["status"]
        if not run: actions=["start"] if dossier["status"]!="delivered" and not _row_get(dossier,"quarantined_at") else []
        elif run["status"] in ("queued","running","waiting_for_user"): actions=["pause","restart"]
        elif run["status"] in ("paused","cap_reached","blocked_sleep","pause_requested"): actions=["resume","restart"]
        else: actions=["restart"]
        display_policy=policy.model_copy(update={"autonomy_enabled": bool(active_for_view and run["status"] in ("queued","running","waiting_for_user","blocked_sleep"))})
        return m.ResearchProgress(dossier_id=dossier_id,run_id=run_id,status=status,policy=display_policy,started_at=started_at,stop_reason=stop_reason,sessions_used=sessions_used,cost_usd=cost_usd,source_count=source_count,unique_source_count=len(citations),primary_source_count=len(primary),unique_domains=len(domains),sources_linked_to_sections=len(linked),sources_with_limitations=len(limited),contradictory_sources=len(contradictory),completed_plan_items=completed,total_plan_items=total,open_needs_input_count=open_needs,open_decision_point_count=open_dps,active_run_id=active_for_view["id"] if active_for_view else None,run_version=run_version,allowed_actions=actions,active_session_id=active_row["id"] if active_row and (not run_id or conn.execute("SELECT research_run_id FROM work_sessions WHERE id=?",(active_row["id"],)).fetchone()["research_run_id"]==run_id) else None,next_wake_at=_dt(wake["due_at"]) if wake else None,completion_report=report)
