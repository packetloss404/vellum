"""Reasoning trail, investigation log, change log, ruled out, and considered-and-rejected."""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt,
    _dt_str,
    _json_list,
    _log_change,
    _row_get,
    _row_to_change,
    _row_to_reasoning,
    _row_to_ruled_out,
    _row_to_investigation_log,
    _row_to_considered_and_rejected,
    _touch_dossier,
    _SourceList,
)


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


# ---------- InvestigationLog ----------


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
    """Powers the "47 sources / 4 sub-investigations / 3 artifacts" header."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT entry_type, COUNT(*) AS n FROM investigation_log WHERE dossier_id = ? GROUP BY entry_type",
            (dossier_id,),
        ).fetchall()
    return {r["entry_type"]: r["n"] for r in rows}


# ---------- ConsideredAndRejected ----------


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
                item.path,
                item.why_compelling,
                item.why_rejected,
                item.cost_of_error,
                _SourceList.dump_json(item.sources).decode(),
                _dt_str(now),
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "considered_and_rejected_added",
            f"Rejected: {data.path}",
        )
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
    from .dossier_store import get_dossier
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
