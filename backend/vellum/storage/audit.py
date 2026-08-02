"""Audit/cost: agent_turns and budget_accounting.

These two append-only time-series tables share a pattern — ``record_X``
appends a row, ``list_X`` queries it, ``get_summary_X`` aggregates. Both
are write-heavy and idempotent under reasonable concurrency assumptions.
The merge keeps them together because they sit at the same logical
layer (cost observability + per-turn telemetry) and have small,
parallel surface areas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt, _dt_str, _row_get, _row_to_agent_turn


# ---------- AgentTurn CRUD (formerly turn_store.py) ----------


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


def list_agent_turns_for_trace(
    trace_id: str,
    dossier_id: Optional[str] = None,
) -> list[m.AgentTurn]:
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


# ---------- Budget accounting (formerly budget_store.py) ----------


def _utc_day_str(dt: Optional[datetime] = None) -> str:
    dt = dt or m.utc_now()
    return dt.strftime("%Y-%m-%d")


def record_budget_usage(
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    day: Optional[str] = None,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> None:
    """Roll per-turn usage into the day's global budget row. UPSERT."""
    day_key = day or _utc_day_str()
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
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


def get_budget_today() -> m.BudgetRollup:
    """Return today's rollup, synthesizing a zero row if no spend yet."""
    day_key = _utc_day_str()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM budget_accounting WHERE day = ?", (day_key,)
        ).fetchone()
    if row is None:
        return m.BudgetRollup(day=day_key, updated_at=m.utc_now())
    return m.BudgetRollup(
        day=row["day"],
        spent_usd=float(row["spent_usd"]),
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        cache_creation_input_tokens=int(_row_get(row, "cache_creation_input_tokens") or 0),
        cache_read_input_tokens=int(_row_get(row, "cache_read_input_tokens") or 0),
        updated_at=_dt(row["updated_at"]),
    )


def list_budget_range(start_day: str, end_day: str) -> list[m.BudgetRollup]:
    """Inclusive range, ordered by day ascending."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM budget_accounting WHERE day >= ? AND day <= ? ORDER BY day",
            (start_day, end_day),
        ).fetchall()
    return [
        m.BudgetRollup(
            day=r["day"],
            spent_usd=float(r["spent_usd"]),
            input_tokens=int(r["input_tokens"]),
            output_tokens=int(r["output_tokens"]),
            cache_creation_input_tokens=int(_row_get(r, "cache_creation_input_tokens") or 0),
            cache_read_input_tokens=int(_row_get(r, "cache_read_input_tokens") or 0),
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]
