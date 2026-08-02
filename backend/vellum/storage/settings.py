"""Settings + idempotency: small key-value tables with parallel surfaces.

Both tables have a tiny CRUD surface (``get_X`` / ``set_X`` /
``record_X``). Folding them into a single module removes two
near-empty files from the storage/ directory without changing any
imports outside the package.
"""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
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
                   input_hash, result_json, is_error, created_at
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
    }


def record_tool_invocation(
    tool_use_id: str,
    dossier_id: str,
    tool_name: str,
    input_hash: str,
    result_json: str,
    is_error: bool = False,
    work_session_id: Optional[str] = None,
) -> None:
    """Record a completed tool dispatch. INSERT OR IGNORE."""
    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO tool_invocations
              (tool_use_id, dossier_id, work_session_id, tool_name,
               input_hash, result_json, is_error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_use_id,
                dossier_id,
                work_session_id,
                tool_name,
                input_hash,
                result_json,
                1 if is_error else 0,
                _dt_str(m.utc_now()),
            ),
        )
