"""WorkSession CRUD, usage tracking, and session summaries."""
from __future__ import annotations

import json
import uuid
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt,
    _dt_str,
    _json_list,
    _row_get,
    _row_to_work_session,
    _row_to_session_summary,
    ActiveWorkSessionExists,
)


def start_work_session(
    dossier_id: str,
    trigger: m.WorkSessionTrigger = m.WorkSessionTrigger.manual,
) -> m.WorkSession:
    now = m.utc_now()
    trace_id = uuid.uuid4().hex
    session = m.WorkSession(
        id=m.new_id("ws"),
        dossier_id=dossier_id,
        started_at=now,
        trigger=trigger,
        trace_id=trace_id,
    )
    try:
        with connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM work_sessions
                 WHERE dossier_id = ? AND ended_at IS NULL
                 ORDER BY started_at DESC LIMIT 1
                """,
                (dossier_id,),
            ).fetchone()
            if existing is not None:
                raise ActiveWorkSessionExists(_row_to_work_session(existing))
            conn.execute(
                """
                INSERT INTO work_sessions (id, dossier_id, started_at, trigger, token_budget_used, trace_id)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (session.id, dossier_id, _dt_str(now), trigger.value, trace_id),
            )
    except Exception as exc:
        existing = get_active_work_session(dossier_id)
        if existing is not None:
            raise ActiveWorkSessionExists(existing) from exc
        raise
    return session


def get_work_session(session_id: str) -> Optional[m.WorkSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_work_session(row) if row else None


def end_work_session(session_id: str) -> Optional[m.WorkSession]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (now_s, session_id),
        )
        row = conn.execute("SELECT * FROM work_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_work_session(row) if row else None


def get_active_work_session(dossier_id: str) -> Optional[m.WorkSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
    return _row_to_work_session(row) if row else None


def list_work_sessions(dossier_id: str) -> list[m.WorkSession]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? ORDER BY started_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_work_session(r) for r in rows]


def increment_session_tokens(session_id: str, tokens: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET token_budget_used = token_budget_used + ? WHERE id = ?",
            (tokens, session_id),
        )


def record_session_usage(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Accumulate per-turn usage on a work_session row."""
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?,
                   cost_usd = cost_usd + ?,
                   token_budget_used = token_budget_used + ?
             WHERE id = ?
            """,
            (
                int(input_tokens),
                int(output_tokens),
                float(cost_usd),
                int(input_tokens + output_tokens),
                session_id,
            ),
        )


def end_work_session_with_reason(
    session_id: str,
    reason: m.WorkSessionEndReason,
) -> Optional[m.WorkSession]:
    """Close a session and stamp end_reason atomically."""
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET ended_at = ?,
                   end_reason = ?
             WHERE id = ? AND ended_at IS NULL
            """,
            (now_s, reason.value, session_id),
        )
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    return _row_to_work_session(row) if row else None


def end_orphan_session_as_crashed(session_id: str) -> Optional[m.WorkSession]:
    """Used by lifecycle reconcile to close a process-crash leftover."""
    return end_work_session_with_reason(session_id, m.WorkSessionEndReason.crashed)


# ---------- Session summaries ----------


def save_session_summary(data: m.SessionSummary) -> m.SessionSummary:
    """UPSERT on session_id."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO session_summaries
                (session_id, dossier_id, summary, confirmed, ruled_out,
                 blocked_on, questions_advanced, recommended_next_action,
                 cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                summary = CASE
                    WHEN excluded.summary != '' THEN excluded.summary
                    ELSE session_summaries.summary
                END,
                confirmed = CASE
                    WHEN excluded.confirmed != '[]' THEN excluded.confirmed
                    ELSE session_summaries.confirmed
                END,
                ruled_out = CASE
                    WHEN excluded.ruled_out != '[]' THEN excluded.ruled_out
                    ELSE session_summaries.ruled_out
                END,
                blocked_on = CASE
                    WHEN excluded.blocked_on != '[]' THEN excluded.blocked_on
                    ELSE session_summaries.blocked_on
                END,
                questions_advanced = CASE
                    WHEN excluded.questions_advanced != '[]' THEN excluded.questions_advanced
                    ELSE session_summaries.questions_advanced
                END,
                recommended_next_action = COALESCE(
                    excluded.recommended_next_action,
                    session_summaries.recommended_next_action
                ),
                cost_usd = excluded.cost_usd
            """,
            (
                data.session_id,
                data.dossier_id,
                data.summary,
                json.dumps(data.confirmed),
                json.dumps(data.ruled_out),
                json.dumps(data.blocked_on),
                json.dumps(data.questions_advanced),
                data.recommended_next_action,
                float(data.cost_usd),
                _dt_str(data.created_at),
            ),
        )
    return data


def get_session_summary(session_id: str) -> Optional[m.SessionSummary]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_session_summary(row) if row else None


def list_session_summaries_for_dossier(dossier_id: str) -> list[m.SessionSummary]:
    """All session summaries for a dossier, ordered by created_at ascending."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM session_summaries WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_session_summary(r) for r in rows]
