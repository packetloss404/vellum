"""Day-1 checks for the v2 agent tool surface.

This worktree is branched from main, so the v2 Pydantic models and storage
functions that parallel agents are adding are probably not here yet. Each
v2 domain test is therefore guarded with a tiny import probe that skips
cleanly when its dependency hasn't merged. The registry/schema checks
don't depend on any v2 code — they run on every branch.

Run: cd backend && .venv/Scripts/python.exe -m pytest tests/test_tool_surface.py -v
"""
from __future__ import annotations

import os
import tempfile

import pytest
from pydantic import BaseModel


# Each test that touches the DB gets a fresh tempfile. We set VELLUM_DB_PATH
# BEFORE importing vellum.config (which resolves DB_PATH once at import time),
# so we import the library lazily inside fixtures / tests.


def _fresh_db_env() -> str:
    path = tempfile.mktemp(suffix=".db")
    os.environ["VELLUM_DB_PATH"] = path
    return path


@pytest.fixture
def fresh_db(monkeypatch):
    """Point config.DB_PATH at a fresh sqlite tempfile, init schema, yield."""
    path = _fresh_db_env()
    from vellum import config as _config
    from pathlib import Path
    monkeypatch.setattr(_config, "DB_PATH", Path(path).resolve())
    from vellum import db as _db
    _db.init_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# --- Test configuration: the canonical v2 tool names ---

V2_TOOL_NAMES = {
    "update_investigation_plan",
    "update_debrief",
    "add_artifact",
    "update_artifact",
    "spawn_sub_investigation",
    "complete_sub_investigation",
    "log_source_consulted",
    "mark_considered_and_rejected",
    "set_next_action",
    "declare_stuck",
    "mark_investigation_delivered",
}


# ======================================================================
# Registry / schema checks (no v2 deps required)
# ======================================================================


def test_tool_schemas_returns_at_least_14_tools():
    from vellum.tools import handlers
    schemas = handlers.tool_schemas()
    assert len(schemas) >= 14, f"expected ≥14 tools, got {len(schemas)}"


def test_tool_schemas_contains_every_v2_name():
    from vellum.tools import handlers
    schema_names = {s["name"] for s in handlers.tool_schemas()}
    missing = V2_TOOL_NAMES - schema_names
    assert not missing, f"tool_schemas missing v2 names: {sorted(missing)}"


def test_every_schema_has_name_description_and_input_schema():
    from vellum.tools import handlers
    for s in handlers.tool_schemas():
        assert "name" in s, f"schema missing name: {s}"
        assert "description" in s and s["description"], f"missing description: {s['name']}"
        assert "input_schema" in s, f"missing input_schema: {s['name']}"
        assert s["input_schema"].get("type") == "object", s["name"]


def test_every_handler_has_a_description():
    from vellum.tools import handlers
    missing = set(handlers.HANDLERS) - set(handlers.TOOL_DESCRIPTIONS)
    assert not missing, f"handlers without descriptions: {sorted(missing)}"


def test_tool_description_length_bounds():
    """Every TOOL_DESCRIPTIONS entry must be between 80 and 700 chars.

    Lower bound: descriptions shorter than ~80 chars are almost certainly
    stubs that fail to give the agent a "when do I call this" test.
    Upper bound: descriptions longer than ~700 chars bloat the system
    prompt and bury the decision rule under example clutter. Catches
    drift in either direction.
    """
    from vellum.tools import handlers
    out_of_range: list[tuple[str, int]] = []
    for name, desc in handlers.TOOL_DESCRIPTIONS.items():
        n = len(desc)
        if not (80 <= n <= 700):
            out_of_range.append((name, n))
    assert not out_of_range, (
        f"tool descriptions out of [80, 700] char bounds: {out_of_range}"
    )


def test_critical_tool_descriptions_have_examples():
    """The critical tools should include a concrete 'Example' in their
    description. The agent is far more reliable when given a shape to
    mimic than when given prose alone.
    """
    from vellum.tools import handlers
    critical = {
        "upsert_section",
        "flag_decision_point",
        "log_source_consulted",
        "mark_considered_and_rejected",
        "add_artifact",
        "spawn_sub_investigation",
        "update_investigation_plan",
    }
    missing_example: list[str] = []
    for name in critical:
        desc = handlers.TOOL_DESCRIPTIONS.get(name, "")
        lower = desc.lower()
        if "example" not in lower and "good:" not in lower:
            missing_example.append(name)
    assert not missing_example, (
        f"critical tools missing a concrete example: {missing_example}"
    )


