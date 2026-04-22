"""HTTP endpoints for the intake conversation flow.

Mirrors the patterns in ``routes.py`` and ``agent_routes.py``: a single
``APIRouter`` with prefix ``/api`` that main.py is expected to include.

The intake flow is a short conversation between the user and an LLM that
accumulates the five fields needed to spin up a Dossier. A session starts
in ``gathering`` and transitions (via agent tool use or the force-commit
escape hatch) to ``committed`` or ``abandoned``. Once it leaves
``gathering``, no more turns are accepted.

Routes:
  POST   /api/intake                 -> start_intake
  POST   /api/intake/{id}/message    -> send_message
  GET    /api/intake/{id}            -> get
  POST   /api/intake/{id}/commit     -> force_commit
  DELETE /api/intake/{id}            -> abandon
  GET    /api/intakes                -> list_all
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..agent.orchestrator import ORCHESTRATOR, AgentAlreadyRunning
from ..intake import storage, tools
from ..intake.models import (
    IntakeSession,
    IntakeStart,
    IntakeStatus,
    IntakeUserTurn,
)
from ..intake.runtime import IntakeAgent


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


async def _kickoff_dossier_agent(dossier_id: Optional[str]) -> None:
    """Auto-start the dossier agent after intake commit.

    The product story is "close the laptop, come back to an evolved
    dossier" — the agent must start working as soon as the dossier exists,
    not when the user happens to click something. We fire ORCHESTRATOR.start
    and swallow AgentAlreadyRunning so double-commit or concurrent callers
    don't break the commit path. Other errors are logged but not raised;
    the commit itself already succeeded and the user will see the dossier.
    """
    if not dossier_id:
        return
    try:
        await ORCHESTRATOR.start(dossier_id)
    except AgentAlreadyRunning:
        pass
    except Exception as exc:  # noqa: BLE001 — commit must not be rolled back
        logger.exception(
            "auto-start after intake commit failed: dossier=%s error=%r",
            dossier_id,
            exc,
        )


def _require_intake(intake_id: str) -> IntakeSession:
    session = storage.get_intake(intake_id)
    if session is None:
        raise HTTPException(404, "intake not found")
    return session


# ---------- intake lifecycle ----------


@router.post("/intake")
async def start_intake(body: Optional[IntakeStart] = None) -> dict:
    """Create a new intake session, optionally running one opening turn.

    If ``opening_message`` is provided, runs a single ``IntakeAgent`` turn
    on it and returns the assistant's first reply alongside the (now
    message-populated) IntakeSession.
    """
    intake = storage.create_intake()

    opening = body.opening_message if body is not None else None
    first_reply: Optional[str] = None

    if opening:
        agent = IntakeAgent(intake.id)
        result = await agent.process_turn(opening)
        first_reply = result.assistant_message
        # Refetch so the response includes the persisted transcript and
        # any status/state updates the turn produced.
        refreshed = storage.get_intake(intake.id)
        if refreshed is not None:
            intake = refreshed

    return {
        "intake": intake.model_dump(mode="json"),
        "first_reply": first_reply,
    }


@router.post("/intake/{intake_id}/message")
async def send_message(intake_id: str, body: IntakeUserTurn) -> dict:
    """Process one user turn against the intake agent.

    Returns the IntakeTurnResult as a dict. Runtime errors are surfaced
    via ``error`` in the body; HTTP status stays 200 in that case.
    """
    intake = _require_intake(intake_id)
    if intake.status != IntakeStatus.gathering:
        raise HTTPException(400, "intake not in gathering status")

    agent = IntakeAgent(intake_id)
    result = await agent.process_turn(body.content)

    # If this turn produced a dossier (agent called commit_intake), kick
    # off the dossier agent so the user returns to an active work session.
    await _kickoff_dossier_agent(result.dossier_id)

    return {
        "intake_status": result.intake_status.value,
        "state": result.state.model_dump(mode="json"),
        "assistant_message": result.assistant_message,
        "dossier_id": result.dossier_id,
        "error": result.error,
    }


@router.get("/intake/{intake_id}", response_model=IntakeSession)
def get(intake_id: str) -> IntakeSession:
    """Return the full intake session including all messages."""
    return _require_intake(intake_id)


@router.post("/intake/{intake_id}/commit")
async def force_commit(intake_id: str) -> dict:
    """Force-commit the intake's current state as a Dossier.

    Invokes the ``commit_intake`` handler directly (no agent turn). Used
    as a manual escape hatch when the user is done but the agent hasn't
    fired the commit itself.
    """
    intake = _require_intake(intake_id)
    if intake.status != IntakeStatus.gathering:
        raise HTTPException(400, "intake not in gathering status")

    result = tools.HANDLERS["commit_intake"](intake_id, {})

    if "error" in result:
        # Preserve the ``missing`` list when the handler returned it so
        # the client can present a targeted message.
        detail: dict = {"error": result["error"]}
        if "missing" in result:
            detail["missing"] = result["missing"]
        raise HTTPException(400, detail)

    # Kick off the dossier agent so the committed dossier becomes active
    # immediately — no "dead dossier" state between commit and first run.
    await _kickoff_dossier_agent(result["dossier_id"])

    return {"dossier_id": result["dossier_id"]}


@router.delete("/intake/{intake_id}")
def abandon(intake_id: str) -> dict:
    """Mark the intake as abandoned. Idempotent on already-abandoned;
    refuses to abandon a committed intake (that would orphan its dossier)."""
    intake = _require_intake(intake_id)
    if intake.status == IntakeStatus.abandoned:
        return {"ok": True}
    if intake.status == IntakeStatus.committed:
        raise HTTPException(
            400,
            {
                "error": "cannot abandon a committed intake",
                "dossier_id": intake.dossier_id,
            },
        )
    storage.update_intake_status(intake_id, IntakeStatus.abandoned)
    return {"ok": True}


# ---------- list view ----------


@router.get("/intakes", response_model=list[IntakeSession])
def list_all(status: Optional[IntakeStatus] = None) -> list[IntakeSession]:
    """List intakes, optionally filtered by status.

    Per storage.list_intakes, returned sessions do NOT include messages
    (the list view stays cheap).
    """
    return storage.list_intakes(status)
