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


def schedule_wake(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Agent-initiated wake scheduler.

    Writes dossiers.wake_at and appends a `scheduled_wake` reasoning_trail
    entry. Non-terminating: the agent should emit this as its final tool
    call for the turn, then stop producing further tool_uses so the turn
    ends naturally — the scheduler will pick it up on its next tick after
    wake_at passes.

    Respects two settings (both editable from UI):
      - sleep_mode_enabled: when False, returns {"ok": False, "reason":
        "sleep_mode_disabled"} and does not write wake_at. The agent can
        then decide to end the turn or surface a decision_point.
      - schedule_wake_max_hours: upper bound on hours_from_now. Exceeding
        it returns {"ok": False, "reason": "exceeds_max"} with the cap.
    """
    from datetime import timedelta

    parsed = m.ScheduleWakeArgs(**args)

    if not storage.get_setting("sleep_mode_enabled", True):
        return {
            "ok": False,
            "reason": "sleep_mode_disabled",
            "message": (
                "sleep mode is off in settings; scheduling a wake is a no-op. "
                "End the turn normally — the user will resume manually."
            ),
        }

    cap = float(storage.get_setting("schedule_wake_max_hours", 72.0))
    if parsed.hours_from_now > cap:
        return {
            "ok": False,
            "reason": "exceeds_max",
            "cap_hours": cap,
            "requested_hours": parsed.hours_from_now,
            "message": (
                f"requested {parsed.hours_from_now}h exceeds the "
                f"schedule_wake_max_hours cap of {cap}h; pick a shorter "
                f"interval or raise the cap in settings"
            ),
        }

    session_id = _ensure_session(dossier_id)
    wake_at = m.utc_now() + timedelta(hours=parsed.hours_from_now)
    storage.set_dossier_wake_at(dossier_id, wake_at, m.WakeReason.scheduled)
    storage.append_reasoning(
        dossier_id,
        m.ReasoningAppend(
            note=(
                f"[scheduled_wake] I'll wake up in {parsed.hours_from_now:g}h "
                f"(at {wake_at.isoformat()}) to continue. Reason: {parsed.reason}"
            ),
            tags=["scheduled_wake"],
        ),
        session_id,
    )
    return {
        "ok": True,
        "wake_at": wake_at.isoformat(),
        "hours_from_now": parsed.hours_from_now,
    }


def mark_investigation_delivered(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Self-declare the investigation complete.

    Sets dossier.status = delivered AND appends a [delivered] reasoning note
    so the plan-diff surfaces the self-declaration alongside the status flip.

    Defense-in-depth guard (day-6): refuse when the dossier isn't actually
    ready. Specifically, if any sub-investigation is still ``running``, or
    any ``needs_input`` is unanswered, or any ``plan_approval`` decision
    point is unresolved, return a structured ``{"ok": False, ...}``
    without flipping dossier.status. The agent can read the refusal and
    either wait (end turn) or explicitly abandon the blockers. Generic
    open decision points are tolerated — the agent may intentionally
    leave those for the user.
    """
    parsed = m.MarkDeliveredArgs(**args)
    why_enough = parsed.why_enough

    # --- Pre-flight guards ------------------------------------------------
    running_subs = storage.list_sub_investigations(
        dossier_id, state=m.SubInvestigationState.running
    )
    if running_subs:
        return {
            "ok": False,
            "reason": "still_running_subs",
            "subs": [{"id": s.id, "scope": s.scope} for s in running_subs],
            "message": (
                f"{len(running_subs)} sub-investigation(s) still running; "
                "wait for them or abandon explicitly before marking delivered"
            ),
        }

    open_needs = storage.list_needs_input(dossier_id, open_only=True)
    if open_needs:
        return {
            "ok": False,
            "reason": "open_needs_input",
            "needs_input": [
                {"id": n.id, "question": n.question} for n in open_needs
            ],
            "message": (
                f"{len(open_needs)} unanswered needs_input item(s); "
                "resolve or resurface before marking delivered"
            ),
        }

    open_dps = storage.list_decision_points(dossier_id, open_only=True)
    open_plan_approvals = [dp for dp in open_dps if dp.kind == "plan_approval"]
    if open_plan_approvals:
        return {
            "ok": False,
            "reason": "open_plan_approval",
            "decision_points": [
                {"id": dp.id, "title": dp.title}
                for dp in open_plan_approvals
            ],
            "message": (
                f"{len(open_plan_approvals)} unresolved plan_approval "
                "decision point(s); the plan has not been approved"
            ),
        }

    # --- All clear: proceed ----------------------------------------------
    session_id = _ensure_session(dossier_id)
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
    return {
        "ok": True,
        "dossier_id": dossier_id,
        "status": m.DossierStatus.delivered.value,
    }


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
    "schedule_wake": schedule_wake,
    "mark_investigation_delivered": mark_investigation_delivered,
}