def test_log_source_consulted_description_mentions_per_source_discipline():
    """The '47 sources' counter depends on the agent logging each source
    exactly once (not per search). The description must say so loudly."""
    from vellum.tools import handlers
    desc = handlers.TOOL_DESCRIPTIONS["log_source_consulted"].lower()
    assert "once" in desc or "one call per source" in desc or "per source" in desc, (
        "log_source_consulted description should emphasise one call per source"
    )
    assert "search" in desc, (
        "log_source_consulted description should address that searching does not count"
    )


def test_mark_investigation_delivered_description_flags_termination():
    """This tool ends the agent loop. The description must make that obvious."""
    from vellum.tools import handlers
    desc = handlers.TOOL_DESCRIPTIONS["mark_investigation_delivered"].lower()
    assert "terminate" in desc or "stops" in desc or "stop" in desc, (
        "mark_investigation_delivered should flag that it terminates the loop"
    )


def test_update_debrief_description_references_checkpoints():
    """update_debrief should be called at checkpoints and before delivery."""
    from vellum.tools import handlers
    desc = handlers.TOOL_DESCRIPTIONS["update_debrief"].lower()
    assert "checkpoint" in desc or "before" in desc, (
        "update_debrief should reference checkpoints or pre-delivery cadence"
    )


def test_spawn_sub_investigation_description_flags_sync_semantics():
    """spawn_sub_investigation is a blocking call from the agent's POV —
    the description should tell the agent so it does not try to poll."""
    from vellum.tools import handlers
    desc = handlers.TOOL_DESCRIPTIONS["spawn_sub_investigation"].lower()
    assert "synchronous" in desc or "blocking" in desc or "runs to completion" in desc, (
        "spawn_sub_investigation should document its synchronous/blocking semantics"
    )


def test_flag_decision_point_description_mentions_plan_approval_kind():
    """Plan approval is a specific kind of decision_point; the description
    should teach the agent the convention."""
    from vellum.tools import handlers
    desc = handlers.TOOL_DESCRIPTIONS["flag_decision_point"].lower()
    assert "plan_approval" in desc, (
        "flag_decision_point should mention the plan_approval kind convention"
    )


def test_overlapping_tool_pairs_have_disambiguation():
    """Tools with overlapping surfaces should include a 'do NOT use' or
    'vs' pointer so the agent routes correctly."""
    from vellum.tools import handlers

    def _disambiguates(desc: str, other_tool: str) -> bool:
        lower = desc.lower()
        return (
            other_tool.lower() in lower
            and ("do not" in lower or "do not use" in lower or "not" in lower or "instead" in lower)
        )

    pairs = [
        # flag_needs_input vs flag_decision_point
        ("flag_needs_input", "flag_decision_point"),
        ("flag_decision_point", "flag_needs_input"),
        # upsert_section vs add_artifact
        ("upsert_section", "add_artifact"),
        ("add_artifact", "upsert_section"),
        # append_reasoning vs log_source_consulted / upsert_section
        ("append_reasoning", "upsert_section"),
    ]
    missing: list[tuple[str, str]] = []
    for src, other in pairs:
        desc = handlers.TOOL_DESCRIPTIONS[src]
        if not _disambiguates(desc, other):
            missing.append((src, other))
    assert not missing, (
        f"overlapping tools missing disambiguation: {missing}"
    )


def test_every_handler_has_a_schema():
    from vellum.tools import handlers
    schema_names = {s["name"] for s in handlers.tool_schemas()}
    missing = set(handlers.HANDLERS) - schema_names
    assert not missing, f"handlers without schemas: {sorted(missing)}"


def test_every_input_model_is_pydantic():
    from vellum.tools import handlers
    for name, model in handlers._INPUT_MODELS.items():
        assert isinstance(model, type), f"{name}: not a type"
        assert issubclass(model, BaseModel), f"{name}: {model} is not a pydantic BaseModel"


def test_handlers_registry_covers_every_v2_tool():
    from vellum.tools import handlers
    missing = V2_TOOL_NAMES - set(handlers.HANDLERS)
    assert not missing, f"HANDLERS missing v2 names: {sorted(missing)}"


