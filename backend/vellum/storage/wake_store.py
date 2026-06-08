"""Sleep-mode wake state queries and mutations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt_str


def set_dossier_wake_at(
    dossier_id: str,
    wake_at: datetime,
    reason: m.WakeReason,
) -> None:
    """Agent-initiated: schedule a future wake via schedule_wake tool."""
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_at = ?, wake_reason = ? WHERE id = ?",
            (_dt_str(wake_at), reason.value, dossier_id),
        )


def mark_wake_pending(dossier_id: str, reason: m.WakeReason) -> None:
    """Signal that this dossier needs a scheduler pick-up on the next tick."""
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_pending = 1, wake_reason = ? WHERE id = ?",
            (reason.value, dossier_id),
        )


def clear_dossier_wake(dossier_id: str) -> None:
    """Clear both wake_at and wake_pending."""
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET wake_at = NULL, wake_pending = 0 WHERE id = ?",
            (dossier_id,),
        )


def list_dossiers_ready_to_wake(now: Optional[datetime] = None) -> list[dict]:
    """Return dossiers the scheduler should pick up on its next tick."""
    now_s = _dt_str(now or m.utc_now())
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id AS dossier_id, wake_at, wake_pending, wake_reason
              FROM dossiers
             WHERE wake_pending = 1
                OR (wake_at IS NOT NULL AND wake_at <= ?)
             ORDER BY COALESCE(wake_at, ''), id
            """,
            (now_s,),
        ).fetchall()
    return [
        {
            "dossier_id": r["dossier_id"],
            "wake_at": r["wake_at"],
            "wake_pending": bool(r["wake_pending"]),
            "wake_reason": r["wake_reason"],
        }
        for r in rows
    ]


def get_dossier_wake_state(dossier_id: str) -> Optional[dict]:
    """Read the current wake fields for a dossier. Returns None if not found."""
    with connect() as conn:
        row = conn.execute(
            "SELECT wake_at, wake_pending, wake_reason FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "wake_at": row["wake_at"],
        "wake_pending": bool(row["wake_pending"]),
        "wake_reason": row["wake_reason"],
    }
