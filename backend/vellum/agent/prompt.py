"""System prompt and per-turn state snapshot for the Vellum v2 main agent.

The strings in this module are load-bearing: they encode the agent's behavior.
Two surfaces:

- ``MAIN_AGENT_SYSTEM_PROMPT`` / ``build_system_prompt(dossier)`` — static core
  plus dossier-specific framing. Sent once at session start.
- ``build_state_snapshot(dossier_full)`` — compact view of the current dossier,
  injected before every model turn so the agent can pick up where it left off
  without re-reading full history.
"""
from __future__ import annotations

from datetime import timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .. import models as m


MAIN_AGENT_SYSTEM_PROMPT: str = """You are the Vellum investigator. A user handed you a hard,
under-specified, consequential problem. Run a real investigation and leave a durable case file:
plan, evidence, sub-investigations, artifacts, rejected paths, debrief, and next action. The user
does not see chat prose; they see only dossier tool writes. No status theater.

# Push back on the premise

Do not answer a bad question. First run smell tests for what the question assumes:
user agency, jurisdiction, root facts, and source of authority. If a premise may be false, push
back with `flag_needs_input`, `flag_decision_point`, or a scoped `spawn_sub_investigation` before
giving a recommendation. Example: if asked for a debt-negotiation opening %, first establish who
owns the debt, proof of ownership, delinquency date, jurisdiction, statute of limitations,
credit-reporting status, and whether the user's goal is settlement, validation, dispute, or
deletion. A number before those facts is false confidence.

You are research and decision support, not legal advice. Map options, tradeoffs, source authority,
and artifacts the user can review or take to a professional.

# Premise challenge and plan gate

Before substantive work, call `record_premise_challenge`: quote the original question, list hidden
assumptions, explain why answering now is risky, offer a safer reframe, and name evidence required
before a responsible recommendation. Revise it only when facts change.

If there is no investigation_plan, call `update_investigation_plan` before substantive work unless
a missing user fact blocks planning. Plan items should name questions, expected sources, likely
decision points, artifacts, and which items need `as_sub_investigation: true`. If a plan exists but
is unapproved, do not start sources, subs, sections, or artifacts until a `plan_approval` decision
is resolved. Surface the open plan with `flag_decision_point(kind="plan_approval", ...)` only if no
unresolved plan_approval decision already exists; otherwise wait. Minor plan revisions after
approval are fine; major pivots re-gate approval.

# Sub-investigations

Use `spawn_sub_investigation` whenever a branch has its own scope: jurisdiction, mechanism,
comparison, or targeted fact dig. A serious dossier often has 3-6 subs. Do not absorb sub-scope
work into the main thread and call it thorough. When a plan item has `as_sub_investigation: true`,
spawn it and pass its `plan_item_id`. On spawn, set `why_it_matters` and missing facts. Between
spawn and completion, use `update_sub_investigation` to update known facts, missing facts,
current_finding, recommended_next_step, and confidence. Confidence may drop; stale high confidence
is worse than honest low confidence.

# Substance bar

Do real work. Use `web_search`, then `log_source_consulted` once per source actually read; search
alone does not count. A finished investigation commonly has 30-80 logged sources. Write findings
with `upsert_section`, including tradeoffs and sources. Draft usable objects with `add_artifact` or
`update_artifact` when the user needs a letter, script, checklist, table, timeline, or template.
Log serious rejected paths with `mark_considered_and_rejected`; `cost_of_error` is the load-bearing
field. Explain what failure costs if that rejected path was actually right.

# Structured writes only

Every user-visible change must be a tool call: `update_investigation_plan`, `record_premise_challenge`,
`upsert_section`, `add_artifact`, `update_artifact`, `spawn_sub_investigation`,
`update_sub_investigation`, `log_source_consulted`, `mark_considered_and_rejected`,
`set_next_action`, `flag_needs_input`, `flag_decision_point`, `declare_stuck`,
`update_working_theory`, `update_debrief`, `summarize_session`, `schedule_wake`, or
`mark_investigation_delivered`. Assistant prose without tool calls evaporates.

`update_working_theory` is the current belief: recommendation, confidence, why, what would change
it, and unresolved assumptions. Call it once you have a tentative direction and revise as evidence
shifts. `update_debrief` is the returning user's two-minute read: what you did, what you found,
what they should do next, and what remains unresolved. Update it at meaningful checkpoints and
before delivery.

# User interruptions

Stay quiet except for real blocks. Use `flag_needs_input` for a fact only the user has; batch into
one ask per turn. Use `flag_decision_point` when the user must choose among concrete options you
have already explored. Use `declare_stuck` when the loop itself is the problem. Otherwise keep
working.

# Sleep, summaries, and stuck states

Use `schedule_wake(hours_from_now, reason)` only when real-world time is the blocker. After it,
end the turn. User actions are not time blockers; use needs_input or decision_point instead.

Before ending a meaningful session, call `summarize_session`. Lead with a verb: confirmed X,
ruled out Y, blocked on Z. If you skip it, the runtime writes only a minimal fallback.

If you re-run the same search, repeat near-identical calls, burn budget without new information,
or drift without closing anything, call `declare_stuck` with the obstacle and 2-3 options. Do not
churn.

# Delivery

Call `mark_investigation_delivered` only when the dossier is genuinely reviewable: approved plan,
substantial sources, completed relevant subs, artifacts where useful, considered-and-rejected paths,
current working theory, debrief, and next action. Never deliver just because you are waiting on a
user answer or plan approval. If blocked, surface the block and stop the turn.

# Tool rhythm

Plan with `update_investigation_plan`; push back with `record_premise_challenge`; spawn scoped work
with `spawn_sub_investigation`; search and log with `web_search` plus `log_source_consulted`; write
findings with `upsert_section`; draft usable objects with `add_artifact`; kill paths with
`mark_considered_and_rejected`; maintain belief with `update_working_theory`; keep the readout fresh
with `update_debrief`; surface only real blocks via `flag_needs_input` or `flag_decision_point`;
summarize before pausing; deliver only when `why_enough` is credible."""


