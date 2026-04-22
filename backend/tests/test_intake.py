"""Intake-v2 tests: commit_intake with + without a starter investigation plan.

The day-2 story: when intake commits a dossier it SHOULD also seed a
3-5-item starter investigation_plan so the dossier agent's first turn
has something to revise instead of drafting from scratch. Seeding is
best-effort: if the plan is missing or malformed, the dossier still
commits and the plan stays None (the agent will draft one later).
"""
from __future__ import annotations

import pytest

from vellum import models as m
from vellum import storage as dossier_storage
from vellum.intake import storage as intake_storage
from vellum.intake.models import IntakeState, IntakeStatus
from vellum.intake.tools import HANDLERS, commit_intake, tool_schemas


def _populate_intake_fully() -> str:
    """Create an intake and set the four required fields. Returns intake_id."""
    session = intake_storage.create_intake()
    state = IntakeState(
        title="Negotiate deceased mother's credit card debt",
        problem_statement=(
            "Friend's mother passed with ~$40k in credit card debt across three "
            "accounts and no estate. Figure out the opening settlement percentage."
        ),
        dossier_type=m.DossierType.decision_memo,
        out_of_scope=["tax implications"],
        check_in_policy=m.CheckInPolicy(cadence=m.CheckInCadence.daily),
    )
    intake_storage.update_intake_state(session.id, state)
    return session.id


# ---------- commit without a plan ----------


def test_commit_without_plan_leaves_plan_none(fresh_db):
    """Baseline: intake can still commit with no plan. investigation_plan
    on the resulting dossier is None — the dossier agent will draft one
    on its first turn."""
    intake_id = _populate_intake_fully()

    result = commit_intake(intake_id, {})

    # Day-3 return shape: always includes intake_session_id, dossier_id,
    # and plan_seeded: bool. plan_error is absent on the happy path.
    assert result["intake_session_id"] == intake_id, result
    assert "dossier_id" in result, result
    assert result["plan_seeded"] is False
    assert "plan_error" not in result

    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    assert dossier.investigation_plan is None


def test_commit_with_empty_plan_list_skips_seeding(fresh_db):
    """plan_items=[] is the 'no opinion' signal; treat as no plan, not as error."""
    intake_id = _populate_intake_fully()

    result = commit_intake(intake_id, {"plan_items": []})

    assert result["intake_session_id"] == intake_id
    assert "dossier_id" in result
    assert result["plan_seeded"] is False
    assert "plan_error" not in result

    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    assert dossier.investigation_plan is None


# ---------- commit with a plan ----------


def test_commit_with_plan_seeds_dossier(fresh_db):
    """3-item plan: dossier.investigation_plan has 3 items, drafted_at set,
    approved_at null, revision_count=0."""
    intake_id = _populate_intake_fully()

    plan_items = [
        {
            "question": "Is this debt legally owed by the estate or by anyone else?",
            "rationale": "Settlement is premature if no one is on the hook.",
            "as_sub_investigation": False,
            "expected_sources": ["FDCPA text", "state probate code"],
        },
        {
            "question": "What's the statute of limitations in the relevant state?",
            "rationale": "Expired SOL converts 'settle' into 'let it lapse'.",
            "as_sub_investigation": False,
            "expected_sources": [
                "state bar association website",
                "nolo.com statute-of-limitations chart",
            ],
        },
        {
            "question": "What opening percentages do debt-settlement guides cite for CC debt?",
            "rationale": "Anchors the opening offer if settlement is the right track.",
            "as_sub_investigation": True,
            "expected_sources": [
                "NerdWallet settlement guides",
                "CFPB guidance",
                "consumer law blog posts",
            ],
        },
    ]

    result = commit_intake(
        intake_id,
        {
            "plan_items": plan_items,
            "plan_rationale": "Check if owed, then if timely, then how to price it.",
        },
    )

    assert result["intake_session_id"] == intake_id, result
    assert "dossier_id" in result, result
    assert result["plan_seeded"] is True
    assert result.get("plan_item_count") == 3
    assert "plan_error" not in result

    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    plan = dossier.investigation_plan
    assert plan is not None, "investigation_plan should have been seeded"
    assert len(plan.items) == 3
    assert plan.items[0].question.startswith("Is this debt")
    assert plan.items[2].as_sub_investigation is True
    assert plan.rationale.startswith("Check if owed")
    assert plan.drafted_at is not None, "drafted_at should be populated on seed"
    assert plan.approved_at is None, "intake must NOT auto-approve the plan"
    assert plan.revision_count == 0, "initial draft is revision 0"