TOOL_DESCRIPTIONS = {
    # v1
    "upsert_section": (
        "Call this to write or revise a finding, recommendation, summary, or piece of evidence "
        "into the dossier body — the substantive prose the user reads. Include sources when you "
        "have them; if you cannot source a claim, set state='provisional'. Use after_section_id "
        "to place the new section immediately after an existing one. "
        "Do NOT use for throwaway drafts, letters, tables, or other usable objects — those are "
        "add_artifact. change_note is the plan-diff line the user reads: write what changed and "
        "why, not a restatement of the body. Good: 'Downgraded after the CA AG bulletin "
        "contradicted the earlier 10-25% finding.' Bad: 'Updated section.'"
    ),
    "update_section_state": (
        "Call to flip a section's state between confident / provisional / blocked when evidence "
        "shifts. Example: promote from provisional to confident after a second source confirms, "
        "or demote to blocked when a key fact becomes unavailable. Always include a reason."
    ),
    "delete_section": (
        "Remove a section from the dossier. Use only when the section is wrong or obsolete, not "
        "merely revised — revisions go through upsert_section. Provide a reason; it lands in the "
        "reasoning trail."
    ),
    "reorder_sections": (
        "Rearrange the dossier's sections. Pass the full list of section_ids in the desired "
        "order — partial lists reorder nothing. Use sparingly; most ordering should come out of "
        "upsert_section's after_section_id."
    ),
    "flag_needs_input": (
        "Ask the user a single crisp factual question and block on the answer. Use when a fact "
        "only the user has would unblock progress (e.g., 'What state do you live in?', 'What's "
        "the amount on the statement?'). Batch small questions into one where possible. "
        "Do NOT use to present a choice between options — that is flag_decision_point. Do not "
        "use for ambiguity you can resolve by reading."
    ),
    "flag_decision_point": (
        "Present the user with a choice between two or more structured options and block on "
        "their pick. Use for 'pick a direction' moments where you've done the legwork and the "
        "user now has to decide. Set kind='plan_approval' when surfacing the investigation plan "
        "for the user's sign-off. "
        "Example: title='Send verification letter now or wait for SOL research?', "
        "kind='strategy', options=[{'label': 'Send now', 'implications': 'starts 30-day "
        "clock'}, {'label': 'Wait', 'implications': 'preserves optionality'}]. "
        "Do NOT use for factual questions (flag_needs_input) or when you are actually stuck "
        "(declare_stuck)."
    ),
    "append_reasoning": (
        "Private note to yourself for coherence across work sessions — the user does not see "
        "this in the main dossier. Use for strategy shifts, hypotheses to revisit, or context "
        "you want future-you to have. Tag with 'strategy_shift', 'rejected_approach', etc. "
        "Do NOT use for user-visible substance (upsert_section) or for one-line progress notes "
        "that belong in the investigation_log via log_source_consulted."
    ),
    "mark_ruled_out": (
        "Record a hypothesis or approach you investigated and rejected. Prevents re-exploration "
        "and shows the user what you considered. Lighter-weight than mark_considered_and_rejected "
        "(which is reserved for paths compelling enough to need a full cost-of-error argument). "
        "Always include a reason."
    ),
    "check_stuck": (
        "Call when you notice yourself looping, over budget, or revising without progress. "
        "Surfaces a decision_point to the user with the options you see. Use declare_stuck "
        "instead if v2 is available; check_stuck is the v1 variant that only logs to the "
        "reasoning trail, not the investigation_log."
    ),
    "request_user_paste": (
        "Ask the user to paste a specific document or block of text (contract language, "
        "collection letter, bank statement). Softer than flag_needs_input: for content you need "
        "to read, not a factual question to answer. Describe precisely what you need so the "
        "user knows exactly what to paste."
    ),
    # v2
    "update_investigation_plan": (
        "Draft or revise the investigation plan before diving in. Each item lists a question, "
        "whether it becomes a sub-investigation, and a rationale. The user sees this and may "
        "redirect; call again whenever scope shifts materially. "
        "Example items: [{'question': 'Does CA SOL bar this debt?', 'becomes_sub_investigation': "
        "true, 'rationale': 'Jurisdiction-specific, worth dedicated dig'}, {'question': 'Draft "
        "a §1692g letter', 'becomes_sub_investigation': false}]. "
        "Set approve=true to self-approve only when the user has given you a clear go-ahead; "
        "otherwise leave false and surface the plan via flag_decision_point(kind='plan_approval')."
    ),
    "update_debrief": (
        "Rewrite the top-of-dossier 2-minute read: what you did, what you found, what the user "
        "should do next, and what you couldn't figure out. Partial updates merge — only non-null "
        "fields land. Call this BEFORE mark_investigation_delivered (delivery with a stale "
        "debrief is a bug) and at meaningful checkpoints: after every completed sub, after a "
        "finding flips state, after the user answers a blocking question. Write for someone who "
        "has been away 18 hours and has 90 seconds."
    ),
    "add_artifact": (
        "Draft a usable object the user can copy, send, or run through: letter, script, "
        "comparison table, timeline, checklist, offer template. Content is markdown. "
        "intended_use tells the user exactly where to use it. "
        "Example args: kind='letter', title='FDCPA §1692g verification request', "
        "content='# Request for Verification\\n...', intended_use='mail certified to Capital "
        "One recovery dept within 30 days of first contact'. "
        "Do NOT use for findings or analysis — those go in upsert_section. An investigation "
        "without at least one artifact is incomplete."
    ),
    "update_artifact": (
        "Revise a previously drafted artifact. Use for tightening language, fixing a cited "
        "amount, or responding to user feedback. change_note is the line the user reads in the "
        "plan-diff — make it specific ('tightened the ask to 30-day window', not 'updated')."
    ),
    "spawn_sub_investigation": (
        "Open a scoped sub-investigation for a question worth its own focused dig — "
        "jurisdictional questions, specific legal mechanisms, head-to-head comparisons, "
        "creditor-specific patterns. SYNCHRONOUS: the sub-agent runs to completion and this "
        "call returns with the sub's findings (return_summary + section/artifact ids). No "
        "polling. "
        "Example: title='CA SOL on credit card debt', scope='California statute of limitations "
        "on credit card accounts', questions=['Does CA SOL bar this collection?', 'Does the "
        "choice-of-law clause change it?']. "
        "Do NOT spawn for trivial lookups — a single source read is log_source_consulted."
    ),
    "complete_sub_investigation": (
        "The sub-agent's ONLY exit call. Pass a 3-8 sentence return_summary (lead with the "
        "answer, state confidence high/medium/low, name conditions if the answer is "
        "conditional), plus findings_section_ids for the sections you wrote and "
        "findings_artifact_ids for artifacts you drafted. Only a sub-agent calls this; the main "
        "agent never does."
    ),
    "log_source_consulted": (
        "Call ONCE PER SOURCE you actually read. Searching does not count — log only after you "
        "have read the page. The user counts these as evidence of work; the '47 sources' "
        "counter on the dossier depends on this call being honest. "
        "Example args: citation='https://www.consumerfinance.gov/rules-policy/regulations/1006/', "
        "why_consulted='Does Reg F cap collection call frequency?', what_learned='Reg F caps at "
        "7 calls per 7 days per debt', supports_section_ids=['sec_abc123']. "
        "Link via supports_section_ids whenever the source backs a claim in a section."
    ),
    "mark_considered_and_rejected": (
        "Record a path you seriously considered and rejected — reserved for options compelling "
        "enough to need a real cost-of-error argument. Lighter rejections go in mark_ruled_out. "
        "Example args: path='File a CFPB complaint immediately', why_compelling='Fast, free, "
        "creates a paper trail', why_rejected='Collector has 15 days to respond, wasting lead "
        "time we need for verification', cost_of_error='Low — can file later if verification "
        "fails'. Weak entries are worse than none; the user reads this as a judgment sample."
    ),
    "set_next_action": (
        "Append a concrete next action for the user — short imperative plus rationale. "
        "Example args: action='Request debt verification from Capital One under FDCPA §1692g', "
        "rationale='Starts the 30-day clock on their verification duty and pauses collection "
        "activity'. Appended to the ordered list; reordering goes through the dedicated "
        "endpoint, not this tool."
    ),
    "declare_stuck": (
        "The v2 stuck-declaration. Call when you detect yourself spinning: repeated identical "
        "tool calls, revising without progress, or scope budget exhausted without a finding. "
        "Logs a stuck_declared entry to the investigation_log AND raises a decision_point to "
        "the user with your options. Stronger than check_stuck (which is v1, reasoning-trail "
        "only). Do not keep burning cycles."
    ),
    "mark_investigation_delivered": (
        "TERMINATES the agent loop — after this call, the agent stops. Call ONLY when the "
        "substance bar is met: multiple sub-investigations completed, tens of sources "
        "consulted, at least one artifact drafted, debrief current (call update_debrief first). "
        "why_enough must name what you covered, what you explicitly left open, and what the "
        "next real action is. The user can re-open the dossier, but you should not call this "
        "speculatively — an under-baked delivery is the worst failure mode."
    ),
    "schedule_wake": (
        "Schedule your own next wake-up. Non-terminating: after this call, end the turn "
        "(stop producing tool_uses) — the runtime will pause you, and the scheduler will "
        "resume you with a fresh work_session after hours_from_now have passed. "
        "Use when you need real-world time to pass before more work is productive: waiting "
        "for a caller to call back, a SOL clock to tick, a scheduled bulletin to publish, "
        "or for the user's next action to land (though for user actions prefer flag_needs_input). "
        "Don't use to pad the run — if you're out of substantive moves and the blocker is "
        "the user, flag_needs_input or flag_decision_point and end the turn; the scheduler "
        "will resume you when the user resolves it. "
        "reason is a short string logged in the reasoning trail so you (on resume) and the "
        "user can see why you stepped back. hours_from_now accepts fractions (e.g. 0.5 for "
        "30 minutes). The schedule_wake_max_hours setting caps the interval."
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
    "schedule_wake": m.ScheduleWakeArgs,
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
