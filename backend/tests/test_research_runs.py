"""Regression tests for versioned autonomous-research lifecycle."""
from __future__ import annotations

import asyncio
import json

import pytest


def _dossier():
    from vellum import models as m, storage
    return storage.create_dossier(m.DossierCreate(title="Run lifecycle", problem_statement="Research safely", dossier_type=m.DossierType.investigation))


def test_start_is_idempotent_and_restart_is_explicit(fresh_db):
    from vellum import models as m, storage
    from vellum.db import connect
    dossier=_dossier(); policy=m.ResearchPolicy(max_sessions=2,max_turns_per_session=11)
    first=storage.start_autonomous_research(dossier.id,policy,idempotency_key="request-0001")
    again=storage.start_autonomous_research(dossier.id,policy,idempotency_key="request-0001")
    assert first.active_run_id==again.active_run_id
    with connect() as conn: assert conn.execute("SELECT COUNT(*) n FROM research_runs WHERE dossier_id=?",(dossier.id,)).fetchone()["n"]==1
    restarted=storage.restart_autonomous_research(dossier.id,policy,idempotency_key="request-0002")
    assert restarted.active_run_id!=first.active_run_id
    assert storage.get_research_run(first.active_run_id).status is m.ResearchRunStatus.superseded


def test_capacity_failure_does_not_create_or_count_session(fresh_db,monkeypatch):
    from vellum import storage
    from vellum.agent.orchestrator import AgentCapacityExceeded
    from vellum.agent.scheduler import Scheduler
    dossier=_dossier(); progress=storage.start_autonomous_research(dossier.id)
    async def reject(*args,**kwargs): raise AgentCapacityExceeded()
    monkeypatch.setattr("vellum.agent.scheduler.ORCHESTRATOR.start",reject)
    asyncio.run(Scheduler(1)._tick())
    assert storage.list_work_sessions(dossier.id)==[]
    assert storage.get_research_progress(dossier.id).sessions_used==0


def test_pause_wins_against_leased_wake(fresh_db):
    from vellum import storage
    dossier=_dossier(); progress=storage.start_autonomous_research(dossier.id)
    [wake]=storage.lease_due_research_wakes("test-owner")
    storage.pause_autonomous_research(dossier.id)
    with pytest.raises(ValueError,match="no longer valid"):
        storage.claim_research_wake_session(wake["id"],"test-owner")
    assert storage.list_work_sessions(dossier.id)==[]


def test_every_run_wake_uses_snapshot_turn_cap(fresh_db,monkeypatch):
    from vellum import models as m, storage
    from vellum.agent.scheduler import Scheduler
    dossier=_dossier(); storage.start_autonomous_research(dossier.id,m.ResearchPolicy(max_turns_per_session=13))
    storage.mark_wake_pending(dossier.id,m.WakeReason.user_note)
    captured={}
    async def accept(dossier_id,**kwargs):
        captured["turns"]=kwargs["max_turns"]
        captured["session_id"]=kwargs["session_factory"]()
        return {"status":"started"}
    monkeypatch.setattr("vellum.agent.scheduler.ORCHESTRATOR.start",accept)
    asyncio.run(Scheduler(1)._tick())
    session=storage.get_work_session(captured["session_id"])
    assert captured["turns"]==13 and session.max_turns_snapshot==13
    assert session.research_run_id is not None and session.wake_id is not None


def test_completion_is_run_scoped_and_abandoned_is_not_completed(fresh_db):
    from vellum import models as m, storage
    from vellum.db import connect
    from vellum.storage import evidence_store
    dossier=_dossier(); progress=storage.start_autonomous_research(dossier.id,m.ResearchPolicy(target_source_count=1,min_primary_sources=1))
    run_id=progress.active_run_id; now=m.utc_now().isoformat()
    with connect() as conn:
        conn.execute("INSERT INTO plan_items (id,dossier_id,plan_item_id,question,status,order_key,created_at,updated_at) VALUES ('p1',?,'p1','q','completed',1,?,?)",(dossier.id,now,now))
    obs=evidence_store.record_observation(dossier_id=dossier.id,url="https://agency.gov/report",provenance="consulted",run_id=run_id,model_source_type="primary")
    evidence_store.record_claim_links(dossier_id=dossier.id,observation_id=obs["observation_id"],claims=["Material finding"],relation="supports",run_id=run_id,materiality="material")
    ready=storage.get_research_progress(dossier.id)
    assert ready.completion_report.ready is True
    from vellum.agent import autonomy
    completed_session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.autonomous)
    storage.end_work_session_with_reason(completed_session.id,m.WorkSessionEndReason.ended_turn)
    assert autonomy.after_session(dossier.id,completed_session.id,m.WorkSessionEndReason.ended_turn).action=="completed"
    completed_progress=storage.get_research_progress(dossier.id)
    assert completed_progress.status=="completed"
    assert completed_progress.active_run_id is None
    assert completed_progress.completion_report.ready is True
    # Create a fresh run explicitly for the abandonment assertion below.
    storage.restart_autonomous_research(dossier.id,m.ResearchPolicy(target_source_count=1,min_primary_sources=1))
    with connect() as conn: conn.execute("UPDATE plan_items SET status='abandoned' WHERE id='p1'")
    incomplete=storage.get_research_progress(dossier.id)
    assert incomplete.completed_plan_items==0
    assert incomplete.completion_report.abandoned_plan_items==1
    assert incomplete.completion_report.ready is False


