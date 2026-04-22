from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import models as m
from .. import storage
from ..agent import telemetry

router = APIRouter(prefix="/api")


# ---------- dossier ----------


@router.post("/dossiers", response_model=m.Dossier)
def create_dossier(data: m.DossierCreate) -> m.Dossier:
    return storage.create_dossier(data)


@router.get("/dossiers", response_model=list[m.Dossier])
def list_dossiers() -> list[m.Dossier]:
    return storage.list_dossiers()


@router.get("/dossiers/{dossier_id}", response_model=m.DossierFull)
def get_dossier(dossier_id: str) -> m.DossierFull:
    full = storage.get_dossier_full(dossier_id)
    if not full:
        raise HTTPException(404, "dossier not found")
    return full


@router.patch("/dossiers/{dossier_id}", response_model=m.Dossier)
def update_dossier(dossier_id: str, patch: m.DossierUpdate) -> m.Dossier:
    result = storage.update_dossier(dossier_id, patch)
    if not result:
        raise HTTPException(404, "dossier not found")
    return result


@router.delete("/dossiers/{dossier_id}")
def delete_dossier(dossier_id: str) -> dict:
    if not storage.delete_dossier(dossier_id):
        raise HTTPException(404, "dossier not found")
    return {"ok": True}


@router.post("/dossiers/{dossier_id}/visit", response_model=m.Dossier)
def mark_visited(dossier_id: str) -> m.Dossier:
    result = storage.mark_dossier_visited(dossier_id)
    if not result:
        raise HTTPException(404, "dossier not found")
    return result


@router.get("/dossiers/{dossier_id}/change-log", response_model=list[m.ChangeLogEntry])
def change_log_since_visit(dossier_id: str) -> list[m.ChangeLogEntry]:
    return storage.list_change_log_since_last_visit(dossier_id)


# ---------- sections ----------


