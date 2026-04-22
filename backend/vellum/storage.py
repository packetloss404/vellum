"""CRUD + aggregate reads for dossiers and their child collections.

All mutations that affect a dossier's visible state append to change_log when a
work_session_id is supplied. Storage functions never emit prose to users — the
only user-visible surface is what's written into these tables.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from pydantic import TypeAdapter

from . import models as m
from .db import connect


# TypeAdapters for list[PydanticModel] round-trips.
_SourceList = TypeAdapter(list[m.Source])
_OptionList = TypeAdapter(list[m.DecisionOption])


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


def _json_list(text: str) -> list:
    return json.loads(text) if text else []


# ---------- row → model converters ----------


def _row_to_dossier(row: sqlite3.Row) -> m.Dossier:
    return m.Dossier(
        id=row["id"],
        title=row["title"],
        problem_statement=row["problem_statement"],
        out_of_scope=_json_list(row["out_of_scope"]),
        dossier_type=m.DossierType(row["dossier_type"]),
        status=m.DossierStatus(row["status"]),
        check_in_policy=m.CheckInPolicy.model_validate_json(row["check_in_policy"]),
        last_visited_at=_dt(row["last_visited_at"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_section(row: sqlite3.Row) -> m.Section:
    return m.Section(
        id=row["id"],
        dossier_id=row["dossier_id"],
        type=m.SectionType(row["type"]),
        title=row["title"],
        content=row["content"],
        state=m.SectionState(row["state"]),
        order=row["order"],
        change_note=row["change_note"],
        sources=_SourceList.validate_json(row["sources"]),
        depends_on=_json_list(row["depends_on"]),
        last_updated=_dt(row["last_updated"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_needs_input(row: sqlite3.Row) -> m.NeedsInput:
    return m.NeedsInput(
        id=row["id"],
        dossier_id=row["dossier_id"],
        question=row["question"],
        blocks_section_ids=_json_list(row["blocks_section_ids"]),
        created_at=_dt(row["created_at"]),
        answered_at=_dt(row["answered_at"]),
        answer=row["answer"],
    )


def _row_to_decision_point(row: sqlite3.Row) -> m.DecisionPoint:
    return m.DecisionPoint(
        id=row["id"],
        dossier_id=row["dossier_id"],
        title=row["title"],
        options=_OptionList.validate_json(row["options"]),
        recommendation=row["recommendation"],
        blocks_section_ids=_json_list(row["blocks_section_ids"]),
        created_at=_dt(row["created_at"]),
        resolved_at=_dt(row["resolved_at"]),
        chosen=row["chosen"],
    )


def _row_to_reasoning(row: sqlite3.Row) -> m.ReasoningTrailEntry:
    return m.ReasoningTrailEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        note=row["note"],
        tags=_json_list(row["tags"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_ruled_out(row: sqlite3.Row) -> m.RuledOut:
    return m.RuledOut(
        id=row["id"],
        dossier_id=row["dossier_id"],
        subject=row["subject"],
        reason=row["reason"],
        sources=_SourceList.validate_json(row["sources"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_work_session(row: sqlite3.Row) -> m.WorkSession:
    return m.WorkSession(
        id=row["id"],
        dossier_id=row["dossier_id"],
        started_at=_dt(row["started_at"]),
        ended_at=_dt(row["ended_at"]),
        trigger=m.WorkSessionTrigger(row["trigger"]),
        token_budget_used=row["token_budget_used"],
    )


def _row_to_change(row: sqlite3.Row) -> m.ChangeLogEntry:
    return m.ChangeLogEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        section_id=row["section_id"],
        kind=row["kind"],
        change_note=row["change_note"],
        created_at=_dt(row["created_at"]),
    )


# ---------- internal helpers ----------


def _touch_dossier(conn: sqlite3.Connection, dossier_id: str) -> None:
    conn.execute(
        "UPDATE dossiers SET updated_at = ? WHERE id = ?",
        (_dt_str(m.utc_now()), dossier_id),
    )


def _log_change(
    conn: sqlite3.Connection,
    dossier_id: str,
    work_session_id: Optional[str],
    kind: m.ChangeKind,
    change_note: str,
    section_id: Optional[str] = None,
) -> None:
    if not work_session_id:
        return
    conn.execute(
        """
        INSERT INTO change_log (id, dossier_id, work_session_id, section_id, kind, change_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m.new_id("chg"),
            dossier_id,
            work_session_id,
            section_id,
            kind,
            change_note,
            _dt_str(m.utc_now()),
        ),
    )


# ---------- Dossier ----------