SYSTEM_PROMPT: str = MAIN_AGENT_SYSTEM_PROMPT


def build_system_prompt(dossier: "m.Dossier") -> str:
    """Returns the static prompt plus dossier-specific framing."""
    oos = dossier.out_of_scope or []
    oos_block = (
        "\n".join(f"- {item}" for item in oos) if oos else "(none specified)"
    )
    policy = dossier.check_in_policy
    policy_line = f"cadence={policy.cadence.value}"
    if policy.notes:
        policy_line += f"; notes: {policy.notes}"

    context = f"""

# This dossier

- title: {dossier.title}
- type: {dossier.dossier_type.value}
- status: {dossier.status.value}

## Problem statement
{dossier.problem_statement}

## Out of scope
{oos_block}

## Check-in policy
{policy_line}
"""
    return MAIN_AGENT_SYSTEM_PROMPT + context


def render_dossier_context(dossier: "m.Dossier") -> str:
    """Renders just the dossier-specific context block (no system prompt).

    Useful for runtimes that want to inject the dossier framing separately
    from the static system prompt.
    """
    oos = dossier.out_of_scope or []
    oos_block = (
        "\n".join(f"- {item}" for item in oos) if oos else "(none specified)"
    )
    policy = dossier.check_in_policy
    policy_line = f"cadence={policy.cadence.value}"
    if policy.notes:
        policy_line += f"; notes: {policy.notes}"

    return f"""# This dossier

- title: {dossier.title}
- type: {dossier.dossier_type.value}
- status: {dossier.status.value}

## Problem statement
{dossier.problem_statement}

## Out of scope
{oos_block}

## Check-in policy
{policy_line}
"""


# ---------- state snapshot helpers ----------


_SNAPSHOT_PREAMBLE = (
    "This is your current dossier state as of the start of this turn. Pick up where you left "
    "off. Remember: user-visible changes only via tool calls; prose in the chat goes nowhere."
)


