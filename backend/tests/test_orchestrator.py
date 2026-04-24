"""Tests for ``vellum.agent.orchestrator.AgentOrchestrator``.

Day-2 contract: parallel dossier runs, one in-flight per dossier,
graceful shutdown, sub-investigation-compatible long runs, and a
``list_active()`` observability hook.

We avoid adding ``pytest-asyncio`` by running each async body under
``asyncio.run`` inside an ordinary sync test function. Every mocked
run uses a small sleep (50-200ms) so the whole module finishes well
under five seconds.

A tiny ``_MockRuntime`` stands in for ``DossierAgent``. The orchestrator
resolves the runtime class through the module global ``_runtime_cls``;
each test patches that global via ``monkeypatch`` and builds a fresh
``AgentOrchestrator`` instance so there is no cross-test state.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import pytest

from vellum.agent import orchestrator as orch_mod
from vellum.agent.orchestrator import (
    AgentAlreadyRunning,
    AgentCapacityExceeded,
    AgentNotRunning,
    AgentOrchestrator,
)


# ---------- mock runtimes ----------


class _SleepRuntime:
    """Baseline mock: sleep for ``duration`` seconds then return a fake result.

    The orchestrator invokes ``run(max_turns=...)`` — accept and ignore it.
    """

    # Class-level so tests can override per-instance by swapping the class.
    duration = 0.1

    def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
        self.dossier_id = dossier_id
        self.model = model

    async def run(self, max_turns: int = 200) -> dict:
        await asyncio.sleep(self.duration)
        return {
            "reason": "ended_turn",
            "turns": 1,
            "session_id": f"ws-mock-{self.dossier_id}",
        }


def _runtime_cls_with_duration(duration: float) -> type:
    """Build a _SleepRuntime subclass with the given sleep duration."""

    class _R(_SleepRuntime):
        pass

    _R.duration = duration
    return _R


# ---------- fixtures ----------


@pytest.fixture()
def orch(monkeypatch: pytest.MonkeyPatch) -> AgentOrchestrator:
    """Fresh orchestrator with the mock runtime wired in."""
    monkeypatch.setattr(orch_mod, "_runtime_cls", _SleepRuntime)
    return AgentOrchestrator()


# ---------- tests ----------


def test_cross_dossier_runs_are_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two dossiers launched concurrently should finish in roughly
    max(d1, d2) wall time, not d1 + d2.

    Uses a generous upper bound (1.6x the single-run duration) to
    absorb scheduler jitter on Windows CI.
    """
    duration = 0.2
    monkeypatch.setattr(orch_mod, "_runtime_cls", _runtime_cls_with_duration(duration))
    orch = AgentOrchestrator()

    async def _body() -> tuple[float, float]:
        # Sequential baseline: same work, one after the other.
        t0 = time.perf_counter()
        await orch.start("seq-A")
        await orch._tasks["seq-A"]
        await orch.start("seq-B")
        await orch._tasks["seq-B"]
        sequential = time.perf_counter() - t0

        # Parallel: both started, then awaited together.
        t0 = time.perf_counter()
        await orch.start("par-A")
        await orch.start("par-B")
        await asyncio.gather(orch._tasks["par-A"], orch._tasks["par-B"])
        parallel = time.perf_counter() - t0

        return sequential, parallel

    sequential, parallel = asyncio.run(_body())

    # Parallel must be meaningfully faster than sequential — at least
    # 1.5x. If the orchestrator silently serialized, parallel ~= sequential.
    assert parallel < sequential / 1.5, (
        f"cross-dossier parallelism regression: "
        f"sequential={sequential:.3f}s parallel={parallel:.3f}s"
    )
    # And parallel should be close to a single run's duration.
    assert parallel < duration * 1.8, (
        f"parallel wall-time too high: {parallel:.3f}s vs single-run {duration:.3f}s"
    )


