"""HTTP endpoints for the multi-dossier agent orchestrator.

Mirrors the pattern in ``routes.py``: a single ``APIRouter`` with prefix
``/api`` that main.py is expected to include. Routes translate orchestrator
exceptions into HTTP status codes:

  - 404 if the dossier doesn't exist
  - 409 on ``AgentAlreadyRunning``
  - 404 on ``AgentNotRunning``
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .. import models as m
from .. import storage
from ..agent.orchestrator import (
    ORCHESTRATOR,
    AgentAlreadyRunning,
    AgentCapacityExceeded,
    AgentNotRunning,
)
from ..config import AGENT_MAX_TURNS, MODEL_PRICING_USD_PER_MTOK


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api")

_VALID_MODELS: frozenset[str] = frozenset(MODEL_PRICING_USD_PER_MTOK.keys())


class StartAgentRequest(BaseModel):
    max_turns: int = Field(default=AGENT_MAX_TURNS, ge=1, le=AGENT_MAX_TURNS)
    model: Optional[str] = None

    @field_validator("model")
    @classmethod
    def model_must_be_known(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_MODELS:
            raise ValueError(
                f"unknown model {v!r}; valid models: {sorted(_VALID_MODELS)}"
            )
        return v


class ResearchPolicyRequest(BaseModel):
    policy: m.ResearchPolicy


class StartResearchRequest(BaseModel):
    policy: Optional[m.ResearchPolicy] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=200)


class RestartResearchRequest(StartResearchRequest):
    confirm: bool


def _require_dossier(dossier_id: str) -> None:
    if storage.get_dossier(dossier_id) is None:
        raise HTTPException(404, "dossier not found")


def _orchestrator_running(dossier_id: str) -> bool:
    try:
        return bool(ORCHESTRATOR.status(dossier_id).get("running"))
    except Exception:
        return False


# ---------- per-dossier agent control ----------


@router.post("/dossiers/{dossier_id}/agent/start")
async def start(
    dossier_id: str,
    body: Optional[StartAgentRequest] = None,
) -> dict:
    _require_dossier(dossier_id)
    params = body or StartAgentRequest()
    if storage.get_active_research_run(dossier_id) is not None:
        raise HTTPException(409, "an autonomous research run exists; use its research controls")
    # An explicit user start overrides self-heal quarantine and resets the
    # failure streak — the user is saying "try again".
    try:
        storage.clear_dossier_quarantine(dossier_id)
    except Exception:
        logger.warning(
            "agent/start: failed to clear quarantine for dossier %s",
            dossier_id, exc_info=True,
        )
    active = storage.get_active_work_session(dossier_id)
    if active is not None:
        if _orchestrator_running(dossier_id):
            raise HTTPException(409, "agent already running for this dossier")
        storage.end_work_session_with_reason(
            active.id, m.WorkSessionEndReason.crashed
        )

    research_run = storage.get_active_research_run(dossier_id)
    max_turns = params.max_turns
    trigger = m.WorkSessionTrigger.manual
    if research_run and research_run.status in {
        m.ResearchRunStatus.queued, m.ResearchRunStatus.running,
        m.ResearchRunStatus.waiting_for_user,
    }:
        trigger = m.WorkSessionTrigger.autonomous
        max_turns = research_run.policy_snapshot.max_turns_per_session
    holder: dict[str, str] = {}
    def create_session() -> str:
        session = storage.start_work_session(dossier_id, trigger=trigger)
        holder["id"] = session.id
        if trigger is m.WorkSessionTrigger.manual:
            storage.mark_work_session_launched(session.id)
        return session.id
    try:
        return await ORCHESTRATOR.start(
            dossier_id,
            max_turns=max_turns,
            model=params.model,
            session_factory=create_session,
        )
    except AgentAlreadyRunning:
        raise HTTPException(409, "agent already running for this dossier")
    except AgentCapacityExceeded:
        raise HTTPException(429, "agent capacity exceeded")
    except storage.ActiveWorkSessionExists as exc:
        return JSONResponse(status_code=409,content={"detail":"work_session already active for this dossier","dossier_id":dossier_id,"active_work_session_id":exc.session.id})


@router.post("/dossiers/{dossier_id}/agent/stop")
async def stop(dossier_id: str) -> dict:
    _require_dossier(dossier_id)
    try:
        result = await ORCHESTRATOR.stop(dossier_id, reason="user_stop")
        dossier = storage.get_dossier(dossier_id)
        if dossier is not None and dossier.research_policy.autonomy_enabled:
            storage.pause_autonomous_research(dossier_id, "stopped_by_user")
            wake = storage.get_dossier_wake_state(dossier_id)
            if wake and wake.get("wake_reason") == m.WakeReason.autonomous_continue.value:
                storage.clear_dossier_wake(dossier_id)
        return result
    except AgentNotRunning:
        raise HTTPException(404, "no active agent for this dossier")


@router.get("/dossiers/{dossier_id}/agent/status")
def status(dossier_id: str) -> dict:
    _require_dossier(dossier_id)
    return ORCHESTRATOR.status(dossier_id)


# ---------- fleet-wide view ----------


@router.get("/agents/running")
def list_running() -> list[dict]:
    return ORCHESTRATOR.list_running()


# ---------- resume (Day-3) ----------
#
# Resume is *explicit*: visiting a dossier is read-only (see
# ``POST /dossiers/{id}/visit`` in routes.py), and this endpoint is the
# single user-facing way to restart the agent on an existing dossier.
# The resume endpoint lives here (not routes.py) because it talks to the
# orchestrator.


@router.post("/dossiers/{dossier_id}/resume")
async def resume(dossier_id: str) -> dict:
    """Resume agent work on a dossier.

    - 404 if the dossier is missing
    - 409 if a work_session is already open on this dossier; the body
      includes ``active_work_session_id`` so the caller can surface the
      collision without another round-trip.
    - Otherwise: opens a new ``work_session`` with
      ``trigger=resume``, fires ``ORCHESTRATOR.start()`` in the
      background, and returns the new session id.

    The orchestrator call is fire-and-forget on purpose: the client
    doesn't need (and shouldn't wait for) the agent's first turn to
    finish before the UI re-renders the dossier.
    """
    if storage.get_dossier(dossier_id) is None:
        raise HTTPException(404, "dossier not found")
    if storage.get_active_research_run(dossier_id) is not None:
        raise HTTPException(409, "an autonomous research run exists; use its research controls")

    # An explicit user resume overrides self-heal quarantine and resets the
    # failure streak — the user is saying "try again".
    try:
        storage.clear_dossier_quarantine(dossier_id)
    except Exception:
        logger.warning(
            "resume: failed to clear quarantine for dossier %s",
            dossier_id, exc_info=True,
        )

    active = storage.get_active_work_session(dossier_id)
    if active is not None:
        # Parity with the /start route: if there's an active session
        # row but the orchestrator has no live task for it (the task
        # errored without going through done_callback, or the process
        # is alive but the task is dead), close the orphan and continue
        # with the resume. Otherwise the user is stuck waiting for a
        # process restart.
        if _orchestrator_running(dossier_id):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "work_session already active for this dossier",
                    "dossier_id": dossier_id,
                    "active_work_session_id": active.id,
                },
            )
        storage.end_work_session_with_reason(
            active.id, m.WorkSessionEndReason.crashed
        )

    try:
        session = storage.start_work_session(
            dossier_id, trigger=m.WorkSessionTrigger.resume
        )
    except storage.ActiveWorkSessionExists as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "work_session already active for this dossier",
                "dossier_id": dossier_id,
                "active_work_session_id": exc.session.id,
            },
        )

    # Fire-and-forget: don't block the HTTP response on the agent's
    # first turn. Any failure is caught + logged by the orchestrator's
    # own done-callback; we surface an AgentAlreadyRunning here only if
    # one slipped between the storage check above (extremely unlikely
    # given the storage-level guard, but belt + braces).
    try:
        await ORCHESTRATOR.start(dossier_id, expected_session_id=session.id)
    except AgentAlreadyRunning:
        # Close the session we just opened so we don't leak an orphan
        # row. Report the collision with the *pre-existing* session
        # we raced against, which is the one the caller cares about.
        try:
            storage.end_work_session(session.id)
        except Exception:
            logger.exception(
                "resume: failed to close just-created session %s after "
                "orchestrator reported AgentAlreadyRunning; will be "
                "cleaned up by next reconcile_at_startup",
                session.id,
            )
        active_now = storage.get_active_work_session(dossier_id)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "work_session already active for this dossier",
                "dossier_id": dossier_id,
                "active_work_session_id": (
                    active_now.id if active_now else None
                ),
            },
        )
    except AgentCapacityExceeded:
        try:
            storage.end_work_session(session.id)
        except Exception:
            logger.exception(
                "resume: failed to close just-created session %s after "
                "orchestrator capacity rejection",
                session.id,
            )
        raise HTTPException(429, "agent capacity exceeded")

    return {
        "dossier_id": dossier_id,
        "work_session_id": session.id,
        "status": "started",
    }


@router.get("/dossiers/{dossier_id}/resume-state")
def resume_state(dossier_id: str) -> dict:
    """Compact read-only snapshot of what the UI needs to decide whether
    to offer a resume action. 404 if the dossier is missing."""
    state = storage.get_dossier_resume_state(dossier_id)
    if state is None:
        raise HTTPException(404, "dossier not found")
    return state


# ---------- bounded autonomous long research ----------


@router.get(
    "/dossiers/{dossier_id}/research",
    response_model=m.ResearchProgress,
)
def research_progress(dossier_id: str) -> m.ResearchProgress:
    progress = storage.get_research_progress(dossier_id)
    if progress is None:
        raise HTTPException(404, "dossier not found")
    return progress


@router.put(
    "/dossiers/{dossier_id}/research/policy",
    response_model=m.ResearchProgress,
)
def save_research_policy(
    dossier_id: str, body: ResearchPolicyRequest
) -> m.ResearchProgress:
    dossier = storage.get_dossier(dossier_id)
    if dossier is None:
        raise HTTPException(404, "dossier not found")
    # Saving limits is not a lifecycle action. Preserve the current enabled
    # bit; POST /research/start and /research/pause own that transition.
    policy = body.policy.model_copy(
        update={
            "autonomy_enabled": dossier.research_policy.autonomy_enabled
        }
    )
    storage.update_research_policy(dossier_id, policy)
    progress = storage.get_research_progress(dossier_id)
    assert progress is not None
    return progress


@router.post(
    "/dossiers/{dossier_id}/research/start",
    response_model=m.ResearchProgress,
)
def start_research(
    dossier_id: str, body: Optional[StartResearchRequest] = None
) -> m.ResearchProgress:
    _require_dossier(dossier_id)
    if not bool(storage.get_setting("sleep_mode_enabled", True)):
        raise HTTPException(
            409,
            "sleep mode must be enabled before autonomous research can start",
        )
    try:
        progress = storage.start_autonomous_research(
            dossier_id,
            body.policy if body is not None else None,
            idempotency_key=body.idempotency_key if body is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if progress is None:
        raise HTTPException(404, "dossier not found")
    return progress


@router.post(
    "/dossiers/{dossier_id}/research/pause",
    response_model=m.ResearchProgress,
)
def pause_research(dossier_id: str) -> m.ResearchProgress:
    progress = storage.pause_autonomous_research(
        dossier_id, "paused_by_user"
    )
    if progress is None:
        raise HTTPException(404, "dossier not found")
    return progress


@router.get("/dossiers/{dossier_id}/research/runs", response_model=list[m.ResearchRun])
def research_runs(dossier_id: str) -> list[m.ResearchRun]:
    _require_dossier(dossier_id)
    return storage.list_research_runs(dossier_id)


@router.get("/dossiers/{dossier_id}/research/runs/{run_id}/evidence")
def research_run_evidence(dossier_id: str, run_id: str) -> dict:
    run = storage.get_research_run(run_id)
    if run is None or run.dossier_id != dossier_id:
        raise HTTPException(404, "research run not found")
    return storage.get_research_evidence(run_id)


@router.post("/dossiers/{dossier_id}/research/runs/{run_id}/pause", response_model=m.ResearchProgress)
def pause_research_run(dossier_id: str, run_id: str) -> m.ResearchProgress:
    active = storage.get_active_research_run(dossier_id)
    if active is None or active.id != run_id:
        raise HTTPException(409, "research run is not active")
    progress = storage.pause_autonomous_research(dossier_id, "paused_by_user")
    assert progress is not None
    return progress


@router.post("/dossiers/{dossier_id}/research/runs/{run_id}/resume", response_model=m.ResearchProgress)
def resume_research_run(dossier_id: str, run_id: str) -> m.ResearchProgress:
    try:
        progress = storage.resume_autonomous_research(dossier_id, run_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if progress is None: raise HTTPException(404, "research run not found")
    return progress


@router.post("/dossiers/{dossier_id}/research/restart", response_model=m.ResearchProgress)
def restart_research(dossier_id: str, body: RestartResearchRequest) -> m.ResearchProgress:
    if not body.confirm: raise HTTPException(400, "confirm must be true to replace the current run")
    try:
        progress = storage.restart_autonomous_research(dossier_id, body.policy, idempotency_key=body.idempotency_key)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if progress is None: raise HTTPException(404, "dossier not found")
    return progress


@router.get("/notifications")
def notifications(unread_only: bool = True) -> list[dict]:
    return storage.list_notifications(unread_only=unread_only)


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: str) -> dict:
    if not storage.mark_notification_read(notification_id):
        raise HTTPException(404, "notification not found")
    return {"id": notification_id, "is_read": True}


# ---------- day 3: computed dossier status ----------


@router.get("/dossiers/{dossier_id}/status")
def dossier_status(dossier_id: str) -> dict:
    """Single authoritative computed status for the dossier page indicator.

    See ``storage.get_dossier_status`` for the precedence rules. Returns 404
    if the dossier does not exist; otherwise returns the full status dict
    (``status`` is one of delivered/running/waiting_plan_approval/
    waiting_input/stuck/idle).
    """
    result = storage.get_dossier_status(dossier_id)
    if result["status"] == "not_found":
        raise HTTPException(404, "dossier not found")
    return result