def create_dossier(data: m.DossierCreate) -> m.Dossier:
    now = m.utc_now()
    dossier = m.Dossier(
        id=m.new_id("dos"),
        title=data.title,
        problem_statement=data.problem_statement,
        out_of_scope=data.out_of_scope,
        dossier_type=data.dossier_type,
        status=m.DossierStatus.active,
        check_in_policy=data.check_in_policy,
        created_at=now,
        updated_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO dossiers (id, title, problem_statement, out_of_scope, dossier_type,
                                  status, check_in_policy, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dossier.id,
                dossier.title,
                dossier.problem_statement,
                json.dumps(dossier.out_of_scope),
                dossier.dossier_type.value,
                dossier.status.value,
                dossier.check_in_policy.model_dump_json(),
                _dt_str(dossier.created_at),
                _dt_str(dossier.updated_at),
            ),
        )
    return dossier


def get_dossier(dossier_id: str) -> Optional[m.Dossier]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
    return _row_to_dossier(row) if row else None


def list_dossiers() -> list[m.Dossier]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dossiers ORDER BY updated_at DESC").fetchall()
    return [_row_to_dossier(r) for r in rows]


def update_dossier(dossier_id: str, patch: m.DossierUpdate) -> Optional[m.Dossier]:
    fields: list[tuple[str, object]] = []
    if patch.title is not None:
        fields.append(("title", patch.title))
    if patch.problem_statement is not None:
        fields.append(("problem_statement", patch.problem_statement))
    if patch.out_of_scope is not None:
        fields.append(("out_of_scope", json.dumps(patch.out_of_scope)))
    if patch.status is not None:
        fields.append(("status", patch.status.value))
    if patch.check_in_policy is not None:
        fields.append(("check_in_policy", patch.check_in_policy.model_dump_json()))
    if not fields:
        return get_dossier(dossier_id)
    fields.append(("updated_at", _dt_str(m.utc_now())))
    set_clause = ", ".join(f"{k} = ?" for k, _ in fields)
    values = [v for _, v in fields] + [dossier_id]
    with connect() as conn:
        conn.execute(f"UPDATE dossiers SET {set_clause} WHERE id = ?", values)
    return get_dossier(dossier_id)


def delete_dossier(dossier_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM dossiers WHERE id = ?", (dossier_id,))
        return cur.rowcount > 0


def mark_dossier_visited(dossier_id: str) -> Optional[m.Dossier]:
    """End any active work_session and update last_visited_at. Called when the user opens the dossier."""
    now = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET ended_at = ? WHERE dossier_id = ? AND ended_at IS NULL",
            (now, dossier_id),
        )
        conn.execute(
            "UPDATE dossiers SET last_visited_at = ?, updated_at = ? WHERE id = ?",
            (now, now, dossier_id),
        )
    return get_dossier(dossier_id)


def get_dossier_full(dossier_id: str) -> Optional[m.DossierFull]:
    dossier = get_dossier(dossier_id)
    if not dossier:
        return None
    return m.DossierFull(
        dossier=dossier,
        sections=list_sections(dossier_id),
        needs_input=list_needs_input(dossier_id),
        decision_points=list_decision_points(dossier_id),
        reasoning_trail=list_reasoning_trail(dossier_id),
        ruled_out=list_ruled_out(dossier_id),
        work_sessions=list_work_sessions(dossier_id),
        # v2: cap investigation_log at the most recent 500 entries to keep the
        # aggregate payload bounded on hot dossiers.
        investigation_log=list_investigation_log(dossier_id, limit=500),
        considered_and_rejected=list_considered_and_rejected(dossier_id),
    )


# ---------- Sections ----------


_ORDER_STEP = 10.0


def _compute_order(conn: sqlite3.Connection, dossier_id: str, after_section_id: Optional[str]) -> float:
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
    # after_section_id not found — fall back to end
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
        # Mirror into reasoning_trail so cross-session coherence is preserved.
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


# ---------- NeedsInput ----------


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


# ---------- DecisionPoint ----------


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
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_points (id, dossier_id, title, options, recommendation,
                                         blocks_section_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                item.title,
                _OptionList.dump_json(item.options).decode(),
                item.recommendation,
                json.dumps(item.blocks_section_ids),
                _dt_str(now),
            ),
        )
        _log_change(conn, dossier_id, work_session_id, "decision_point_added", item.title)
        _touch_dossier(conn, dossier_id)
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
        row = conn.execute("SELECT * FROM decision_points WHERE id = ?", (decision_id,)).fetchone()
    return _row_to_decision_point(row)


