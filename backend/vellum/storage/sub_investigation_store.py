"""SubInvestigation CRUD, state transitions, and plan-item sync."""
from __future__ import annotations

import json
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt_str,
    _json_list,
    _log_change,
    _row_get,
    _row_to_sub_investigation,
    _touch_dossier,
)
from .plan_items_store import set_plan_item_status_with_conn


def _set_plan_item_status(
    conn,
    dossier_id: str,
    plan_item_id: Optional[str],
    new_status: str,
    sub_investigation_id: Optional[str] = None,
) -> None:
    """Flip a single plan item's status via direct UPDATE on plan_items table.

    Replaces the old read-modify-write on the investigation_plan JSON blob.
    """
    if not plan_item_id:
        return
    set_plan_item_status_with_conn(
        conn, dossier_id, plan_item_id, new_status,
        sub_investigation_id=sub_investigation_id if new_status == "in_progress" else None,
    )


def finalize_plan_on_delivery(
    dossier_id: str,
    work_session_id: Optional[str] = None,
) -> dict:
    """Sweep non-terminal plan items to `completed` when a dossier delivers.

    Now operates on plan_items table directly instead of the JSON blob.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT plan_item_id, status FROM plan_items WHERE dossier_id = ?",
            (dossier_id,),
        ).fetchall()
        if not rows:
            return {"items_flipped": 0, "from_planned": 0, "from_in_progress": 0}

        from_planned = 0
        from_in_progress = 0
        now_s = _dt_str(m.utc_now())
        for row in rows:
            status = row["status"]
            if status in ("completed", "abandoned"):
                continue
            if status == "planned":
                from_planned += 1
            elif status == "in_progress":
                from_in_progress += 1
            conn.execute(
                "UPDATE plan_items SET status = 'completed', updated_at = ? "
                "WHERE dossier_id = ? AND plan_item_id = ?",
                (now_s, dossier_id, row["plan_item_id"]),
            )
        total = from_planned + from_in_progress
        if total == 0:
            return {"items_flipped": 0, "from_planned": 0, "from_in_progress": 0}

        note = (
            f"Plan finalized on delivery: {total} item(s) flipped to completed "
            f"({from_planned} planned, {from_in_progress} in_progress)."
        )
        _log_change(
            conn, dossier_id, work_session_id, "plan_updated", note,
        )
        _touch_dossier(conn, dossier_id)
    return {
        "items_flipped": total,
        "from_planned": from_planned,
        "from_in_progress": from_in_progress,
    }


def spawn_sub_investigation(
    dossier_id: str,
    data: m.SubInvestigationSpawn,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    now = m.utc_now()
    sub = m.SubInvestigation(
        id=m.new_id("sub"),
        dossier_id=dossier_id,
        parent_section_id=data.parent_section_id,
        plan_item_id=data.plan_item_id,
        title=data.title,
        scope=data.scope,
        questions=data.questions,
        state=m.SubInvestigationState.running,
        why_it_matters=data.why_it_matters,
        known_facts=data.known_facts,
        missing_facts=data.missing_facts,
        started_at=now,
    )
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sub_investigations (id, dossier_id, parent_section_id, plan_item_id,
                                            title, scope, questions, state, return_summary,
                                            findings_section_ids, findings_artifact_ids,
                                            why_it_matters, known_facts, missing_facts,
                                            started_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub.id,
                dossier_id,
                sub.parent_section_id,
                sub.plan_item_id,
                sub.title,
                sub.scope,
                json.dumps(sub.questions),
                sub.state.value,
                sub.return_summary,
                json.dumps(sub.findings_section_ids),
                json.dumps(sub.findings_artifact_ids),
                sub.why_it_matters,
                json.dumps(sub.known_facts),
                json.dumps(sub.missing_facts),
                _dt_str(sub.started_at),
                None,
            ),
        )
        _set_plan_item_status(conn, dossier_id, sub.plan_item_id, "in_progress", sub_investigation_id=sub.id)
        display = sub.title or sub.scope
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_spawned",
            f"Spawned sub-investigation: {display}",
        )
        _touch_dossier(conn, dossier_id)
    return sub


def get_sub_investigation(sub_id: str) -> Optional[m.SubInvestigation]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row) if row else None


def list_sub_investigations(
    dossier_id: str,
    state: Optional[m.SubInvestigationState] = None,
) -> list[m.SubInvestigation]:
    q = "SELECT * FROM sub_investigations WHERE dossier_id = ?"
    params: list[object] = [dossier_id]
    if state is not None:
        q += " AND state = ?"
        params.append(state.value)
    q += " ORDER BY started_at"
    with connect() as conn:
        rows = conn.execute(q, params).fetchall()
    return [_row_to_sub_investigation(r) for r in rows]


def update_sub_investigation_state(
    dossier_id: str,
    sub_id: str,
    patch: m.SubInvestigationStateUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        if patch.new_state == m.SubInvestigationState.blocked:
            conn.execute(
                "UPDATE sub_investigations SET state = ?, blocked_reason = ? WHERE id = ?",
                (patch.new_state.value, patch.reason, sub_id),
            )
        else:
            conn.execute(
                "UPDATE sub_investigations SET state = ?, blocked_reason = NULL WHERE id = ?",
                (patch.new_state.value, sub_id),
            )
        display = _row_get(existing, "title") or existing["scope"]
        _log_change(
            conn, dossier_id, work_session_id, "state_changed",
            f"sub-investigation '{display}': "
            f"{existing['state']} → {patch.new_state.value} ({patch.reason})",
        )
        if patch.new_state == m.SubInvestigationState.abandoned:
            _set_plan_item_status(
                conn, dossier_id, _row_get(existing, "plan_item_id"), "abandoned",
            )
        elif patch.new_state == m.SubInvestigationState.delivered:
            _set_plan_item_status(
                conn, dossier_id, _row_get(existing, "plan_item_id"), "completed",
            )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def update_sub_investigation(
    dossier_id: str,
    sub_id: str,
    patch: m.SubInvestigationUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    """Partial-merge update of a sub-investigation's semantic fields."""
    patch_data = patch.model_dump(exclude_none=True)
    if not patch_data:
        return get_sub_investigation(sub_id)
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        set_parts: list[str] = []
        values: list[object] = []
        for k, v in patch_data.items():
            if k in ("known_facts", "missing_facts"):
                set_parts.append(f"{k} = ?")
                values.append(json.dumps(v))
            elif k == "confidence":
                set_parts.append(f"{k} = ?")
                values.append(v.value if hasattr(v, "value") else str(v))
            else:
                set_parts.append(f"{k} = ?")
                values.append(v)
        values.append(sub_id)
        conn.execute(
            f"UPDATE sub_investigations SET {', '.join(set_parts)} WHERE id = ?",
            values,
        )
        if "confidence" in patch_data:
            old_conf = _row_get(existing, "confidence") or "unknown"
            new_conf_raw = patch_data["confidence"]
            new_conf = new_conf_raw.value if hasattr(new_conf_raw, "value") else str(new_conf_raw)
            if old_conf != new_conf:
                display = _row_get(existing, "title") or existing["scope"]
                _log_change(
                    conn, dossier_id, work_session_id, "state_changed",
                    f"sub-investigation '{display[:40]}': {old_conf} -> {new_conf}",
                )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def complete_sub_investigation(
    dossier_id: str,
    sub_id: str,
    data: m.SubInvestigationComplete,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            """
            UPDATE sub_investigations
            SET state = ?, return_summary = ?, findings_section_ids = ?,
                findings_artifact_ids = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                m.SubInvestigationState.delivered.value,
                data.return_summary,
                json.dumps(data.findings_section_ids),
                json.dumps(data.findings_artifact_ids),
                now_s,
                sub_id,
            ),
        )
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_completed",
            f"Completed sub-investigation '{existing['scope']}': {data.return_summary}",
        )
        _set_plan_item_status(
            conn, dossier_id, _row_get(existing, "plan_item_id"), "completed",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)


def abandon_sub_investigation(
    dossier_id: str,
    sub_id: str,
    reason: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.SubInvestigation]:
    now_s = _dt_str(m.utc_now())
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ? AND dossier_id = ?",
            (sub_id, dossier_id),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            "UPDATE sub_investigations SET state = ?, completed_at = ? WHERE id = ?",
            (m.SubInvestigationState.abandoned.value, now_s, sub_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "sub_investigation_abandoned",
            f"Abandoned sub-investigation '{existing['scope']}': {reason}",
        )
        _set_plan_item_status(
            conn, dossier_id, _row_get(existing, "plan_item_id"), "abandoned",
        )
        _touch_dossier(conn, dossier_id)
        row = conn.execute(
            "SELECT * FROM sub_investigations WHERE id = ?", (sub_id,)
        ).fetchone()
    return _row_to_sub_investigation(row)
