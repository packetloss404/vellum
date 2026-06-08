"""AgentTurn CRUD and cost aggregation."""
from __future__ import annotations

from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _row_to_agent_turn,
)


def create_agent_turn(data: m.AgentTurnCreate) -> m.AgentTurn:
    now = m.utc_now()
    turn = m.AgentTurn(
        id=m.new_id("agt"),
        dossier_id=data.dossier_id,
        work_session_id=data.work_session_id,
        sub_investigation_id=data.sub_investigation_id,
        trace_id=data.trace_id,
        turn_index=data.turn_index,
        model=data.model,
        input_tokens=data.input_tokens,
        output_tokens=data.output_tokens,
        cache_creation_input_tokens=data.cache_creation_input_tokens,
        cache_read_input_tokens=data.cache_read_input_tokens,
        cost_usd=data.cost_usd,
        duration_ms=data.duration_ms,
        tool_calls_count=data.tool_calls_count,
        stop_reason=data.stop_reason,
        notes=data.notes,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_turns (
                id, dossier_id, work_session_id, sub_investigation_id,
                trace_id, turn_index, model,
                input_tokens, output_tokens,
                cache_creation_input_tokens, cache_read_input_tokens,
                cost_usd, duration_ms, tool_calls_count,
                stop_reason, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.id,
                turn.dossier_id,
                turn.work_session_id,
                turn.sub_investigation_id,
                turn.trace_id,
                turn.turn_index,
                turn.model,
                turn.input_tokens,
                turn.output_tokens,
                turn.cache_creation_input_tokens,
                turn.cache_read_input_tokens,
                turn.cost_usd,
                turn.duration_ms,
                turn.tool_calls_count,
                turn.stop_reason,
                turn.notes,
                _dt_str(now),
            ),
        )
    return turn


def list_agent_turns_for_dossier(
    dossier_id: str, limit: int = 100
) -> list[m.AgentTurn]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_turns WHERE dossier_id = ? ORDER BY created_at DESC LIMIT ?",
            (dossier_id, limit),
        ).fetchall()
    return [_row_to_agent_turn(r) for r in rows]


def list_agent_turns_for_session(
    work_session_id: str,
) -> list[m.AgentTurn]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_turns WHERE work_session_id = ? ORDER BY turn_index",
            (work_session_id,),
        ).fetchall()
    return [_row_to_agent_turn(r) for r in rows]


def list_agent_turns_for_trace(trace_id: str, dossier_id: Optional[str] = None) -> list[m.AgentTurn]:
    with connect() as conn:
        if dossier_id is not None:
            rows = conn.execute(
                "SELECT * FROM agent_turns WHERE trace_id = ? AND dossier_id = ? ORDER BY created_at",
                (trace_id, dossier_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_turns WHERE trace_id = ? ORDER BY created_at",
                (trace_id,),
            ).fetchall()
    return [_row_to_agent_turn(r) for r in rows]


def get_turn_cost_summary_for_dossier(dossier_id: str) -> dict:
    """Aggregate cost/tokens by model for a dossier."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT model,
                   COUNT(*) AS turn_count,
                   SUM(input_tokens) AS total_input_tokens,
                   SUM(output_tokens) AS total_output_tokens,
                   SUM(cache_creation_input_tokens) AS total_cache_creation_input_tokens,
                   SUM(cache_read_input_tokens) AS total_cache_read_input_tokens,
                   SUM(cost_usd) AS total_cost_usd,
                   SUM(duration_ms) AS total_duration_ms,
                   SUM(tool_calls_count) AS total_tool_calls
              FROM agent_turns
             WHERE dossier_id = ?
             GROUP BY model
             ORDER BY total_cost_usd DESC
            """,
            (dossier_id,),
        ).fetchall()
    return [
        {
            "model": r["model"],
            "turn_count": r["turn_count"],
            "total_input_tokens": r["total_input_tokens"] or 0,
            "total_output_tokens": r["total_output_tokens"] or 0,
            "total_cache_creation_input_tokens": r["total_cache_creation_input_tokens"] or 0,
            "total_cache_read_input_tokens": r["total_cache_read_input_tokens"] or 0,
            "total_cost_usd": round(r["total_cost_usd"] or 0.0, 6),
            "total_duration_ms": r["total_duration_ms"] or 0,
            "total_tool_calls": r["total_tool_calls"] or 0,
        }
        for r in rows
    ]