def list_decision_points(dossier_id: str, open_only: bool = False) -> list[m.DecisionPoint]:
    q = "SELECT * FROM decision_points WHERE dossier_id = ?"
    if open_only:
        q += " AND resolved_at IS NULL"
    q += " ORDER BY created_at"
    with connect() as conn:
        rows = conn.execute(q, (dossier_id,)).fetchall()
    return [_row_to_decision_point(r) for r in rows]


# ---------- ReasoningTrail ----------


def append_reasoning(
    dossier_id: str,
    data: m.ReasoningAppend,
    work_session_id: Optional[str] = None,
) -> m.ReasoningTrailEntry:
    now = m.utc_now()
    entry = m.ReasoningTrailEntry(
        id=m.new_id("rtr"),
        dossier_id=dossier_id,
        work_session_id=work_session_id,
        note=data.note,
        tags=data.tags,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO reasoning_trail (id, dossier_id, work_session_id, note, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                dossier_id,
                work_session_id,
                entry.note,
                json.dumps(entry.tags),
                _dt_str(now),
            ),
        )
    return entry


def list_reasoning_trail(dossier_id: str) -> list[m.ReasoningTrailEntry]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reasoning_trail WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_reasoning(r) for r in rows]


# ---------- RuledOut ----------


def add_ruled_out(
    dossier_id: str,
    data: m.RuledOutCreate,
    work_session_id: Optional[str] = None,
) -> m.RuledOut:
    now = m.utc_now()
    item = m.RuledOut(
        id=m.new_id("ro"),
        dossier_id=dossier_id,
        subject=data.subject,
        reason=data.reason,
        sources=data.sources,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO ruled_out (id, dossier_id, subject, reason, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                item.subject,
                item.reason,
                _SourceList.dump_json(item.sources).decode(),
                _dt_str(now),
            ),
        )
        _log_change(conn, dossier_id, work_session_id, "ruled_out_added", f"Ruled out: {item.subject}")
        _touch_dossier(conn, dossier_id)
    return item


def list_ruled_out(dossier_id: str) -> list[m.RuledOut]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ruled_out WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_ruled_out(r) for r in rows]


# ---------- WorkSession ----------


def start_work_session(
    dossier_id: str,
    trigger: m.WorkSessionTrigger = m.WorkSessionTrigger.manual,
) -> m.WorkSession:
    now = m.utc_now()
    session = m.WorkSession(
        id=m.new_id("ws"),
        dossier_id=dossier_id,
        started_at=now,
        trigger=trigger,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO work_sessions (id, dossier_id, started_at, trigger, token_budget_used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (session.id, dossier_id, _dt_str(now), trigger.value),
        )
    return session


def end_work_session(session_id: str) -> Optional[m.WorkSession]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (now_s, session_id),
        )
        row = conn.execute("SELECT * FROM work_sessions WHERE id = ?", (session_id,)).fetchone()
    return _row_to_work_session(row) if row else None


def get_active_work_session(dossier_id: str) -> Optional[m.WorkSession]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
    return _row_to_work_session(row) if row else None


def list_work_sessions(dossier_id: str) -> list[m.WorkSession]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM work_sessions WHERE dossier_id = ? ORDER BY started_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_work_session(r) for r in rows]


def increment_session_tokens(session_id: str, tokens: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET token_budget_used = token_budget_used + ? WHERE id = ?",
            (tokens, session_id),
        )


# ---------- ChangeLog ----------


def list_change_log_for_session(dossier_id: str, session_id: str) -> list[m.ChangeLogEntry]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM change_log WHERE dossier_id = ? AND work_session_id = ? ORDER BY created_at",
            (dossier_id, session_id),
        ).fetchall()
    return [_row_to_change(r) for r in rows]


def list_change_log_since_last_visit(dossier_id: str) -> list[m.ChangeLogEntry]:
    """The plan-diff: everything the agent did since the user was last here."""
    dossier = get_dossier(dossier_id)
    if not dossier:
        return []
    with connect() as conn:
        if dossier.last_visited_at is None:
            rows = conn.execute(
                "SELECT * FROM change_log WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM change_log WHERE dossier_id = ? AND created_at > ? ORDER BY created_at",
                (dossier_id, _dt_str(dossier.last_visited_at)),
            ).fetchall()
    return [_row_to_change(r) for r in rows]


# ---------- v2: InvestigationLog ----------
#
# The investigation_log is the typed, countable "evidence of work" surface
# (source_consulted, sub_investigation_spawned, etc.). It is *separate* from
# change_log (user-visit-diff) by design — appends here do NOT write to
# change_log. This keeps the "47 sources consulted" counter from polluting the
# since-last-visit plan-diff the user reads when they return.


