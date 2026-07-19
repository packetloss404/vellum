"""Dossier CRUD, status computation, and dossier-level field updates."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from .. import models as m
from ..db import connect
from ._helpers import (
    _dt,
    _dt_str,
    _json_list,
    _log_change,
    _row_get,
    _row_to_dossier,
    _strip_tool_markup,
    _strip_tool_markup_list,
    _touch_dossier,
    ActiveWorkSessionExists,
    _SourceList,
    _OptionList,
)
from .decision_point_store import add_decision_point, list_decision_points
from .section_store import list_sections
from .needs_input_store import list_needs_input
from .log_store import append_reasoning
from .plan_items_store import (
    list_plan_items_with_conn,
    bulk_replace_plan_items_with_conn,
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
                                  status, check_in_policy, debrief, investigation_plan,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dossier.id,
                dossier.title,
                dossier.problem_statement,
                json.dumps(dossier.out_of_scope),
                dossier.dossier_type.value,
                dossier.status.value,
                dossier.check_in_policy.model_dump_json(),
                None,
                None,
                _dt_str(dossier.created_at),
                _dt_str(dossier.updated_at),
            ),
        )
    return dossier


def get_dossier(dossier_id: str) -> Optional[m.Dossier]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
        if row is None:
            return None
        dossier = _row_to_dossier(row)
        if dossier.investigation_plan is not None:
            plan_items = list_plan_items_with_conn(conn, dossier_id)
            dossier = dossier.model_copy(
                update={"investigation_plan": dossier.investigation_plan.model_copy(update={"items": plan_items})}
            )
        return dossier


def list_dossiers() -> list[m.Dossier]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM dossiers ORDER BY updated_at DESC").fetchall()
        result: list[m.Dossier] = []
        for r in rows:
            d = _row_to_dossier(r)
            if d.investigation_plan is not None:
                plan_items = list_plan_items_with_conn(conn, d.id)
                d = d.model_copy(
                    update={"investigation_plan": d.investigation_plan.model_copy(update={"items": plan_items})}
                )
            result.append(d)
        return result


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


def get_dossier_resume_state(dossier_id: str) -> Optional[dict]:
    """Compact "can we resume this dossier?" snapshot."""
    with connect() as conn:
        dossier_row = conn.execute(
            "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if dossier_row is None:
            return None

        plan_json = dossier_row["investigation_plan"]
        has_plan = plan_json is not None and plan_json != ""
        plan_approved = False
        if has_plan:
            try:
                plan = m.InvestigationPlan.model_validate_json(plan_json)
                plan_approved = plan.approved_at is not None
            except Exception:
                plan_approved = False

        active_row = conn.execute(
            "SELECT id FROM work_sessions "
            "WHERE dossier_id = ? AND ended_at IS NULL "
            "ORDER BY started_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
        active_work_session_id = active_row["id"] if active_row else None

        last_ended_row = conn.execute(
            "SELECT ended_at FROM work_sessions "
            "WHERE dossier_id = ? AND ended_at IS NOT NULL "
            "ORDER BY ended_at DESC LIMIT 1",
            (dossier_id,),
        ).fetchone()
        last_session_ended_at = (
            _dt(last_ended_row["ended_at"]) if last_ended_row else None
        )

        open_ni_row = conn.execute(
            "SELECT COUNT(*) AS n FROM needs_input "
            "WHERE dossier_id = ? AND answered_at IS NULL",
            (dossier_id,),
        ).fetchone()
        open_needs_input_count = int(open_ni_row["n"]) if open_ni_row else 0

        open_dp_row = conn.execute(
            "SELECT COUNT(*) AS n FROM decision_points "
            "WHERE dossier_id = ? AND resolved_at IS NULL",
            (dossier_id,),
        ).fetchone()
        open_decision_point_count = int(open_dp_row["n"]) if open_dp_row else 0

        delivered = dossier_row["status"] == m.DossierStatus.delivered.value

        wake_at_raw = _row_get(dossier_row, "wake_at")
        wake_pending = bool(_row_get(dossier_row, "wake_pending") or 0)
        wake_reason = _row_get(dossier_row, "wake_reason")

        return {
            "dossier_id": dossier_id,
            "has_plan": has_plan,
            "plan_approved": plan_approved,
            "active_work_session_id": active_work_session_id,
            "last_session_ended_at": last_session_ended_at,
            "last_visited_at": _dt(dossier_row["last_visited_at"]),
            "open_needs_input_count": open_needs_input_count,
            "open_decision_point_count": open_decision_point_count,
            "delivered": delivered,
            "wake_at": _dt(wake_at_raw) if wake_at_raw else None,
            "wake_pending": wake_pending,
            "wake_reason": wake_reason,
        }


def mark_dossier_visited(dossier_id: str) -> Optional[m.Dossier]:
    """Update last_visited_at when the user opens the dossier."""
    now = _dt_str(m.utc_now())
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET last_visited_at = ?, updated_at = ? WHERE id = ?",
            (now, now, dossier_id),
        )
    return get_dossier(dossier_id)


def get_dossier_full(dossier_id: str) -> Optional[m.DossierFull]:
    with connect() as conn:
        from ._helpers import (
            _row_to_section,
            _row_to_needs_input,
            _row_to_user_note,
            _row_to_decision_point,
            _row_to_reasoning,
            _row_to_ruled_out,
            _row_to_work_session,
            _row_to_next_action,
            _row_to_artifact,
            _row_to_sub_investigation,
            _row_to_investigation_log,
            _row_to_considered_and_rejected,
            _row_to_session_summary,
        )

        dossier_row = conn.execute(
            "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if dossier_row is None:
            return None
        dossier = _row_to_dossier(dossier_row)

        # Populate plan items from the plan_items table (authoritative source).
        if dossier.investigation_plan is not None:
            plan_items = list_plan_items_with_conn(conn, dossier_id)
            dossier = dossier.model_copy(
                update={"investigation_plan": dossier.investigation_plan.model_copy(update={"items": plan_items})}
            )

        sections = [
            _row_to_section(r) for r in conn.execute(
                'SELECT * FROM sections WHERE dossier_id = ? ORDER BY "order"',
                (dossier_id,),
            ).fetchall()
        ]
        needs_input = [
            _row_to_needs_input(r) for r in conn.execute(
                "SELECT * FROM needs_input WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        decision_points = [
            _row_to_decision_point(r) for r in conn.execute(
                "SELECT * FROM decision_points WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        user_notes = [
            _row_to_user_note(r) for r in conn.execute(
                "SELECT * FROM user_notes WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        reasoning_trail = [
            _row_to_reasoning(r) for r in conn.execute(
                "SELECT * FROM reasoning_trail WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        ruled_out = [
            _row_to_ruled_out(r) for r in conn.execute(
                "SELECT * FROM ruled_out WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        work_sessions = [
            _row_to_work_session(r) for r in conn.execute(
                "SELECT * FROM work_sessions WHERE dossier_id = ? ORDER BY started_at",
                (dossier_id,),
            ).fetchall()
        ]
        next_actions = [
            _row_to_next_action(r) for r in conn.execute(
                "SELECT * FROM next_actions WHERE dossier_id = ? ORDER BY priority",
                (dossier_id,),
            ).fetchall()
        ]
        artifacts = [
            _row_to_artifact(r) for r in conn.execute(
                "SELECT * FROM artifacts WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        sub_investigations = [
            _row_to_sub_investigation(r) for r in conn.execute(
                "SELECT * FROM sub_investigations WHERE dossier_id = ? ORDER BY started_at",
                (dossier_id,),
            ).fetchall()
        ]
        investigation_log = [
            _row_to_investigation_log(r) for r in conn.execute(
                "SELECT * FROM investigation_log WHERE dossier_id = ? "
                "ORDER BY created_at LIMIT ?",
                (dossier_id, 500),
            ).fetchall()
        ]
        considered_and_rejected = [
            _row_to_considered_and_rejected(r) for r in conn.execute(
                "SELECT * FROM considered_and_rejected WHERE dossier_id = ? "
                "ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]
        session_summaries = [
            _row_to_session_summary(r) for r in conn.execute(
                "SELECT * FROM session_summaries WHERE dossier_id = ? ORDER BY created_at",
                (dossier_id,),
            ).fetchall()
        ]

    return m.DossierFull(
        dossier=dossier,
        sections=sections,
        needs_input=needs_input,
        user_notes=user_notes,
        decision_points=decision_points,
        reasoning_trail=reasoning_trail,
        ruled_out=ruled_out,
        work_sessions=work_sessions,
        next_actions=next_actions,
        artifacts=artifacts,
        sub_investigations=sub_investigations,
        investigation_log=investigation_log,
        considered_and_rejected=considered_and_rejected,
        session_summaries=session_summaries,
    )


# ---------- Debrief ----------


def update_debrief(
    dossier_id: str,
    patch: m.DebriefUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Merge non-None fields into existing debrief, set last_updated, persist, log, touch."""
    with connect() as conn:
        row = conn.execute(
            "SELECT debrief FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_json = row["debrief"]
        if existing_json:
            current = m.Debrief.model_validate_json(existing_json)
        else:
            current = m.Debrief(last_updated=m.utc_now())
        sanitized_patch = {
            k: (_strip_tool_markup(v) if isinstance(v, str) else v)
            for k, v in patch.model_dump(exclude_none=True).items()
        }
        merged = current.model_copy(update=sanitized_patch)
        merged = merged.model_copy(update={"last_updated": m.utc_now()})
        conn.execute(
            "UPDATE dossiers SET debrief = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )
        note_parts = [k for k, v in patch.model_dump(exclude_none=True).items()]
        note = "Debrief updated: " + (", ".join(note_parts) if note_parts else "(no changes)")
        _log_change(conn, dossier_id, work_session_id, "debrief_updated", note)
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- WorkingTheory ----------


def update_working_theory(
    dossier_id: str,
    patch: m.WorkingTheoryUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Partial-merge update with a required-fields gate on first write."""
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT working_theory FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_raw = _row_get(row, "working_theory")
        current: Optional[m.WorkingTheory] = (
            m.WorkingTheory.model_validate_json(existing_raw)
            if existing_raw else None
        )
        patch_data = patch.model_dump(exclude_none=True)
        for _k in ("recommendation", "why", "what_would_change_it"):
            if _k in patch_data and isinstance(patch_data[_k], str):
                patch_data[_k] = _strip_tool_markup(patch_data[_k]) or ""
        if "unresolved_assumptions" in patch_data:
            patch_data["unresolved_assumptions"] = _strip_tool_markup_list(
                patch_data["unresolved_assumptions"]
            )
        if current is None:
            required = {"recommendation", "confidence", "why", "what_would_change_it"}
            missing = sorted(required - set(patch_data.keys()))
            if missing:
                raise ValueError(
                    "update_working_theory: first write must include all fields; "
                    f"missing: {', '.join(missing)}"
                )
            merged = m.WorkingTheory(
                recommendation=patch_data["recommendation"],
                confidence=m.WorkingTheoryConfidence(patch_data["confidence"])
                    if not isinstance(patch_data["confidence"], m.WorkingTheoryConfidence)
                    else patch_data["confidence"],
                why=patch_data["why"],
                what_would_change_it=patch_data["what_would_change_it"],
                unresolved_assumptions=patch_data.get("unresolved_assumptions", []),
                updated_at=now,
            )
            old_confidence = None
        else:
            merged = current.model_copy(update={**patch_data, "updated_at": now})
            old_confidence = current.confidence

        conn.execute(
            "UPDATE dossiers SET working_theory = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )

        confidence_changed = (
            old_confidence is not None and old_confidence != merged.confidence
        )
        changed_fields = list(patch_data.keys())
        note_body = (
            ", ".join(changed_fields) if changed_fields else "(no changes)"
        )
        if current is None:
            note = (
                f"Working theory drafted ({merged.confidence.value}): "
                f"{merged.recommendation[:120]}"
            )
        else:
            note = (
                f"Working theory updated ({merged.confidence.value}): "
                f"{note_body}"
            )
        _log_change(
            conn, dossier_id, work_session_id, "working_theory_updated", note,
        )
        if confidence_changed:
            _log_change(
                conn, dossier_id, work_session_id, "state_changed",
                f"working_theory: {old_confidence.value} → {merged.confidence.value}",
            )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- PremiseChallenge ----------


def update_premise_challenge(
    dossier_id: str,
    patch: m.PremiseChallengeUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Partial-merge update. First write requires all five content fields."""
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT premise_challenge FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_raw = _row_get(row, "premise_challenge")
        current: Optional[m.PremiseChallenge] = (
            m.PremiseChallenge.model_validate_json(existing_raw)
            if existing_raw else None
        )
        patch_data = patch.model_dump(exclude_none=True)
        for _k in ("original_question", "why_answering_now_is_risky", "safer_reframe"):
            if _k in patch_data and isinstance(patch_data[_k], str):
                patch_data[_k] = _strip_tool_markup(patch_data[_k]) or ""
        for _k in ("hidden_assumptions", "required_evidence_before_answering"):
            if _k in patch_data:
                patch_data[_k] = _strip_tool_markup_list(patch_data[_k])
        if current is None:
            required = {
                "original_question", "hidden_assumptions",
                "why_answering_now_is_risky", "safer_reframe",
                "required_evidence_before_answering",
            }
            missing = sorted(required - set(patch_data.keys()))
            if missing:
                raise ValueError(
                    "update_premise_challenge: first write must include all "
                    f"fields; missing: {', '.join(missing)}"
                )
            merged = m.PremiseChallenge(
                original_question=patch_data["original_question"],
                hidden_assumptions=patch_data["hidden_assumptions"],
                why_answering_now_is_risky=patch_data["why_answering_now_is_risky"],
                safer_reframe=patch_data["safer_reframe"],
                required_evidence_before_answering=patch_data["required_evidence_before_answering"],
                updated_at=now,
            )
        else:
            merged = current.model_copy(update={**patch_data, "updated_at": now})

        conn.execute(
            "UPDATE dossiers SET premise_challenge = ? WHERE id = ?",
            (merged.model_dump_json(), dossier_id),
        )
        changed_fields = list(patch_data.keys())
        note_body = ", ".join(changed_fields) if changed_fields else "(no changes)"
        note = (
            f"Premise challenge drafted: {merged.safer_reframe[:120]}"
            if current is None
            else f"Premise challenge updated: {note_body}"
        )
        _log_change(
            conn, dossier_id, work_session_id, "premise_challenge_updated", note,
        )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


# ---------- InvestigationPlan ----------


def _plan_revision_is_minor(
    current: m.InvestigationPlan, new_items: list[m.PlanItem]
) -> tuple[bool, str]:
    """Returns (is_minor, diff_summary)."""
    prior_by_id = {it.id: it for it in current.items}
    new_by_id = {it.id: it for it in new_items}
    removed = [iid for iid in prior_by_id if iid not in new_by_id]
    edited_questions: list[str] = []
    for iid, prior in prior_by_id.items():
        cur = new_by_id.get(iid)
        if cur is None:
            continue
        if (prior.question or "").strip() != (cur.question or "").strip():
            edited_questions.append(iid)
    added = [iid for iid in new_by_id if iid not in prior_by_id]
    if removed or edited_questions:
        return False, f"removed={len(removed)} edited_questions={len(edited_questions)} added={len(added)}"
    return True, f"added={len(added)}"


def update_investigation_plan(
    dossier_id: str,
    data: m.InvestigationPlanUpdate,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Replace items + rationale. Sets revised_at + increments revision_count if
    plan exists; sets drafted_at if new. Sets approved_at to now if approve=True
    and approved_at is None.

    Items are written to the plan_items table; the dossiers.investigation_plan
    JSON blob stores only the metadata (rationale, drafted_at, etc.) with an
    empty items list for backward compat with the JSON column.
    """
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT investigation_plan FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        existing_json = row["investigation_plan"]
        current: Optional[m.InvestigationPlan] = None
        minor: bool = False
        diff: str = ""
        if existing_json:
            current = m.InvestigationPlan.model_validate_json(existing_json)
            # Read existing items from plan_items table for minor-check
            current_items = list_plan_items_with_conn(conn, dossier_id)
            current_with_items = current.model_copy(update={"items": current_items})
            minor, diff = _plan_revision_is_minor(current_with_items, data.items)
            preserved_approved_at = (
                current.approved_at if (current.approved_at is None or minor) else None
            )
            new_plan = m.InvestigationPlan(
                items=[],
                rationale=data.rationale,
                drafted_at=current.drafted_at,
                approved_at=preserved_approved_at,
                revised_at=now,
                revision_count=current.revision_count + 1,
            )
        else:
            new_plan = m.InvestigationPlan(
                items=[],
                rationale=data.rationale,
                drafted_at=now,
                approved_at=None,
                revised_at=None,
                revision_count=0,
            )
        if data.approve and new_plan.approved_at is None:
            new_plan = new_plan.model_copy(update={"approved_at": now})
        # Write metadata to JSON blob (items list is empty — authoritative
        # items live in the plan_items table).
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (new_plan.model_dump_json(), dossier_id),
        )
        # Bulk-replace items in the plan_items table.
        # Convert any legacy InvestigationPlanItem objects to PlanItem.
        plan_items: list[m.PlanItem] = []
        for it in data.items:
            if isinstance(it, m.PlanItem):
                plan_items.append(it)
            else:
                plan_items.append(m.PlanItem(
                    id=it.id,
                    question=it.question,
                    rationale=it.rationale,
                    expected_sources=it.expected_sources,
                    as_sub_investigation=it.as_sub_investigation,
                    status=m.PlanItemStatus(it.status) if it.status else m.PlanItemStatus.planned,
                ))
        bulk_replace_plan_items_with_conn(conn, dossier_id, plan_items)
        if current is None:
            note = f"Plan drafted ({len(data.items)} items)"
        elif current.approved_at is not None:
            if minor:
                note = f"Plan revised (minor, approval preserved): {diff}"
            else:
                note = f"Plan revised (pivot — re-gated for approval): {diff}"
        else:
            note = f"Plan revised (rev {new_plan.revision_count}, {len(data.items)} items)"
        if data.approve:
            note += " — approved"
        _log_change(conn, dossier_id, work_session_id, "plan_updated", note)
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


def approve_investigation_plan(
    dossier_id: str,
    work_session_id: Optional[str] = None,
) -> Optional[m.Dossier]:
    """Stamp approved_at = now on the dossier's plan."""
    now = m.utc_now()
    with connect() as conn:
        row = conn.execute(
            "SELECT investigation_plan FROM dossiers WHERE id = ?", (dossier_id,)
        ).fetchone()
        if not row:
            return None
        plan_json = row["investigation_plan"]
        if not plan_json:
            return get_dossier(dossier_id)
        current = m.InvestigationPlan.model_validate_json(plan_json)
        if current.approved_at is not None:
            return get_dossier(dossier_id)
        item_count = conn.execute(
            "SELECT COUNT(*) FROM plan_items WHERE dossier_id = ?", (dossier_id,)
        ).fetchone()[0]
        approved = current.model_copy(update={"approved_at": now})
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (approved.model_dump_json(), dossier_id),
        )
        _log_change(
            conn, dossier_id, work_session_id, "plan_updated",
            f"Plan approved ({item_count} items)",
        )
        _touch_dossier(conn, dossier_id)
    return get_dossier(dossier_id)


def replan_dossier(dossier_id: str) -> dict:
    """Backfill or reset the plan_approval decision_point for a dossier."""
    dossier = get_dossier(dossier_id)
    if dossier is None:
        return {"ok": False, "reason": "not_found"}
    plan = dossier.investigation_plan
    if plan is None:
        return {"ok": False, "reason": "no_plan"}

    existing_open = [
        dp for dp in list_decision_points(dossier_id, open_only=True)
        if dp.kind == "plan_approval"
    ]
    plan_unapproved = False
    if plan.approved_at is not None:
        now = m.utc_now()
        unapproved = plan.model_copy(update={
            "approved_at": None,
            "revised_at": now,
            "revision_count": plan.revision_count + 1,
        })
        with connect() as conn:
            conn.execute(
                "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
                (unapproved.model_dump_json(), dossier_id),
            )
            _log_change(
                conn, dossier_id, None, "plan_updated",
                "Plan un-approved (replan requested); awaiting fresh approval.",
            )
            _touch_dossier(conn, dossier_id)
        plan_unapproved = True
    elif existing_open:
        return {
            "ok": True,
            "action": "already_pending",
            "dossier_id": dossier_id,
            "decision_point_id": existing_open[0].id,
            "plan_unapproved": False,
        }

    action = "replanned" if plan_unapproved else "backfilled"
    dp = add_decision_point(
        dossier_id,
        m.DecisionPointCreate(
            title="Approve investigation plan, or redirect?",
            options=[
                m.DecisionOption(
                    label="Approve",
                    implications=(
                        "Approve the plan as drafted. The agent will start "
                        "substantive investigation on its next wake."
                    ),
                    recommended=True,
                ),
                m.DecisionOption(
                    label="Redirect",
                    implications=(
                        "Ask the agent to reframe before starting — useful if "
                        "the plan is missing a key angle or assumes the wrong "
                        "framing. The agent will re-draft the plan and surface "
                        "a fresh approval."
                    ),
                    recommended=False,
                ),
            ],
            recommendation=(
                "Review the plan items above. Approve to unblock substantive "
                "work, or redirect if the framing is off."
            ),
            kind="plan_approval",
        ),
        work_session_id=None,
    )
    return {
        "ok": True,
        "action": action,
        "dossier_id": dossier_id,
        "decision_point_id": dp.id,
        "plan_unapproved": plan_unapproved,
    }


# ---------- Computed dossier status ----------


def _decision_point_is_plan_approval(row: sqlite3.Row) -> bool:
    """Decide whether a decision_points row is a plan-approval gate."""
    try:
        kind = row["kind"]
    except (IndexError, KeyError):
        kind = None
    if kind == "plan_approval":
        return True
    title = (row["title"] or "").lower()
    if "plan_approval" in title or "plan approval" in title:
        return True
    return "plan" in title and ("approve" in title or "approval" in title)


def _stuck_is_recent(last_stuck_at: datetime, last_visited_at: Optional[datetime]) -> bool:
    if last_visited_at is not None:
        return last_stuck_at > last_visited_at
    return (m.utc_now() - last_stuck_at) <= timedelta(hours=24)


def get_dossier_status(dossier_id: str) -> dict:
    """Single authoritative computed read for the dossier status indicator."""
    from .session_store import get_active_work_session

    dossier = get_dossier(dossier_id)
    if dossier is None:
        return {
            "dossier_id": dossier_id,
            "status": "not_found",
            "status_detail": "dossier not found",
            "active_work_session_id": None,
            "unresolved_plan_approval_id": None,
            "open_needs_input_count": 0,
            "open_decision_point_count": 0,
            "last_stuck_at": None,
            "delivered": False,
        }

    active_ws = get_active_work_session(dossier_id)
    active_ws_id = active_ws.id if active_ws else None

    with connect() as conn:
        dp_rows = conn.execute(
            "SELECT * FROM decision_points WHERE dossier_id = ? AND resolved_at IS NULL",
            (dossier_id,),
        ).fetchall()
        ni_rows = conn.execute(
            "SELECT id FROM needs_input WHERE dossier_id = ? AND answered_at IS NULL",
            (dossier_id,),
        ).fetchall()
        stuck_row = conn.execute(
            """
            SELECT created_at FROM investigation_log
             WHERE dossier_id = ? AND entry_type = ?
             ORDER BY created_at DESC LIMIT 1
            """,
            (dossier_id, m.InvestigationLogEntryType.stuck_declared.value),
        ).fetchone()

    unresolved_plan_approval_id: Optional[str] = None
    open_non_plan_dp_count = 0
    for row in dp_rows:
        if _decision_point_is_plan_approval(row):
            if unresolved_plan_approval_id is None:
                unresolved_plan_approval_id = row["id"]
        else:
            open_non_plan_dp_count += 1

    open_needs_input_count = len(ni_rows)
    last_stuck_at = _dt(stuck_row["created_at"]) if stuck_row else None

    delivered = dossier.status == m.DossierStatus.delivered

    if delivered:
        status = "delivered"
        detail = "dossier is delivered"
    else:
        running = False
        try:
            from ..agent.orchestrator import ORCHESTRATOR
            running = any(
                r.get("dossier_id") == dossier_id and r.get("status") == "running"
                for r in ORCHESTRATOR.list_active()
            )
        except Exception:  # noqa: BLE001
            running = False

        if running:
            status = "running"
            detail = "agent is actively running"
        elif (
            dossier.investigation_plan is not None
            and dossier.investigation_plan.approved_at is None
            and unresolved_plan_approval_id is not None
        ):
            status = "waiting_plan_approval"
            detail = "plan drafted; waiting for approval"
        elif open_needs_input_count > 0 or open_non_plan_dp_count > 0:
            status = "waiting_input"
            parts = []
            if open_needs_input_count > 0:
                parts.append(f"{open_needs_input_count} open question(s)")
            if open_non_plan_dp_count > 0:
                parts.append(f"{open_non_plan_dp_count} unresolved decision(s)")
            detail = "waiting on: " + ", ".join(parts)
        elif last_stuck_at is not None and _stuck_is_recent(
            last_stuck_at, dossier.last_visited_at
        ):
            status = "stuck"
            detail = "agent declared stuck and has not recovered"
        else:
            status = "idle"
            detail = "no active work"

    return {
        "dossier_id": dossier_id,
        "status": status,
        "status_detail": detail,
        "active_work_session_id": active_ws_id,
        "unresolved_plan_approval_id": unresolved_plan_approval_id,
        "open_needs_input_count": open_needs_input_count,
        "open_decision_point_count": open_non_plan_dp_count,
        "last_stuck_at": last_stuck_at,
        "delivered": delivered,
    }
