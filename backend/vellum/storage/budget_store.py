"""Budget accounting and day-rollup queries."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt, _dt_str


def _utc_day_str(dt: Optional[datetime] = None) -> str:
    dt = dt or m.utc_now()
    return dt.strftime("%Y-%m-%d")


def record_budget_usage(
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    day: Optional[str] = None,
) -> None:
    """Roll per-turn usage into the day's global budget row. UPSERT."""
    day_key = day or _utc_day_str()
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO budget_accounting (day, spent_usd, input_tokens, output_tokens, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                spent_usd = spent_usd + excluded.spent_usd,
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens,
                updated_at = excluded.updated_at
            """,
            (day_key, float(cost_usd), int(input_tokens), int(output_tokens), now_s),
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
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]