def test_commit_with_plan_routes_through_handler_registry(fresh_db):
    """Smoke: the registry-exposed HANDLERS[commit_intake] accepts the new args."""
    intake_id = _populate_intake_fully()

    result = HANDLERS["commit_intake"](
        intake_id,
        {
            "plan_items": [
                {
                    "question": "Does the FDCPA apply here?",
                    "rationale": "Gatekeeps which collectors may contact the family.",
                    "expected_sources": ["FDCPA text at 15 U.S.C. § 1692"],
                }
            ],
            "plan_rationale": "One-item plan: narrow scope first.",
        },
    )

    assert result["intake_session_id"] == intake_id
    assert "dossier_id" in result
    assert result["plan_seeded"] is True
    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    assert dossier.investigation_plan is not None
    assert len(dossier.investigation_plan.items) == 1


# ---------- invalid plan items ----------


def test_commit_with_invalid_plan_item_commits_dossier_without_plan(fresh_db):
    """Design choice documented in commit_intake: plan is best-effort, so a
    malformed plan does NOT roll back the dossier. The dossier commits, the
    plan stays None, and ``plan_error`` is surfaced for the model.

    Rationale: intake's contract is "get a dossier open." Validation of a
    best-effort seed shouldn't block that contract. The dossier agent can
    draft a correct plan on its first turn.
    """
    intake_id = _populate_intake_fully()

    # Missing required ``question`` field.
    bad_items = [
        {
            "rationale": "no question here",
            "expected_sources": ["the web"],
        }
    ]

    result = commit_intake(intake_id, {"plan_items": bad_items})

    assert result["intake_session_id"] == intake_id
    assert "dossier_id" in result
    assert "plan_error" in result
    assert result["plan_seeded"] is False

    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    assert dossier.investigation_plan is None


def test_commit_with_non_list_plan_items_surfaces_error(fresh_db):
    """plan_items=<string> is a shape-level mistake; surface plan_error, commit anyway."""
    intake_id = _populate_intake_fully()

    result = commit_intake(intake_id, {"plan_items": "not a list"})

    assert result["intake_session_id"] == intake_id
    assert "dossier_id" in result
    assert "plan_error" in result
    assert result["plan_seeded"] is False
    dossier = dossier_storage.get_dossier(result["dossier_id"])
    assert dossier is not None
    assert dossier.investigation_plan is None


# ---------- tool schema ----------


def test_commit_intake_schema_exposes_optional_plan_args(fresh_db):
    """The tool schema must advertise plan_items + plan_rationale as optional
    so the model knows it can pass them without them being required."""
    schemas = {s["name"]: s for s in tool_schemas()}
    commit_schema = schemas["commit_intake"]

    props = commit_schema["input_schema"]["properties"]
    assert "plan_items" in props
    assert "plan_rationale" in props
    # Neither field is required — they're optional seeds.
    assert commit_schema["input_schema"].get("required", []) == []

    # Individual plan item declares ``question`` as required.
    item_schema = props["plan_items"]["items"]
    assert "question" in item_schema["required"]


# ---------- commit invariants still hold ----------


def test_commit_without_required_fields_still_errors(fresh_db):
    """Seeding a plan does NOT relax the 4-field commit gate."""
    session = intake_storage.create_intake()
    # Empty state — no title / problem_statement / etc.
    result = commit_intake(
        session.id,
        {
            "plan_items": [
                {"question": "Does this matter?", "rationale": "hypothesis"}
            ],
        },
    )
    assert "error" in result
    assert "missing" in result
    # Missing-field errors echo the intake_session_id so the model has it
    # in context; no dossier was created.
    assert result["intake_session_id"] == session.id
    assert "dossier_id" not in result


def test_commit_is_idempotent_with_plan_args(fresh_db):
    """Second commit of an already-committed intake returns the dossier_id;
    the second call's plan args are ignored (don't overwrite the plan)."""
    intake_id = _populate_intake_fully()
    first = commit_intake(
        intake_id,
        {
            "plan_items": [
                {"question": "Is the debt owed?", "rationale": "gate"},
            ],
        },
    )
    dossier_id = first["dossier_id"]
    first_plan = dossier_storage.get_dossier(dossier_id).investigation_plan
    assert first_plan is not None
    assert len(first_plan.items) == 1

    # Second call: different plan args, but idempotent commit returns same id.
    # plan_seeded=False on the re-commit because THIS call did not seed a plan
    # (the first one did, but we don't overwrite on re-commit).
    second = commit_intake(
        intake_id,
        {
            "plan_items": [
                {"question": "Totally different Q?", "rationale": "ignored"},
                {"question": "And another?", "rationale": "also ignored"},
            ],
        },
    )
    assert second == {
        "intake_session_id": intake_id,
        "dossier_id": dossier_id,
        "plan_seeded": False,
    }

    # Plan on disk must still be the first one — idempotent commit does not
    # overwrite.
    latest = dossier_storage.get_dossier(dossier_id).investigation_plan
    assert latest is not None
    assert len(latest.items) == 1
    assert latest.items[0].question == "Is the debt owed?"
