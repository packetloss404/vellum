"""HTTP endpoints for the multi-dossier agent orchestrator.

Mirrors the pattern in ``routes.py``: a single ``APIRouter`` with prefix
``/api`` that main.py is expected to include. Routes translate orchestrator
exceptions into HTTP status codes:

  - 404 if the dossier doesn't exist
  - 409 on ``AgentAlreadyRunning``
  - 404 on ``AgentNotRunning``
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..agent.orchestrator import (
    ORCHESTRATOR,
    AgentAlreadyRunning,
    AgentNotRunning,
)


router = APIRouter(prefix="/api")


class StartAgentRequest(BaseModel):
    max_turns: int = Field(default=200, ge=1)
    model: Optional[str] = None


def _require_dossier(dossier_id: str) -> None:
    if storage.get_dossier(dossier_id) is None:
        raise HTTPException(404, "dossier not found")


# ---------- per-dossier agent control ----------


@router.post("/dossiers/{dossier_id}/agent/start")
async def start(
    dossier_id: str,
    body: Optional[StartAgentRequest] = None,
) -> dict:
    _require_dossier(dossier_id)
    params = body or StartAgentRequest()
    try:
        return await ORCHESTRATOR.start(
            dossier_id,
            max_turns=params.max_turns,
            model=params.model,
        )
    except AgentAlreadyRunning:
        raise HTTPException(409, "agent already running for this dossier")


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
