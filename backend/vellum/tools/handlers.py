"""Agent tool handlers — v2 tool surface.

The agent does not speak to the user directly. Every user-visible mutation of a
dossier happens through one of these handlers. Each handler:

- Resolves/creates a work_session for the dossier so change_log entries are
  grouped correctly for the plan-diff sidebar.
- Validates arguments via a Pydantic input model.
- Calls storage.
- Returns a compact dict for the agent — IDs and state, not prose.

v1 tools (upsert_section, flag_needs_input, etc.) are kept so intake/runtime
code that already targets them keeps working. v2 adds the investigation-centric
tools: investigation plan, debrief, artifacts, sub-investigations, source
consultation logging, considered-and-rejected, and self-declared delivery.

Some v2 handlers depend on Pydantic types + storage functions that land in
parallel worktrees. This module imports them lazily and exposes the handler
surface regardless — the handlers themselves will raise AttributeError if
called before the v2 deps are merged, which is fine for day 1.

The JSON Schemas exposed to the agent are derived from the input Pydantic
models in ``tool_schemas()``.
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


# ===================================================================
# v1 tool handlers (kept — existing runtime/intake depends on them)
# ===================================================================


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


# ===================================================================
# v2 tool handlers
# ===================================================================


def update_investigation_plan(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Draft or revise the investigation plan.

    Mirrors InvestigationPlanUpdate from models.py (parallel worktree). The
    agent passes the full plan shape; we hand it to storage and return the
    plan id + approval state.
    """
    session_id = _ensure_session(dossier_id)
    plan = storage.update_investigation_plan(
        dossier_id, m.InvestigationPlanUpdate(**args), session_id
    )
    return {
        "plan_id": getattr(plan, "id", None),
        "approved": getattr(plan, "approved", False),
        "item_count": len(getattr(plan, "items", []) or []),
    }


