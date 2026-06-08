"""NeedsInput CRUD and resolution."""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _log_change,
    _row_to_needs_input,
    _touch_dossier,
)


def add_needs_input(
    dossier_id: str,
    data: m.NeedsInputCreate,
    work_session_id: Optional[str] = None,
) -> m.NeedsInput:
    now = m.utc_now()
    item = m.NeedsInput(
        id=m.new_id("ni"),
        dossier_id=dossier_id,
        question=data.question,
        blocks_section_ids=data.blocks_section_ids,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO needs_input (id, dossier_id, question, blocks_section_ids, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (item.id, dossier_id, item.question, json.dumps(item.blocks_section_ids), _dt_str(now)),
        )
        _log_change(conn, dossier_id, work_session_id, "needs_input_added", item.question)
        _touch_dossier(conn, dossier_id)
    return item


def resolve_needs_input(
    dossier_id: str,
    needs_input_id: str,
    answer: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.NeedsInput]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM needs_input WHERE id = ? AND dossier_id = ?",
            (needs_input_id, dossier_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE needs_input SET answered_at = ?, answer = ? WHERE id = ?",
            (now_s, answer, needs_input_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "needs_input_resolved",
            f"Answered: {row['question']}",
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
                (m.WakeReason.needs_input_resolved.value, dossier_id),
            )
        row = conn.execute("SELECT * FROM needs_input WHERE id = ?", (needs_input_id,)).fetchone()
    return _row_to_needs_input(row)


def list_needs_input(dossier_id: str, open_only: bool = False) -> list[m.NeedsInput]:
    q = "SELECT * FROM needs_input WHERE dossier_id = ?"
    if open_only:
        q += " AND answered_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_needs_input(r) for r in rows]