@router.post("/dossiers/{dossier_id}/sections", response_model=m.Section)
def upsert_section(
    dossier_id: str,
    data: m.SectionUpsert,
    work_session_id: Optional[str] = None,
) -> m.Section:
    try:
        return storage.upsert_section(dossier_id, data, work_session_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.patch("/dossiers/{dossier_id}/sections/{section_id}/state", response_model=m.Section)
def update_section_state(
    dossier_id: str,
    section_id: str,
    patch: m.SectionStateUpdate,
    work_session_id: Optional[str] = None,
) -> m.Section:
    try:
        return storage.update_section_state(dossier_id, section_id, patch, work_session_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/dossiers/{dossier_id}/sections/{section_id}")
def delete_section(
    dossier_id: str,
    section_id: str,
    reason: str,
    work_session_id: Optional[str] = None,
) -> dict:
    if not storage.delete_section(dossier_id, section_id, reason, work_session_id):
        raise HTTPException(404, "section not found")
    return {"ok": True}


@router.post("/dossiers/{dossier_id}/sections/reorder", response_model=list[m.Section])
def reorder_sections(
    dossier_id: str,
    section_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.Section]:
    try:
        return storage.reorder_sections(dossier_id, section_ids, work_session_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- needs_input ----------


@router.post("/dossiers/{dossier_id}/needs-input", response_model=m.NeedsInput)
def add_needs_input(
    dossier_id: str,
    data: m.NeedsInputCreate,
    work_session_id: Optional[str] = None,
) -> m.NeedsInput:
    return storage.add_needs_input(dossier_id, data, work_session_id)


@router.post("/dossiers/{dossier_id}/needs-input/{needs_input_id}/resolve", response_model=m.NeedsInput)
def resolve_needs_input(
    dossier_id: str,
    needs_input_id: str,
    data: m.NeedsInputResolve,
    work_session_id: Optional[str] = None,
) -> m.NeedsInput:
    result = storage.resolve_needs_input(dossier_id, needs_input_id, data.answer, work_session_id)
    if not result:
        raise HTTPException(404, "needs_input not found")
    return result


# ---------- decision_point ----------


@router.post("/dossiers/{dossier_id}/decision-points", response_model=m.DecisionPoint)
def add_decision_point(
    dossier_id: str,
    data: m.DecisionPointCreate,
    work_session_id: Optional[str] = None,
) -> m.DecisionPoint:
    return storage.add_decision_point(dossier_id, data, work_session_id)


@router.post("/dossiers/{dossier_id}/decision-points/{decision_id}/resolve", response_model=m.DecisionPoint)
def resolve_decision_point(
    dossier_id: str,
    decision_id: str,
    data: m.DecisionPointResolve,
    work_session_id: Optional[str] = None,
) -> m.DecisionPoint:
    result = storage.resolve_decision_point(dossier_id, decision_id, data.chosen, work_session_id)
    if not result:
        raise HTTPException(404, "decision_point not found")
    return result


# ---------- reasoning ----------


@router.post("/dossiers/{dossier_id}/reasoning", response_model=m.ReasoningTrailEntry)
def append_reasoning(
    dossier_id: str,
    data: m.ReasoningAppend,
    work_session_id: Optional[str] = None,
) -> m.ReasoningTrailEntry:
    return storage.append_reasoning(dossier_id, data, work_session_id)


# ---------- ruled_out ----------


@router.post("/dossiers/{dossier_id}/ruled-out", response_model=m.RuledOut)
def add_ruled_out(
    dossier_id: str,
    data: m.RuledOutCreate,
    work_session_id: Optional[str] = None,
) -> m.RuledOut:
    return storage.add_ruled_out(dossier_id, data, work_session_id)


# ---------- work_sessions ----------


@router.post("/dossiers/{dossier_id}/work-sessions", response_model=m.WorkSession)
def start_work_session(dossier_id: str, data: m.WorkSessionStart) -> m.WorkSession:
    return storage.start_work_session(dossier_id, data.trigger)


@router.post("/work-sessions/{session_id}/end", response_model=m.WorkSession)
def end_work_session(session_id: str) -> m.WorkSession:
    result = storage.end_work_session(session_id)
    if not result:
        raise HTTPException(404, "work_session not found")
    return result


# ---------- debrief ----------


@router.put("/dossiers/{dossier_id}/debrief", response_model=m.Dossier)
def update_debrief(
    dossier_id: str,
    patch: m.DebriefUpdate,
    work_session_id: Optional[str] = None,
) -> m.Dossier:
    result = storage.update_debrief(dossier_id, patch, work_session_id)
    if not result:
        raise HTTPException(404, "dossier not found")
    return result


# ---------- investigation_plan ----------


@router.put("/dossiers/{dossier_id}/investigation-plan", response_model=m.Dossier)
def update_investigation_plan(
    dossier_id: str,
    data: m.InvestigationPlanUpdate,
    work_session_id: Optional[str] = None,
) -> m.Dossier:
    result = storage.update_investigation_plan(dossier_id, data, work_session_id)
    if not result:
        raise HTTPException(404, "dossier not found")
    return result


# ---------- next_actions ----------


@router.post("/dossiers/{dossier_id}/next-actions", response_model=m.NextAction)
def add_next_action(
    dossier_id: str,
    data: m.NextActionCreate,
    work_session_id: Optional[str] = None,
) -> m.NextAction:
    return storage.add_next_action(dossier_id, data, work_session_id)


@router.get("/dossiers/{dossier_id}/next-actions", response_model=list[m.NextAction])
def list_next_actions(
    dossier_id: str,
    include_completed: bool = True,
) -> list[m.NextAction]:
    return storage.list_next_actions(dossier_id, include_completed=include_completed)


@router.post(
    "/dossiers/{dossier_id}/next-actions/{action_id}/complete",
    response_model=m.NextAction,
)
def complete_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> m.NextAction:
    result = storage.complete_next_action(dossier_id, action_id, work_session_id)
    if not result:
        raise HTTPException(404, "next_action not found")
    return result


@router.delete("/dossiers/{dossier_id}/next-actions/{action_id}")
def remove_next_action(
    dossier_id: str,
    action_id: str,
    work_session_id: Optional[str] = None,
) -> dict:
    if not storage.remove_next_action(dossier_id, action_id, work_session_id):
        raise HTTPException(404, "next_action not found")
    return {"ok": True}


@router.post(
    "/dossiers/{dossier_id}/next-actions/reorder",
    response_model=list[m.NextAction],
)
def reorder_next_actions(
    dossier_id: str,
    action_ids: list[str],
    work_session_id: Optional[str] = None,
) -> list[m.NextAction]:
    try:
        return storage.reorder_next_actions(dossier_id, action_ids, work_session_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- artifacts ----------


@router.post("/dossiers/{dossier_id}/artifacts", response_model=m.Artifact)
def create_artifact(
    dossier_id: str,
    data: m.ArtifactCreate,
    work_session_id: Optional[str] = None,
) -> m.Artifact:
    if not storage.get_dossier(dossier_id):
        raise HTTPException(404, "dossier not found")
    return storage.create_artifact(dossier_id, data, work_session_id)


@router.get("/dossiers/{dossier_id}/artifacts", response_model=list[m.Artifact])
def list_artifacts(dossier_id: str) -> list[m.Artifact]:
    return storage.list_artifacts(dossier_id)


@router.get("/artifacts/{artifact_id}", response_model=m.Artifact)
def get_artifact(artifact_id: str) -> m.Artifact:
    result = storage.get_artifact(artifact_id)
    if not result:
        raise HTTPException(404, "artifact not found")
    return result


@router.patch("/dossiers/{dossier_id}/artifacts/{artifact_id}", response_model=m.Artifact)
def update_artifact(
    dossier_id: str,
    artifact_id: str,
    patch: m.ArtifactUpdate,
    work_session_id: Optional[str] = None,
) -> m.Artifact:
    result = storage.update_artifact(dossier_id, artifact_id, patch, work_session_id)
    if not result:
        raise HTTPException(404, "artifact not found")
    return result


@router.delete("/dossiers/{dossier_id}/artifacts/{artifact_id}")
def delete_artifact(
    dossier_id: str,
    artifact_id: str,
    work_session_id: Optional[str] = None,
) -> dict:
    if not storage.delete_artifact(dossier_id, artifact_id, work_session_id):
        raise HTTPException(404, "artifact not found")
    return {"ok": True}


# ---------- sub_investigations ----------


class SubInvestigationAbandonBody(BaseModel):
    reason: str


@router.post("/dossiers/{dossier_id}/sub-investigations", response_model=m.SubInvestigation)
def spawn_sub_investigation(
    dossier_id: str,
    data: m.SubInvestigationSpawn,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    return storage.spawn_sub_investigation(dossier_id, data, work_session_id)


@router.get("/dossiers/{dossier_id}/sub-investigations", response_model=list[m.SubInvestigation])
def list_sub_investigations(
    dossier_id: str,
    state: Optional[m.SubInvestigationState] = None,
) -> list[m.SubInvestigation]:
    return storage.list_sub_investigations(dossier_id, state)


@router.get("/sub-investigations/{sub_id}", response_model=m.SubInvestigation)
def get_sub_investigation(sub_id: str) -> m.SubInvestigation:
    result = storage.get_sub_investigation(sub_id)
    if not result:
        raise HTTPException(404, "sub_investigation not found")
    return result


@router.post(
    "/dossiers/{dossier_id}/sub-investigations/{sub_id}/complete",
    response_model=m.SubInvestigation,
)
def complete_sub_investigation(
    dossier_id: str,
    sub_id: str,
    data: m.SubInvestigationComplete,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    result = storage.complete_sub_investigation(dossier_id, sub_id, data, work_session_id)
    if not result:
        raise HTTPException(404, "sub_investigation not found")
    return result


@router.patch(
    "/dossiers/{dossier_id}/sub-investigations/{sub_id}/state",
    response_model=m.SubInvestigation,
)
def update_sub_investigation_state(
    dossier_id: str,
    sub_id: str,
    patch: m.SubInvestigationStateUpdate,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    result = storage.update_sub_investigation_state(dossier_id, sub_id, patch, work_session_id)
    if not result:
        raise HTTPException(404, "sub_investigation not found")
    return result


@router.post(
    "/dossiers/{dossier_id}/sub-investigations/{sub_id}/abandon",
    response_model=m.SubInvestigation,
)
def abandon_sub_investigation(
    dossier_id: str,
    sub_id: str,
    data: SubInvestigationAbandonBody,
    work_session_id: Optional[str] = None,
) -> m.SubInvestigation:
    result = storage.abandon_sub_investigation(dossier_id, sub_id, data.reason, work_session_id)
    if not result:
        raise HTTPException(404, "sub_investigation not found")
    return result


# ---------- v2: investigation_log ----------


@router.post(
    "/dossiers/{dossier_id}/investigation-log",
    response_model=m.InvestigationLogEntry,
)
def append_investigation_log(
    dossier_id: str,
    data: m.InvestigationLogAppend,
    work_session_id: Optional[str] = None,
) -> m.InvestigationLogEntry:
    return storage.append_investigation_log(dossier_id, data, work_session_id)


@router.get(
    "/dossiers/{dossier_id}/investigation-log",
    response_model=list[m.InvestigationLogEntry],
)
def list_investigation_log(
    dossier_id: str,
    entry_type: Optional[m.InvestigationLogEntryType] = None,
    limit: int = 500,
) -> list[m.InvestigationLogEntry]:
    return storage.list_investigation_log(dossier_id, entry_type, limit)


@router.get("/dossiers/{dossier_id}/investigation-log/counts")
def investigation_log_counts(dossier_id: str) -> dict[str, int]:
    return storage.count_investigation_log_by_type(dossier_id)


# ---------- v2: considered_and_rejected ----------


@router.post(
    "/dossiers/{dossier_id}/considered-and-rejected",
    response_model=m.ConsideredAndRejected,
)
def add_considered_and_rejected(
    dossier_id: str,
    data: m.ConsideredAndRejectedCreate,
    work_session_id: Optional[str] = None,
) -> m.ConsideredAndRejected:
    return storage.add_considered_and_rejected(dossier_id, data, work_session_id)


@router.get(
    "/dossiers/{dossier_id}/considered-and-rejected",
    response_model=list[m.ConsideredAndRejected],
)
def list_considered_and_rejected(dossier_id: str) -> list[m.ConsideredAndRejected]:
    return storage.list_considered_and_rejected(dossier_id)


# ---------- telemetry / stats ----------


@router.get("/work-sessions/{session_id}/stats")
def work_session_stats(session_id: str) -> dict:
    stats = telemetry.session_stats(session_id)
    if stats is None:
        raise HTTPException(404, "work_session not found")
    return stats
