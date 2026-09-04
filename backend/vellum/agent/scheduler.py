"""Lease-based scheduler for autonomous research plus legacy dossier wakes."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .. import models as m, storage
from ..config import SCHEDULER_POLL_SECONDS
from .orchestrator import ORCHESTRATOR, AgentAlreadyRunning, AgentCapacityExceeded

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
        self.poll_seconds = max(1, int(poll_seconds))
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()
        self._lease_owner = f"scheduler:{uuid.uuid4().hex}"

    def start(self) -> asyncio.Task:
        if self._task is not None and not self._task.done(): return self._task
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="vellum-scheduler")
        return self._task

    async def stop(self, timeout: float = 5.0) -> None:
        if self._task is None: return
        self._stopping.set(); self._task.cancel()
        try: await asyncio.wait_for(_await_quiet(self._task), timeout=timeout)
        except asyncio.TimeoutError: logger.warning("scheduler did not stop within %.1fs", timeout)
        self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try: await self._tick()
            except asyncio.CancelledError: raise
            except Exception: logger.exception("scheduler tick raised; continuing")
            try: await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError: pass

    async def _tick(self) -> None:
        try: enabled = storage.get_setting("sleep_mode_enabled", True)
        except Exception:
            logger.warning("scheduler: failed to read sleep setting", exc_info=True); return
        if not enabled: return

        try:
            research = await asyncio.to_thread(storage.lease_due_research_wakes, self._lease_owner)
        except Exception:
            logger.warning("scheduler: failed to lease research wakes", exc_info=True)
            research = []
        handled = set()
        for entry in research:
            handled.add(entry["dossier_id"])
            await self._wake_research(entry)

        # One-release compatibility for non-research and pre-migration wakes.
        try:
            ready = await asyncio.to_thread(storage.list_dossiers_ready_to_wake)
        except Exception:
            logger.warning("scheduler: failed to read legacy wakes", exc_info=True)
            return
        for entry in ready:
            if entry["dossier_id"] not in handled and storage.get_active_research_run(entry["dossier_id"]) is None:
                await self._wake_one(entry)

    async def _wake_research(self, entry: dict) -> None:
        dossier_id=entry["dossier_id"]; wake_id=entry["id"]; run_id=entry["run_id"]
        policy=m.ResearchPolicy.model_validate_json(entry["policy_snapshot"])
        holder: dict[str, str] = {}

        def create_session() -> str:
            session_id = storage.claim_research_wake_session(wake_id, self._lease_owner)
            holder["id"] = session_id
            return session_id

        try:
            await ORCHESTRATOR.start(dossier_id, max_turns=policy.max_turns_per_session, session_factory=create_session)
        except (AgentAlreadyRunning, AgentCapacityExceeded):
            # Crucially, capacity is checked before session_factory executes.
            await asyncio.to_thread(storage.release_research_wake, wake_id, self._lease_owner)
            return
        except Exception:
            logger.warning("scheduler: research wake failed for %s", dossier_id, exc_info=True)
            if "id" in holder:
                await asyncio.to_thread(storage.end_work_session_with_reason, holder["id"], m.WorkSessionEndReason.error)
            else:
                await asyncio.to_thread(storage.release_research_wake, wake_id, self._lease_owner)
            return
        logger.info("scheduler: launched research run=%s dossier=%s wake=%s turns=%d", run_id, dossier_id, wake_id, policy.max_turns_per_session)

    async def _wake_one(self, entry: dict) -> None:
        dossier_id=entry["dossier_id"]; reason=entry.get("wake_reason")
        wake_at=entry.get("wake_at")
        if wake_at and entry.get("wake_pending"):
            try:
                parsed=datetime.fromisoformat(wake_at.replace("Z","+00:00")); parsed=parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                if parsed > datetime.now(timezone.utc): return
            except (ValueError,TypeError): pass
        active=await asyncio.to_thread(storage.get_active_work_session,dossier_id)
        if active is not None:
            try: running=bool(ORCHESTRATOR.status(dossier_id).get("running"))
            except Exception: running=False
            if running: return
            await asyncio.to_thread(storage.end_work_session_with_reason,active.id,m.WorkSessionEndReason.crashed)

        holder: dict[str,str]={}
        def create_session() -> str:
            session=storage.start_work_session(dossier_id,m.WorkSessionTrigger.scheduled)
            holder["id"]=session.id
            storage.mark_work_session_launched(session.id)
            return session.id
        try:
            await ORCHESTRATOR.start(dossier_id,session_factory=create_session)
        except (AgentAlreadyRunning,AgentCapacityExceeded): return
        except Exception:
            if "id" in holder: await asyncio.to_thread(storage.end_work_session_with_reason,holder["id"],m.WorkSessionEndReason.error)
            return
        await asyncio.to_thread(storage.clear_dossier_wake,dossier_id)
        logger.info("scheduler: woke dossier=%s reason=%s",dossier_id,reason)


async def _await_quiet(task: asyncio.Task) -> None:
    try: await task
    except (asyncio.CancelledError,Exception): pass


SCHEDULER=Scheduler()