def test_sleep_switch_suspends_and_requeues_runs(fresh_db):
    from vellum import models as m, storage
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id)
    storage.set_setting("sleep_mode_enabled",False)
    assert storage.get_research_run(started.active_run_id).status is m.ResearchRunStatus.blocked_sleep
    assert storage.get_research_progress(dossier.id).next_wake_at is None
    storage.set_setting("sleep_mode_enabled",True)
    assert storage.get_research_run(started.active_run_id).status is m.ResearchRunStatus.queued
    assert storage.get_research_progress(dossier.id).next_wake_at is not None


def test_tool_invocation_claim_replay_and_hash_conflict(fresh_db):
    from vellum import storage
    dossier=_dossier()
    claimed=storage.claim_tool_invocation("tool-1",dossier.id,"write","hash-a")
    assert claimed["state"]=="claimed"
    assert storage.claim_tool_invocation("tool-1",dossier.id,"write","hash-a")["state"]=="in_progress"
    storage.complete_tool_invocation("tool-1","hash-a",json.dumps({"ok":True}))
    assert storage.claim_tool_invocation("tool-1",dossier.id,"write","hash-a")["state"]=="completed"
    with pytest.raises(ValueError,match="conflicting input"):
        storage.claim_tool_invocation("tool-1",dossier.id,"write","hash-b")


def test_db_tool_unit_of_work_rolls_back_partial_handler_and_caches_error(fresh_db):
    from vellum import storage
    from vellum.db import connect
    dossier=_dossier()
    def broken_handler():
        with connect() as conn:
            conn.execute("UPDATE dossiers SET title='partial' WHERE id=?",(dossier.id,))
        raise RuntimeError("boom")
    result=storage.execute_db_tool_invocation("tool-atomic",dossier.id,"write","hash",broken_handler)
    assert result["is_error"] is True
    assert storage.get_dossier(dossier.id).title=="Run lifecycle"
    replay=storage.execute_db_tool_invocation("tool-atomic",dossier.id,"write","hash",lambda: {"should":"not run"})
    assert replay["result_json"]==result["result_json"]


def test_waiting_transition_creates_one_quiet_notification(fresh_db):
    from vellum import models as m, storage
    from vellum.agent import autonomy
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id)
    session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.autonomous)
    storage.add_needs_input(dossier.id,m.NeedsInputCreate(question="Which jurisdiction?"),session.id)
    storage.end_work_session_with_reason(session.id,m.WorkSessionEndReason.ended_turn)
    decision=autonomy.after_session(dossier.id,session.id,m.WorkSessionEndReason.ended_turn)
    assert decision.action=="waiting"
    notices=storage.list_notifications()
    assert len(notices)==1 and notices[0]["event_type"]=="run_waiting_for_user"
    assert storage.mark_notification_read(notices[0]["id"])
    assert storage.list_notifications()==[]


def test_init_migrates_legacy_research_window(fresh_db):
    from vellum import models as m, storage
    from vellum.db import connect, init_db
    dossier=_dossier(); started=m.utc_now().isoformat()
    policy=m.ResearchPolicy(autonomy_enabled=True)
    with connect() as conn:
        conn.execute("UPDATE dossiers SET research_policy=?,research_started_at=?,wake_pending=1,wake_reason='autonomous_continue' WHERE id=?",(policy.model_dump_json(),started,dossier.id))
    init_db()
    run=storage.get_active_research_run(dossier.id)
    assert run is not None and run.initiated_by=="migration"
    assert storage.get_research_progress(dossier.id).next_wake_at is not None


def test_error_retry_cannot_exceed_atomic_session_cap(fresh_db):
    from vellum import models as m, storage
    dossier=_dossier(); progress=storage.start_autonomous_research(dossier.id,m.ResearchPolicy(max_sessions=1))
    [wake]=storage.lease_due_research_wakes("owner")
    session_id=storage.claim_research_wake_session(wake["id"],"owner")
    storage.end_work_session_with_reason(session_id,m.WorkSessionEndReason.error)
    storage.schedule_research_wake(dossier.id,progress.run_id,m.WakeReason.error_retry)
    assert storage.lease_due_research_wakes("owner-2")==[]
    capped=storage.get_research_progress(dossier.id)
    assert capped.status=="cap_reached" and capped.sessions_used==1
    assert len(storage.list_work_sessions(dossier.id))==1


