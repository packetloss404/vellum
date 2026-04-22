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
    session, err = _intake_or_error(intake_id)
    if err:
        return err

    # Idempotency: if already committed, just echo the dossier_id.
    if session.status == im.IntakeStatus.committed and session.dossier_id:
        return {"dossier_id": session.dossier_id}

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

    if missing:
        return {
            "error": f"missing fields: {', '.join(missing)}",
            "missing": missing,
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
    return {"dossier_id": dossier.id}


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
        "dossier_type, and check_in_policy are set (out_of_scope is optional)."
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
                "properties": {},
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