def update_debrief(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the top-of-dossier 2-minute read.

    Partial updates allowed — the storage layer merges only non-null fields.
    """
    session_id = _ensure_session(dossier_id)
    debrief = storage.update_debrief(
        dossier_id, m.DebriefUpdate(**args), session_id
    )
    return {"debrief_id": getattr(debrief, "id", None)}


def add_artifact(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Create a usable artifact (letter, script, table, etc.)."""
    session_id = _ensure_session(dossier_id)
    art = storage.create_artifact(dossier_id, m.ArtifactCreate(**args), session_id)
    return {
        "artifact_id": art.id,
        "kind": art.kind.value if hasattr(art.kind, "value") else art.kind,
        "state": art.state.value if hasattr(art.state, "value") else art.state,
    }


def update_artifact(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Revise a previously drafted artifact."""
    session_id = _ensure_session(dossier_id)
    artifact_id = args.pop("artifact_id")
    art = storage.update_artifact(
        dossier_id, artifact_id, m.ArtifactUpdate(**args), session_id
    )
    return {
        "artifact_id": art.id,
        "state": art.state.value if hasattr(art.state, "value") else art.state,
    }


def spawn_sub_investigation(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Open a scoped sub-investigation. Day 1 just records the spawn row."""
    session_id = _ensure_session(dossier_id)
    sub = storage.spawn_sub_investigation(
        dossier_id, m.SubInvestigationSpawn(**args), session_id
    )
    return {"sub_investigation_id": sub.id, "state": "running"}


def complete_sub_investigation(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Called from a sub-investigation agent to return findings."""
    session_id = _ensure_session(dossier_id)
    sub_investigation_id = args.pop("sub_investigation_id")
    sub = storage.complete_sub_investigation(
        dossier_id, sub_investigation_id, m.SubInvestigationComplete(**args), session_id
    )
    return {
        "sub_investigation_id": getattr(sub, "id", sub_investigation_id),
        "state": getattr(getattr(sub, "state", None), "value", "completed"),
    }


def log_source_consulted(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Log every source actually consulted. Required, not optional."""
    session_id = _ensure_session(dossier_id)
    citation: str = args["citation"]
    why_consulted: str = args["why_consulted"]
    what_learned: str = args["what_learned"]
    supports_section_ids: list[str] = args.get("supports_section_ids") or []
    summary = f"{citation[:80]} — {what_learned[:120]}"
    entry = storage.append_investigation_log(
        dossier_id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted
            if hasattr(m, "InvestigationLogEntryType")
            else "source_consulted",
            payload={
                "citation": citation,
                "why_consulted": why_consulted,
                "what_learned": what_learned,
                "supports_section_ids": supports_section_ids,
            },
            summary=summary,
        ),
        session_id,
    )
    return {"log_entry_id": getattr(entry, "id", None)}


def mark_considered_and_rejected(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Record a seriously-considered-then-rejected path."""
    session_id = _ensure_session(dossier_id)
    item = storage.add_considered_and_rejected(
        dossier_id, m.ConsideredAndRejectedCreate(**args), session_id
    )
    return {"considered_and_rejected_id": item.id}


def set_next_action(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Add a concrete next action for the user."""
    session_id = _ensure_session(dossier_id)
    item = storage.add_next_action(
        dossier_id, m.NextActionCreate(**args), session_id
    )
    return {"next_action_id": item.id}


def declare_stuck(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """v2 stuck-declaration: logs to investigation_log AND raises a decision_point.

    Stronger than `check_stuck`: targets the investigation_log so the user sees
    a dedicated `stuck_declared` entry, not just a reasoning trail note.
    """
    session_id = _ensure_session(dossier_id)
    summary = args["summary_of_attempts"]
    options = args["options_for_user"]
    recommendation = args.get("recommendation") or summary

    storage.append_investigation_log(
        dossier_id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.stuck_declared
            if hasattr(m, "InvestigationLogEntryType")
            else "stuck_declared",
            payload={
                "summary_of_attempts": summary,
                "options_for_user": options,
                "recommendation": recommendation,
            },
            summary=f"stuck: {summary[:160]}",
        ),
        session_id,
    )
    dp = storage.add_decision_point(
        dossier_id,
        m.DecisionPointCreate(
            title="Stuck — need your direction",
            options=[m.DecisionOption(**o) for o in options],
            recommendation=recommendation,
        ),
        session_id,
    )
    return {"decision_point_id": dp.id}


def mark_investigation_delivered(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Self-declare the investigation complete.

    Sets dossier.status = delivered AND appends a [delivered] reasoning note
    so the plan-diff surfaces the self-declaration alongside the status flip.
    """
    session_id = _ensure_session(dossier_id)
    parsed = m.MarkDeliveredArgs(**args)
    why_enough = parsed.why_enough

    storage.update_dossier(
        dossier_id, m.DossierUpdate(status=m.DossierStatus.delivered)
    )
    storage.append_reasoning(
        dossier_id,
        m.ReasoningAppend(
            note=f"[delivered] {why_enough}",
            tags=["delivered"],
        ),
        session_id,
    )
    return {"dossier_id": dossier_id, "status": m.DossierStatus.delivered.value}


# ===================================================================
# Registry + schemas for Agent SDK wiring
# ===================================================================


HANDLERS = {
    # v1
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
    # v2
    "update_investigation_plan": update_investigation_plan,
    "update_debrief": update_debrief,
    "add_artifact": add_artifact,
    "update_artifact": update_artifact,
    "spawn_sub_investigation": spawn_sub_investigation,
    "complete_sub_investigation": complete_sub_investigation,
    "log_source_consulted": log_source_consulted,
    "mark_considered_and_rejected": mark_considered_and_rejected,
    "set_next_action": set_next_action,
    "declare_stuck": declare_stuck,
    "mark_investigation_delivered": mark_investigation_delivered,
}


TOOL_DESCRIPTIONS = {
    # v1
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
    # v2
    "update_investigation_plan": (
        "Draft or revise the investigation plan. Call this before diving in — list the questions you "
        "expect to investigate, whether each becomes a sub-investigation, and a rationale for the "
        "shape. The user sees this and may redirect. Call again when scope shifts. "
        "Set approve=true only if you want to mark it as user-approved (typically the user does this; "
        "set true to self-approve when the user has not explicitly said otherwise and you're confident)."
    ),
    "update_debrief": (
        "Rewrite the top-of-dossier 2-minute read: what you did, what you found, what the user should "
        "do next, and what you couldn't figure out. Partial updates allowed — only non-null fields are "
        "merged. This is the first thing the user reads when they return — write for someone who has "
        "been away for 18 hours and has 90 seconds."
    ),
    "add_artifact": (
        "Draft a usable thing: letter, script, comparison table, timeline, checklist, offer template, "
        "or other. Content is markdown. intended_use tells the user where to use it "
        "('mail to Capital One recovery dept'; 'read on first call with collector'). An investigation "
        "without at least one artifact is incomplete."
    ),
    "update_artifact": (
        "Revise a previously drafted artifact. change_note is the line the user reads in the "
        "plan-diff sidebar — make it specific."
    ),
    "spawn_sub_investigation": (
        "Open a scoped sub-investigation for a question that deserves its own attention. Use for "
        "jurisdictional questions, specific legal mechanisms, head-to-head comparisons. You'll "
        "receive the sub_investigation_id; the sub-agent will run and return findings before this "
        "tool call returns. Do NOT spawn sub-investigations for trivial lookups — those go in "
        "log_source_consulted."
    ),
    "complete_sub_investigation": (
        "Called from WITHIN a sub-investigation agent to return findings. Include a 3–8 sentence "
        "return_summary and pointers to the sections/artifacts you produced. Only a sub-agent calls "
        "this — the main agent does not."
    ),
    "log_source_consulted": (
        "Log every source you actually read and drew on, one call per source. This is not optional — "
        "the user counts these as evidence of work. citation is a URL or a plain citation; "
        "why_consulted is the question you were answering; what_learned is a one-sentence takeaway. "
        "Link to the sections the source supports via supports_section_ids when possible."
    ),
    "mark_considered_and_rejected": (
        "Record a path you seriously considered and rejected. Include why it was compelling "
        "(what made it tempting), why you rejected it (evidence, reasoning), and cost_of_error "
        "(what happens if you were wrong to reject). The user reads this to see your judgment — "
        "weak entries are worse than none."
    ),
    "set_next_action": (
        "Add a concrete next action for the user. Short imperative ('Request debt verification from "
        "Capital One under FDCPA §1692g'), with rationale. Appended to the ordered list; to reorder, "
        "use the dedicated reorder endpoint."
    ),
    "declare_stuck": (
        "Call when you detect yourself spinning: repeated identical tool calls, revising without "
        "progress, or you've exceeded the section token budget. Summarize what you tried and present "
        "options to the user as a decision_point. Do not keep burning cycles."
    ),
    "mark_investigation_delivered": (
        "Self-declare the investigation complete. why_enough should list: what you covered, what you "
        "explicitly left open, what the next real action is. The user can still re-open. Only call "
        "this when the substance bar is met: multiple sub-investigations completed, tens of sources "
        "consulted, at least one artifact drafted, debrief current."
    ),
}


# Pydantic models whose shape maps 1:1 to a tool's `args` — used to derive
# JSON Schemas. Tools whose args don't fit a single model get hand-written
# schemas in `tool_schemas()` below.
#
# v2 types (ArtifactCreate, DebriefUpdate, etc.) are looked up lazily via
# getattr so this module still imports cleanly on branches where those
# models haven't merged yet. Any missing type becomes a None entry that
# `tool_schemas()` skips.
_INPUT_MODELS: dict[str, type] = {
    # v1
    "upsert_section": m.SectionUpsert,
    "flag_needs_input": m.NeedsInputCreate,
    "flag_decision_point": m.DecisionPointCreate,
    "append_reasoning": m.ReasoningAppend,
    "mark_ruled_out": m.RuledOutCreate,
    "mark_investigation_delivered": m.MarkDeliveredArgs,
}


def _maybe_add(name: str, attr: str) -> None:
    model = getattr(m, attr, None)
    if model is not None:
        _INPUT_MODELS[name] = model


# v2 lazy-wire: only register if the model exists in this worktree.
_maybe_add("update_investigation_plan", "InvestigationPlanUpdate")
_maybe_add("update_debrief", "DebriefUpdate")
_maybe_add("add_artifact", "ArtifactCreate")
_maybe_add("spawn_sub_investigation", "SubInvestigationSpawn")
_maybe_add("mark_considered_and_rejected", "ConsideredAndRejectedCreate")
_maybe_add("set_next_action", "NextActionCreate")


# Permissive placeholder schemas used when a v2 Pydantic model hasn't merged
# yet. Keeps `tool_schemas()` stable at 14+ entries on any branch. Real
# schemas take precedence automatically once the model shows up in
# `_INPUT_MODELS` via `_maybe_add`.
_PLACEHOLDER_V2_SCHEMAS: dict[str, dict[str, Any]] = {
    "update_investigation_plan": {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object"}},
            "approve": {"type": "boolean", "default": False},
            "rationale": {"type": "string"},
        },
        "required": ["items"],
        "additionalProperties": True,
    },
    "update_debrief": {
        "type": "object",
        "properties": {
            "what_i_did": {"type": "string"},
            "what_i_found": {"type": "string"},
            "what_you_should_do_next": {"type": "string"},
            "what_i_couldnt_figure_out": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "add_artifact": {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "intended_use": {"type": "string"},
        },
        "required": ["kind", "title", "content"],
        "additionalProperties": True,
    },
    "spawn_sub_investigation": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "question": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["title", "question"],
        "additionalProperties": True,
    },
    "mark_considered_and_rejected": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "why_compelling": {"type": "string"},
            "why_rejected": {"type": "string"},
            "cost_of_error": {"type": "string"},
        },
        "required": ["path", "why_compelling", "why_rejected", "cost_of_error"],
        "additionalProperties": True,
    },
    "set_next_action": {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["action", "rationale"],
        "additionalProperties": True,
    },
}


def _section_ids_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "default": []}


def _decision_option_schema() -> dict[str, Any]:
    """JSON-schema shape for a DecisionOption dict — doesn't depend on v2."""
    return m.DecisionOption.model_json_schema()


def tool_schemas() -> list[dict[str, Any]]:
    """Emit Anthropic-tool-compatible schemas for the agent.

    For tools whose args map cleanly to a Pydantic model, we derive the schema
    from the model. For tools that wrap extra state (an id + patch fields,
    multi-field composites), we hand-write the schema to stay honest about
    what the agent must send.
    """
    schemas: list[dict[str, Any]] = []

    # --- Pydantic-derived schemas ---
    for name, model in _INPUT_MODELS.items():
        if model is None:
            continue
        schemas.append({
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": model.model_json_schema(),
        })

    # --- v2 placeholder fallbacks for tools whose model hasn't merged yet ---
    registered = {s["name"] for s in schemas}
    for name, placeholder in _PLACEHOLDER_V2_SCHEMAS.items():
        if name in registered:
            continue
        schemas.append({
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "input_schema": placeholder,
        })

    # --- v1 hand-written schemas ---
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
                    "items": _decision_option_schema(),
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

    # --- v2 hand-written schemas (for tools that aren't a single model) ---

    # update_artifact: artifact_id + ArtifactUpdate fields merged.
    artifact_update_model = getattr(m, "ArtifactUpdate", None)
    if artifact_update_model is not None:
        inner = artifact_update_model.model_json_schema()
        props = {"artifact_id": {"type": "string"}}
        props.update(inner.get("properties", {}))
        required = ["artifact_id"] + list(inner.get("required", []))
        schema: dict[str, Any] = {"type": "object", "properties": props, "required": required}
        # Preserve $defs from the inner model if present so refs still resolve.
        if "$defs" in inner:
            schema["$defs"] = inner["$defs"]
        schemas.append({
            "name": "update_artifact",
            "description": TOOL_DESCRIPTIONS["update_artifact"],
            "input_schema": schema,
        })
    else:
        # v2 model hasn't landed — publish a permissive placeholder so the
        # surface count is stable and the agent won't break on day-1 wiring.
        schemas.append({
            "name": "update_artifact",
            "description": TOOL_DESCRIPTIONS["update_artifact"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "artifact_id": {"type": "string"},
                    "change_note": {"type": "string"},
                },
                "required": ["artifact_id", "change_note"],
                "additionalProperties": True,
            },
        })

    # complete_sub_investigation: sub_investigation_id + SubInvestigationComplete fields.
    sub_complete_model = getattr(m, "SubInvestigationComplete", None)
    if sub_complete_model is not None:
        inner = sub_complete_model.model_json_schema()
        props = {"sub_investigation_id": {"type": "string"}}
        props.update(inner.get("properties", {}))
        required = ["sub_investigation_id"] + list(inner.get("required", []))
        schema = {"type": "object", "properties": props, "required": required}
        if "$defs" in inner:
            schema["$defs"] = inner["$defs"]
        schemas.append({
            "name": "complete_sub_investigation",
            "description": TOOL_DESCRIPTIONS["complete_sub_investigation"],
            "input_schema": schema,
        })
    else:
        schemas.append({
            "name": "complete_sub_investigation",
            "description": TOOL_DESCRIPTIONS["complete_sub_investigation"],
            "input_schema": {
                "type": "object",
                "properties": {
                    "sub_investigation_id": {"type": "string"},
                    "return_summary": {"type": "string"},
                },
                "required": ["sub_investigation_id", "return_summary"],
                "additionalProperties": True,
            },
        })

    # log_source_consulted: four loose fields, not a single model.
    schemas.append({
        "name": "log_source_consulted",
        "description": TOOL_DESCRIPTIONS["log_source_consulted"],
        "input_schema": {
            "type": "object",
            "properties": {
                "citation": {"type": "string"},
                "why_consulted": {"type": "string"},
                "what_learned": {"type": "string"},
                "supports_section_ids": _section_ids_schema(),
            },
            "required": ["citation", "why_consulted", "what_learned"],
        },
    })

    # declare_stuck: summary + options + recommendation.
    schemas.append({
        "name": "declare_stuck",
        "description": TOOL_DESCRIPTIONS["declare_stuck"],
        "input_schema": {
            "type": "object",
            "properties": {
                "summary_of_attempts": {"type": "string"},
                "options_for_user": {
                    "type": "array",
                    "items": _decision_option_schema(),
                },
                "recommendation": {"type": "string"},
            },
            "required": ["summary_of_attempts", "options_for_user", "recommendation"],
        },
    })

    return schemas