def _trunc(text: str, limit: int) -> str:
    if text is None:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _age(created_at, now) -> str:
    if created_at is None:
        return "?"
    # Normalize to tz-aware for subtraction.
    ca = created_at
    if ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    n = now
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    delta = n - ca
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _budget_pressure_block(now) -> Optional[str]:
    """Render a 'Budget pressure' snapshot section only when near/past the cap.

    Returns None when:
      - settings / budget rollup are unreadable (best-effort, never raise)
      - daily_cap_usd is 0 (user disabled caps)
      - today's spend is below warn_fraction of the cap

    When we DO render, the block tells the agent how to adapt: narrow scope,
    summarize, or consider pausing. Budgets remain SOFT — we never demand a
    mark_delivered; we recommend strategies so the agent plans accordingly.
    """
    try:
        from .. import storage as _storage
    except Exception:
        return None
    try:
        cap = float(_storage.get_setting("budget_daily_soft_cap_usd", 0) or 0)
        warn_fraction = float(_storage.get_setting("budget_daily_warn_fraction", 0.8) or 0.8)
        session_cap = float(_storage.get_setting("budget_per_session_soft_cap_usd", 0) or 0)
    except Exception:
        return None
    if cap <= 0:
        return None
    try:
        roll = _storage.get_budget_today()
    except Exception:
        return None
    spent = roll.spent_usd
    warn_threshold = cap * warn_fraction
    if spent < warn_threshold:
        return None
    crossed = spent >= cap
    pct = (spent / cap * 100.0) if cap > 0 else 0.0

    lines: list[str] = ["## Budget pressure"]
    if crossed:
        lines.append(
            f"Today's spend ${spent:.2f} has crossed the soft cap of ${cap:.2f} ({pct:.0f}%)."
        )
        lines.append(
            "Budgets are SOFT — nobody is terminating this run. But the cost-benefit has "
            "changed: every additional turn needs to be clearly high-leverage. Adapt now:"
        )
        lines.append(
            "  - STOP broad exploration. No new sub-investigations unless one is the only "
            "path to a blocking answer."
        )
        lines.append(
            "  - NARROW any in-flight research to the single question that would most "
            "change the current working theory."
        )
        lines.append(
            "  - Prefer `update_working_theory` + `update_debrief` + `set_next_action` over "
            "new evidence-gathering. Summarize what you know over hunting for more."
        )
        lines.append(
            "  - If marginal value looks low: surface a `flag_decision_point` asking the "
            "user whether to continue, pause, or deliver with current best recommendation. "
            "Do NOT silently keep spending as if nothing changed."
        )
    else:
        lines.append(
            f"Today's spend ${spent:.2f} is {pct:.0f}% of the ${cap:.2f} soft cap — "
            f"inside the warn zone."
        )
        lines.append(
            "No hard action yet, but start leaning conservative: prefer narrow, "
            "high-signal moves over broad exploration. Revise the working theory when a "
            "sub returns rather than spawning another parallel one."
        )
    if session_cap > 0:
        lines.append(f"(per-session soft cap is ${session_cap:.2f}; check how much this session has spent.)")
    return "\n".join(lines)


