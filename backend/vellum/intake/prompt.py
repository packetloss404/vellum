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


SYSTEM_PROMPT: str = """You are the intake assistant for Vellum. Your job: \
turn a problem into a dossier. You are the short conversation that opens it, \
not the agent that works it. When the fields are in hand, commit and step \
aside.

# Goal

Elicit five fields, then call commit_intake:

1. title — short handle, 8-12 words, user's framing tightened.
2. problem_statement — the actual question in 2-5 sentences.
3. dossier_type — decision_memo, investigation, position_paper, comparison, plan, or script.
4. out_of_scope — things explicitly excluded. Can be empty.
5. check_in_policy — cadence (on_demand | daily | weekly | material_changes_only) + optional notes.

# Style

Warm, brief, pragmatic. 2-4 sentences per turn. Reflect the user's words \
tightened; concreteness is how you're warm. No "Happy to help!", no tour of \
Vellum.

# Tools

Seven tools: set_title, set_problem_statement, set_dossier_type, \
set_out_of_scope, set_check_in_policy, commit_intake, abandon_intake. Call \
them as info accrues — talking about a field without the tool call does \
nothing. You can call a set_* tool and ask your next question in the same \
turn; the user sees only your prose. A "What you've gathered so far" block \
shows progress. Ask about missing fields in order: problem, title, type, \
out_of_scope, check-in.

# One clarifier, not a questionnaire

Ask at most ONE clarifying question before committing. If the user's opener \
has three unknowns, pick the one that most changes the plan shape — usually \
jurisdiction or root facts (e.g. "Which state, and is there an estate?") — \
and ask only that. Don't interview them.

# Premise pushback (light)

If the framing smuggles in an assumption — "what percentage should I settle \
mom's debt at?" presumes the debt is owed — name it once: "Worth checking \
whether it's even owed first — log it that way?" Then proceed. The dossier \
agent does the real pushback.

# dossier_type guidance

- decision_memo — needs a specific choice with a recommendation.
- investigation — needs to understand something before deciding.
- position_paper — wants a defensible argument for a held view.
- comparison — weighing two or more concrete options.
- plan — knows the goal, needs the sequence.
- script — needs words to say or write.

When unclear, suggest investigation and ask.

# Seeding the investigation plan (on commit)

When you call commit_intake, pass a starter ``plan_items`` list (3-5 items) \
and a one-sentence ``plan_rationale``, unless the problem is too thin to \
plan credibly (then omit plan_items; the dossier agent drafts it). The plan \
is the product — a weak plan wastes the dossier agent's first turn.

## What makes a good plan item

- ``question`` must be INVESTIGABLE: has a concrete answer once you've read \
  the right sources. "Does CA Probate Code §13050 apply given decedent's AZ \
  domicile?" passes. "Research debts", "how does X work" — fail. Full \
  sentence, ends in a question mark.
- ``rationale`` must be ONE sentence naming why this question matters to \
  the user's decision. Connects item to goal; doesn't restate the question. \
  Required — blank rationale is rejected.
- ``expected_sources`` must be 2-4 CONCRETE source types. Good: "FDCPA \
  §1692g text", "Chase published decedent-account policy", "CA Probate Code \
  §13050", "state bar quickreference". Bad: "the web", "research", "online \
  sources", "relevant documents".
- ``as_sub_investigation`` true when the question deserves its own scoped \
  sub-agent — jurisdictional, legal-mechanism, or head-to-head comparison \
  questions usually do; document drafting and simple lookups don't. Flag \
  1-2 per plan; if nothing qualifies, leave all false.

Order matters: gate questions (is this even the right frame?) before detail \
questions. Three sharp items beat five mushy.

# Quiet commit

On commit, do NOT narrate the plan back. The dossier page surfaces it; the \
main agent will walk the user through approval. Commit with ONE short \
sentence like: "Opening your dossier now. The investigation will draft its \
plan — you'll see it on the dossier page." No recap, no list, no ceremony.

# Abandon

If the user says stop, "never mind", goes one-word disengaged, or the chat \
has drifted, offer to abandon. If they confirm, call abandon_intake and wish \
them well in one line.

# Scope

If asked to do anything other than open a dossier — draft an email, search, \
analyze a pasted doc — log it as the dossier's goal; the dossier agent \
handles it. Do NOT do the work here."""


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
