"""Section CRUD and ordering."""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _json_list,
    _log_change,
    _row_to_section,
    _strip_tool_markup,
    _touch_dossier,
    _SourceList,
    _ORDER_STEP,
)


def _compute_order(conn, dossier_id: str, after_section_id: Optional[str]) -> float:
    """Place section immediately after the given section, or at end if None."""
    rows = conn.execute(
        'SELECT id, "order" FROM sections WHERE dossier_id = ? ORDER BY "order"',
        (dossier_id,),
    ).fetchall()
    if not rows:
        return _ORDER_STEP
    if after_section_id is None:
        return rows[-1]["order"] + _ORDER_STEP
    for i, row in enumerate(rows):
        if row["id"] == after_section_id:
            next_order = rows[i + 1]["order"] if i + 1 < len(rows) else row["order"] + 2 * _ORDER_STEP
            return (row["order"] + next_order) / 2
    return rows[-1]["order"] + _ORDER_STEP


def list_sections(dossier_id: str) -> list[m.Section]:
    with connect() as conn:
        rows = conn.execute(
            'SELECT * FROM sections WHERE dossier_id = ? ORDER BY "order"',
            (dossier_id,),
        ).fetchall()
    return [_row_to_section(r) for r in rows]


def get_section(section_id: str) -> Optional[m.Section]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row) if row else None


def upsert_section(
    dossier_id: str,
    data: m.SectionUpsert,
    work_session_id: Optional[str] = None,
) -> m.Section:
    now = m.utc_now()
    now_s = _dt_str(now)
    with connect() as conn:
        if data.section_id:
            existing = conn.execute(
                "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
                (data.section_id, dossier_id),
            ).fetchone()
            if not existing:
                raise KeyError(f"section {data.section_id} not found in dossier {dossier_id}")
            conn.execute(
                """
                UPDATE sections SET type = ?, title = ?, content = ?, state = ?,
                    change_note = ?, sources = ?, depends_on = ?, last_updated = ?
                WHERE id = ?
                """,
                (
                    data.type.value,
                    data.title,
                    data.content,
                    data.state.value,
                    data.change_note,
                    _SourceList.dump_json(data.sources).decode(),
                    json.dumps(data.depends_on),
                    now_s,
                    data.section_id,
                ),
            )
            kind: m.ChangeKind = "section_updated"
            section_id = data.section_id
            if existing["state"] != data.state.value:
                _log_change(conn, dossier_id, work_session_id, "state_changed",
                            f"{data.title}: {existing['state']} → {data.state.value}", section_id)
        else:
            section_id = m.new_id("sec")
            order = _compute_order(conn, dossier_id, data.after_section_id)
            conn.execute(
                """
                INSERT INTO sections (id, dossier_id, type, title, content, state, "order",
                                      change_note, sources, depends_on, last_updated, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    section_id,
                    dossier_id,
                    data.type.value,
                    data.title,
                    data.content,
                    data.state.value,
                    order,
                    data.change_note,
                    _SourceList.dump_json(data.sources).decode(),
                    json.dumps(data.depends_on),
                    now_s,
                    now_s,
                ),
            )
            kind = "section_created"
        _log_change(conn, dossier_id, work_session_id, kind, data.change_note or data.title, section_id)
        _touch_dossier(conn, dossier_id)
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row)


def update_section_state(
    dossier_id: str,
    section_id: str,
    patch: m.SectionStateUpdate,
    work_session_id: Optional[str] = None,
) -> m.Section:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
            (section_id, dossier_id),
        ).fetchone()
        if not existing:
            raise KeyError(f"section {section_id} not found in dossier {dossier_id}")
        conn.execute(
            "UPDATE sections SET state = ?, change_note = ?, last_updated = ? WHERE id = ?",
            (patch.new_state.value, patch.reason, now_s, section_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "state_changed",
            f"{existing['title']}: {existing['state']} → {patch.new_state.value} ({patch.reason})",
            section_id,
        )
        conn.execute(
            """
            INSERT INTO reasoning_trail (id, dossier_id, work_session_id, note, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                m.new_id("rtr"),
                dossier_id,
                work_session_id,
                f"[state_change] {existing['title']}: {existing['state']} → {patch.new_state.value}. Reason: {patch.reason}",
                json.dumps(["state_change"]),
                now_s,
            ),
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute("SELECT * FROM sections WHERE id = ?", (section_id,)).fetchone()
    return _row_to_section(row)


def delete_section(
    dossier_id: str,
    section_id: str,
    reason: str,
    work_session_id: Optional[str] = None,
) -> bool:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sections WHERE id = ? AND dossier_id = ?",
            (section_id, dossier_id),
        ).fetchone()
        if not existing:
            return False
        conn.execute("DELETE FROM sections WHERE id = ?", (section_id,))
        _log_change(
            conn, dossier_id, work_session_id, "section_deleted",
            f"Deleted '{existing['title']}': {reason}", section_id,
        )
        # Clean up references to the deleted section in other sections' depends_on lists.
        other_rows = conn.execute(
            "SELECT id, depends_on FROM sections WHERE dossier_id = ?",
            (dossier_id,),
        ).fetchall()
        for row in other_rows:
            deps = _json_list(row["depends_on"])
            if section_id in deps:
                updated_deps = [d for d in deps if d != section_id]
                conn.execute(
                    "UPDATE sections SET depends_on = ? WHERE id = ?",
                    (json.dumps(updated_deps), row["id"]),
                )
        _touch_dossier(conn, dossier_id)
    return True


def reorder_sections(
    dossier_id: str,
    section_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.Section]:
    with connect() as conn:
        existing_ids = {
            r["id"]
            for r in conn.execute(
                "SELECT id FROM sections WHERE dossier_id = ?", (dossier_id,)
            ).fetchall()
        }
        if set(section_ids) != existing_ids:
            raise ValueError("reorder section_ids must match existing section set exactly")
        for i, sid in enumerate(section_ids, start=1):
            conn.execute(
                'UPDATE sections SET "order" = ? WHERE id = ?',
                (i * _ORDER_STEP, sid),
            )
        _log_change(
            conn, dossier_id, work_session_id, "sections_reordered",
            f"Reordered {len(section_ids)} sections",
        )
        _touch_dossier(conn, dossier_id)
    return list_sections(dossier_id)
