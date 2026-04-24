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
from pydantic import BaseModel, Field

from .. import models as m
from .. import storage
from ..agent.orchestrator import (
    ORCHESTRATOR,
    AgentAlreadyRunning,
    AgentCapacityExceeded,
    AgentNotRunning,
)
from ..config import AGENT_MAX_TURNS


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api")


class StartAgentRequest(BaseModel):
    max_turns: int = Field(default=AGENT_MAX_TURNS, ge=1, le=AGENT_MAX_TURNS)
    model: Optional[str] = None


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
    active = storage.get_active_work_session(dossier_id)
    if active is not None:
        if _orchestrator_running(dossier_id):
            raise HTTPException(409, "agent already running for this dossier")
        storage.end_work_session_with_reason(
            active.id, m.WorkSessionEndReason.crashed
        )

    try:
        session = storage.start_work_session(
            dossier_id, trigger=m.WorkSessionTrigger.manual
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

    try:
        return await ORCHESTRATOR.start(
            dossier_id,
            max_turns=params.max_turns,
            model=params.model,
            expected_session_id=session.id,
        )
    except AgentAlreadyRunning:
        try:
            storage.end_work_session(session.id)
        except Exception:
            logger.exception(
                "agent/start: failed to close just-created session %s after "
                "orchestrator reported AgentAlreadyRunning",
                session.id,
            )
        raise HTTPException(409, "agent already running for this dossier")
    except AgentCapacityExceeded:
        try:
            storage.end_work_session(session.id)
        except Exception:
            logger.exception(
                "agent/start: failed to close just-created session %s after "
                "orchestrator capacity rejection",
                session.id,
            )
        raise HTTPException(429, "agent capacity exceeded")


@router.post("/dossiers/{dossier_id}/agent/stop")
async def stop(dossier_id: str) -> dict:
    _require_dossier(dossier_id)
    try:
        return await ORCHESTRATOR.stop(dossier_id, reason="user_stop")
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

    active = storage.get_active_work_session(dossier_id)
    if active is not None:
        # 409 with structured body so the client gets both the error
        # detail AND the id of the offending session in one response.
        return JSONResponse(
            status_code=409,
            content={
                "detail": "work_session already active for this dossier",
                "dossier_id": dossier_id,
                "active_work_session_id": active.id,
            },
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