def test_second_start_for_same_dossier_is_rejected(orch: AgentOrchestrator) -> None:
    async def _body() -> None:
        await orch.start("dup")
        try:
            await orch.start("dup")
        except AgentAlreadyRunning:
            pass
        else:
            raise AssertionError("expected AgentAlreadyRunning on duplicate start")
        # Task is still the first one; let it finish cleanly.
        await orch._tasks["dup"]

    asyncio.run(_body())


def test_start_same_dossier_after_completion_succeeds(orch: AgentOrchestrator) -> None:
    """Re-starting a dossier once its prior task has completed is allowed."""

    async def _body() -> None:
        await orch.start("reuse")
        await orch._tasks["reuse"]
        # Done-callback should have pruned _tasks; next start is clean.
        # Yield once to let the done-callback run.
        await asyncio.sleep(0)
        assert "reuse" not in orch._tasks
        await orch.start("reuse")
        await orch._tasks["reuse"]

    asyncio.run(_body())


def test_shutdown_cancels_in_flight_and_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long-running tasks must be cancelled and awaited by shutdown."""
    # Long enough that shutdown *must* cancel to finish quickly.
    monkeypatch.setattr(orch_mod, "_runtime_cls", _runtime_cls_with_duration(5.0))
    orch = AgentOrchestrator()

    async def _body() -> None:
        await orch.start("long-A")
        await orch.start("long-B")
        task_a = orch._tasks["long-A"]
        task_b = orch._tasks["long-B"]

        t0 = time.perf_counter()
        await orch.shutdown()
        elapsed = time.perf_counter() - t0

        # Shutdown should be fast — certainly well under the 5s sleep.
        assert elapsed < 1.0, f"shutdown took too long: {elapsed:.3f}s"
        assert task_a.cancelled() or task_a.done()
        assert task_b.cancelled() or task_b.done()
        # _tasks should be empty after shutdown.
        assert orch._tasks == {}
        assert orch._started_at == {}

    asyncio.run(_body())


def test_list_active_reflects_state_before_during_after(
    orch: AgentOrchestrator,
) -> None:
    async def _body() -> None:
        # Before: empty.
        assert orch.list_active() == []

        await orch.start("obs-A")
        await orch.start("obs-B")

        # During: both tracked with a status. Give the loop a tick so
        # the coroutines actually start executing (status == "running").
        await asyncio.sleep(0)
        active = orch.list_active()
        ids = {e["dossier_id"] for e in active}
        assert ids == {"obs-A", "obs-B"}, ids
        for entry in active:
            assert "started_at" in entry
            assert entry["status"] in {"running", "scheduled"}

        # Stop A; let the done-callback run; list_active no longer shows A.
        await orch.stop("obs-A")
        await asyncio.sleep(0)
        ids_after_stop = {e["dossier_id"] for e in orch.list_active()}
        assert "obs-A" not in ids_after_stop
        assert "obs-B" in ids_after_stop

        # Let B finish naturally.
        await orch._tasks["obs-B"]
        await asyncio.sleep(0)
        assert orch.list_active() == []

    asyncio.run(_body())


def test_sub_agent_inline_long_run_is_not_killed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single dossier run that internally takes a while (simulating a
    sub-agent loop) must not be timed out or killed by the orchestrator.

    The orchestrator doesn't impose wall-clock deadlines on in-flight
    runs, so this is really a regression guard: if anyone adds one,
    this test fails.
    """

    class _LongInnerRuntime:
        """Simulates a runtime that spends most of its time inside a
        sub-agent loop (via a single long inner sleep)."""

        def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
            self.dossier_id = dossier_id
            self.model = model

        async def run(self, max_turns: int = 200) -> dict:
            # Single long sleep stands in for a sub-agent loop — the
            # orchestrator has no way to tell this is "sub work" vs
            # "main work". Duration is a couple of hundred ms so the
            # test stays snappy but is clearly longer than any trivial
            # task scheduler hiccup.
            await asyncio.sleep(0.25)
            return {
                "reason": "ended_turn",
                "turns": 1,
                "session_id": "ws-inner",
                "note": "sub-agent loop completed inline",
            }

    monkeypatch.setattr(orch_mod, "_runtime_cls", _LongInnerRuntime)
    orch = AgentOrchestrator()

    async def _body() -> None:
        await orch.start("sub-parent")
        t0 = time.perf_counter()
        result = await orch._tasks["sub-parent"]
        elapsed = time.perf_counter() - t0

        # The task must have completed naturally (not cancelled).
        assert not orch._tasks  # done-callback pruned (after await returns)
        assert elapsed >= 0.2, (
            f"inner sleep was suspiciously short: {elapsed:.3f}s"
        )
        assert isinstance(result, dict)
        assert result["reason"] == "ended_turn"
        assert result["note"] == "sub-agent loop completed inline"

    asyncio.run(_body())


