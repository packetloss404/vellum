"""Shared helpers for storage sub-modules.

Row converters, sanitizers, and internal helpers used across multiple domain
modules. Importing this module has no side effects — it never touches the DB.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Optional

from pydantic import TypeAdapter

from .. import models as m
from ..db import connect


# TypeAdapters for list[PydanticModel] round-trips.
_SourceList = TypeAdapter(list[m.Source])
_OptionList = TypeAdapter(list[m.DecisionOption])


# ---------- Tool-markup sanitizer ----------

_TOOL_MARKUP_RE = re.compile(
    r"""
    <\/?\s*(?:parameter|invoke|function_calls|tool_use|answer|thinking|result)
      (?:\s[^>]*)?>
    |
    <\/[a-z_][a-z0-9_]*>
    """,
    flags=re.IGNORECASE | re.VERBOSE,
)


def _strip_tool_markup(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    cleaned = _TOOL_MARKUP_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() if cleaned != text else cleaned


def _strip_tool_markup_list(items: Optional[list[str]]) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for v in items:
        if isinstance(v, str):
            cleaned = _strip_tool_markup(v)
            if cleaned:
                out.append(cleaned)
        else:
            out.append(v)
    return out


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


def _dt_str(dt: datetime) -> str:
    return dt.isoformat()


def _json_list(text: str) -> list:
    return json.loads(text) if text else []


# ---------- row → model converters ----------


def _row_get(row: sqlite3.Row, key: str, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default


def _row_to_dossier(row: sqlite3.Row) -> m.Dossier:
    debrief_json = row["debrief"]
    plan_json = row["investigation_plan"]
    theory_json = _row_get(row, "working_theory")
    pc_json = _row_get(row, "premise_challenge")

    debrief = m.Debrief.model_validate_json(debrief_json) if debrief_json else None
    if debrief is not None:
        debrief = debrief.model_copy(update={
            "what_i_did": _strip_tool_markup(debrief.what_i_did) or "",
            "what_i_found": _strip_tool_markup(debrief.what_i_found) or "",
            "what_you_should_do_next": _strip_tool_markup(debrief.what_you_should_do_next) or "",
            "what_i_couldnt_figure_out": _strip_tool_markup(debrief.what_i_couldnt_figure_out) or "",
        })

    working_theory = (
        m.WorkingTheory.model_validate_json(theory_json) if theory_json else None
    )
    if working_theory is not None:
        working_theory = working_theory.model_copy(update={
            "recommendation": _strip_tool_markup(working_theory.recommendation) or "",
            "why": _strip_tool_markup(working_theory.why) or "",
            "what_would_change_it": _strip_tool_markup(working_theory.what_would_change_it) or "",
            "unresolved_assumptions": _strip_tool_markup_list(working_theory.unresolved_assumptions),
        })

    premise_challenge = (
        m.PremiseChallenge.model_validate_json(pc_json) if pc_json else None
    )
    if premise_challenge is not None:
        premise_challenge = premise_challenge.model_copy(update={
            "original_question": _strip_tool_markup(premise_challenge.original_question) or "",
            "hidden_assumptions": _strip_tool_markup_list(premise_challenge.hidden_assumptions),
            "why_answering_now_is_risky": _strip_tool_markup(premise_challenge.why_answering_now_is_risky) or "",
            "safer_reframe": _strip_tool_markup(premise_challenge.safer_reframe) or "",
            "required_evidence_before_answering": _strip_tool_markup_list(premise_challenge.required_evidence_before_answering),
        })

    return m.Dossier(
        id=row["id"],
        title=row["title"],
        problem_statement=row["problem_statement"],
        out_of_scope=_json_list(row["out_of_scope"]),
        dossier_type=m.DossierType(row["dossier_type"]),
        status=m.DossierStatus(row["status"]),
        check_in_policy=m.CheckInPolicy.model_validate_json(row["check_in_policy"]),
        debrief=debrief,
        investigation_plan=(
            m.InvestigationPlan.model_validate_json(plan_json) if plan_json else None
        ),
        working_theory=working_theory,
        premise_challenge=premise_challenge,
        last_visited_at=_dt(row["last_visited_at"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


def _row_to_next_action(row: sqlite3.Row) -> m.NextAction:
    return m.NextAction(
        id=row["id"],
        dossier_id=row["dossier_id"],
        action=row["action"],
        rationale=row["rationale"],
        priority=int(row["priority"]),
        completed=bool(row["completed"]),
        completed_at=_dt(row["completed_at"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_section(row: sqlite3.Row) -> m.Section:
    return m.Section(
        id=row["id"],
        dossier_id=row["dossier_id"],
        type=m.SectionType(row["type"]),
        title=_strip_tool_markup(row["title"]) or "",
        content=_strip_tool_markup(row["content"]) or "",
        state=m.SectionState(row["state"]),
        order=row["order"],
        change_note=_strip_tool_markup(row["change_note"]) or "",
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
    kind = row["kind"] if "kind" in row.keys() else "generic"
    return m.DecisionPoint(
        id=row["id"],
        dossier_id=row["dossier_id"],
        title=row["title"],
        options=_OptionList.validate_json(row["options"]),
        recommendation=row["recommendation"],
        blocks_section_ids=_json_list(row["blocks_section_ids"]),
        kind=kind or "generic",
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
    end_reason_raw = _row_get(row, "end_reason")
    end_reason = m.WorkSessionEndReason(end_reason_raw) if end_reason_raw else None
    return m.WorkSession(
        id=row["id"],
        dossier_id=row["dossier_id"],
        started_at=_dt(row["started_at"]),
        ended_at=_dt(row["ended_at"]),
        trigger=m.WorkSessionTrigger(row["trigger"]),
        token_budget_used=row["token_budget_used"],
        input_tokens=_row_get(row, "input_tokens") or 0,
        output_tokens=_row_get(row, "output_tokens") or 0,
        cost_usd=_row_get(row, "cost_usd") or 0.0,
        end_reason=end_reason,
        trace_id=_row_get(row, "trace_id") or "",
    )


def _row_to_agent_turn(row: sqlite3.Row) -> m.AgentTurn:
    return m.AgentTurn(
        id=row["id"],
        dossier_id=row["dossier_id"],
        work_session_id=row["work_session_id"],
        sub_investigation_id=_row_get(row, "sub_investigation_id"),
        trace_id=row["trace_id"],
        turn_index=int(row["turn_index"]),
        model=row["model"],
        input_tokens=int(row["input_tokens"] or 0),
        output_tokens=int(row["output_tokens"] or 0),
        cache_creation_input_tokens=int(row["cache_creation_input_tokens"] or 0),
        cache_read_input_tokens=int(row["cache_read_input_tokens"] or 0),
        cost_usd=float(row["cost_usd"] or 0.0),
        duration_ms=int(row["duration_ms"] or 0),
        tool_calls_count=int(row["tool_calls_count"] or 0),
        stop_reason=_row_get(row, "stop_reason"),
        notes=_row_get(row, "notes"),
        created_at=_dt(row["created_at"]),
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


def _row_to_artifact(row: sqlite3.Row) -> m.Artifact:
    return m.Artifact(
        id=row["id"],
        dossier_id=row["dossier_id"],
        kind=m.ArtifactKind(row["kind"]),
        title=row["title"],
        content=row["content"],
        intended_use=row["intended_use"],
        state=m.ArtifactState(row["state"]),
        kind_note=row["kind_note"],
        supersedes=row["supersedes"],
        last_updated=_dt(row["last_updated"]),
        created_at=_dt(row["created_at"]),
    )


def _row_to_sub_investigation(row: sqlite3.Row) -> m.SubInvestigation:
    return m.SubInvestigation(
        id=row["id"],
        dossier_id=row["dossier_id"],
        parent_section_id=row["parent_section_id"],
        plan_item_id=_row_get(row, "plan_item_id"),
        title=_row_get(row, "title"),
        scope=row["scope"],
        questions=_json_list(row["questions"]),
        state=m.SubInvestigationState(row["state"]),
        return_summary=row["return_summary"],
        findings_section_ids=_json_list(row["findings_section_ids"]),
        findings_artifact_ids=_json_list(row["findings_artifact_ids"]),
        why_it_matters=_row_get(row, "why_it_matters"),
        known_facts=_json_list(_row_get(row, "known_facts") or "[]"),
        missing_facts=_json_list(_row_get(row, "missing_facts") or "[]"),
        current_finding=_row_get(row, "current_finding"),
        recommended_next_step=_row_get(row, "recommended_next_step"),
        confidence=m.InvestigationConfidence(_row_get(row, "confidence") or "unknown"),
        blocked_reason=_row_get(row, "blocked_reason"),
        started_at=_dt(row["started_at"]),
        completed_at=_dt(row["completed_at"]),
    )


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


def _row_to_session_summary(row: sqlite3.Row) -> m.SessionSummary:
    return m.SessionSummary(
        session_id=row["session_id"],
        dossier_id=row["dossier_id"],
        summary=row["summary"] or "",
        confirmed=_json_list(row["confirmed"]),
        ruled_out=_json_list(row["ruled_out"]),
        blocked_on=_json_list(row["blocked_on"]),
        questions_advanced=_json_list(_row_get(row, "questions_advanced") or "[]"),
        recommended_next_action=row["recommended_next_action"],
        cost_usd=float(row["cost_usd"] or 0.0),
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
    conn.execute(
        """
        INSERT INTO change_log (id, dossier_id, work_session_id, section_id, kind, change_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m.new_id("chg"),
            dossier_id,
            work_session_id or "system",
            section_id,
            kind,
            change_note,
            _dt_str(m.utc_now()),
        ),
    )


class ActiveWorkSessionExists(Exception):
    """Raised when a dossier already has an open work_session."""

    def __init__(self, session: m.WorkSession) -> None:
        self.session = session
        super().__init__(
            f"work_session already active for dossier {session.dossier_id}: {session.id}"
        )


# Ordering constant shared by sections and next_actions.
_ORDER_STEP = 10.0
