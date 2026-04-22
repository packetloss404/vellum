"""Multi-dossier agent orchestrator.

Owns the set of in-flight ``DossierAgent.run()`` tasks. One task per
dossier at a time; N dossiers run concurrently as independent
``asyncio.Task``s — no queueing.

Design notes:
  - ``_tasks: dict[str, asyncio.Task]`` keyed by dossier_id. Membership
    is the source of truth for "is an agent running for X?".
  - Every spawned task has a ``done_callback`` that removes itself from
    ``_tasks`` and logs the outcome. This handles the race between
    ``stop()`` and natural completion cleanly: whichever path finishes
    the task first, the callback prunes tracking exactly once.
  - ``stop()`` issues ``task.cancel()`` then awaits with a 30 s grace
    period. The callback still fires and prunes; ``stop()`` just waits
    for cancellation to propagate.
  - ``shutdown()`` cancels everything and awaits; safe to call from a
    FastAPI shutdown hook.
  - Exceptions raised inside the runtime are never silently swallowed:
    the done-callback logs them. The runtime itself is responsible for
    closing its own ``work_session`` on error.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger(__name__)


class AgentAlreadyRunning(Exception):
    """Raised by ``start()`` when a task is already active for the dossier."""


class AgentNotRunning(Exception):
    """Raised by ``stop()`` when no task is active for the dossier."""


# Import the real runtime lazily so this module is importable even if the
# runtime's transitive deps (e.g. anthropic SDK, MODEL config) aren't ready
# yet in a given environment. The ``__main__`` smoke test monkeypatches
# ``_runtime_cls`` with a mock to exercise the orchestrator structurally.
try:  # pragma: no cover - exercised indirectly
    from .runtime import DossierAgent as _RealDossierAgent  # type: ignore
    _runtime_cls: Any = _RealDossierAgent
except Exception as _import_err:  # pragma: no cover
    logger.warning("DossierAgent runtime not importable (%s); using stub.", _import_err)

    class _StubDossierAgent:
        def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
            self.dossier_id = dossier_id
            self.model = model

        async def run(self, max_turns: int = 200) -> Any:
            raise RuntimeError(
                "DossierAgent runtime is not available in this environment; "
                "inject a runtime by setting vellum.agent.orchestrator._runtime_cls."
            )

    _runtime_cls = _StubDossierAgent


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentOrchestrator:
    """Tracks active agent tasks across dossiers.

    One in-flight task per dossier is enforced. Multiple dossiers run in
    parallel as asyncio tasks — there is no queue.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._started_at: dict[str, str] = {}
        # Guards the start/stop critical sections so concurrent callers
        # can't both observe "no task" and both create one.
        self._lock = asyncio.Lock()

    # ---------- internal helpers ----------

    def _make_done_callback(self, dossier_id: str):
        def _on_done(task: asyncio.Task) -> None:
            # Prune tracking regardless of outcome. This is the single
            # place that removes entries from ``_tasks``; both natural
            # completion and cancellation funnel through here.
            self._tasks.pop(dossier_id, None)
            self._started_at.pop(dossier_id, None)
            if task.cancelled():
                logger.info("agent task cancelled: dossier=%s", dossier_id)
                return
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "agent task errored: dossier=%s error=%r",
                    dossier_id,
                    exc,
                    exc_info=exc,
                )
                return
            result = task.result()
            logger.info(
                "agent task finished: dossier=%s result=%r", dossier_id, result
            )

        return _on_done

    # ---------- public API ----------

    async def start(
        self,
        dossier_id: str,
        max_turns: int = 200,
        model: Optional[str] = None,
    ) -> dict:
        """Launch a ``DossierAgent.run()`` as an asyncio.Task.

        Raises ``AgentAlreadyRunning`` if a task already exists for this
        dossier. Returns a small descriptor of the launch.
        """
        async with self._lock:
            existing = self._tasks.get(dossier_id)
            if existing is not None and not existing.done():
                raise AgentAlreadyRunning(
                    f"agent already running for dossier {dossier_id}"
                )

            agent = _runtime_cls(dossier_id, model=model)
            started_at = _utcnow_iso()
            coro = agent.run(max_turns=max_turns)
            task = asyncio.create_task(coro, name=f"dossier-agent:{dossier_id}")
            task.add_done_callback(self._make_done_callback(dossier_id))
            self._tasks[dossier_id] = task
            self._started_at[dossier_id] = started_at

            logger.info(
                "agent started: dossier=%s model=%s max_turns=%d",
                dossier_id,
                model,
                max_turns,
            )
            return {
                "status": "started",
                "dossier_id": dossier_id,
                "started_at": started_at,
            }

    async def stop(self, dossier_id: str, reason: str = "user_stop") -> dict:
        """Cancel the running task and wait briefly for clean shutdown.

        Raises ``AgentNotRunning`` if nothing is active for this dossier.
        """
        # Snapshot under the lock so we don't fight a concurrent start().
        async with self._lock:
            task = self._tasks.get(dossier_id)
            if task is None or task.done():
                raise AgentNotRunning(
                    f"no active agent for dossier {dossier_id}"
                )
            started_at = self._started_at.get(dossier_id)
            task.cancel()

        stopped_cleanly = True
        try:
            await asyncio.wait_for(asyncio.shield(_await_quiet(task)), timeout=30)
        except asyncio.TimeoutError:
            stopped_cleanly = False
            logger.warning(
                "agent did not cancel within 30s: dossier=%s", dossier_id
            )

        logger.info(
            "agent stopped: dossier=%s reason=%s clean=%s",
            dossier_id,
            reason,
            stopped_cleanly,
        )
        return {
            "status": "stopped",
            "dossier_id": dossier_id,
            "reason": reason,
            "started_at": started_at,
            "stopped_cleanly": stopped_cleanly,
        }

    def status(self, dossier_id: str) -> dict:
        task = self._tasks.get(dossier_id)
        running = task is not None and not task.done()
        return {
            "running": running,
            "started_at": self._started_at.get(dossier_id) if running else None,
        }

    def list_running(self) -> list[dict]:
        out: list[dict] = []
        for dossier_id, task in list(self._tasks.items()):
            if task.done():
                continue
            out.append(
                {
                    "dossier_id": dossier_id,
                    "started_at": self._started_at.get(dossier_id),
                }
            )
        return out

    async def shutdown(self) -> None:
        """Cancel every active task and wait for them to finish.

        Intended as a FastAPI shutdown hook. Never raises — individual
        task failures are logged by the done-callback.
        """
        tasks = list(self._tasks.values())
        if not tasks:
            return
        logger.info("orchestrator shutdown: cancelling %d task(s)", len(tasks))
        for task in tasks:
            task.cancel()
        # Wait for everything to settle, but don't hang the app if a task
        # ignores cancellation. ``return_exceptions=True`` so one bad task
        # doesn't abort the gather.
        try:
            await asyncio.wait_for(
                asyncio.gather(*(_await_quiet(t) for t in tasks), return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.warning("orchestrator shutdown timed out after 30s; abandoning tasks")
        # The done-callbacks should have cleared _tasks already; belt + braces.
        self._tasks.clear()
        self._started_at.clear()


async def _await_quiet(task: asyncio.Task) -> None:
    """Await a task, swallowing CancelledError. Other exceptions are
    left to the done-callback to log."""
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        # The done-callback logs these with full tracebacks; re-raising
        # here would just produce noise in ``stop()`` / ``shutdown()``.
        pass


# Process-wide singleton. main.py wires this into shutdown hooks;
# routes import ORCHESTRATOR directly.
ORCHESTRATOR = AgentOrchestrator()


# ---------- structural smoke test ----------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Mock runtime so we don't need the real anthropic SDK / DB.
    class _MockRuntime:
        def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
            self.dossier_id = dossier_id
            self.model = model

        async def run(self, max_turns: int = 200) -> dict:
            # Long-ish so we can observe concurrency & cancellation.
            await asyncio.sleep(5.0)
            return {
                "reason": "ended_turn",
                "turns": 1,
                "session_id": f"ws-mock-{self.dossier_id}",
            }

    async def _main() -> int:
        # Inject the mock. When run as ``python -m vellum.agent.orchestrator``
        # this file executes under ``__name__ == "__main__"``; the orchestrator
        # class resolves ``_runtime_cls`` via the module globals of *this*
        # module, so patch the globals directly rather than re-importing (a
        # second import would produce a separate module object).
        globals()["_runtime_cls"] = _MockRuntime
        orch = AgentOrchestrator()

        # 1. Start two dossiers concurrently; both should be tracked.
        r_a = await orch.start("dos-A")
        r_b = await orch.start("dos-B")
        assert r_a["status"] == "started" and r_b["status"] == "started"
        assert orch.status("dos-A")["running"] is True
        assert orch.status("dos-B")["running"] is True
        print("[1] started two dossiers concurrently")

        # 2. list_running shows both.
        running = orch.list_running()
        ids = {r["dossier_id"] for r in running}
        assert ids == {"dos-A", "dos-B"}, ids
        print(f"[2] list_running -> {ids}")

        # 3. Starting A again raises AgentAlreadyRunning.
        try:
            await orch.start("dos-A")
        except AgentAlreadyRunning as e:
            print(f"[3] AgentAlreadyRunning as expected: {e}")
        else:
            print("[3] FAIL: expected AgentAlreadyRunning")
            return 1

        # 4. Stop B -> status(B).running == False.
        await orch.stop("dos-B", reason="test")
        assert orch.status("dos-B")["running"] is False
        print("[4] stopped dos-B; running=False")

        # 5. Stop nonexistent -> AgentNotRunning.
        try:
            await orch.stop("dos-does-not-exist")
        except AgentNotRunning as e:
            print(f"[5] AgentNotRunning as expected: {e}")
        else:
            print("[5] FAIL: expected AgentNotRunning")
            return 1

        # 6. shutdown() -> no tasks left.
        await orch.shutdown()
        # Give any final callbacks a tick.
        await asyncio.sleep(0)
        assert orch.list_running() == [], orch.list_running()
        print("[6] shutdown: no tasks remain")

        print("\nAll orchestrator smoke tests passed.")
        return 0

    sys.exit(asyncio.run(_main()))
