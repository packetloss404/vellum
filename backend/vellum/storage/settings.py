"""Settings + idempotency: small key-value tables with parallel surfaces.

Both tables have a tiny CRUD surface (``get_X`` / ``set_X`` /
``record_X``). Folding them into a single module removes two
near-empty files from the storage/ directory without changing any
imports outside the package.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from .. import models as m
from ..db import connect, unit_of_work
from ._helpers import _dt, _dt_str


# ---------- Settings (formerly settings_store.py) ----------


def get_setting(key: str, default=None):
    """Return the JSON-decoded value for `key`, or `default` if not set."""
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return default
    return json.loads(row["value_json"])


def set_setting(key: str, value) -> m.Setting:
    """UPSERT a setting. Value is JSON-encoded. Returns the stored row."""
    now_s = _dt_str(m.utc_now())
    blob = json.dumps(value)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, blob, now_s),
        )
    if key == "sleep_mode_enabled":
        # Import lazily to keep the storage package import graph acyclic.
        from .research import sync_runs_for_sleep_mode
        sync_runs_for_sleep_mode(bool(value))
    return m.Setting(key=key, value=value, updated_at=m.utc_now())


def list_settings() -> list[m.Setting]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json, updated_at FROM settings ORDER BY key"
        ).fetchall()
    return [
        m.Setting(
            key=r["key"],
            value=json.loads(r["value_json"]),
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]


def seed_default_settings(defaults: dict) -> None:
    """Insert missing defaults only — never overwrite an edited value."""
    with connect() as conn:
        for key, value in defaults.items():
            row = conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                continue
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), _dt_str(m.utc_now())),
            )


# ---------- Tool invocation idempotency (formerly idempotency_store.py) ----------


def get_tool_invocation(tool_use_id: str) -> Optional[dict]:
    """Return a previously-recorded tool_result for this tool_use_id, or None."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT tool_use_id, dossier_id, work_session_id, tool_name,
                   input_hash, result_json, is_error, state, claimed_at,
                   completed_at, created_at
              FROM tool_invocations
             WHERE tool_use_id = ?
            """,
            (tool_use_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "tool_use_id": row["tool_use_id"],
        "dossier_id": row["dossier_id"],
        "work_session_id": row["work_session_id"],
        "tool_name": row["tool_name"],
        "input_hash": row["input_hash"],
        "result_json": row["result_json"],
        "is_error": bool(row["is_error"]),
        "created_at": row["created_at"],
        "state": row["state"],
        "claimed_at": row["claimed_at"],
        "completed_at": row["completed_at"],
    }


def claim_tool_invocation(
    tool_use_id: str,
    dossier_id: str,
    tool_name: str,
    input_hash: str,
    work_session_id: Optional[str] = None,
) -> dict:
    """Durably claim a tool call before its handler mutates state.

    A repeated ID with different input is rejected; it can never inherit an
    unrelated cached result. The returned state is ``claimed``, ``in_progress``
    or ``completed``. DB-only handlers can execute and complete as one logical
    unit while network/spawn handlers use this as their stable saga boundary.
    """
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM tool_invocations WHERE tool_use_id=?", (tool_use_id,)).fetchone()
        if row is not None:
            if row["input_hash"] != input_hash or row["tool_name"] != tool_name or row["dossier_id"] != dossier_id:
                raise ValueError("tool_use_id replayed with conflicting input")
            return {"state": "completed" if row["state"] == "completed" else "in_progress", "invocation": get_tool_invocation(tool_use_id)}
        conn.execute(
            "INSERT INTO tool_invocations (tool_use_id,dossier_id,work_session_id,tool_name,input_hash,result_json,is_error,state,claimed_at,created_at) VALUES (?,?,?,?,?,'null',0,'claimed',?,?)",
            (tool_use_id, dossier_id, work_session_id, tool_name, input_hash, now_s, now_s),
        )
    return {"state": "claimed", "invocation": get_tool_invocation(tool_use_id)}


def complete_tool_invocation(tool_use_id: str, input_hash: str, result_json: str,
                             is_error: bool = False) -> None:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute("SELECT input_hash,state FROM tool_invocations WHERE tool_use_id=?", (tool_use_id,)).fetchone()
        if row is None:
            raise ValueError("tool invocation was not claimed")
        if row["input_hash"] != input_hash:
            raise ValueError("tool_use_id completion input hash conflict")
        conn.execute("UPDATE tool_invocations SET result_json=?,is_error=?,state='completed',completed_at=? WHERE tool_use_id=?",
                     (result_json, 1 if is_error else 0, now_s, tool_use_id))


def execute_db_tool_invocation(
    tool_use_id: str, dossier_id: str, tool_name: str, input_hash: str,
    handler: Callable[[], object], work_session_id: Optional[str] = None,
) -> dict:
    """Execute a DB-only handler and its invocation result atomically.

    Handler storage calls reuse this transaction through ``db.connect``. A
    savepoint rolls back partial handler writes while still committing a
    deterministic error result. Network/spawn handlers must use the explicit
    claim/complete saga instead; no database transaction is held over I/O.
    """
    now_s = _dt_str(m.utc_now())
    with unit_of_work() as conn:
        row = conn.execute("SELECT * FROM tool_invocations WHERE tool_use_id=?", (tool_use_id,)).fetchone()
        if row:
            if row["input_hash"] != input_hash or row["tool_name"] != tool_name or row["dossier_id"] != dossier_id:
                raise ValueError("tool_use_id replayed with conflicting input")
            return {"state": row["state"], "result_json": row["result_json"], "is_error": bool(row["is_error"])}
        conn.execute("INSERT INTO tool_invocations (tool_use_id,dossier_id,work_session_id,tool_name,input_hash,result_json,is_error,state,claimed_at,created_at) VALUES (?,?,?,?,?,'null',0,'claimed',?,?)",
                     (tool_use_id,dossier_id,work_session_id,tool_name,input_hash,now_s,now_s))
        conn.execute("SAVEPOINT tool_handler")
        try:
            result = handler()
        except Exception as exc:  # commit a replay-safe error, not partial writes
            conn.execute("ROLLBACK TO tool_handler"); conn.execute("RELEASE tool_handler")
            result_json = f"{type(exc).__name__}: {exc}"
            conn.execute("UPDATE tool_invocations SET result_json=?,is_error=1,state='completed',completed_at=? WHERE tool_use_id=?",
                         (result_json,_dt_str(m.utc_now()),tool_use_id))
            return {"state":"completed","result_json":result_json,"is_error":True}
        conn.execute("RELEASE tool_handler")
        result_json = json.dumps(result, default=str)
        conn.execute("UPDATE tool_invocations SET result_json=?,is_error=0,state='completed',completed_at=? WHERE tool_use_id=?",
                     (result_json,_dt_str(m.utc_now()),tool_use_id))
        return {"state":"completed","result_json":result_json,"is_error":False}


def record_tool_invocation(
    tool_use_id: str,
    dossier_id: str,
    tool_name: str,
    input_hash: str,
    result_json: str,
    is_error: bool = False,
    work_session_id: Optional[str] = None,
) -> None:
    """Backward-compatible claim+complete wrapper with conflict protection."""
    claim_tool_invocation(tool_use_id, dossier_id, tool_name, input_hash, work_session_id)
    complete_tool_invocation(tool_use_id, input_hash, result_json, is_error)
