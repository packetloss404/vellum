"""Self-healing errored/crashed sessions: backoff retry + quarantine.

Covers vellum/agent/self_heal.py and its wiring:

  * runtime.py finally — error end schedules a backoff retry; healthy end
    resets the failure streak
  * lifecycle._recover_one_work_session — crash recovery routes through the
    same policy so crash-loops back off and quarantine
  * wake_store — quarantined dossiers never appear in ready-to-wake
  * agent routes — explicit start/resume clears the quarantine
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


# ---------- helpers ----------


def _mk_dossier(title: str = "Self-heal test dossier") -> str:
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement="Exercise the self-heal path.",
            dossier_type=m.DossierType.investigation,
        )
    ).id


def _error_state(dossier_id: str) -> dict:
    from vellum import storage

    state = storage.get_dossier_error_state(dossier_id)
    assert state is not None
    return state


def _wake_state(dossier_id: str) -> dict:
    from vellum import storage

    state = storage.get_dossier_wake_state(dossier_id)
    assert state is not None
    return state


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------- backoff math ----------


def test_backoff_doubles_and_caps(monkeypatch):
    from vellum.agent import self_heal

    monkeypatch.setattr(self_heal, "ERROR_RETRY_BASE_SECONDS", 300)
    monkeypatch.setattr(self_heal, "ERROR_RETRY_CAP_SECONDS", 21600)

    assert self_heal.backoff_seconds(1) == 300
    assert self_heal.backoff_seconds(2) == 600
    assert self_heal.backoff_seconds(3) == 1200
    assert self_heal.backoff_seconds(4) == 2400
    # 300 * 2^9 = 153600 > cap
    assert self_heal.backoff_seconds(10) == 21600


# ---------- failure policy ----------


def test_error_failure_schedules_backoff_wake(fresh_db):
    from vellum import models as m
    from vellum.agent import self_heal

    did = _mk_dossier()
    before = datetime.now(timezone.utc)

    result = self_heal.on_session_failure(did, kind="error")

    assert result["action"] == "retry"
    assert result["count"] == 1
    assert _error_state(did)["consecutive_error_count"] == 1

    wake = _wake_state(did)
    assert wake["wake_pending"] is False
    assert wake["wake_reason"] == m.WakeReason.error_retry.value
    wake_at = _parse_dt(wake["wake_at"])
    delta = (wake_at - before).total_seconds()
    assert self_heal.ERROR_RETRY_BASE_SECONDS - 60 <= delta <= self_heal.ERROR_RETRY_BASE_SECONDS + 60


def test_successive_errors_escalate_delay(fresh_db):
    from vellum.agent import self_heal

    did = _mk_dossier()
    before = datetime.now(timezone.utc)

    self_heal.on_session_failure(did, kind="error")
    first_wake = _parse_dt(_wake_state(did)["wake_at"])
    self_heal.on_session_failure(did, kind="error")
    second_wake = _parse_dt(_wake_state(did)["wake_at"])

    assert _error_state(did)["consecutive_error_count"] == 2
    first_delay = (first_wake - before).total_seconds()
    second_delay = (second_wake - before).total_seconds()
    assert second_delay > first_delay * 1.5


def test_quarantine_after_max_failures(fresh_db, monkeypatch):
    from vellum import storage
    from vellum.agent import self_heal

    monkeypatch.setattr(self_heal, "ERROR_RETRY_MAX", 3)
    did = _mk_dossier()

    assert self_heal.on_session_failure(did, kind="error")["action"] == "retry"
    assert self_heal.on_session_failure(did, kind="error")["action"] == "retry"
    result = self_heal.on_session_failure(did, kind="error")

    assert result["action"] == "quarantined"
    state = _error_state(did)
    assert state["quarantined_at"] is not None
    assert "3 consecutive failed sessions" in state["quarantine_reason"]

    # Quarantine clears wake fields so nothing sneaks through a tick.
    wake = _wake_state(did)
    assert wake["wake_pending"] is False
    assert wake["wake_at"] is None

    # The user sees a loud trail note.
    full = storage.get_dossier_full(did)
    notes = [e for e in full.reasoning_trail if "quarantine" in e.tags]
    assert len(notes) == 1
    assert "Resume" in notes[0].note

    # And the dossier model surfaces the state for the UI.
    dossier = storage.get_dossier(did)
    assert dossier.quarantined_at is not None
    assert dossier.consecutive_error_count == 3


def test_quarantined_dossier_excluded_from_ready_to_wake(fresh_db):
    from vellum import models as m, storage

    did = _mk_dossier()
    storage.mark_wake_pending(did, m.WakeReason.needs_input_resolved)
    assert any(e["dossier_id"] == did for e in storage.list_dossiers_ready_to_wake())

    storage.set_dossier_quarantined(did, "test quarantine")
    assert not any(
        e["dossier_id"] == did for e in storage.list_dossiers_ready_to_wake()
    )


def test_success_resets_failure_streak(fresh_db):
    from vellum.agent import self_heal

    did = _mk_dossier()
    self_heal.on_session_failure(did, kind="error")
    self_heal.on_session_failure(did, kind="error")
    assert _error_state(did)["consecutive_error_count"] == 2

    self_heal.on_session_success(did)
    assert _error_state(did)["consecutive_error_count"] == 0


def test_first_crash_wakes_immediately_second_backs_off(fresh_db):
    from vellum import models as m
    from vellum.agent import self_heal

    did = _mk_dossier()

    r1 = self_heal.on_session_failure(did, kind="crash")
    assert r1 == {"action": "retry", "count": 1, "delay_seconds": 0}
    wake = _wake_state(did)
    assert wake["wake_pending"] is True
    assert wake["wake_reason"] == m.WakeReason.crash_resume.value

    r2 = self_heal.on_session_failure(did, kind="crash")
    assert r2["count"] == 2
    assert r2["delay_seconds"] > 0
    wake = _wake_state(did)
    assert wake["wake_at"] is not None
    assert wake["wake_reason"] == m.WakeReason.error_retry.value


def test_sleep_mode_off_counts_but_does_not_wake(fresh_db):
    from vellum import storage
    from vellum.agent import self_heal

    storage.set_setting("sleep_mode_enabled", False)
    did = _mk_dossier()

    result = self_heal.on_session_failure(did, kind="error")

    assert result["action"] == "noop"
    assert _error_state(did)["consecutive_error_count"] == 1
    wake = _wake_state(did)
    assert wake["wake_pending"] is False
    assert wake["wake_at"] is None


def test_clear_quarantine_resets_count(fresh_db):
    from vellum import storage

    did = _mk_dossier()
    for _ in range(5):
        storage.increment_consecutive_error_count(did)
    storage.set_dossier_quarantined(did, "test")

    storage.clear_dossier_quarantine(did)

    state = _error_state(did)
    assert state["quarantined_at"] is None
    assert state["quarantine_reason"] is None
    assert state["consecutive_error_count"] == 0


# ---------- lifecycle wiring ----------


def test_lifecycle_crash_recovery_bumps_streak(fresh_db):
    from vellum import lifecycle, models as m, storage

    did = _mk_dossier()
    storage.start_work_session(did, m.WorkSessionTrigger.manual)  # orphan

    report = lifecycle.reconcile_at_startup()

    assert report.recovered_work_sessions == 1
    assert _error_state(did)["consecutive_error_count"] == 1
    assert _wake_state(did)["wake_pending"] is True


def test_lifecycle_crash_loop_quarantines(fresh_db, monkeypatch):
    from vellum import lifecycle, models as m, storage
    from vellum.agent import self_heal

    monkeypatch.setattr(self_heal, "ERROR_RETRY_MAX", 2)
    did = _mk_dossier()

    for boot in range(2):
        storage.start_work_session(did, m.WorkSessionTrigger.manual)  # orphan
        lifecycle.reconcile_at_startup()
        # Simulate the scheduler consuming the wake between boots.
        storage.clear_dossier_wake(did)

    state = _error_state(did)
    assert state["quarantined_at"] is not None
    assert not any(
        e["dossier_id"] == did for e in storage.list_dossiers_ready_to_wake()
    )


# ---------- runtime wiring ----------


def _make_erroring_agent(dossier_id: str):
    """DossierAgent whose model stream always raises."""
    from vellum.agent import runtime as rt

    def _stream(**kwargs: Any) -> Any:
        raise RuntimeError("simulated transient API failure")

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=_stream)
    agent = rt.DossierAgent(dossier_id=dossier_id, model="mock-model")
    agent._client = client
    return agent


def test_runtime_error_end_schedules_retry(fresh_db):
    from vellum import models as m, storage

    did = _mk_dossier()
    agent = _make_erroring_agent(did)

    result = asyncio.run(agent.run(max_turns=3))

    assert result.reason == "error"
    sessions = storage.list_work_sessions(did)
    assert sessions and sessions[-1].end_reason == m.WorkSessionEndReason.error

    assert _error_state(did)["consecutive_error_count"] == 1
    wake = _wake_state(did)
    assert wake["wake_reason"] == m.WakeReason.error_retry.value
    assert wake["wake_at"] is not None


def test_runtime_healthy_end_resets_streak(fresh_db):
    from vellum import storage
    from vellum.agent import runtime as rt

    did = _mk_dossier()
    storage.increment_consecutive_error_count(did)
    storage.increment_consecutive_error_count(did)

    def _stream(**kwargs: Any) -> Any:
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

        class _StreamCM:
            async def __aenter__(self):
                class _Stream:
                    async def get_final_message(self_inner):
                        return msg

                return _Stream()

            async def __aexit__(self, *exc):
                return False

        return _StreamCM()

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=_stream)
    agent = rt.DossierAgent(dossier_id=did, model="mock-model")
    agent._client = client

    result = asyncio.run(agent.run(max_turns=3))

    assert result.reason == "ended_turn"
    assert _error_state(did)["consecutive_error_count"] == 0


# ---------- API wiring ----------


@pytest.fixture
def client(fresh_db, monkeypatch):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _patch_orchestrator_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from vellum.agent import orchestrator as orch_mod

    async def _fake_start(
        dossier_id: str,
        max_turns: int = 200,
        model: Optional[str] = None,
        expected_session_id: Optional[str] = None,
    ) -> dict:
        return {"status": "started", "dossier_id": dossier_id}

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", _fake_start)


def test_resume_clears_quarantine(client, monkeypatch):
    from vellum import storage

    _patch_orchestrator_start(monkeypatch)
    did = _mk_dossier()
    storage.set_dossier_quarantined(did, "test")

    resp = client.post(f"/api/dossiers/{did}/resume")

    assert resp.status_code == 200
    state = _error_state(did)
    assert state["quarantined_at"] is None
    assert state["consecutive_error_count"] == 0


def test_agent_start_clears_quarantine(client, monkeypatch):
    from vellum import storage

    _patch_orchestrator_start(monkeypatch)
    did = _mk_dossier()
    storage.set_dossier_quarantined(did, "test")

    resp = client.post(f"/api/dossiers/{did}/agent/start")

    assert resp.status_code == 200
    assert _error_state(did)["quarantined_at"] is None
