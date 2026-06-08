"""DecisionPoint CRUD and resolution."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _json_list,
    _log_change,
    _row_to_decision_point,
    _touch_dossier,
    _OptionList,
)


_APPROVE_PATTERN = re.compile(r"approve|approved|yes", re.IGNORECASE)


def _get_open_plan_approval_row(
    conn: sqlite3.Connection,
    dossier_id: str,
) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM decision_points
         WHERE dossier_id = ?
           AND kind = 'plan_approval'
           AND resolved_at IS NULL
         ORDER BY created_at DESC, id DESC
         LIMIT 1
        """,
        (dossier_id,),
    ).fetchone()


def add_decision_point(
    dossier_id: str,
    data: m.DecisionPointCreate,
    work_session_id: Optional[str] = None,
) -> m.DecisionPoint:
    now = m.utc_now()
    item = m.DecisionPoint(
        id=m.new_id("dp"),
        dossier_id=dossier_id,
        title=data.title,
        options=data.options,
        recommendation=data.recommendation,
        blocks_section_ids=data.blocks_section_ids,
        kind=data.kind,
        created_at=now,
    )
    try:
        with connect() as conn:
            if data.kind == "plan_approval":
                existing = _get_open_plan_approval_row(conn, dossier_id)
                if existing is not None:
                    return _row_to_decision_point(existing)
            conn.execute(
                """
                INSERT INTO decision_points (id, dossier_id, title, options, recommendation,
                                             blocks_section_ids, kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    dossier_id,
                    item.title,
                    _OptionList.dump_json(item.options).decode(),
                    item.recommendation,
                    json.dumps(item.blocks_section_ids),
                    item.kind,
                    _dt_str(now),
                ),
            )
            _log_change(conn, dossier_id, work_session_id, "decision_point_added", item.title)
            _touch_dossier(conn, dossier_id)
    except sqlite3.IntegrityError as exc:
        if data.kind == "plan_approval":
            with connect() as conn:
                existing = _get_open_plan_approval_row(conn, dossier_id)
            if existing is not None:
                return _row_to_decision_point(existing)
        raise
    return item


def resolve_decision_point(
    dossier_id: str,
    decision_id: str,
    chosen: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.DecisionPoint]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM decision_points WHERE id = ? AND dossier_id = ?",
            (decision_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE decision_points SET resolved_at = ?, chosen = ? WHERE id = ?",
            (now_s, chosen, decision_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "decision_point_resolved",
            f"Decided '{row['title']}' → {chosen}",
        )
        _touch_dossier(conn, dossier_id)
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
                (m.WakeReason.decision_resolved.value, dossier_id),
            )
        row = conn.execute("SELECT * FROM decision_points WHERE id = ?", (decision_id,)).fetchone()
    resolved = _row_to_decision_point(row)
    if (
        resolved.kind == "plan_approval"
        and _APPROVE_PATTERN.search(chosen or "")
    ):
        from .dossier_store import approve_investigation_plan
        approve_investigation_plan(dossier_id, work_session_id)
    return resolved


def list_decision_points(dossier_id: str, open_only: bool = False) -> list[m.DecisionPoint]:
    q = "SELECT * FROM decision_points WHERE dossier_id = ?"
    if open_only:
        q += " AND resolved_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_decision_point(r) for r in rows]
