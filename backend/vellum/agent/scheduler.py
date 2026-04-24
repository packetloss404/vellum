"""Sleep-mode scheduler.

A single asyncio coroutine that polls SQLite every N seconds (default 30,
configured via ``VELLUM_SCHEDULER_POLL_SECONDS``) for dossiers that need to
wake. A dossier is "wake-ready" when EITHER:

  * ``dossiers.wake_pending = 1`` — set by:
      - ``lifecycle.reconcile_at_startup`` (crash-resume)
      - ``storage.resolve_needs_input`` (reactive wake on user answer)
  * ``dossiers.wake_at <= now`` — set by the agent via the ``schedule_wake``
    tool when a real-world time interval is the blocker.

For each ready dossier, the scheduler:

  1. Reads the current ``sleep_mode_enabled`` setting — if off, skips the
     tick. We keep the coroutine running so toggling the setting back on
     doesn't need a restart.
  2. Pre-creates a work_session with ``trigger=scheduled`` (Ian's call:
     both wake_at and wake_pending paths produce ``scheduled`` sessions;
     the semantic distinction lives in ``dossiers.wake_reason``).
  3. Calls ``ORCHESTRATOR.start(dossier_id)``. ``AgentAlreadyRunning`` and
     process-wide capacity pressure leave wake fields intact for retry.
  4. Clears ``wake_at`` and ``wake_pending`` only after a successful start.
     A storage failure leaves the flag set so the next tick retries.

Design choices intentionally not made:
  * Distributed locking — single-process Vellum. If we ever fork workers,
    the arch doc's Postgres ``FOR UPDATE SKIP LOCKED`` is the fault line.
  * APScheduler — would add a dependency for behavior we can express in
    ~100 lines here. See research/vellum_sleep_mode_architecture.md §4.4.
  * Hard budget termination — budgets in Vellum are soft signals (see
    stuck.py:8-9). The scheduler does not refuse to start based on spend.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .. import models as m
from .. import storage
from ..config import SCHEDULER_POLL_SECONDS
from .orchestrator import ORCHESTRATOR, AgentAlreadyRunning, AgentCapacityExceeded


logger = logging.getLogger(__name__)


class Scheduler:
    """Polling scheduler for wake-ready dossiers.

    One instance per process. ``start()`` launches the polling coroutine;
    ``stop()`` cancels it and waits briefly. Idempotent — calling ``start``
    twice returns the same task; calling ``stop`` on a never-started
    scheduler is a no-op.
    """

    def __init__(self, poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
        self.poll_seconds = max(1, int(poll_seconds))
        self._task: Optional[asyncio.Task] = None
        self._stopping: asyncio.Event = asyncio.Event()

    # ---------- lifecycle ----------

    def start(self) -> asyncio.Task:
        if self._task is not None and not self._task.done():
            return self._task
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="vellum-scheduler")
        logger.info("scheduler started (poll=%ds)", self.poll_seconds)
        return self._task

    async def stop(self, timeout: float = 5.0) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await asyncio.wait_for(_await_quiet(self._task), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("scheduler did not stop within %.1fs", timeout)
        self._task = None
        logger.info("scheduler stopped")

    # ---------- tick body ----------

    async def _run(self) -> None:
        # First tick runs immediately so crash-resume picks up as soon as
        # the lifespan finishes booting. Subsequent ticks wait poll_seconds.
        while not self._stopping.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A tick failing must never kill the scheduler. Log and
                # continue; next tick will try again.
                logger.exception("scheduler tick raised; continuing")
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self.poll_seconds
                )
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        # Respect the master switch. We still run the loop so a later
        # settings flip takes effect without a process restart — we just
        # skip the work.
        try:
            enabled = storage.get_setting("sleep_mode_enabled", True)
        except Exception:
            logger.warning("scheduler: failed to read sleep_mode_enabled; skipping tick", exc_info=True)
            return
        if not enabled:
            return

        try:
            ready = await asyncio.to_thread(storage.list_dossiers_ready_to_wake)
        except Exception:
            logger.warning("scheduler: failed to read wake-ready dossiers", exc_info=True)
            return

        for entry in ready:
            await self._wake_one(entry)

    async def _wake_one(self, entry: dict) -> None:
        dossier_id = entry["dossier_id"]
        reason = entry.get("wake_reason")

        # Pre-create a session with trigger=scheduled. If a DB session exists
        # but no orchestrator task owns it, treat it as stale crash debris and
        # close it before starting a fresh scheduled run.
        pre_created_session_id: Optional[str] = None
        try:
            active = await asyncio.to_thread(
                storage.get_active_work_session, dossier_id
            )
            if active is not None:
                running = False
                try:
                    running = bool(ORCHESTRATOR.status(dossier_id).get("running"))
                except Exception:
                    running = False
                if not running:
                    await asyncio.to_thread(
                        storage.end_work_session_with_reason,
                        active.id,
                        m.WorkSessionEndReason.crashed,
                    )
                    active = None
            if active is None:
                session = await asyncio.to_thread(
                    storage.start_work_session,
                    dossier_id,
                    m.WorkSessionTrigger.scheduled,
                )
                pre_created_session_id = session.id
        except Exception:
            logger.warning(
                "scheduler: failed to prepare session for dossier %s (reason=%s); "
                "will retry on next tick",
                dossier_id, reason, exc_info=True,
            )
            return

        try:
            await ORCHESTRATOR.start(
                dossier_id,
                expected_session_id=pre_created_session_id,
            )
        except (AgentAlreadyRunning, AgentCapacityExceeded) as exc:
            # Either someone got there first (user clicked Resume / prior
            # tick still running), or process-wide capacity is saturated.
            # Do NOT treat this as "wake satisfied": the currently-running
            # session took its state snapshot at its own start and has no
            # way to see a needs_input answer / decision resolution that
            # landed after that. If we clear wake_pending here, the change
            # the user made dies on the floor.
            #
            # Instead: keep wake_pending set, bail out without the clear
            # below. The next scheduler tick will retry; if the other
            # session has ended by then, a fresh session picks up the
            # user's change. If it's still running, we retry again — a
            # 30s poll is cheap.
            #
            # Clean up any session we just created so we don't leak.
            if pre_created_session_id is not None:
                try:
                    await asyncio.to_thread(
                        storage.end_work_session, pre_created_session_id
                    )
                except Exception:
                    logger.warning(
                        "scheduler: created session %s but couldn't close it "
                        "after wake deferral; next reconcile will clean up",
                        pre_created_session_id, exc_info=True,
                    )
            logger.info(
                "scheduler: dossier=%s wake deferred — %s; "
                "wake_pending retained for next tick (reason=%s)",
                dossier_id, type(exc).__name__, reason,
            )
            return
        except Exception:
            logger.error(
                "scheduler: failed to start agent for dossier %s (reason=%s); "
                "wake_pending retained for retry",
                dossier_id, reason, exc_info=True,
            )
            # Close the pre-created session so we don't accumulate orphans.
            if pre_created_session_id is not None:
                try:
                    await asyncio.to_thread(
                        storage.end_work_session, pre_created_session_id
                    )
                except Exception:
                    pass
            # Do NOT clear wake fields — next tick will retry.
            return

        # Clear wake fields only after a successful start. On failure we
        # leave them set so the next tick retries.
        try:
            await asyncio.to_thread(storage.clear_dossier_wake, dossier_id)
        except Exception:
            logger.warning(
                "scheduler: started agent for dossier %s but failed to clear "
                "wake fields; will be re-picked on next tick (start call will "
                "then raise AgentAlreadyRunning and be swallowed)",
                dossier_id, exc_info=True,
            )
        logger.info(
            "scheduler: woke dossier=%s reason=%s", dossier_id, reason
        )


async def _await_quiet(task: asyncio.Task) -> None:
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


# Process-wide singleton.
SCHEDULER = Scheduler()
