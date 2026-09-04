from __future__ import annotations

import asyncio


def _dossier():
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title="Long research",
            problem_statement="Compare the evidence across several competing claims.",
        )
    )


def test_research_policy_round_trip_and_source_quality_rollup(fresh_db):
    from vellum import models as m, storage
    from vellum.tools import handlers

    dossier = _dossier()
    policy = m.ResearchPolicy(
        depth=m.ResearchDepth.deep,
        max_sessions=8,
        max_cost_usd=25,
        target_source_count=40,
        min_primary_sources=6,
    )
    assert storage.update_research_policy(dossier.id, policy) == policy
    sec_one = storage.upsert_section(dossier.id, m.SectionUpsert(
        type=m.SectionType.evidence, title="One", state=m.SectionState.provisional,
        change_note="test",
    ))
    sec_two = storage.upsert_section(dossier.id, m.SectionUpsert(
        type=m.SectionType.evidence, title="Two", state=m.SectionState.provisional,
        change_note="test", after_section_id=sec_one.id,
    ))

    handlers.log_source_consulted(
        dossier.id,
        {
            "citation": "https://www.example.gov/rule/",
            "source_title": "Final rule",
            "source_type": "primary",
            "authority": "official",
            "why_consulted": "Establish the controlling rule",
            "what_learned": "The rule applies from 2025 onward.",
            "supports_section_ids": [sec_one.id],
            "limitations": "Does not cover the earlier period.",
        },
    )
    # Same URL with harmless normalisation differences counts as another log
    # event but not another unique source.
    handlers.log_source_consulted(
        dossier.id,
        {
            "citation": "https://www.example.gov/rule",
            "source_type": "secondary",
            "why_consulted": "Cross-check",
            "what_learned": "Confirmed the same effective date.",
            "contradicts_section_ids": [sec_two.id],
        },
    )

    progress = storage.get_research_progress(dossier.id)
    assert progress is not None
    assert progress.policy.depth == m.ResearchDepth.deep
    assert progress.source_count == 2
    assert progress.unique_source_count == 1
    # A model-declared primary label alone is not an independently-qualified
    # primary source in the legacy/no-run compatibility view.
    assert progress.primary_source_count == 0
    assert progress.unique_domains == 1
    assert progress.sources_linked_to_sections == 1
    assert progress.sources_with_limitations == 1
    assert progress.contradictory_sources == 1


def test_healthy_autonomous_session_schedules_continuation(fresh_db):
    from vellum import models as m, storage
    from vellum.agent import autonomy

    dossier = _dossier()
    policy = m.ResearchPolicy(
        depth=m.ResearchDepth.deep,
        max_sessions=3,
        max_cost_usd=20,
        continuation_delay_minutes=2,
    )
    storage.start_autonomous_research(dossier.id, policy)
    session = storage.start_work_session(
        dossier.id, m.WorkSessionTrigger.autonomous
    )
    storage.end_work_session_with_reason(
        session.id, m.WorkSessionEndReason.ended_turn
    )

    decision = autonomy.after_session(
        dossier.id, session.id, m.WorkSessionEndReason.ended_turn
    )
    assert decision.action == "scheduled"
    wake = storage.get_dossier_wake_state(dossier.id)
    assert wake is not None
    assert wake["wake_at"] is not None
    assert wake["wake_reason"] == m.WakeReason.autonomous_continue.value


def test_autonomy_pauses_at_session_cap(fresh_db):
    from vellum import models as m, storage
    from vellum.agent import autonomy

    dossier = _dossier()
    storage.start_autonomous_research(
        dossier.id,
        m.ResearchPolicy(max_sessions=1, max_cost_usd=20),
    )
    session = storage.start_work_session(
        dossier.id, m.WorkSessionTrigger.autonomous
    )
    storage.end_work_session_with_reason(
        session.id, m.WorkSessionEndReason.ended_turn
    )

    decision = autonomy.after_session(
        dossier.id, session.id, m.WorkSessionEndReason.ended_turn
    )
    assert decision.action == "paused"
    assert decision.reason == "session_cap_reached"
    progress = storage.get_research_progress(dossier.id)
    assert progress is not None
    assert progress.status == "cap_reached"
    assert not progress.policy.autonomy_enabled


def test_scheduler_uses_autonomous_trigger(fresh_db, monkeypatch):
    from vellum import models as m, storage
    from vellum.agent import orchestrator as orch_mod
    from vellum.agent.scheduler import Scheduler

    dossier = _dossier()
    storage.start_autonomous_research(
        dossier.id,
        m.ResearchPolicy(max_turns_per_session=17),
    )
    captured: dict[str, str] = {}

    async def fake_start(dossier_id: str, **kwargs):
        captured["session_id"] = kwargs["session_factory"]()
        captured["max_turns"] = kwargs["max_turns"]
        return {"status": "started"}

    monkeypatch.setattr(orch_mod.ORCHESTRATOR, "start", fake_start)
    monkeypatch.setattr(
        orch_mod.ORCHESTRATOR, "status", lambda _dossier_id: {"running": False}
    )
    asyncio.run(Scheduler(poll_seconds=1)._tick())

    session = storage.get_work_session(captured["session_id"])
    assert session is not None
    assert session.trigger == m.WorkSessionTrigger.autonomous
    assert captured["max_turns"] == 17


def test_research_api_start_and_pause(fresh_db, monkeypatch):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    dossier = _dossier()
    with TestClient(create_app()) as client:
        started = client.post(
            f"/api/dossiers/{dossier.id}/research/start",
            json={
                "policy": {
                    "depth": "deep",
                    "autonomy_enabled": False,
                    "max_sessions": 5,
                    "max_turns_per_session": 25,
                    "max_cost_usd": 18,
                    "target_source_count": 30,
                    "min_primary_sources": 5,
                    "continuation_delay_minutes": 1,
                }
            },
        )
        assert started.status_code == 200, started.text
        assert started.json()["policy"]["autonomy_enabled"] is True
        assert started.json()["status"] == "queued"

        paused = client.post(f"/api/dossiers/{dossier.id}/research/pause")
        assert paused.status_code == 200, paused.text
        assert paused.json()["policy"]["autonomy_enabled"] is False
        assert paused.json()["status"] == "paused"
