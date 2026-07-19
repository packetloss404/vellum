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
    """Return dossiers the scheduler should pick up on its next tick.

    Quarantined dossiers are excluded — they only run again via an explicit
    user resume (which clears the quarantine).
    """
    now_s = _dt_str(now or m.utc_now())
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id AS dossier_id, wake_at, wake_pending, wake_reason
              FROM dossiers
             WHERE status != 'delivered'
               AND quarantined_at IS NULL
               AND (
                     wake_pending = 1
                     OR (wake_at IS NOT NULL AND wake_at <= ?)
                   )
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


def increment_consecutive_error_count(dossier_id: str) -> int:
    """Bump the failed-session counter and return the new value.

    Read-back happens in the same connection so two racing writers can't
    both observe the same pre-increment value.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET consecutive_error_count = consecutive_error_count + 1 "
            "WHERE id = ?",
            (dossier_id,),
        )
        row = conn.execute(
            "SELECT consecutive_error_count FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
    return int(row["consecutive_error_count"]) if row is not None else 0


def reset_consecutive_error_count(dossier_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET consecutive_error_count = 0 WHERE id = ?",
            (dossier_id,),
        )


def set_dossier_quarantined(dossier_id: str, reason: str) -> None:
    """Quarantine: stop all auto-wakes until the user explicitly resumes.

    Clears wake_at/wake_pending in the same statement so a wake set before
    the quarantine decision can't leak through a scheduler tick.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET quarantined_at = ?, quarantine_reason = ?, "
            "wake_at = NULL, wake_pending = 0 WHERE id = ?",
            (_dt_str(m.utc_now()), reason, dossier_id),
        )


def clear_dossier_quarantine(dossier_id: str) -> None:
    """Lift the quarantine and reset the failure counter (user said retry)."""
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET quarantined_at = NULL, quarantine_reason = NULL, "
            "consecutive_error_count = 0 WHERE id = ?",
            (dossier_id,),
        )


def get_dossier_error_state(dossier_id: str) -> Optional[dict]:
    """Read the self-heal fields for a dossier. Returns None if not found."""
    with connect() as conn:
        row = conn.execute(
            "SELECT consecutive_error_count, quarantined_at, quarantine_reason "
            "FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "consecutive_error_count": int(row["consecutive_error_count"]),
        "quarantined_at": row["quarantined_at"],
        "quarantine_reason": row["quarantine_reason"],
    }


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