def build_state_snapshot(dossier_full: "m.DossierFull") -> str:
    """Compact per-turn state block. Target ~500-1500 tokens."""
    from .. import models as m  # local import to avoid circularity at import time

    d = dossier_full.dossier
    now = m.utc_now()

    lines: list[str] = []
    lines.append(_SNAPSHOT_PREAMBLE)
    lines.append("")

    # Budget pressure — only rendered when >= warn fraction, and only if a
    # daily cap is configured. Placed near the top because it changes how the
    # agent should plan the rest of its moves.
    bp = _budget_pressure_block(now)
    if bp is not None:
        lines.append(bp)
        lines.append("")

    # Working theory — current belief, if any.
    wt = d.working_theory
    if wt is not None:
        lines.append("## Current working theory")
        lines.append(f"confidence: {wt.confidence.value}")
        lines.append(f"recommendation: {_trunc(wt.recommendation, 200)}")
        lines.append(f"why: {_trunc(wt.why, 200)}")
        lines.append(f"what would change it: {_trunc(wt.what_would_change_it, 200)}")
        lines.append(f"(updated {_age(wt.updated_at, now)} ago)")
        lines.append("")
    else:
        lines.append("## Current working theory")
        lines.append(
            "(none yet — call `update_working_theory` once you have a tentative direction)"
        )
        lines.append("")

    # Plan approval status — the gate on substantive work.
    plan = d.investigation_plan
    lines.append("## Plan status")
    if plan is None:
        lines.append("No plan yet — draft one via update_investigation_plan before anything else.")
    elif plan.approved_at is None:
        lines.append(
            "PLAN DRAFTED (awaiting user approval). Next move: flag_decision_point with "
            "kind=plan_approval, or refine via update_investigation_plan first. Do NOT begin "
            "substantive work (sources, subs, sections, artifacts) until approved."
        )
    else:
        lines.append(
            f"PLAN APPROVED ({plan.approved_at.isoformat()}). Proceed with substantive work."
        )
    lines.append("")

    lines.append("## Dossier")
    lines.append(f"title: {d.title}")
    lines.append(f"type: {d.dossier_type.value}  status: {d.status.value}")
    if d.last_visited_at is not None:
        lines.append(f"last user visit: {_age(d.last_visited_at, now)} ago")
    else:
        lines.append("last user visit: never (fresh dossier)")
    lines.append("")

    # Sections
    lines.append(f"## Sections ({len(dossier_full.sections)})")
    if not dossier_full.sections:
        lines.append("(none yet — the dossier is empty)")
    else:
        for s in dossier_full.sections:
            preview = _trunc(s.content, 150) if s.content else "(empty)"
            src_count = len(s.sources)
            src_tag = f"{src_count} src" if src_count else "no src"
            line1 = (
                f"- [{s.id}] {s.type.value}/{s.state.value}  \"{_trunc(s.title, 80)}\""
                f"  ({src_tag})"
            )
            lines.append(line1)
            lines.append(f"    content: {preview}")
            if s.change_note:
                lines.append(f"    change_note: {_trunc(s.change_note, 120)}")
    lines.append("")

    # Open needs_input
    open_ni = [n for n in dossier_full.needs_input if n.answered_at is None]
    lines.append(f"## Open needs_input ({len(open_ni)})")
    if not open_ni:
        lines.append("(none open)")
    else:
        for n in open_ni:
            lines.append(
                f"- [{n.id}] ({_age(n.created_at, now)} old) {_trunc(n.question, 200)}"
            )
    lines.append("")

    # Open decision_points
    open_dp = [dp for dp in dossier_full.decision_points if dp.resolved_at is None]
    lines.append(f"## Open decision_points ({len(open_dp)})")
    if not open_dp:
        lines.append("(none open)")
    else:
        for dp in open_dp:
            labels = " | ".join(_trunc(o.label, 40) for o in dp.options) or "(no options)"
            lines.append(f"- [{dp.id}] \"{_trunc(dp.title, 80)}\"  options: {labels}")
    lines.append("")

    # Ruled out
    lines.append(f"## Ruled out ({len(dossier_full.ruled_out)})")
    if not dossier_full.ruled_out:
        lines.append("(nothing ruled out yet)")
    else:
        for r in dossier_full.ruled_out:
            lines.append(
                f"- [{r.id}] {_trunc(r.subject, 60)} — {_trunc(r.reason, 120)}"
            )
    lines.append("")

    # Recent reasoning trail (last 10)
    trail = dossier_full.reasoning_trail[-10:]
    lines.append(
        f"## Recent reasoning_trail (last {len(trail)} of {len(dossier_full.reasoning_trail)})"
    )
    if not trail:
        lines.append("(empty — no notes yet)")
    else:
        for r in trail:
            tag_str = f"[{','.join(r.tags)}] " if r.tags else ""
            lines.append(
                f"- ({_age(r.created_at, now)} ago) {tag_str}{_trunc(r.note, 180)}"
            )

    return "\n".join(lines)
