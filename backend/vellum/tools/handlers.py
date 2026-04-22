"""Agent tool handlers.

The agent does not speak to the user directly. Every user-visible mutation of a
dossier happens through one of these handlers. Each handler:

- Resolves/creates a work_session for the dossier so change_log entries are
  grouped correctly for the plan-diff sidebar.
- Validates arguments via a Pydantic input model.
- Calls storage.
- Returns a compact dict for the agent — IDs and state, not prose.

Day 2 will wire these into Claude Agent SDK tool definitions. The JSON Schemas
exposed to the agent are derived from the input Pydantic models in
``tool_schemas()``.
"""
from __future__ import annotations

from typing import Any

from .. import models as m
from .. import storage


def _ensure_session(dossier_id: str) -> str:
    session = storage.get_active_work_session(dossier_id)
    if session:
        return session.id
    return storage.start_work_session(dossier_id, m.WorkSessionTrigger.resume).id


# ---------- tool handlers ----------


def upsert_section(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    section = storage.upsert_section(dossier_id, m.SectionUpsert(**args), session_id)
    return {"section_id": section.id, "state": section.state.value, "order": section.order}


def update_section_state(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    section_id = args.pop("section_id")
    section = storage.update_section_state(
        dossier_id, section_id, m.SectionStateUpdate(**args), session_id
    )
    return {"section_id": section.id, "state": section.state.value}


def delete_section(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    ok = storage.delete_section(dossier_id, args["section_id"], args["reason"], session_id)
    return {"deleted": ok}


def reorder_sections(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    sections = storage.reorder_sections(dossier_id, args["section_ids"], session_id)
    return {"section_ids": [s.id for s in sections]}


def flag_needs_input(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    item = storage.add_needs_input(dossier_id, m.NeedsInputCreate(**args), session_id)
    return {"needs_input_id": item.id}


def flag_decision_point(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    item = storage.add_decision_point(dossier_id, m.DecisionPointCreate(**args), session_id)
    return {"decision_point_id": item.id}


def append_reasoning(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    entry = storage.append_reasoning(dossier_id, m.ReasoningAppend(**args), session_id)
    return {"reasoning_id": entry.id}


def mark_ruled_out(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    session_id = _ensure_session(dossier_id)
    item = storage.add_ruled_out(dossier_id, m.RuledOutCreate(**args), session_id)
    return {"ruled_out_id": item.id}


def check_stuck(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Agent-initiated stuck surface: logs a reasoning note AND raises a decision_point."""
    session_id = _ensure_session(dossier_id)
    summary = args["summary_of_attempts"]
    options = args["options_for_user"]
    storage.append_reasoning(
        dossier_id,
        m.ReasoningAppend(note=f"[stuck] {summary}", tags=["stuck"]),
        session_id,
    )
    dp = storage.add_decision_point(
        dossier_id,
        m.DecisionPointCreate(
            title=f"Stuck — need your direction",
            options=[m.DecisionOption(**o) for o in options],
            recommendation=summary,
        ),
        session_id,
    )
    return {"decision_point_id": dp.id}


def request_user_paste(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Softer needs_input specifically for asking the user for a document."""
    session_id = _ensure_session(dossier_id)
    item = storage.add_needs_input(
        dossier_id,
        m.NeedsInputCreate(question=f"[paste requested] {args['what_needed']}"),
        session_id,
    )
    return {"needs_input_id": item.id}


# ---------- registry + schemas for Agent SDK wiring (day 2) ----------


HANDLERS = {
    "upsert_section": upsert_section,
    "update_section_state": update_section_state,
    "delete_section": delete_section,
    "reorder_sections": reorder_sections,
    "flag_needs_input": flag_needs_input,
    "flag_decision_point": flag_decision_point,
    "append_reasoning": append_reasoning,
    "mark_ruled_out": mark_ruled_out,
    "check_stuck": check_stuck,
    "request_user_paste": request_user_paste,
}


TOOL_DESCRIPTIONS = {
    "upsert_section": (
        "Create or update a section of the dossier. Use this for every finding, "
        "recommendation, summary, or piece of evidence. Always include sources if you have them; "
        "if you cannot source a claim, set state='provisional'. Provide after_section_id to place "
        "the new section immediately after an existing one. "
        "change_note is the line the user reads in their plan-diff sidebar — write it for that "
        "reader: what changed and why, not a restatement of the section body. "
        "'Updated section' is a bad change_note; 'Downgraded after the CA AG bulletin contradicted "
        "the earlier 10-25% finding' is a good one."
    ),
    "update_section_state": (
        "Change a section's state (confident / provisional / blocked). Use this when new evidence "
        "contradicts a confident finding, or when you've resolved a blocker. Always include a reason."
    ),
    "delete_section": (
        "Remove a section from the dossier. Provide a reason — it is logged to the reasoning trail."
    ),
    "reorder_sections": (
        "Reorder the dossier's sections by providing the full list of section_ids in desired order."
    ),
    "flag_needs_input": (
        "Post a single crisp question to the user and block on it. Use only when you are actually "
        "stuck and an answer would unblock progress. Batch small questions into one when possible."
    ),
    "flag_decision_point": (
        "Present the user with a choice between structured options. Use for 'pick a direction' moments, "
        "not for factual questions."
    ),
    "append_reasoning": (
        "Private log for your own coherence across work sessions. The user does not see this directly. "
        "Tag strategic shifts ('strategy_shift'), rejected approaches ('rejected_approach'), etc."
    ),
    "mark_ruled_out": (
        "Record that you investigated something and rejected it, with the reason. This prevents you from "
        "re-investigating it and shows the user what you considered."
    ),
    "check_stuck": (
        "Call when you notice yourself looping, over-budget, or revising without progress. Surfaces a "
        "decision_point to the user with the options you see. Do not keep burning cycles."
    ),
    "request_user_paste": (
        "Specifically request a document or block of text from the user (contract language, statement, etc.). "
        "Softer than flag_needs_input — for content you need to read, not a question you need answered."
    ),
}


_INPUT_MODELS: dict[str, type] = {
    "upsert_section": m.SectionUpsert,
    "flag_needs_input": m.NeedsInputCreate,
    "flag_decision_point": m.DecisionPointCreate,
    "append_reasoning": m.ReasoningAppend,
    "mark_ruled_out": m.RuledOutCreate,
}


def tool_schemas() -> list[dict[str, Any]]:
    """Emit Anthropic-tool-compatible schemas for the agent. Day 2 wires these up."""
    schemas = []

    # Pydantic-derived schemas for the "data-in" tools.
    for name, model in _INPUT_MODELS.items():
        schema = model.model_json_schema()
        schemas.append({
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": schema,
        })

    # Hand-written schemas for the ones that wrap extra state.
    schemas.append({
        "name": "update_section_state",
        "description": TOOL_DESCRIPTIONS["update_section_state"],
        "input_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "new_state": {"type": "string", "enum": [s.value for s in m.SectionState]},
                "reason": {"type": "string"},
            },
            "required": ["section_id", "new_state", "reason"],
        },
    })
    schemas.append({
        "name": "delete_section",
        "description": TOOL_DESCRIPTIONS["delete_section"],
        "input_schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["section_id", "reason"],
        },
    })
    schemas.append({
        "name": "reorder_sections",
        "description": TOOL_DESCRIPTIONS["reorder_sections"],
        "input_schema": {
            "type": "object",
            "properties": {
                "section_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["section_ids"],
        },
    })
    schemas.append({
        "name": "check_stuck",
        "description": TOOL_DESCRIPTIONS["check_stuck"],
        "input_schema": {
            "type": "object",
            "properties": {
                "summary_of_attempts": {"type": "string"},
                "options_for_user": {
                    "type": "array",
                    "items": m.DecisionOption.model_json_schema(),
                },
            },
            "required": ["summary_of_attempts", "options_for_user"],
        },
    })
    schemas.append({
        "name": "request_user_paste",
        "description": TOOL_DESCRIPTIONS["request_user_paste"],
        "input_schema": {
            "type": "object",
            "properties": {
                "what_needed": {"type": "string"},
            },
            "required": ["what_needed"],
        },
    })

    return schemas


# ---------- Extension points for day-2 agents ----------
#
# HANDLER_OVERRIDES: map of tool_name -> callable(dossier_id, args) -> result.
#   When set, the dispatcher calls the override instead of HANDLERS[name].
#   Used by sub_runtime to turn spawn_sub_investigation into a real blocking
#   sub-agent run rather than a mere row-insert.
#
# TOOL_HOOKS: list of callables called AFTER every dispatch with
#   (dossier_id, tool_name, args, result). Non-blocking, best-effort; errors
#   in hooks are logged and swallowed. Used by telemetry.

from typing import Callable

HANDLER_OVERRIDES: dict[str, Callable[[str, dict[str, Any]], Any]] = {}
TOOL_HOOKS: list[Callable[[str, str, dict[str, Any], Any], None]] = []


def dispatch(dossier_id: str, tool_name: str, args: dict[str, Any]) -> Any:
    """Unified dispatch path: override -> default handler -> hooks.

    Runtimes MUST call this instead of HANDLERS[name] directly, so override
    registration and telemetry work.
    """
    impl = HANDLER_OVERRIDES.get(tool_name) or HANDLERS.get(tool_name)
    if impl is None:
        raise KeyError(f"unknown tool: {tool_name}")
    result = impl(dossier_id, args)
    for hook in TOOL_HOOKS:
        try:
            hook(dossier_id, tool_name, args, result)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "tool hook raised; swallowing", exc_info=True
            )
    return result