def test_list_active_entry_shape(orch: AgentOrchestrator) -> None:
    """The day-2 telemetry hook promises a specific entry shape."""

    async def _body() -> None:
        await orch.start("shape-A")
        await asyncio.sleep(0)
        entries = orch.list_active()
        assert len(entries) == 1
        entry = entries[0]
        assert set(entry.keys()) == {"dossier_id", "started_at", "status"}
        assert entry["dossier_id"] == "shape-A"
        assert isinstance(entry["started_at"], str) and entry["started_at"]
        assert entry["status"] in {"running", "scheduled", "cancelled", "done"}
        await orch._tasks["shape-A"]

    asyncio.run(_body())


def test_stop_raises_agent_not_running_for_unknown_dossier(
    orch: AgentOrchestrator,
) -> None:
    async def _body() -> None:
        try:
            await orch.stop("never-started")
        except AgentNotRunning:
            return
        raise AssertionError("expected AgentNotRunning")

    asyncio.run(_body())


def test_errored_run_prunes_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    """A runtime that raises should still clear ``_tasks`` so a fresh
    ``start()`` succeeds afterwards."""

    class _BoomRuntime:
        def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
            self.dossier_id = dossier_id

        async def run(self, max_turns: int = 200) -> Any:
            await asyncio.sleep(0.05)
            raise RuntimeError("mock runtime boom")

    monkeypatch.setattr(orch_mod, "_runtime_cls", _BoomRuntime)
    orch = AgentOrchestrator()

    async def _body() -> None:
        await orch.start("boom")
        # Await the task directly, swallowing the exception the same way
        # the done-callback does in production.
        with pytest.raises(RuntimeError):
            await orch._tasks["boom"]
        # Give the done-callback a tick to prune.
        await asyncio.sleep(0)
        assert "boom" not in orch._tasks
        # And a fresh start should now work.
        await orch.start("boom")
        with pytest.raises(RuntimeError):
            await orch._tasks["boom"]

    asyncio.run(_body())


def test_start_caps_max_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    class _RecordingRuntime:
        def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
            self.dossier_id = dossier_id

        async def run(self, max_turns: int = 200) -> dict:
            seen.append(max_turns)
            return {"reason": "ended_turn", "turns": 1, "session_id": "ws"}

    monkeypatch.setattr(orch_mod, "_runtime_cls", _RecordingRuntime)
    monkeypatch.setattr(orch_mod, "AGENT_MAX_TURNS", 3)
    orch = AgentOrchestrator()

    async def _body() -> None:
        await orch.start("capped", max_turns=999)
        await orch._tasks["capped"]

    asyncio.run(_body())
    assert seen == [3]


def test_process_wide_concurrency_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch_mod, "_runtime_cls", _runtime_cls_with_duration(0.2))
    monkeypatch.setattr(orch_mod, "AGENT_MAX_CONCURRENT_RUNS", 1)
    orch = AgentOrchestrator()

    async def _body() -> None:
        await orch.start("first")
        with pytest.raises(AgentCapacityExceeded):
            await orch.start("second")
        await orch.shutdown()

    asyncio.run(_body())
