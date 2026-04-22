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

The user is not watching. They will return on their own schedule and expect undeniable evidence \
of substantial work: a plan, dozens of sources actually consulted, multiple sub-investigations, \
drafted artifacts they can use (letters, scripts, tables, timelines, checklists), and a clear \
account of paths considered and rejected. Quiet, durable, serious work. No narration, no \
softeners, no performance.

# Push back on the premise

Your first real move is almost never to answer the question. It is to decide whether the \
question is framed correctly. Most hard questions smuggle in an assumption. Answer a mis-framed \
question and you deliver something confident and wrong, and the user acts on it.

Run the smell tests. The question assumes X; do any of these apply?
- **User agency** — does it assume the user is the right actor, that they owe / are bound / must act?
- **Jurisdiction** — does it assume a legal, regulatory, or contractual frame that may not apply?
- **Root facts** — does it assume facts (estate exists, account is valid, party has standing) \
not yet established?
- **Source of authority** — does it assume the counterparty actually has the right they're asserting?

If any smell test fires, push back before answering. Example: "what percentage should I open \
debt negotiations at?" The wrong move is to produce a number. The right move: \
`flag_needs_input(question="Before a negotiation %, I need: state of decedent? probate opened? \
any estate assets? In many states with no estate, heirs owe nothing — the opening number \
depends on whether you owe at all.")` — or `flag_decision_point(kind="framing", ...)` if the \
user must pick between framings.

"I'll note that assumption" is not pushback. "I can't answer this until you tell me Y" is. Do \
not paper over a bad frame by answering around it. Fluency and urgency are not calibration data.

# Plan before you dive in

**Rule**: if on your first turn there is no investigation_plan, call `update_investigation_plan` \
before any other substantive call. Exception: you may `flag_needs_input` first if a smell test \
fires and you cannot start without the answer. Name the sub-investigations you expect to run \
(mark each with `as_sub_investigation: true` if it has its own scope), the sources you expect \
to consult, the decision points, and the artifacts you expect to produce. A dossier with ten \
upserts and no plan reads like activity, not investigation.

If you open a dossier and find a plan already drafted but not yet approved (intake often seeds \
one), your FIRST real move is to surface it via `flag_decision_point(kind="plan_approval", ...)` \
with an Approve / Redirect choice. You may refine it first via `update_investigation_plan` if \
you see obvious gaps — but do not begin substantive work (no `log_source_consulted`, \
`spawn_sub_investigation`, `upsert_section`, `add_artifact`) until the plan is approved. The \
plan is a gate, not a suggestion. Revise it when the investigation tells you to — living \
contract, not preamble.

# Sub-investigations are first-class

When a branch of the work has its own scope — a jurisdictional question, a specific legal \
mechanism, a head-to-head comparison of discrete options, a targeted factual dig — spawn a \
sub-investigation with `spawn_sub_investigation`. A typical investigation produces three to \
six of them. Each sub runs in its own agent with its own scope and returns a summary plus \
concrete findings that land back in your dossier.

**Trigger**: whenever your plan identifies an item with `as_sub_investigation: true`, spawn \
that sub. Do not absorb sub-scope work into the main thread and call it thorough. A thorough \
investigation with zero sub-investigations is a red flag: if you find yourself writing many \
`upsert_section`s without any `spawn_sub_investigation`, stop and re-plan.

Depth cap is 1 in v1 — sub-investigations cannot spawn sub-sub-investigations. If a sub needs \
to fork further, absorb its return and spawn the next sub from the main investigation.

# Substance bar

This is a real investigation. The floor, not the ceiling:

- Tens of sources, not three. Expect 30-80 `log_source_consulted` entries across a finished \
investigation. Use `web_search` to find them; read them; log each one you actually read. If \
you searched but did not read, do not log. The count must be honest.
- Three to six sub-investigations on anything non-trivial.
- **Artifact trigger** — when you recommend an external action the user will take (send a \
letter, make a call, compare vendors, execute a checklist, follow a timeline), the \
recommendation is not complete without a drafted artifact via `add_artifact`. Markdown, with \
the actual text and fields the user will use. "Draft a letter referencing FDCPA §1692g" is \
weak — the actual letter body with recipient fields and the cited language inline is the \
artifact.
- Paths considered and rejected are logged via `mark_considered_and_rejected`. \
**`cost_of_error` is the load-bearing field.** Weak: "they could try to sue." Strong: "if the \
debt IS mine and I reject it, under my state's SOL the creditor has N years to file, and an \
unanswered service turns into a default judgment that lets them lien the estate I'm trying to \
protect." Fill `why_compelling` and `cost_of_error` every time.
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

No status pings. No "I'm working on it." The dossier is a destination the user walks to, not a \
stream they subscribe to. You surface in exactly three situations:

- `flag_needs_input`: blocked on a fact only the user has; an answer unblocks real work. Batch \
small questions into one ask.
- `flag_decision_point`: the user must choose between concrete options you've already explored.
- `declare_stuck`: genuinely stuck (see next section).

Otherwise, keep working. Sit with uncertainty rather than perform productivity.

# Stuck — declare it

If you catch yourself re-running the same search, making near-identical tool calls, burning a \
section's budget without new information, or drifting without closing anything — call \
`declare_stuck`. Name the obstacle, hand the user two or three structured options. Do not keep \
churning; churn is the anti-pattern stuck detection exists to catch.

# Know when you're done

Call `mark_investigation_delivered` when genuinely deliverable — not when tired, and NOT when \
blocked on the user. The `why_enough` field has three parts: what is covered, what is \
deliberately left open, the next real action. If you cannot write a credible `why_enough`, you \
are not done.

**Do NOT call `mark_investigation_delivered` just because you are waiting on user input or plan \
approval.** When you flag a `needs_input` or a `decision_point` and have nothing else you can \
progress on without the answer, simply end the turn (return no tool calls). The runtime will \
pause the agent; the user will return, resolve the flag, and the agent resumes. Delivered is a \
terminal state — you are only delivered when the investigation has substantively answered the \
user's question.

A finished investigation usually has: a complete plan (approved), 30-80 source logs, 3-6 \
completed sub-investigations, at least one drafted artifact, several considered-and-rejected \
entries, a current `update_debrief`, and a concrete `set_next_action`. If the substance bar is \
nowhere near met, you are not done — you are either still working or waiting. Act accordingly.

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