def test_model_call_reservation_enforces_turn_and_cost_caps(fresh_db):
    from vellum import models as m, storage
    dossier=_dossier(); storage.start_autonomous_research(dossier.id,m.ResearchPolicy(max_turns_per_session=5,max_cost_usd=1))
    [wake]=storage.lease_due_research_wakes("owner")
    session_id=storage.claim_research_wake_session(wake["id"],"owner")
    for expected in range(1,6):
        assert storage.reserve_model_call(session_id)=={"allowed":True,"reason":None,"turn_number":expected}
    assert storage.reserve_model_call(session_id)["reason"]=="turn_cap_reached"
    storage.record_turn_usage(session_id,1,1,1.0)
    assert storage.reserve_model_call(session_id)["reason"]=="cost_cap_reached"
    assert storage.get_research_progress(dossier.id).status=="cap_reached"


@pytest.mark.parametrize("blocker_kind",["needs_input","decision"])
def test_public_blocker_resolution_requeues_waiting_run_atomically(fresh_db,blocker_kind):
    from vellum import models as m, storage
    from vellum.agent import autonomy
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id)
    session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.autonomous)
    if blocker_kind=="needs_input":
        blocker=storage.add_needs_input(dossier.id,m.NeedsInputCreate(question="Which state?"),session.id)
    else:
        blocker=storage.add_decision_point(dossier.id,m.DecisionPointCreate(title="Choose",options=[m.DecisionOption(label="A")]),session.id)
    storage.end_work_session_with_reason(session.id,m.WorkSessionEndReason.ended_turn)
    assert autonomy.after_session(dossier.id,session.id,m.WorkSessionEndReason.ended_turn).action=="waiting"
    waiting_version=storage.get_research_run(started.run_id).state_version
    if blocker_kind=="needs_input": storage.resolve_needs_input(dossier.id,blocker.id,"Illinois")
    else: storage.resolve_decision_point(dossier.id,blocker.id,"A")
    run=storage.get_research_run(started.run_id); progress=storage.get_research_progress(dossier.id)
    assert run.status is m.ResearchRunStatus.queued and run.state_version>waiting_version
    assert progress.next_wake_at is not None


def test_restart_rejected_during_active_session_and_when_sleep_disabled(fresh_db):
    from vellum import models as m, storage
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id)
    session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.autonomous)
    with pytest.raises(ValueError,match="work session is active"):
        storage.restart_autonomous_research(dossier.id,idempotency_key="restart-active")
    storage.end_work_session_with_reason(session.id,m.WorkSessionEndReason.ended_turn)
    storage.pause_autonomous_research(dossier.id)
    storage.set_setting("sleep_mode_enabled",False)
    with pytest.raises(ValueError,match="sleep mode"):
        storage.restart_autonomous_research(dossier.id,idempotency_key="restart-sleep-off")
    assert storage.get_active_research_run(dossier.id).id==started.run_id


def test_generic_start_and_resume_do_not_touch_research_run(fresh_db,monkeypatch):
    from fastapi.testclient import TestClient
    from vellum import storage
    from vellum.main import create_app
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id); storage.pause_autonomous_research(dossier.id)
    async def should_not_start(*args,**kwargs): raise AssertionError("orchestrator must not start")
    monkeypatch.setattr("vellum.agent.orchestrator.ORCHESTRATOR.start",should_not_start)
    with TestClient(create_app()) as client:
        assert client.post(f"/api/dossiers/{dossier.id}/agent/start").status_code==409
        assert client.post(f"/api/dossiers/{dossier.id}/resume").status_code==409
    assert storage.list_work_sessions(dossier.id)==[]
    assert storage.get_active_research_run(dossier.id).id==started.run_id


def test_unlinked_session_cannot_advance_research_run(fresh_db):
    from vellum import models as m, storage
    from vellum.agent import autonomy
    dossier=_dossier(); started=storage.start_autonomous_research(dossier.id); storage.pause_autonomous_research(dossier.id)
    session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.manual)
    storage.end_work_session_with_reason(session.id,m.WorkSessionEndReason.ended_turn)
    before=storage.get_research_run(started.run_id)
    assert autonomy.after_session(dossier.id,session.id,m.WorkSessionEndReason.ended_turn).action=="noop"
    after=storage.get_research_run(started.run_id)
    assert after.state_version==before.state_version and after.status==before.status


def test_idempotency_replay_identifies_original_and_terminal_requires_restart(fresh_db):
    from vellum import models as m, storage
    dossier=_dossier(); first=storage.start_autonomous_research(dossier.id,idempotency_key="original-start")
    storage.pause_autonomous_research(dossier.id)
    second=storage.restart_autonomous_research(dossier.id,idempotency_key="explicit-restart")
    replay=storage.start_autonomous_research(dossier.id,idempotency_key="original-start")
    assert replay.run_id==first.run_id and replay.status=="superseded"
    session=storage.start_work_session(dossier.id,m.WorkSessionTrigger.autonomous)
    storage.end_work_session_with_reason(session.id,m.WorkSessionEndReason.ended_turn)
    storage.transition_run_after_session(dossier.id,session.id,"completed","test")
    with pytest.raises(ValueError,match="explicit restart"):
        storage.start_autonomous_research(dossier.id)
    assert storage.get_research_run(second.run_id).status is m.ResearchRunStatus.completed
