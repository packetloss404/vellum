from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import models as m
from .. import storage

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
