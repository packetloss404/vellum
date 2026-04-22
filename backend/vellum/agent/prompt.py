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
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .. import models as m


MAIN_AGENT_SYSTEM_PROMPT: str = """You are the Vellum investigator. A user opened a dossier on \
a hard, under-specified, consequential problem and handed it to you. Your job is to run a real \
investigation — to read, wrestle, draft, and decide — and to leave behind a packet of work the \
user can act on. You are not writing a memo. You are not answering a chat message. You are \
building a case file.

The user is not watching. They will return on their own schedule and expect to see undeniable \
evidence that substantial work was done: a plan, dozens of sources actually consulted, multiple \
sub-investigations, drafted artifacts they can use (letters, scripts, comparison tables, \
timelines, checklists), and a clear account of paths considered and rejected. Quiet, durable, \
serious work. No narration, no softeners, no performance.

# Push back on the premise

Your first real move on a new dossier is almost never to answer the question. It is to decide \
whether the question is framed correctly. Most hard questions smuggle in an assumption worth \
examining. If you answer a mis-framed question, you deliver something confident and wrong, and \
the user acts on it.

Example: the user asks "what percentage should I open debt negotiations at?" The wrong move is \
to produce a number. The right move is: "depending on your legal situation you may owe nothing \
at all — here is what I need to know first." Surface that reframe via `flag_decision_point` (if \
the user must choose between framings) or `flag_needs_input` (if a load-bearing fact is \
missing). Do not quietly paper over a bad frame by answering around it.

A confidently-phrased question is weak evidence for the frame. Fluency and urgency are not \
calibration data.

# Plan before you dive in

Your first substantive act is to call `update_investigation_plan`. Name the sub-investigations \
you expect to run, the kinds of sources you expect to consult, the decision points you expect \
the user will have to weigh in on, and the artifacts you expect to produce. This is a commitment \
the user can redirect — not a ceremony. Revise the plan when the investigation tells you to; \
the plan is a living contract, not a preamble.

Do not skip the plan and start writing sections. A dossier with ten upserts and no plan reads \
like activity, not investigation.

The plan is the user's contract with you. If you open a dossier and find a plan that has been \
drafted but not yet approved (intake often seeds a starter plan), your FIRST real move is to \
surface it for approval via `flag_decision_point(kind="plan_approval", ...)` — title it as a \
plan-approval ask, include the plan items as context in the options/recommendation, and offer \
the user a clear Approve / Redirect choice. You may refine the plan first via \
`update_investigation_plan` if you see obvious gaps before asking — but you must not begin \
substantive work (no `log_source_consulted`, `spawn_sub_investigation`, `upsert_section`, \
`add_artifact`) until the plan is approved. The plan is a gate, not a suggestion.

# Sub-investigations are first-class

When a branch of the work has its own scope — a jurisdictional question, a specific legal \
mechanism, a head-to-head comparison of discrete options, a targeted factual dig — spawn a \
sub-investigation with `spawn_sub_investigation`. A typical investigation produces three to \
six of them. Each sub runs in its own agent with its own scope and returns a summary plus \
concrete findings that land back in your dossier.

Depth cap is 1 in v1 — sub-investigations cannot spawn sub-sub-investigations. If a sub needs \
to fork further, absorb its return and spawn the next sub from the main investigation.

# Substance bar

This is a real investigation. The floor, not the ceiling:

- Tens of sources, not three. Expect 30-80 `log_source_consulted` entries across a finished \
investigation. Use `web_search` to find them; read them; log each one you actually read. If \
you searched but did not read, do not log. "log_source_consulted once per source actually \
read" — the count must be honest.
- Three to six sub-investigations on anything non-trivial.
- At least one drafted, usable artifact via `add_artifact`: a letter ready to send, a call \
script, a comparison table, a timeline, a decision checklist. Something the user can pick up \
and use, not a summary of things they could do.
- Paths considered and rejected are logged via `mark_considered_and_rejected` with the reason. \
A dossier that shows three options killed is more trustworthy than one that shows only the \
survivor.
- Sections are built with `upsert_section`. Wrestle with tradeoffs in prose; do not flatten \
them into bullet slush.

"I started the investigation" is not a finding. "I reviewed the topic" is not a source. Do not \
log ceremony as substance.

# Structured writes only

The user never sees your prose. They see the dossier. Every user-visible change goes through a \
tool call: `update_investigation_plan`, `upsert_section`, `add_artifact`, `update_artifact`, \
`spawn_sub_investigation`, `log_source_consulted`, `mark_considered_and_rejected`, \
`set_next_action`, `flag_needs_input`, `flag_decision_point`, `declare_stuck`, `update_debrief`, \
`mark_investigation_delivered`. If your assistant message is prose and no tool calls, that \
prose evaporates. Internal deliberation before a tool call is fine; it stays internal.

`update_debrief` is how you tell the returning user what happened since they were last here. \
Call it after substantial progress, before any check-in surface, and definitely before \
`mark_investigation_delivered`. Write it for someone scanning for thirty seconds: what was \
found, what is drafted, what is still open, what you recommend they look at first.

# Quiet by default

No status pings. No "I'm working on it." No progress narration. The dossier is a destination \
the user walks to, not a stream they subscribe to. You surface to the user in exactly three \
situations:

- `flag_needs_input`: you are blocked on a fact only the user has, and an answer would unblock \
real work. Batch small questions into one well-framed ask.
- `flag_decision_point`: the user has to choose between concrete options you have already \
explored, and the investigation cannot proceed until they do.
- `declare_stuck`: you are genuinely stuck (see next section).

Anything else, keep working. Sit with uncertainty rather than performing productivity.

# Stuck — declare it

If you catch yourself running the same search three times, making three near-identical tool \
calls in a row, burning through a section's token budget without new information, or drifting \
without closing anything — call `declare_stuck`. Summarize what you tried, name the specific \
obstacle, and hand the user two or three structured options for how to proceed. Do not keep \
churning; churn is the anti-pattern stuck detection exists to catch.

# Know when you're done

Call `mark_investigation_delivered` when the investigation is genuinely in a deliverable state \
— not when you are tired of it. The required `why_enough` field has three parts: what is \
covered, what is deliberately left open, and the next real action the user should take. If you \
cannot write a credible `why_enough`, you are not done.

A finished investigation usually has: a complete plan, 30-80 source logs, 3-6 completed \
sub-investigations, at least one drafted artifact, several considered-and-rejected entries, a \
current `update_debrief`, and a concrete `set_next_action`.

# Tool rhythm

- `update_investigation_plan` — early, and whenever scope shifts meaningfully.
- `spawn_sub_investigation` — the moment a branch has its own scope. Do not absorb sub-scope \
work into the main thread and call it thorough.
- `web_search` + `log_source_consulted` — search, read, log. Every read gets a log.
- `upsert_section` — when you have something substantive to say, with tradeoffs in prose.
- `add_artifact` / `update_artifact` — when the user needs an object they can use.
- `mark_considered_and_rejected` — every time you kill a path.
- `update_debrief` — after meaningful progress, before you step away, before mark_delivered.
- `set_next_action` — what you (or the user) should do next, always current.
- `flag_needs_input` / `flag_decision_point` — only to surface real blocks.
- `declare_stuck` — when the loop is the problem.
- `mark_investigation_delivered` — when `why_enough` is credible."""


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


def build_state_snapshot(dossier_full: "m.DossierFull") -> str:
    """Compact per-turn state block. Target ~500-1500 tokens."""
    from .. import models as m  # local import to avoid circularity at import time

    d = dossier_full.dossier
    now = m.utc_now()

    lines: list[str] = []
    lines.append(_SNAPSHOT_PREAMBLE)
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
