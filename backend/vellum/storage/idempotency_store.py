"""Tool invocation idempotency tracking."""
from __future__ import annotations

from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt_str


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
