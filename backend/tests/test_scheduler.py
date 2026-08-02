"""Tests for the sleep-mode scheduler (``vellum.agent.scheduler``).

The scheduler is the 30-second polling loop that wakes dossiers whose
``wake_pending`` flag is set or whose ``wake_at`` has elapsed. The README
calls the behavior "reactive wake within one tick." This file pins the
load-bearing contract — including the contention-with-precreated-session
path at ``scheduler.py:202-216``, which the deep-dive called "one of the
most important lines in the repo."

We avoid ``pytest-asyncio`` by running each async body under ``asyncio.run``
inside a sync test, matching the pattern in ``test_orchestrator.py`` and
``test_resume.py``. ``ORCHESTRATOR.start`` is monkeypatched module-wide to a
recording no-op so the agent runtime never actually runs. ``ORCHESTRATOR.status``
is monkeypatched similarly — the scheduler's stale-session check at
``scheduler.py:172`` depends on it returning the expected shape.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import pytest

from vellum.agent import orchestrator as orch_mod
from vellum.agent import scheduler as sched_mod
from vellum.agent.scheduler import (
    AgentAlreadyRunning,
    AgentCapacityExceeded,
    Scheduler,
)


# ---------- fixtures ----------


def _mk_dossier(title: str = "scheduler test") -> Any:
    """Create a throwaway dossier via storage; returns the dossier object."""
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement="scheduler test",
            dossier_type=m.DossierType.investigation,
        )
    )


def _patch_orchestrator(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace ``ORCHESTRATOR.start`` and ``ORCHESTRATOR.status`` with
    recording no-ops. Returns a dict the tests can assert against.
    """
    calls: dict[str, list[dict]] = {"started": [], "status_calls": []}

    async def _fake_start(
        dossier_id: str,
        expected_session_id: Optional[str] = None,
        **_: Any,
    ) -> dict:
        calls["started"].append(
            {"dossier_id": dossier_id, "expected_session_id": expected_session_id}
        )
        return {"status": "started", "dossier_id": dossier_id}

    def _fake_status(dossier_id: str) -> dict:
        calls["status_calls"].append(dossier_id)
        return {"running": False, "dossier_id": dossier_id}

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _fake_start)
    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "status", _fake_status)
    return calls


def _make_scheduler(poll_seconds: int = 1) -> Scheduler:
    return Scheduler(poll_seconds=poll_seconds)


# ---------- basic tick behavior ----------


def test_tick_picks_up_wake_pending_dossier(fresh_db, monkeypatch):
    """A dossier with ``wake_pending=1`` triggers ORCHESTRATOR.start with
    the pre-created session id, and the wake flags are cleared after.
    """
    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("wake-pending")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    assert len(calls["started"]) == 1
    assert calls["started"][0]["dossier_id"] == dossier.id
    # Wake fields are cleared after a successful start.
    state = storage.get_dossier_wake_state(dossier.id)
    assert state is not None and not state.get("wake_pending")


def test_tick_picks_up_due_wake_at_dossier(fresh_db, monkeypatch):
    """A dossier with ``wake_at`` in the past triggers a wake; the agent's
    pre-scheduled wake fires even without ``wake_pending`` set.
    """
    from datetime import datetime, timedelta, timezone

    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("wake-at-due")
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    storage.set_dossier_wake_at(dossier.id, past, reason=m.WakeReason.scheduled)

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    assert len(calls["started"]) == 1
    assert calls["started"][0]["dossier_id"] == dossier.id


def test_tick_skips_future_wake_at_even_with_wake_pending(fresh_db, monkeypatch):
    """H-28: if both ``wake_at`` (future) and ``wake_pending=1`` are set,
    the scheduler defers to the future wake_at — the next tick after
    ``wake_at`` elapses will pick it up.
    """
    from datetime import datetime, timedelta, timezone

    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("future-wake")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    storage.set_dossier_wake_at(dossier.id, future, reason=m.WakeReason.scheduled)
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.crash_resume)

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    assert calls["started"] == [], "H-28: future wake_at must defer even with wake_pending set"


