"""Intake-agent tool handlers.

The intake conversation uses these tools to accumulate the five dossier-creation
fields and eventually commit them into a real Dossier. Each handler mirrors the
pattern established in ``vellum.tools.handlers``:

- Validate args (usually via enum coercion).
- Read the current IntakeSession, mutate the one field, persist.
- Return a compact dict for the agent — state snapshot, not prose.

Unlike the day-1 dossier handlers, there is no work_session/change_log here:
intake has no plan-diff, just an accumulating state blob and a commit.
"""
from __future__ import annotations

from typing import Any, Callable

from .. import models as m
from .. import storage as dossier_storage
from . import models as im
from . import storage as intake_storage


# ---------- helpers ----------


def _intake_or_error(intake_id: str):
    """Fetch the intake session or return an error-dict sentinel.

    Returns (session, None) on success or (None, error_dict) on miss, so callers
    can ``return err`` without further branching.
    """
    session = intake_storage.get_intake(intake_id)
    if session is None:
        return None, {"error": "intake not found"}
    return session, None


def _state_ok(state: im.IntakeState) -> dict[str, Any]:
    return {"ok": True, "state": state.model_dump(mode="json")}


# ---------- tool handlers ----------


def set_title(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    title = args.get("title", "")
    if not isinstance(title, str) or not title.strip():
        return {"error": "title must be a non-empty string"}
    state = session.state.model_copy(update={"title": title.strip()})
    updated = intake_storage.update_intake_state(intake_id, state)
    return _state_ok(updated.state)


def set_problem_statement(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    ps = args.get("problem_statement", "")
    if not isinstance(ps, str) or not ps.strip():
        return {"error": "problem_statement must be a non-empty string"}
    state = session.state.model_copy(update={"problem_statement": ps.strip()})
    updated = intake_storage.update_intake_state(intake_id, state)
    return _state_ok(updated.state)


def set_dossier_type(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    raw = args.get("dossier_type")
    try:
        dtype = m.DossierType(raw)
    except ValueError:
        return {
            "error": f"invalid dossier_type: {raw!r}",
            "allowed": [t.value for t in m.DossierType],
        }
    state = session.state.model_copy(update={"dossier_type": dtype})
    updated = intake_storage.update_intake_state(intake_id, state)
    return _state_ok(updated.state)


def set_out_of_scope(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    items = args.get("items", [])
    if not isinstance(items, list) or not all(isinstance(s, str) for s in items):
        return {"error": "items must be a list of strings"}
    # Replace semantics — keep it simple.
    cleaned = [s.strip() for s in items if s.strip()]
    state = session.state.model_copy(update={"out_of_scope": cleaned})
    updated = intake_storage.update_intake_state(intake_id, state)
    return _state_ok(updated.state)


def set_check_in_policy(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    raw = args.get("cadence")
    try:
        cadence = m.CheckInCadence(raw)
    except ValueError:
        return {
            "error": f"invalid cadence: {raw!r}",
            "allowed": [c.value for c in m.CheckInCadence],
        }
    notes = args.get("notes", "") or ""
    if not isinstance(notes, str):
        return {"error": "notes must be a string"}
    policy = m.CheckInPolicy(cadence=cadence, notes=notes)
    state = session.state.model_copy(update={"check_in_policy": policy})
    updated = intake_storage.update_intake_state(intake_id, state)
    return _state_ok(updated.state)


def commit_intake(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Commit the gathered intake as a dossier, optionally seeding a plan.

    Args may contain:
      - ``plan_items``: optional list of investigation-plan-item dicts
        ({question, rationale, as_sub_investigation, expected_sources}).
      - ``plan_rationale``: optional one-sentence rationale for the plan.

    Return shape (day-3 polish):
      - On successful commit:
          {
              "intake_session_id": str,
              "dossier_id": str,
              "plan_seeded": bool,
              "plan_error"?: str,   # only present when plan provided but rejected
          }
      - On missing-required-field:
          {"error": ..., "missing": [...]}  — the model can recover by calling
          the appropriate set_* tools, then retrying commit_intake.
      - On intake-not-found:
          {"error": "intake not found"}
      - Idempotent: if this intake was already committed, echoes the same
        dossier_id with ``plan_seeded=False`` (we don't overwrite the plan
        on a re-commit; the first commit wins).

    If ``plan_items`` is provided and non-empty, after creating the dossier
    we call ``storage.update_investigation_plan`` with ``approve=False`` so
    the seeded plan is explicitly a draft the user (or the day-2 agent)
    can approve/redirect. If validation of the plan fails, the dossier
    still commits — the plan is best-effort seeding, not a hard commit
    dependency. This keeps intake's contract ("get a dossier open") intact
    even when the model drafts a malformed plan; the dossier agent can
    draft a fresh plan on its first turn.
    """
    session, err = _intake_or_error(intake_id)
    if err:
        return err

    # Idempotency: if already committed, echo the dossier_id with the
    # day-3 shape. plan_seeded=False on the re-commit reflects that THIS
    # call did not seed a plan (we don't overwrite on re-commit); callers
    # that need to know whether a plan was ever seeded should read the
    # dossier directly.
    if session.status == im.IntakeStatus.committed and session.dossier_id:
        return {
            "intake_session_id": intake_id,
            "dossier_id": session.dossier_id,
            "plan_seeded": False,
        }

    state = session.state
    missing: list[str] = []
    if not state.title:
        missing.append("title")
    if not state.problem_statement:
        missing.append("problem_statement")
    if state.dossier_type is None:
        missing.append("dossier_type")
    if state.check_in_policy is None:
        missing.append("check_in_policy")
    # out_of_scope is allowed to be an empty list — the user genuinely may
    # have nothing to exclude — but the FIELD must have been considered.
    # We don't enforce that here; the intake agent's prompt already asks.

    if missing:
        # Recoverable error: model can call set_* tools for the named
        # fields and retry. ``intake_session_id`` echoed so the model has
        # the ID in its local context if it needs to reference it.
        return {
            "error": f"missing required fields: {', '.join(missing)}",
            "missing": missing,
            "intake_session_id": intake_id,
        }

    # All required fields present — construct and persist.
    create = m.DossierCreate(
        title=state.title,
        problem_statement=state.problem_statement,
        out_of_scope=state.out_of_scope,
        dossier_type=state.dossier_type,
        check_in_policy=state.check_in_policy,
    )
    dossier = dossier_storage.create_dossier(create)
    intake_storage.update_intake_status(
        intake_id, im.IntakeStatus.committed, dossier_id=dossier.id
    )

    # Best-effort plan seeding. We treat the plan as an opening draft so
    # failure here must NOT roll back the committed dossier. On validation
    # errors we surface ``plan_error`` to the model alongside dossier_id
    # so it knows the plan didn't stick and can retry via the dossier-side
    # plan tools once the agent takes over.
    result: dict[str, Any] = {
        "intake_session_id": intake_id,
        "dossier_id": dossier.id,
        "plan_seeded": False,
    }
    plan_items_raw = args.get("plan_items")
    if plan_items_raw:
        if not isinstance(plan_items_raw, list):
            result["plan_error"] = "plan_items must be a list"
            return result
        plan_rationale = args.get("plan_rationale", "") or ""
        if not isinstance(plan_rationale, str):
            result["plan_error"] = "plan_rationale must be a string"
            return result
        try:
            items = [m.InvestigationPlanItem.model_validate(i) for i in plan_items_raw]
            patch = m.InvestigationPlanUpdate(
                items=items,
                rationale=plan_rationale,
                approve=False,
            )
        except Exception as exc:  # pydantic ValidationError or TypeError
            result["plan_error"] = f"invalid plan: {type(exc).__name__}: {exc}"
            return result
        dossier_storage.update_investigation_plan(dossier.id, patch)
        result["plan_seeded"] = True
        result["plan_item_count"] = len(items)
    return result


def abandon_intake(intake_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session, err = _intake_or_error(intake_id)
    if err:
        return err
    # Idempotent: no-op if already abandoned.
    if session.status != im.IntakeStatus.abandoned:
        intake_storage.update_intake_status(intake_id, im.IntakeStatus.abandoned)
    return {"ok": True}


# ---------- registry + schemas for Agent SDK wiring ----------


HANDLERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "set_title": set_title,
    "set_problem_statement": set_problem_statement,
    "set_dossier_type": set_dossier_type,
    "set_out_of_scope": set_out_of_scope,
    "set_check_in_policy": set_check_in_policy,
    "commit_intake": commit_intake,
    "abandon_intake": abandon_intake,
}


TOOL_DESCRIPTIONS: dict[str, str] = {
    "set_title": (
        "Set the dossier's short title. Call once the user has given you "
        "something to work with; it's OK to revise it later."
    ),
    "set_problem_statement": (
        "Record the user's problem in their own words, tightened for clarity. "
        "This is the single most important field."
    ),
    "set_dossier_type": (
        "Classify the dossier as one of: decision_memo, investigation, "
        "position_paper, comparison, plan, script. Default to 'investigation' "
        "if unsure."
    ),
    "set_out_of_scope": (
        "Record items the user has explicitly excluded from scope. Replaces "
        "the full list each call."
    ),
    "set_check_in_policy": (
        "Record how often the user expects to check in "
        "(on_demand | daily | weekly | material_changes_only), plus optional notes."
    ),
    "commit_intake": (
        "Create the dossier and end the intake. Only call when title, problem_statement, "
        "dossier_type, and check_in_policy are set (out_of_scope is optional — "
        "but confirm the user has nothing to exclude before calling). "
        "Returns intake_session_id, dossier_id, plan_seeded: bool, and plan_error (optional). "
        "If required fields are missing, returns an error with a ``missing`` list — "
        "call the matching set_* tool(s), then retry commit_intake. "
        "May optionally seed a starter investigation plan via plan_items (3-5 items) "
        "+ plan_rationale; if omitted, the dossier agent drafts the plan on its first turn. "
        "Plan seeding is best-effort: a malformed plan returns plan_error but the dossier "
        "still commits."
    ),
    "abandon_intake": (
        "Mark the intake abandoned when the user asks to stop or the conversation has "
        "gone off-track. Pass a short 'reason' for the log."
    ),
}


def tool_schemas() -> list[dict[str, Any]]:
    """Emit Anthropic-tool-compatible schemas for all 7 intake tools."""
    dossier_types = [t.value for t in m.DossierType]
    cadences = [c.value for c in m.CheckInCadence]

    return [
        {
            "name": "set_title",
            "description": TOOL_DESCRIPTIONS["set_title"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short dossier title."},
                },
                "required": ["title"],
            },
        },
        {
            "name": "set_problem_statement",
            "description": TOOL_DESCRIPTIONS["set_problem_statement"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "problem_statement": {
                        "type": "string",
                        "description": "The problem in the user's words, tightened.",
                    },
                },
                "required": ["problem_statement"],
            },
        },
        {
            "name": "set_dossier_type",
            "description": TOOL_DESCRIPTIONS["set_dossier_type"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "dossier_type": {"type": "string", "enum": dossier_types},
                },
                "required": ["dossier_type"],
            },
        },
        {
            "name": "set_out_of_scope",
            "description": TOOL_DESCRIPTIONS["set_out_of_scope"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Full replacement list of out-of-scope items.",
                    },
                },
                "required": ["items"],
            },
        },
        {
            "name": "set_check_in_policy",
            "description": TOOL_DESCRIPTIONS["set_check_in_policy"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "cadence": {"type": "string", "enum": cadences},
                    "notes": {"type": "string", "default": ""},
                },
                "required": ["cadence"],
            },
        },
        {
            "name": "commit_intake",
            "description": TOOL_DESCRIPTIONS["commit_intake"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "plan_items": {
                        "type": "array",
                        "description": (
                            "Optional starter investigation plan — 3 to 5 concrete "
                            "sub-questions seeded for the dossier agent to revise "
                            "rather than draft from scratch. Omit if the problem is "
                            "too thin to plan credibly."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {
                                    "type": "string",
                                    "description": "A concrete, investigable sub-question.",
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "One sentence on why this is worth investigating.",
                                },
                                "as_sub_investigation": {
                                    "type": "boolean",
                                    "description": (
                                        "True only if this deserves its own scoped "
                                        "sub-agent; default false for leaf questions."
                                    ),
                                    "default": False,
                                },
                                "expected_sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "2-4 concrete source types the answer likely "
                                        "comes from (e.g. 'FDCPA text', 'IRS Pub 559')."
                                    ),
                                },
                            },
                            "required": ["question"],
                        },
                    },
                    "plan_rationale": {
                        "type": "string",
                        "description": (
                            "One-sentence rationale for the plan shape (why these "
                            "items, why in this order). Optional."
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "abandon_intake",
            "description": TOOL_DESCRIPTIONS["abandon_intake"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the intake is being abandoned (for logging).",
                    },
                },
                "required": ["reason"],
            },
        },
    ]


# ---------- smoke test ----------


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from .. import config, db

    # Throwaway DB — same pattern as day-2 tests.
    tmp = Path(tempfile.mkdtemp(prefix="vellum_intake_tools_")) / "test.db"
    config.DB_PATH = tmp
    db.init_db(tmp)

    # Create a fresh intake via the sibling storage.
    session = intake_storage.create_intake()
    intake_id = session.id
    assert session.status == im.IntakeStatus.gathering

    # 1. Populate the four required fields.
    r = set_title(intake_id, {"title": "Should we migrate analytics to DuckDB?"})
    assert r.get("ok") is True, r
    assert r["state"]["title"].startswith("Should we")

    r = set_problem_statement(
        intake_id,
        {"problem_statement": "Analytics queries are saturating our primary Postgres."},
    )
    assert r.get("ok") is True, r

    r = set_dossier_type(intake_id, {"dossier_type": "investigation"})
    assert r.get("ok") is True, r
    assert r["state"]["dossier_type"] == "investigation"

    # Invalid enum should produce an error dict without mutating state.
    bad = set_dossier_type(intake_id, {"dossier_type": "not_a_thing"})
    assert "error" in bad and "allowed" in bad

    r = set_check_in_policy(intake_id, {"cadence": "on_demand"})
    assert r.get("ok") is True, r
    assert r["state"]["check_in_policy"]["cadence"] == "on_demand"

    bad_cad = set_check_in_policy(intake_id, {"cadence": "hourly"})
    assert "error" in bad_cad

    # 2. out_of_scope is allowed to stay empty — is_complete() does not require it.
    # Commit with the 4 required fields.
    committed = commit_intake(intake_id, {})
    assert "dossier_id" in committed, committed
    dossier_id = committed["dossier_id"]

    # 3. Verify the dossier actually exists in the real store.
    dossier = dossier_storage.get_dossier(dossier_id)
    assert dossier is not None
    assert dossier.dossier_type == m.DossierType.investigation
    assert dossier.title.startswith("Should we")

    # 4. Incomplete-commit path: fresh intake, try to commit before filling in.
    empty_session = intake_storage.create_intake()
    bad_commit = commit_intake(empty_session.id, {})
    assert "error" in bad_commit and "missing" in bad_commit
    assert set(bad_commit["missing"]) >= {
        "title",
        "problem_statement",
        "dossier_type",
        "check_in_policy",
    }

    # 5. Intake-not-found path.
    missing_err = set_title("intk_does_not_exist", {"title": "x"})
    assert missing_err == {"error": "intake not found"}

    # 6. out_of_scope replace semantics.
    r = set_out_of_scope(empty_session.id, {"items": ["OLTP migration", "vendor warehouses"]})
    assert r["state"]["out_of_scope"] == ["OLTP migration", "vendor warehouses"]
    r = set_out_of_scope(empty_session.id, {"items": ["just this one"]})
    assert r["state"]["out_of_scope"] == ["just this one"]

    # 7. abandon_intake on a fresh intake, then again (idempotent).
    doomed = intake_storage.create_intake()
    a1 = abandon_intake(doomed.id, {"reason": "user changed their mind"})
    assert a1 == {"ok": True}
    a2 = abandon_intake(doomed.id, {"reason": "still abandoning"})
    assert a2 == {"ok": True}

    # 8. Tool schemas — 7 entries, each well-formed.
    schemas = tool_schemas()
    assert len(schemas) == 7, f"expected 7 schemas, got {len(schemas)}"
    names = {s["name"] for s in schemas}
    assert names == set(HANDLERS.keys())
    for s in schemas:
        assert "name" in s and "description" in s and "input_schema" in s
        assert s["input_schema"]["type"] == "object"

    print("intake tools OK")
