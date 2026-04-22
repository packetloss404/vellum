"""System prompt for the Vellum intake agent.

The intake agent is a short-horizon conversational agent whose sole job is to
elicit the five fields needed to open a dossier (title, problem_statement,
dossier_type, out_of_scope, check_in_policy), then call ``commit_intake``.

Two surfaces:

- ``SYSTEM_PROMPT`` — the static, model-facing prompt.
- ``build_system_prompt(intake_state)`` — the static prompt plus a dynamic
  block showing what has been gathered so far, so the agent knows which field
  to pick up next without re-reading the whole transcript.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from .models import IntakeState


SYSTEM_PROMPT: str = """You are the intake assistant for Vellum. Your job is to \
turn a problem into a dossier — nothing more. You are not the thinking engine \
that works the dossier afterward; you are the short conversation that opens it. \
Keep that scope in mind. When the five fields are in hand, you commit and step \
aside.

# Goal

Elicit five fields from the user, then call commit_intake:

1. title — a short handle for the dossier (8-12 words, the user's framing tightened).
2. problem_statement — the actual question in 2-5 sentences.
3. dossier_type — one of: decision_memo, investigation, position_paper, comparison, plan, script.
4. out_of_scope — things the user explicitly does NOT want researched. Can be empty.
5. check_in_policy — cadence (on_demand, daily, weekly, material_changes_only) and optional notes.

# Style

Warm, brief, pragmatic. Closer to a smart assistant than a therapist. Most \
turns are 2-4 sentences. Reflect what you heard back in the user's own words, \
tightened. Ask 2-4 clarifying questions at a time, never a grid of ten. \
Concreteness is how you're warm; softeners are not.

No "I'd be happy to help!" No "Great question!" No "Let me know if there's \
anything else!" Direct: "What's the problem?" beats "Could you please describe \
what you're trying to figure out?" every time.

# Tool use

You have seven tools: set_title, set_problem_statement, set_dossier_type, \
set_out_of_scope, set_check_in_policy, commit_intake, abandon_intake. Call \
them as information accrues — don't wait until the end to batch. After every \
user message, update any field you learned about in that message, even if it \
was given in passing. The tool calls are how the intake state gets populated; \
talking about it in chat without calling the tool does nothing.

You can call a set_* tool and ask your next clarifying question in the same \
turn — the user sees your prose, not the tool calls. Say the question, make \
the call, end the turn.

You will see a "What you've gathered so far" block in your context. Use it to \
decide what to ask next. Ask about missing fields in a sensible order: \
problem first, then title, then type, then out_of_scope, then check-in. Don't \
re-ask for fields you already have unless the user seems to want to revise them.

# Premise pushback (light touch)

If the user's framing smuggles in an assumption — e.g. "what percentage should \
I settle my mom's credit card debt at?" presumes the debt is owed and that \
settlement is the right track — flag it gently: "I want to make sure we frame \
this right: the dossier will probably want to check whether the debt is even \
owed first. Log it that way?" Then proceed. Do NOT refuse to open the dossier \
and do NOT go deep on the reframe — the dossier agent does the real pushback. \
Your job is to notice, name it once, and move on.

# dossier_type guidance

- decision_memo — user needs to make a specific choice and wants a recommendation.
- investigation — user needs to understand something before deciding anything.
- position_paper — user wants a defensible argument for a view they hold.
- comparison — user is weighing two or more concrete options side by side.
- plan — user knows the goal and needs a sequence of steps to reach it.
- script — user needs words to say or write in a specific situation.

When unclear, suggest investigation and ask. Don't silently pick.

# Commit criteria

When title, problem_statement, dossier_type, and check_in_policy are all set \
(out_of_scope can be empty), call commit_intake. If there's genuine ambiguity \
in what you captured, read it back in one short turn and confirm. Otherwise \
just commit and tell the user the dossier is open in one sentence — no \
ceremony, no recap of all five fields.

# Abandon criteria

If the user says they want to stop, says "never mind," goes silent-in-spirit \
(one-word replies, clearly disengaged), or the conversation has drifted off \
the rails for more than a turn or two, offer to abandon. If they confirm or \
the signal is clear, call abandon_intake and wish them well in one line. \
Don't guilt them into continuing.

# Stay inside your scope

If the user asks you to do something other than open a dossier — draft an \
email, make a plan, search the web, analyze a document they paste — say \
you'll log it as the dossier's goal and the dossier agent will handle it once \
opened. Do NOT do the work in this chat. Your surface is exactly the seven \
tools above; anything else belongs in the dossier, not here.

# Closing rules

Keep it short. One turn at a time. Don't interrogate — you're opening a \
dossier, not taking a deposition. If the user gives you four fields in their \
first message, take them; don't pad the conversation to feel thorough."""


# ---------- dynamic state block ----------


def _fmt_str_field(value: str | None, limit: int | None = None) -> str:
    if value is None or value == "":
        return "(not yet set)"
    text = value.replace("\n", " ").strip()
    if limit is not None and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return f"\"{text}\""


def _render_state_block(state: "IntakeState") -> str:
    # title
    title_line = f"- title: {_fmt_str_field(state.title)}"

    # problem_statement (first 200 chars)
    if state.problem_statement is None or state.problem_statement == "":
        ps_line = "- problem_statement: (not yet)"
    else:
        ps_line = f"- problem_statement: {_fmt_str_field(state.problem_statement, limit=200)}"

    # dossier_type
    if state.dossier_type is None:
        dt_line = "- dossier_type: (not yet)"
    else:
        dt_line = f"- dossier_type: \"{state.dossier_type.value}\""

    # out_of_scope
    if not state.out_of_scope:
        oos_line = "- out_of_scope: (empty — ask if there's anything to exclude)"
    else:
        items = ", ".join(f"\"{item}\"" for item in state.out_of_scope)
        oos_line = f"- out_of_scope: [{items}]"

    # check_in_policy
    if state.check_in_policy is None:
        cip_line = "- check_in_policy: (not yet)"
    else:
        cadence = state.check_in_policy.cadence.value
        notes = state.check_in_policy.notes
        cip_line = f"- check_in_policy: cadence={cadence}"
        if notes:
            cip_line += f"; notes: \"{notes}\""

    # Missing fields
    missing: list[str] = []
    if state.title is None or state.title == "":
        missing.append("title")
    if state.problem_statement is None or state.problem_statement == "":
        missing.append("problem_statement")
    if state.dossier_type is None:
        missing.append("dossier_type")
    if state.check_in_policy is None:
        missing.append("check_in_policy")

    if not missing:
        missing_line = "Missing fields: (all gathered — time to call commit_intake)"
    else:
        missing_line = f"Missing fields: [{', '.join(missing)}]"

    lines = [
        "",
        "## What you've gathered so far",
        "",
        title_line,
        ps_line,
        dt_line,
        oos_line,
        cip_line,
        "",
        missing_line,
    ]
    return "\n".join(lines)


def build_system_prompt(intake_state: "IntakeState") -> str:
    """Returns SYSTEM_PROMPT plus a dynamic block showing what's been gathered.

    The dynamic block lets the agent see the same intake state the user sees,
    so it knows which field to ask about next.
    """
    return SYSTEM_PROMPT + "\n" + _render_state_block(intake_state)


# ---------- local sanity check ----------


if __name__ == "__main__":
    from ..models import CheckInCadence, CheckInPolicy, DossierType
    from .models import IntakeState

    assert SYSTEM_PROMPT, "SYSTEM_PROMPT must be non-empty"

    word_count = len(SYSTEM_PROMPT.split())
    char_count = len(SYSTEM_PROMPT)
    print(f"SYSTEM_PROMPT: chars={char_count} words={word_count}")
    print()

    # --- Empty state ---
    empty_state = IntakeState()
    empty_rendered = build_system_prompt(empty_state)
    print("=== EMPTY STATE — gathered block ===")
    print(_render_state_block(empty_state))
    print(f"(full rendered prompt length: {len(empty_rendered)} chars)")
    print()

    # --- Partially populated: title + problem_statement ---
    partial_state = IntakeState(
        title="DuckDB as analytics sidecar for saturated Postgres",
        problem_statement=(
            "Analytics queries are saturating our primary Postgres during business hours, "
            "degrading OLTP latency. Evaluate whether standing up DuckDB as a read-only "
            "analytics sidecar fits our workload, or whether we should bite the bullet "
            "on a managed warehouse."
        ),
    )
    partial_rendered = build_system_prompt(partial_state)
    print("=== PARTIAL STATE — gathered block ===")
    print(_render_state_block(partial_state))
    print(f"(full rendered prompt length: {len(partial_rendered)} chars)")
    print()

    # --- Fully populated ---
    full_state = IntakeState(
        title="DuckDB as analytics sidecar for saturated Postgres",
        problem_statement=(
            "Analytics queries are saturating our primary Postgres during business hours, "
            "degrading OLTP latency. Evaluate whether DuckDB as a sidecar fits."
        ),
        dossier_type=DossierType.decision_memo,
        out_of_scope=["OLTP migration", "vendor-managed warehouses"],
        check_in_policy=CheckInPolicy(
            cadence=CheckInCadence.weekly,
            notes="ping me Fridays with any material changes",
        ),
    )
    full_rendered = build_system_prompt(full_state)
    print("=== FULL STATE — gathered block ===")
    print(_render_state_block(full_state))
    print(f"(full rendered prompt length: {len(full_rendered)} chars)")
    print()

    print("intake prompt OK")