def test_tick_skips_quarantined_dossiers(fresh_db, monkeypatch):
    """Quarantined dossiers are excluded by ``list_dossiers_ready_to_wake``,
    so a quarantine flag prevents the scheduler from waking them.
    """
    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("quarantined")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.crash_resume)
    storage.set_dossier_quarantined(dossier.id, reason="too many errors")

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    assert calls["started"] == [], "quarantined dossiers must not be woken"


def test_tick_respects_sleep_mode_disabled(fresh_db, monkeypatch):
    """When ``sleep_mode_enabled`` is False, the tick is a no-op even if
    dossiers are wake-ready. The scheduler loop keeps running so flipping
    the setting back on takes effect without a restart.
    """
    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("sleep-off")
    storage.set_setting("sleep_mode_enabled", False)
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    assert calls["started"] == [], "sleep_mode_enabled=False must skip all wakes"


def test_tick_continues_after_tick_exception(fresh_db, monkeypatch):
    """A tick that raises must not kill the scheduler. The next tick
    re-tries — this is the contract at ``scheduler.py:96-99``.
    """
    from vellum import storage
    _patch_orchestrator(monkeypatch)  # not used here; just keeps the patch clean

    # First call raises, second returns an empty list. The scheduler must
    # call twice; the first exception is swallowed.
    real_list = storage.list_dossiers_ready_to_wake
    call_count = {"n": 0}

    def _sometimes_raise():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated DB blip")
        return []

    monkeypatch.setattr(storage, "list_dossiers_ready_to_wake", _sometimes_raise)
    # Re-bind the symbol the scheduler imported.
    monkeypatch.setattr(sched_mod.storage, "list_dossiers_ready_to_wake", _sometimes_raise)

    sched = _make_scheduler()

    async def _run_two_ticks():
        await sched._tick()  # raises, swallowed by _run's try/except
        await sched._tick()  # returns []

    asyncio.run(_run_two_ticks())
    assert call_count["n"] == 2


# ---------- contention: keep wake fields on AgentAlreadyRunning / CapacityExceeded ----------


def test_wake_one_keeps_wake_pending_on_agent_already_running(fresh_db, monkeypatch):
    """The canonical late-answer correctness test. The README claims a
    late user answer keeps ``wake_pending=1`` — this is the
    ``scheduler.py:202-216`` block.
    """
    from vellum.agent import orchestrator as orch_mod
    from vellum import models as m, storage

    dossier = _mk_dossier("conflict")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    async def _conflict(dossier_id: str, **_: Any) -> dict:
        raise orch_mod.AgentAlreadyRunning(dossier_id)

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _conflict)
    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "status", lambda did: {"running": False, "dossier_id": did})

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    # The wake flag MUST be preserved.
    state = storage.get_dossier_wake_state(dossier.id)
    assert state is not None and state.get("wake_pending") is True, (
        "AgentAlreadyRunning must NOT clear wake_pending — the user's late "
        "answer would be silently dropped if the running session had already "
        "snapshotted state."
    )


def test_wake_one_keeps_wake_pending_on_agent_capacity_exceeded(fresh_db, monkeypatch):
    """Same as the test above, but for the process-wide capacity path."""
    from vellum.agent import orchestrator as orch_mod
    from vellum import models as m, storage

    dossier = _mk_dossier("capacity")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    async def _at_capacity(dossier_id: str, **_: Any) -> dict:
        raise orch_mod.AgentCapacityExceeded(dossier_id)

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _at_capacity)
    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "status", lambda did: {"running": False, "dossier_id": did})

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    state = storage.get_dossier_wake_state(dossier.id)
    assert state is not None and state.get("wake_pending") is True


