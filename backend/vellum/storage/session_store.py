"""WorkSession CRUD, usage tracking, and session summaries."""
from __future__ import annotations

import json
import sqlite3
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
    *,
    research_run_id: Optional[str] = None,
    wake_id: Optional[str] = None,
    max_turns_snapshot: Optional[int] = None,
) -> m.WorkSession:
    now = m.utc_now()
    trace_id = uuid.uuid4().hex
    implicit_run = False
    if research_run_id is None and trigger is m.WorkSessionTrigger.autonomous:
        from .research import get_active_research_run
        active_run = get_active_research_run(dossier_id)
        if active_run is not None:
            research_run_id = active_run.id
            max_turns_snapshot = active_run.policy_snapshot.max_turns_per_session
            implicit_run = True
    session = m.WorkSession(
        id=m.new_id("ws"),
        dossier_id=dossier_id,
        started_at=now,
        trigger=trigger,
        trace_id=trace_id,
        research_run_id=research_run_id,
        wake_id=wake_id,
        max_turns_snapshot=max_turns_snapshot,
        launched_at=now if implicit_run else None,
        launch_state="launched" if implicit_run else "created",
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
                INSERT INTO work_sessions
                    (id, dossier_id, started_at, trigger, token_budget_used, trace_id,
                     research_run_id, wake_id, max_turns_snapshot, launched_at, launch_state)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (session.id, dossier_id, _dt_str(now), trigger.value, trace_id,
                 research_run_id, wake_id, max_turns_snapshot,
                 _dt_str(now) if implicit_run else None,
                 "launched" if implicit_run else "created"),
            )
    except sqlite3.IntegrityError as exc:
        existing = get_active_work_session(dossier_id)
        if existing is not None:
            raise ActiveWorkSessionExists(existing) from exc
        raise
    if implicit_run and research_run_id:
        from .research import mark_run_session_launched
        mark_run_session_launched(research_run_id, session.id)
    return session


def mark_work_session_launched(session_id: str) -> Optional[m.WorkSession]:
    """Mark a pre-created session as owned by an accepted orchestrator task."""
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET launched_at=?,launch_state='launched' "
            "WHERE id=? AND launch_state='created'",
            (now_s, session_id),
        )
        row = conn.execute("SELECT * FROM work_sessions WHERE id=?", (session_id,)).fetchone()
    return _row_to_work_session(row) if row else None


def increment_work_session_turns(session_id: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE work_sessions SET turns_started=turns_started+1 WHERE id=?", (session_id,))


def reserve_model_call(session_id: str) -> dict:
    """Atomically reserve one main/sub model attempt under session/run caps."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT ws.*,rr.status AS run_status,rr.sessions_started,rr.cost_usd AS run_cost,"
            "rr.policy_snapshot,rr.state_version FROM work_sessions ws "
            "LEFT JOIN research_runs rr ON rr.id=ws.research_run_id WHERE ws.id=?",
            (session_id,),
        ).fetchone()
        if row is None or row["ended_at"] is not None:
            return {"allowed": False, "reason": "session_inactive"}
        limit = row["max_turns_snapshot"]
        if row["research_run_id"]:
            policy = m.ResearchPolicy.model_validate_json(row["policy_snapshot"])
            limit = int(limit or policy.max_turns_per_session)
            if row["run_status"] not in ("running", "queued"):
                return {"allowed": False, "reason": row["run_status"] or "run_inactive"}
            if int(row["sessions_started"] or 0) > policy.max_sessions:
                return {"allowed": False, "reason": "session_cap_reached"}
            if float(row["run_cost"] or 0) >= policy.max_cost_usd:
                from .research import _transition
                updated = _transition(
                    conn, row["research_run_id"], "cap_reached",
                    stop_reason="cost_cap_reached", event_type="run_cap_reached",
                    payload={"reason": "cost_cap_reached"}, notify=True,
                )
                conn.execute(
                    "UPDATE research_wakes SET state='cancelled',updated_at=? "
                    "WHERE run_id=? AND state IN ('pending','leased')",
                    (_dt_str(m.utc_now()), row["research_run_id"]),
                )
                return {"allowed": False, "reason": "cost_cap_reached"}
        if limit is not None and int(row["turns_started"] or 0) >= int(limit):
            return {"allowed": False, "reason": "turn_cap_reached"}
        conn.execute("UPDATE work_sessions SET turns_started=turns_started+1 WHERE id=?", (session_id,))
        return {"allowed": True, "reason": None, "turn_number": int(row["turns_started"] or 0) + 1}


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
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> None:
    """Accumulate per-turn usage on a work_session row."""
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?,
                   cache_creation_input_tokens = cache_creation_input_tokens + ?,
                   cache_read_input_tokens = cache_read_input_tokens + ?,
                   cost_usd = cost_usd + ?,
                   token_budget_used = token_budget_used + ?
             WHERE id = ?
            """,
            (
                int(input_tokens),
                int(output_tokens),
                int(cache_creation_input_tokens),
                int(cache_read_input_tokens),
                float(cost_usd),
                int(input_tokens + output_tokens),
                session_id,
            ),
        )
        conn.execute(
            "UPDATE research_runs SET cost_usd=cost_usd+?,updated_at=? "
            "WHERE id=(SELECT research_run_id FROM work_sessions WHERE id=?)",
            (float(cost_usd), now_s, session_id),
        )


def record_turn_usage(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> None:
    """Accumulate per-turn usage on both the work_session row and the daily
    budget rollup in a single transaction so they never diverge."""
    day_key = m.utc_now().strftime("%Y-%m-%d")
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            UPDATE work_sessions
               SET input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?,
                   cache_creation_input_tokens = cache_creation_input_tokens + ?,
                   cache_read_input_tokens = cache_read_input_tokens + ?,
                   cost_usd = cost_usd + ?,
                   token_budget_used = token_budget_used + ?
             WHERE id = ?
            """,
            (
                int(input_tokens),
                int(output_tokens),
                int(cache_creation_input_tokens),
                int(cache_read_input_tokens),
                float(cost_usd),
                int(input_tokens + output_tokens),
                session_id,
            ),
        )
        conn.execute(
            "UPDATE research_runs SET cost_usd=cost_usd+?,updated_at=? "
            "WHERE id=(SELECT research_run_id FROM work_sessions WHERE id=?)",
            (float(cost_usd), now_s, session_id),
        )
        conn.execute(
            """
            INSERT INTO budget_accounting (day, spent_usd, input_tokens, output_tokens,
                cache_creation_input_tokens, cache_read_input_tokens, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                spent_usd = spent_usd + excluded.spent_usd,
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                cache_creation_input_tokens = cache_creation_input_tokens + excluded.cache_creation_input_tokens,
                cache_read_input_tokens = cache_read_input_tokens + excluded.cache_read_input_tokens,
                updated_at = excluded.updated_at
            """,
            (
                day_key,
                float(cost_usd),
                int(input_tokens),
                int(output_tokens),
                int(cache_creation_input_tokens),
                int(cache_read_input_tokens),
                now_s,
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
                   end_reason = ?,
                   launch_state = 'ended'
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