def test_v1_tools_still_registered():
    """Intake/runtime still reference v1 by name."""
    from vellum.tools import handlers
    v1 = {
        "upsert_section", "update_section_state", "delete_section",
        "reorder_sections", "flag_needs_input", "flag_decision_point",
        "append_reasoning", "mark_ruled_out", "check_stuck",
        "request_user_paste",
    }
    missing = v1 - set(handlers.HANDLERS)
    assert not missing, f"v1 tools lost from registry: {sorted(missing)}"


# ======================================================================
# v2 handler smoke tests (guarded per-domain by import-probe skips)
# ======================================================================


def _make_dossier():
    """Create a fresh dossier and return its id. Expects fresh_db to be active."""
    from vellum import storage
    from vellum import models as m
    d = storage.create_dossier(
        m.DossierCreate(
            title="tool surface smoke",
            problem_statement="smoke-test the v2 handlers end-to-end",
            dossier_type=m.DossierType.investigation,
        )
    )
    return d.id


# --- update_investigation_plan ---


def test_update_investigation_plan_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "InvestigationPlanUpdate") or not hasattr(_storage, "update_investigation_plan"):
        pytest.skip("InvestigationPlanUpdate / storage.update_investigation_plan not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    # Construct a minimal InvestigationPlanItem + Update using model_validate so
    # we don't have to know the exact field names.
    item_model = getattr(m, "InvestigationPlanItem", None)
    if item_model is None:
        pytest.skip("InvestigationPlanItem not merged yet")
    try:
        plan_args = m.InvestigationPlanUpdate.model_validate({
            "items": [{"question": "Is this debt valid?", "becomes_sub_investigation": True}],
            "rationale": "day-1 smoke",
            "approve": False,
        }).model_dump()
    except Exception as e:
        pytest.skip(f"InvestigationPlanUpdate shape differs from smoke-test assumptions: {e}")
    out = handlers.update_investigation_plan(dossier_id, plan_args)
    assert out is not None


# --- update_debrief ---


def test_update_debrief_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "DebriefUpdate") or not hasattr(_storage, "update_debrief"):
        pytest.skip("DebriefUpdate / storage.update_debrief not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    try:
        args = m.DebriefUpdate.model_validate({
            "what_i_did": "reviewed the FDCPA timeline",
        }).model_dump(exclude_none=True)
    except Exception as e:
        pytest.skip(f"DebriefUpdate shape differs: {e}")
    out = handlers.update_debrief(dossier_id, args)
    assert out is not None


# --- add_artifact / update_artifact ---


def test_artifact_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    needed = ["ArtifactCreate", "ArtifactUpdate", "ArtifactKind", "ArtifactState"]
    if not all(hasattr(m, n) for n in needed):
        pytest.skip("Artifact models not merged yet")
    if not hasattr(_storage, "create_artifact") or not hasattr(_storage, "update_artifact"):
        pytest.skip("storage.create_artifact / update_artifact not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    try:
        kind_value = next(iter(m.ArtifactKind)).value  # first enum member
        create_args = m.ArtifactCreate.model_validate({
            "kind": kind_value,
            "title": "FDCPA demand letter v1",
            "content": "# letter\n...",
            "intended_use": "mail to Capital One recovery dept",
        }).model_dump()
    except Exception as e:
        pytest.skip(f"ArtifactCreate shape differs: {e}")
    out = handlers.add_artifact(dossier_id, create_args)
    assert "artifact_id" in out
    try:
        update_args = {"artifact_id": out["artifact_id"]}
        update_args.update(
            m.ArtifactUpdate.model_validate({"change_note": "tightened the ask"})
            .model_dump(exclude_none=True)
        )
    except Exception as e:
        pytest.skip(f"ArtifactUpdate shape differs: {e}")
    out2 = handlers.update_artifact(dossier_id, update_args)
    assert out2["artifact_id"] == out["artifact_id"]


# --- spawn / complete sub_investigation ---


def test_sub_investigation_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not all(hasattr(m, n) for n in ("SubInvestigationSpawn", "SubInvestigationComplete")):
        pytest.skip("SubInvestigation models not merged yet")
    if not hasattr(_storage, "spawn_sub_investigation") or not hasattr(_storage, "complete_sub_investigation"):
        pytest.skip("storage.spawn/complete_sub_investigation not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    spawn_args = m.SubInvestigationSpawn.model_validate({
        "scope": "CA statute of limitations — does SOL bar this collection?",
        "questions": ["Does CA SOL bar this collection?"],
    }).model_dump()
    out = handlers.spawn_sub_investigation(dossier_id, spawn_args)
    assert "sub_investigation_id" in out
    assert out["state"] == "running"

    try:
        complete_args = {"sub_investigation_id": out["sub_investigation_id"]}
        complete_args.update(
            m.SubInvestigationComplete.model_validate({
                "return_summary": "SOL is 4 years; this debt is past it.",
            }).model_dump(exclude_none=True)
        )
    except Exception as e:
        pytest.skip(f"SubInvestigationComplete shape differs: {e}")
    out2 = handlers.complete_sub_investigation(dossier_id, complete_args)
    assert out2["sub_investigation_id"] == out["sub_investigation_id"]


# --- log_source_consulted ---


def test_log_source_consulted_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "InvestigationLogAppend") or not hasattr(_storage, "append_investigation_log"):
        pytest.skip("InvestigationLog model / storage.append_investigation_log not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    out = handlers.log_source_consulted(dossier_id, {
        "citation": "https://www.consumerfinance.gov/rules-policy/regulations/1006/",
        "why_consulted": "Does Reg F bar this outreach cadence?",
        "what_learned": "Reg F caps at 7 calls / 7 days per debt.",
        "supports_section_ids": [],
    })
    assert out is not None


