"""User notes: "tell the agent something" mid-investigation.

Creating a note is the user tapping the agent on the shoulder — it rides the
same reactive-wake pipeline as ``resolve_needs_input``: the insert and the
``wake_pending`` flip happen in one transaction, and the scheduler resumes
the agent on its next tick. The runtime surfaces unseen notes in every state
snapshot and marks them seen only when a session ends healthy, so notes are
never lost to an errored session.
"""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import _dt_str, _log_change, _row_to_user_note, _touch_dossier


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
