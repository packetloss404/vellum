"""Dossier lifecycle: wake state, user notes, next actions.

This module merges three formerly-separate per-entity stores that share
the same conceptual surface — "things the user or the runtime stamps on
a dossier that aren't core dossier rows." All three flow through the
``_log_change`` + ``_touch_dossier`` post-write pattern, and the wake
operations write the ``dossiers`` table directly while user_notes and
next_actions touch related side tables.

The merge reduces the storage/ directory from 17 files to 13 without
changing the public surface — every function is still re-exported from
``vellum.storage`` by the same name.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _ORDER_STEP, _dt, _dt_str, _log_change, _row_to_user_note, _touch_dossier


def _row_to_next_action(row) -> m.NextAction:
    """Row → NextAction model. The priority column is REAL (SQL) to support
    midpoint reorders; we keep the storage-side view as float for honesty.
    """
    return m.NextAction(
        id=row["id"],
        dossier_id=row["dossier_id"],
        action=row["action"],
        rationale=row["rationale"],
        priority=float(row["priority"]),
        completed=bool(row["completed"]),
        completed_at=_dt(row["completed_at"]) if row["completed_at"] else None,
        created_at=_dt(row["created_at"]),
    )


# ---------- Wake / sleep-mode (formerly wake_store.py) ----------


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


def set_dossier_last_signal_kind(dossier_id: str, kind: str) -> None:
    """Persist the kind of stuck signal that last fired on this dossier.

    Mirrors the stuck_escalation_count write in agent/stuck.py: best-effort
    and asynchronous from the runtime's perspective. A write failure must
    not break signal emission.
    """
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET last_signal_kind = ? WHERE id = ?",
            (kind, dossier_id),
        )


def get_dossier_last_signal_kind(dossier_id: str) -> Optional[str]:
    """Read the last_signal_kind column. Returns None if dossier missing or
    the column is NULL (i.e. no signal has fired on this dossier).
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT last_signal_kind FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()
    if row is None:
        return None
    return row["last_signal_kind"]


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


# ---------- User notes (formerly user_note_store.py) ----------


def create_user_note(
    dossier_id: str,
    data: m.UserNoteCreate,
    work_session_id: Optional[str] = None,
) -> m.UserNote:
    now = m.utc_now()
    note = m.UserNote(
        id=m.new_id("un"),
        dossier_id=dossier_id,
        content=data.content,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_notes (id, dossier_id, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (note.id, dossier_id, note.content, _dt_str(now)),
        )
        _log_change(
            conn, dossier_id, work_session_id, "user_note_added",
            f"Note from you: {data.content[:120]}",
        )
        _touch_dossier(conn, dossier_id)
        # Reactive wake, same gating as needs_input resolution: with sleep
        # mode off the user drives resumes manually.
        sleep_mode_on = True
        try:
            setting = conn.execute(
                "SELECT value_json FROM settings WHERE key = 'sleep_mode_enabled'"
            ).fetchone()
            if setting is not None:
                sleep_mode_on = json.loads(setting["value_json"])
        except Exception:
            pass
        if sleep_mode_on:
            conn.execute(
                "UPDATE dossiers SET wake_pending = 1, wake_reason = ? WHERE id = ?",
                (m.WakeReason.user_note.value, dossier_id),
            )
    return note


def list_user_notes(dossier_id: str, unseen_only: bool = False) -> list[m.UserNote]:
    q = "SELECT * FROM user_notes WHERE dossier_id = ?"
    if unseen_only:
        q += " AND seen_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_user_note(r) for r in rows]


def mark_user_notes_seen(note_ids: list[str]) -> int:
    """Stamp seen_at on the given notes. Returns how many rows changed.

    Only unseen notes are stamped — a note surfaced by two overlapping
    sessions keeps its first seen_at.
    """
    if not note_ids:
        return 0
    now_s = _dt_str(m.utc_now())
    placeholders = ",".join("?" for _ in note_ids)
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE user_notes SET seen_at = ? "
            f"WHERE id IN ({placeholders}) AND seen_at IS NULL",
            [now_s, *note_ids],
        )
    return cur.rowcount


# ---------- Next actions (formerly next_action_store.py) ----------


def _compute_next_action_priority(
    conn, dossier_id: str, after_action_id: Optional[str]
) -> float:
    rows = conn.execute(
        "SELECT id, priority FROM next_actions WHERE dossier_id = ? ORDER BY priority",
        (dossier_id,),
    ).fetchall()
    if not rows:
        return _ORDER_STEP
    if after_action_id is None:
        return rows[-1]["priority"] + _ORDER_STEP
    for i, row in enumerate(rows):
        if row["id"] == after_action_id:
            next_p = (
                rows[i + 1]["priority"]
                if i + 1 < len(rows)
                else row["priority"] + 2 * _ORDER_STEP
            )
            return (row["priority"] + next_p) / 2
    return rows[-1]["priority"] + _ORDER_STEP


def add_next_action(
    dossier_id: str,
    data: m.NextActionCreate,
    work_session_id: Optional[str] = None,
) -> m.NextAction:
    now = m.utc_now()
    action_id = m.new_id("act")
    with connect() as conn:
        priority = _compute_next_action_priority(conn, dossier_id, data.after_action_id)
        conn.execute(
            """
            INSERT INTO next_actions (id, dossier_id, action, rationale, priority,
                                      completed, completed_at, created_at)
            VALUES (?, ?, ?, ?, ?, 0, NULL, ?)
            """,
            (
                action_id,
                dossier_id,
                data.action,
                data.rationale,
                priority,
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "next_action_added",
            f"Next action: {data.action}",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ?", (action_id,)
        ).fetchone()
    return _row_to_next_action(row)


def list_next_actions(
    dossier_id: str, include_completed: bool = True
) -> list[m.NextAction]:
    q = "SELECT * FROM next_actions WHERE dossier_id = ?"
    if not include_completed:
        q += " AND completed = 0"
    q += " ORDER BY priority"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_next_action(r) for r in rows]


def complete_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.NextAction]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ? AND dossier_id = ?",
            (action_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE next_actions SET completed = 1, completed_at = ? WHERE id = ?",
            (now_s, action_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "next_action_completed",
            f"Completed: {row['action']}",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ?", (action_id,)
        ).fetchone()
    return _row_to_next_action(row)


def remove_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM next_actions WHERE id = ? AND dossier_id = ?",
            (action_id, dossier_id),
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM next_actions WHERE id = ?", (action_id,))
        _log_change(
            conn, dossier_id, work_session_id, "next_action_removed",
            f"Removed: {row['action']}",
        )
        _touch_dossier(conn, dossier_id)
    return True


def reorder_next_actions(
    dossier_id: str,
    action_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.NextAction]:
    with connect() as conn:
        existing_ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM next_actions WHERE dossier_id = ?", (dossier_id,)
            ).fetchall()
        }
        if set(action_ids) != existing_ids:
            raise ValueError(
                "reorder action_ids must match existing next_action set exactly"
            )
        for i, aid in enumerate(action_ids, start=1):
            conn.execute(
                "UPDATE next_actions SET priority = ? WHERE id = ?",
                (i * _ORDER_STEP, aid),
            )
        _touch_dossier(conn, dossier_id)
    return list_next_actions(dossier_id)
