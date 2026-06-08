"""NextAction CRUD and ordering."""
from __future__ import annotations

from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _log_change,
    _row_to_next_action,
    _touch_dossier,
    _ORDER_STEP,
)


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