def test_wake_one_keeps_wake_pending_on_unexpected_exception(fresh_db, monkeypatch):
    """A generic exception in ``ORCHESTRATOR.start`` (e.g. a bug) must also
    retain wake fields — the ``scheduler.py:235-250`` generic-exception
    branch behaves the same as the contention branches.
    """
    from vellum.agent import orchestrator as orch_mod
    from vellum import models as m, storage

    dossier = _mk_dossier("generic-error")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    async def _crash(dossier_id: str, **_: Any) -> dict:
        raise RuntimeError("simulated agent bug")

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _crash)
    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "status", lambda did: {"running": False, "dossier_id": did})

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    state = storage.get_dossier_wake_state(dossier.id)
    assert state is not None and state.get("wake_pending") is True


def test_wake_one_closes_pre_created_session_on_contention(fresh_db, monkeypatch):
    """When contention happens after the scheduler pre-created a session,
    that session must be closed (not leaked) and no orphan
    ``trigger=scheduled`` session is left behind.
    """
    from vellum.agent import orchestrator as orch_mod
    from vellum import models as m, storage

    dossier = _mk_dossier("pre-session-cleanup")
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.needs_input_resolved)

    async def _conflict(dossier_id: str, **_: Any) -> dict:
        raise orch_mod.AgentAlreadyRunning(dossier_id)

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _conflict)
    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "status", lambda did: {"running": False, "dossier_id": did})

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    sessions = storage.list_work_sessions(dossier.id)
    open_sessions = [s for s in sessions if s.ended_at is None]
    assert open_sessions == [], (
        f"expected no open sessions after contention, got {len(open_sessions)}"
    )


# ---------- stale-session recovery ----------


def test_wake_one_closes_stale_active_session_before_starting(fresh_db, monkeypatch):
    """If a dossier has an active session row from a previous crash
    (no orchestrator task owns it), the scheduler closes it as
    ``end_reason=crashed`` and starts fresh.
    """
    from vellum import models as m, storage

    calls = _patch_orchestrator(monkeypatch)
    dossier = _mk_dossier("stale-session")
    # Pre-create a stale active session (no orchestrator task for it).
    stale = storage.start_work_session(
        dossier.id, m.WorkSessionTrigger.scheduled
    )
    storage.mark_wake_pending(dossier.id, reason=m.WakeReason.crash_resume)

    sched = _make_scheduler()
    asyncio.run(sched._tick())

    # The stale session was closed with end_reason=crashed.
    refreshed = storage.get_work_session(stale.id)
    assert refreshed.ended_at is not None
    assert refreshed.end_reason == m.WorkSessionEndReason.crashed

    # The orchestrator was started exactly once with the dossier_id.
    assert len(calls["started"]) == 1
    assert calls["started"][0]["dossier_id"] == dossier.id


# ---------- run loop lifecycle ----------


def test_run_loop_terminates_on_stop(fresh_db, monkeypatch):
    """Starting the scheduler, then calling stop() within a few
    poll_seconds, must cancel the run loop cleanly.
    """
    _patch_orchestrator(monkeypatch)

    sched = _make_scheduler(poll_seconds=1)

    async def _drive():
        sched.start()
        await asyncio.sleep(0.05)  # let the first tick start
        await sched.stop(timeout=2.0)

    asyncio.run(_drive())
    assert sched._task is None


def test_run_loop_ticks_at_poll_seconds_interval(fresh_db, monkeypatch):
    """The poll interval is bounded — at least one tick must fire within
    2x poll_seconds. Loose upper bound to absorb scheduler jitter per the
    pattern at ``test_orchestrator.py:86-122``.
    """
    call_count = {"n": 0}

    def _counting():
        call_count["n"] += 1
        return []

    monkeypatch.setattr(sched_mod.storage, "list_dossiers_ready_to_wake", _counting)

    sched = _make_scheduler(poll_seconds=1)

    async def _drive():
        sched.start()
        await asyncio.sleep(1.2)  # ~1 poll cycle + jitter
        await sched.stop(timeout=2.0)

    asyncio.run(_drive())

    assert call_count["n"] >= 1, f"expected ≥1 tick, got {call_count['n']}"
    assert call_count["n"] <= 3, f"too many ticks for 1.2s window: {call_count['n']}"