def _row_to_investigation_log(row: sqlite3.Row) -> m.InvestigationLogEntry:
    return m.InvestigationLogEntry(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        sub_investigation_id=row["sub_investigation_id"],
        entry_type=m.InvestigationLogEntryType(row["entry_type"]),
        payload=json.loads(row["payload"]) if row["payload"] else {},
        summary=row["summary"],
        created_at=_dt(row["created_at"]),
    )


def append_investigation_log(
    dossier_id: str,
    data: m.InvestigationLogAppend,
    work_session_id: Optional[str] = None,
) -> m.InvestigationLogEntry:
    now = m.utc_now()
    entry = m.InvestigationLogEntry(
        id=m.new_id("ilg"),
        dossier_id=dossier_id,
        work_session_id=work_session_id,
        sub_investigation_id=data.sub_investigation_id,
        entry_type=data.entry_type,
        payload=data.payload,
        summary=data.summary,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO investigation_log (id, dossier_id, work_session_id, sub_investigation_id,
                                           entry_type, payload, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                dossier_id,
                work_session_id,
                data.sub_investigation_id,
                data.entry_type.value,
                json.dumps(data.payload),
                data.summary,
                _dt_str(now),
            ),
        )
        # Note: intentionally do NOT call _log_change — see module-level comment.
    return entry


def list_investigation_log(
    dossier_id: str,
    entry_type: Optional[m.InvestigationLogEntryType] = None,
    limit: int = 500,
) -> list[m.InvestigationLogEntry]:
    q = "SELECT * FROM investigation_log WHERE dossier_id = ?"
    params: list[object] = [dossier_id]
    if entry_type is not None:
        q += " AND entry_type = ?"
        params.append(entry_type.value)
    q += " ORDER BY created_at LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_investigation_log(r) for r in rows]


def count_investigation_log_by_type(dossier_id: str) -> dict[str, int]:
    """Powers the "47 sources / 4 sub-investigations / 3 artifacts" header in the UI."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT entry_type, COUNT(*) AS n FROM investigation_log WHERE dossier_id = ? GROUP BY entry_type",
            (dossier_id,),
        ).fetchall()
    return {r["entry_type"]: r["n"] for r in rows}


# ---------- v2: ConsideredAndRejected ----------


def _row_to_considered_and_rejected(row: sqlite3.Row) -> m.ConsideredAndRejected:
    return m.ConsideredAndRejected(
        id=row["id"],
        dossier_id=row["dossier_id"],
        sub_investigation_id=row["sub_investigation_id"],
        path=row["path"],
        why_compelling=row["why_compelling"],
        why_rejected=row["why_rejected"],
        cost_of_error=row["cost_of_error"],
        sources=_SourceList.validate_json(row["sources"]),
        created_at=_dt(row["created_at"]),
    )


def add_considered_and_rejected(
    dossier_id: str,
    data: m.ConsideredAndRejectedCreate,
    work_session_id: Optional[str] = None,
) -> m.ConsideredAndRejected:
    now = m.utc_now()
    item = m.ConsideredAndRejected(
        id=m.new_id("crj"),
        dossier_id=dossier_id,
        sub_investigation_id=data.sub_investigation_id,
        path=data.path,
        why_compelling=data.why_compelling,
        why_rejected=data.why_rejected,
        cost_of_error=data.cost_of_error,
        sources=data.sources,
        created_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO considered_and_rejected
                (id, dossier_id, sub_investigation_id, path, why_compelling, why_rejected,
                 cost_of_error, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                dossier_id,
                data.sub_investigation_id,
                data.path,
                data.why_compelling,
                data.why_rejected,
                data.cost_of_error,
                _SourceList.dump_json(data.sources).decode(),
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "considered_and_rejected_added",
            f"Rejected: {data.path}",
        )
        # Also append to investigation_log so the "paths considered" counter
        # reflects this. Inline insert keeps the timestamp inside the same txn.
        conn.execute(
            """
            INSERT INTO investigation_log (id, dossier_id, work_session_id, sub_investigation_id,
                                           entry_type, payload, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.new_id("ilg"),
                dossier_id,
                work_session_id,
                data.sub_investigation_id,
                m.InvestigationLogEntryType.path_rejected.value,
                json.dumps({"considered_and_rejected_id": item.id}),
                f"Rejected: {data.path}",
                _dt_str(now),
            ),
        )
        _touch_dossier(conn, dossier_id)
    return item


def list_considered_and_rejected(dossier_id: str) -> list[m.ConsideredAndRejected]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM considered_and_rejected WHERE dossier_id = ? ORDER BY created_at",
            (dossier_id,),
        ).fetchall()
    return [_row_to_considered_and_rejected(r) for r in rows]
