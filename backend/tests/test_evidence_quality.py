from __future__ import annotations

import json
import asyncio
import sqlite3

import pytest

from vellum import models as m
from vellum.agent import evidence, research_strategy
from vellum.storage import evidence_store
from vellum import storage
from vellum.tools import handlers
from vellum.agent import runtime


def test_canonicalize_url_is_conservative_and_drops_tracking() -> None:
    assert evidence_store.canonicalize_url(
        "HTTPS://WWW.Example.COM:443/a/../report/?utm_source=x&id=7#part"
    ) == "https://example.com/report/?id=7"


@pytest.mark.parametrize("url", ["", "file:///etc/passwd", "javascript:alert(1)", "https://u:p@example.com/"])
def test_canonicalize_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(ValueError):
        evidence_store.canonicalize_url(url)


def test_authority_is_only_verified_from_deterministic_domain() -> None:
    assert evidence_store.official_domain_marker("consumerfinance.gov")[0] == "government_domain"
    assert evidence_store.official_domain_marker("consumerfinance-gov.example")[0] == "unverified"


def test_parse_anthropic_evidence_separates_discovery_and_citation() -> None:
    secret = "ENCRYPTED_DO_NOT_STORE"
    blocks = [
        {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [{
                "type": "web_search_result",
                "url": "https://example.com/source",
                "title": "Source",
                "page_age": "2 days ago",
                "encrypted_content": secret,
            }],
        },
        {
            "type": "text",
            "text": "A supported statement.",
            "citations": [{
                "type": "web_search_result_location",
                "url": "https://example.com/source",
                "title": "Source",
                "cited_text": "The cited evidence.",
                "encrypted_index": "also-secret",
            }],
        },
    ]
    parsed = evidence.parse_anthropic_evidence(blocks)
    assert [item.provenance for item in parsed] == ["discovered", "cited"]
    assert parsed[0].excerpt is None
    assert parsed[1].excerpt == "The cited evidence."
    assert secret not in repr(parsed)
    assert "also-secret" not in repr(parsed)


def test_cited_excerpt_is_bounded() -> None:
    parsed = evidence.parse_anthropic_evidence([{
        "type": "text",
        "citations": [{
            "type": "web_search_result_location",
            "url": "https://example.com",
            "cited_text": "x" * 10_000,
        }],
    }])
    assert len(parsed[0].excerpt or "") == evidence.MAX_EVIDENCE_EXCERPT_CHARS


def test_deep_and_standard_are_behaviorally_distinct() -> None:
    standard = research_strategy.for_policy(m.ResearchPolicy(depth=m.ResearchDepth.standard))
    deep = research_strategy.for_policy(m.ResearchPolicy(depth=m.ResearchDepth.deep))
    assert standard.instructions != deep.instructions
    assert standard.requires_disconfirmation is False
    assert deep.requires_disconfirmation is True
    assert "triangulate" in deep.instructions.lower()
    assert "final claim" in deep.instructions.lower()
    assert "parent investigator owns" in research_strategy.render_for_sub(
        m.ResearchPolicy(depth=m.ResearchDepth.deep)
    )


def test_record_observation_never_persists_encrypted_content(fresh_db) -> None:
    dossier = storage.create_dossier(
        m.DossierCreate(title="Evidence", problem_statement="Test evidence storage")
    )
    result = evidence_store.record_observation(
        dossier_id=dossier.id,
        url="https://www.consumerfinance.gov/rules-policy/",
        title="Rules",
        provenance="cited",
        excerpt="A short cited excerpt.",
        provider="anthropic_web_search",
        provider_ref="citation:test",
        model_authority="official",
    )
    assert result["authority_status"] == "government_domain"

    from vellum.db import connect
    with connect() as conn:
        source = conn.execute("SELECT * FROM evidence_sources WHERE id=?", (result["source_id"],)).fetchone()
        observation = conn.execute("SELECT * FROM evidence_observations WHERE id=?", (result["observation_id"],)).fetchone()
    assert source["model_authority"] == "official"
    assert observation["provenance"] == "cited"
    assert observation["excerpt_sha256"]
    assert "encrypted_content" not in json.dumps(dict(observation))


def test_provider_refs_are_namespaced_per_dossier(fresh_db) -> None:
    one = storage.create_dossier(m.DossierCreate(title="One", problem_statement="one"))
    two = storage.create_dossier(m.DossierCreate(title="Two", problem_statement="two"))
    first = evidence_store.record_observation(
        dossier_id=one.id, url="https://example.com/report", provenance="cited",
        provider="anthropic_web_search", provider_ref="same-result",
    )
    second = evidence_store.record_observation(
        dossier_id=two.id, url="https://example.com/report", provenance="cited",
        provider="anthropic_web_search", provider_ref="same-result",
    )
    assert first["observation_id"] != second["observation_id"]