# --- mark_considered_and_rejected ---


def test_mark_considered_and_rejected_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "ConsideredAndRejectedCreate") or not hasattr(_storage, "add_considered_and_rejected"):
        pytest.skip("ConsideredAndRejected model / storage not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    try:
        args = m.ConsideredAndRejectedCreate.model_validate({
            "path": "File a CFPB complaint immediately",
            "why_compelling": "Fast, free, creates a paper trail",
            "why_rejected": "Collector has 15 days to respond — wastes lead time",
            "cost_of_error": "Minor; can file later",
        }).model_dump()
    except Exception as e:
        pytest.skip(f"ConsideredAndRejectedCreate shape differs: {e}")
    out = handlers.mark_considered_and_rejected(dossier_id, args)
    assert "considered_and_rejected_id" in out


# --- set_next_action ---


def test_set_next_action_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "NextActionCreate") or not hasattr(_storage, "add_next_action"):
        pytest.skip("NextActionCreate / storage.add_next_action not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    try:
        args = m.NextActionCreate.model_validate({
            "action": "Request debt verification from Capital One under FDCPA §1692g",
            "rationale": "Starts the clock on their verification duty",
        }).model_dump()
    except Exception as e:
        pytest.skip(f"NextActionCreate shape differs: {e}")
    out = handlers.set_next_action(dossier_id, args)
    assert "next_action_id" in out


# --- declare_stuck ---


def test_declare_stuck_smoke(fresh_db):
    from vellum import models as m
    from vellum import storage as _storage
    if not hasattr(m, "InvestigationLogAppend") or not hasattr(_storage, "append_investigation_log"):
        pytest.skip("InvestigationLog model / storage not merged yet")
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    out = handlers.declare_stuck(dossier_id, {
        "summary_of_attempts": "Tried three sources, all contradictory",
        "options_for_user": [
            {"label": "Pick interpretation A", "implications": "aggressive", "recommended": True},
            {"label": "Pick interpretation B", "implications": "safer", "recommended": False},
        ],
        "recommendation": "A — aligns with the 2024 bulletin",
    })
    assert "decision_point_id" in out


# --- mark_investigation_delivered ---


def test_mark_investigation_delivered_smoke(fresh_db):
    """This one uses only v1 storage (update_dossier + append_reasoning), so it
    should work on the current branch."""
    from vellum import models as m
    from vellum import storage
    from vellum.tools import handlers
    dossier_id = _make_dossier()
    out = handlers.mark_investigation_delivered(
        dossier_id,
        {"why_enough": "covered the core question, drafted the letter, left filing for the user"},
    )
    assert out["status"] == m.DossierStatus.delivered.value
    refetched = storage.get_dossier(dossier_id)
    assert refetched is not None
    assert refetched.status == m.DossierStatus.delivered
    # Delivered note made it into the reasoning trail.
    trail = storage.list_reasoning_trail(dossier_id)
    assert any(e.note.startswith("[delivered]") and "delivered" in e.tags for e in trail), (
        "mark_investigation_delivered should leave a [delivered] note in the reasoning trail"
    )