def test_log_source_rejects_cross_dossier_section(fresh_db) -> None:
    one = storage.create_dossier(m.DossierCreate(title="One", problem_statement="one"))
    two = storage.create_dossier(m.DossierCreate(title="Two", problem_statement="two"))
    foreign = storage.upsert_section(
        two.id,
        m.SectionUpsert(
            type=m.SectionType.finding,
            title="Foreign",
            content="Not part of dossier one",
            state=m.SectionState.provisional,
            change_note="seed",
        ),
    )
    with pytest.raises(ValueError, match="does not belong"):
        handlers.log_source_consulted(one.id, {
            "citation": "https://example.com/report",
            "why_consulted": "Check evidence",
            "what_learned": "A finding",
            "supports_section_ids": [foreign.id],
        })


def test_log_source_keeps_model_authority_claim_separate(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Evidence", problem_statement="test"))
    result = handlers.log_source_consulted(dossier.id, {
        "citation": "https://example.com/report",
        "why_consulted": "Check evidence",
        "what_learned": "A finding",
        "source_type": "primary",
        "authority": "official",
        "key_claims": ["The report states the finding."],
    })
    assert result["authority_status"] == "unverified"
    assert len(result["claim_ids"]) == 1
    from vellum.db import connect
    with connect() as conn:
        row = conn.execute("SELECT * FROM evidence_sources WHERE id=?", (result["source_id"],)).fetchone()
    assert row["model_authority"] == "official"
    assert row["authority_status"] == "unverified"


def test_runtime_claims_before_mutating_handler_and_replays_result(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Ledger", problem_statement="test"))
    calls = 0

    def mutating_handler(_dossier_id, args):
        nonlocal calls
        calls += 1
        args.pop("value")
        return {"ok": True}

    handlers.HANDLER_OVERRIDES["ledger_test"] = mutating_handler
    agent = runtime.DossierAgent(dossier.id)
    original = {"value": "preserve-in-hash"}
    expected_hash = runtime._hash_tool_input(dict(original))
    first = asyncio.run(agent._dispatch_client_tool("ledger_test", original, "toolu_ledger"))
    second = asyncio.run(agent._dispatch_client_tool("ledger_test", {"value": "preserve-in-hash"}, "toolu_ledger"))
    assert first.get("is_error") is not True
    assert second.get("is_error") is not True
    assert calls == 1
    assert storage.get_tool_invocation("toolu_ledger")["input_hash"] == expected_hash


def test_runtime_never_reexecutes_in_progress_invocation(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Ledger", problem_statement="test"))
    calls = 0

    def should_not_run(_dossier_id, _args):
        nonlocal calls
        calls += 1
        return {"ok": True}

    handlers.HANDLER_OVERRIDES["ledger_busy"] = should_not_run
    payload = {"value": 1}
    storage.claim_tool_invocation(
        "toolu_busy", dossier.id, "ledger_busy", runtime._hash_tool_input(payload)
    )
    result = asyncio.run(
        runtime.DossierAgent(dossier.id)._dispatch_client_tool(
            "ledger_busy", payload, "toolu_busy"
        )
    )
    assert result["is_error"] is True
    assert "tool_invocation_in_progress" in result["content"]
    assert calls == 0


def test_same_claim_links_multiple_consulted_observations_without_duplicate_claim(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Claims", problem_statement="test"))
    first = evidence_store.record_observation(
        dossier_id=dossier.id, url="https://example.com/a", provenance="consulted"
    )
    second = evidence_store.record_observation(
        dossier_id=dossier.id, url="https://example.org/b", provenance="consulted"
    )
    claim_one = evidence_store.record_claim_links(
        dossier_id=dossier.id, observation_id=first["observation_id"],
        claims=["A material claim"], relation="supports",
    )
    claim_two = evidence_store.record_claim_links(
        dossier_id=dossier.id, observation_id=second["observation_id"],
        claims=["A material claim"], relation="supports",
    )
    assert claim_one == claim_two
    from vellum.db import connect
    with connect() as conn:
        claim_count = conn.execute("SELECT COUNT(*) n FROM research_claims").fetchone()["n"]
        link_count = conn.execute("SELECT COUNT(*) n FROM claim_evidence").fetchone()["n"]
    assert claim_count == 1
    assert link_count == 2


def test_autonomous_delivery_is_blocked_until_evidence_contract_passes(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Delivery", problem_statement="test"))
    storage.start_autonomous_research(dossier.id)
    result = handlers.mark_investigation_delivered(
        dossier.id, {"why_enough": "I believe this is finished."}
    )
    assert result["ok"] is False
    assert result["reason"] == "evidence_audit_failed"
    assert storage.get_dossier(dossier.id).status != m.DossierStatus.delivered


def test_db_handler_partial_writes_roll_back_but_error_is_replay_safe(fresh_db, monkeypatch) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Atomic", problem_statement="test"))

    def partial_then_fail(dossier_id, args):
        storage.append_reasoning(
            dossier_id,
            m.ReasoningAppend(note="must roll back", tags=["partial"]),
        )
        args.pop("value")
        raise RuntimeError("boom after write")

    monkeypatch.setitem(handlers.HANDLERS, "atomic_failure_test", partial_then_fail)
    result = asyncio.run(
        runtime.DossierAgent(dossier.id)._dispatch_client_tool(
            "atomic_failure_test", {"value": 1}, "toolu_atomic_failure"
        )
    )
    assert result["is_error"] is True
    assert "boom after write" in result["content"]
    assert storage.list_reasoning_trail(dossier.id) == []
    invocation = storage.get_tool_invocation("toolu_atomic_failure")
    assert invocation["state"] == "completed"
    assert invocation["is_error"] is True


def _attach_session_to_run(session_id: str, run_id: str) -> None:
    from vellum.db import connect

    with connect() as conn:
        conn.execute(
            "UPDATE work_sessions SET research_run_id=? WHERE id=?",
            (run_id, session_id),
        )


def test_old_session_never_inherits_newest_active_run(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Attribution", problem_statement="test"))
    old_manual = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    storage.start_autonomous_research(dossier.id)
    active = storage.get_active_research_run(dossier.id)
    assert active is not None

    observation = evidence_store.record_observation(
        dossier_id=dossier.id,
        work_session_id=old_manual.id,
        url="https://example.com/old-session",
        provenance="cited",
    )
    from vellum.db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT run_id FROM evidence_observations WHERE id=?",
            (observation["observation_id"],),
        ).fetchone()
    assert row["run_id"] is None


def test_restart_rejects_old_run_writes_and_scopes_new_observation(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(title="Restart", problem_statement="test"))
    storage.start_autonomous_research(dossier.id)
    run_one = storage.get_active_research_run(dossier.id)
    session_one = storage.start_work_session(dossier.id, m.WorkSessionTrigger.autonomous)
    _attach_session_to_run(session_one.id, run_one.id)
    first = evidence_store.record_observation(
        dossier_id=dossier.id,
        work_session_id=session_one.id,
        url="https://example.com/repeated",
        provenance="cited",
        provider="anthropic_web_search",
        provider_ref="same-citation",
    )

    storage.end_work_session(session_one.id)
    storage.restart_autonomous_research(dossier.id)
    run_two = storage.get_active_research_run(dossier.id)
    assert run_two is not None and run_two.id != run_one.id
    with pytest.raises(ValueError, match="superseded"):
        evidence_store.record_observation(
            dossier_id=dossier.id,
            run_id=run_one.id,
            url="https://example.com/late-write",
            provenance="cited",
        )
    with pytest.raises(ValueError, match="superseded"):
        evidence_store.record_claim_links(
            dossier_id=dossier.id,
            observation_id=first["observation_id"],
            claims=["Late claim"],
            relation="supports",
        )
    session_two = storage.start_work_session(dossier.id, m.WorkSessionTrigger.autonomous)
    _attach_session_to_run(session_two.id, run_two.id)
    second = evidence_store.record_observation(
        dossier_id=dossier.id,
        work_session_id=session_two.id,
        url="https://example.com/repeated",
        provenance="cited",
        provider="anthropic_web_search",
        provider_ref="same-citation",
    )
    assert second["observation_id"] != first["observation_id"]
    from vellum.db import connect
    with connect() as conn:
        run_ids = {
            row["run_id"] for row in conn.execute(
                "SELECT run_id FROM evidence_observations WHERE id IN (?,?)",
                (first["observation_id"], second["observation_id"]),
            ).fetchall()
        }
    assert run_ids == {run_one.id, run_two.id}


def test_versioned_progress_counts_first_class_limitations(fresh_db) -> None:
    dossier = storage.create_dossier(m.DossierCreate(
        title="Limitations",
        problem_statement="test",
        research_policy=m.ResearchPolicy(target_source_count=1, min_primary_sources=0),
    ))
    storage.start_autonomous_research(dossier.id)
    run = storage.get_active_research_run(dossier.id)
    session = storage.start_work_session(dossier.id, m.WorkSessionTrigger.autonomous)
    _attach_session_to_run(session.id, run.id)
    result = handlers.log_source_consulted(dossier.id, {
        "citation": "https://example.com/limited",
        "why_consulted": "Check a bounded source",
        "what_learned": "It supports one narrow point.",
        "limitations": "The sample covers only one region.",
        "key_claims": ["The narrow point is supported."],
    })
    progress = storage.get_research_progress(dossier.id)
    assert result["observation_id"]
    assert progress.unique_source_count == 1
    assert progress.sources_with_limitations == 1

    from vellum.db import connect
    with connect() as conn:
        row = conn.execute(
            "SELECT limitations FROM evidence_observations WHERE id=?",
            (result["observation_id"],),
        ).fetchone()
    assert row["limitations"] == "The sample covers only one region."


def test_init_db_adds_limitations_to_legacy_observations(tmp_path) -> None:
    from vellum import db

    db_path = tmp_path / "legacy-evidence.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE evidence_observations (
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, run_id TEXT,
                work_session_id TEXT, provenance TEXT NOT NULL, retrieved_at TEXT,
                page_age TEXT, published_at TEXT, excerpt TEXT, excerpt_sha256 TEXT,
                provider TEXT, provider_ref TEXT, created_at TEXT NOT NULL,
                UNIQUE(provider, provider_ref)
            )"""
        )
    db.init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(evidence_observations)")
        }
    assert "limitations" in columns
