"""Tests for the v2 Vellum agent prompts (main + sub-investigation)."""
from __future__ import annotations

from vellum.agent.prompt import MAIN_AGENT_SYSTEM_PROMPT
from vellum.agent.sub_prompt import (
    SUB_INVESTIGATION_SYSTEM_PROMPT,
    render_sub_scope,
)


# ---------- length bounds ----------


def test_main_prompt_length_bounds() -> None:
    n = len(MAIN_AGENT_SYSTEM_PROMPT)
    assert n >= 2000, f"main prompt too short: {n} chars"
    assert n <= 10000, f"main prompt too long: {n} chars"


def test_sub_prompt_length_bounds() -> None:
    n = len(SUB_INVESTIGATION_SYSTEM_PROMPT)
    assert n >= 800, f"sub prompt too short: {n} chars"
    assert n <= 5000, f"sub prompt too long: {n} chars"


# ---------- required tokens ----------


_MAIN_REQUIRED_TOKENS = [
    "investigation",
    "push back",
    "plan",
    "sub-investigation",
    "log_source_consulted",
    "artifact",
    "update_debrief",
    "mark_investigation_delivered",
    "flag_needs_input",
]


def test_main_prompt_contains_required_tokens() -> None:
    lower = MAIN_AGENT_SYSTEM_PROMPT.lower()
    missing = [t for t in _MAIN_REQUIRED_TOKENS if t.lower() not in lower]
    assert not missing, f"main prompt missing tokens: {missing}"


# ---------- day 5 pressure-test additions ----------


def test_main_prompt_has_smell_tests_for_premise_pushback() -> None:
    """Premise pushback must be concrete, not abstract — the prompt should cue
    the agent to check specific categories of assumption in the question."""
    lower = MAIN_AGENT_SYSTEM_PROMPT.lower()
    assert "smell test" in lower or "smell tests" in lower, (
        "main prompt should reference 'smell tests' for premise pushback"
    )
    assert "assumes" in lower, (
        "main prompt should talk about what the question 'assumes'"
    )


def test_main_prompt_emphasises_cost_of_error() -> None:
    """cost_of_error is the load-bearing field on considered_and_rejected —
    the prompt must call this out, not just list the tool."""
    lower = MAIN_AGENT_SYSTEM_PROMPT.lower()
    assert "cost_of_error" in lower or "cost of error" in lower or "cost-of-error" in lower, (
        "main prompt should emphasise cost_of_error on considered-and-rejected"
    )


def test_main_prompt_mentions_key_tool_names_explicitly() -> None:
    """Core tools must be called out by exact name so the agent knows to invoke
    them, not just describe them."""
    required = [
        "update_investigation_plan",
        "spawn_sub_investigation",
        "mark_considered_and_rejected",
        "add_artifact",
        "flag_decision_point",
        "flag_needs_input",
    ]
    missing = [t for t in required if t not in MAIN_AGENT_SYSTEM_PROMPT]
    assert not missing, f"main prompt missing explicit tool names: {missing}"


_SUB_REQUIRED_TOKENS = [
    "complete_sub_investigation",
    "return_summary",
    "sub-investigator",
    "scope",
]


def test_sub_prompt_contains_required_tokens() -> None:
    lower = SUB_INVESTIGATION_SYSTEM_PROMPT.lower()
    missing = [t for t in _SUB_REQUIRED_TOKENS if t.lower() not in lower]
    assert not missing, f"sub prompt missing tokens: {missing}"


def test_sub_prompt_does_not_mention_spawn_sub_investigation() -> None:
    # Depth cap = 1: sub-investigators cannot spawn further subs, and the
    # prompt should not leak that tool name as if it were available.
    assert "spawn_sub_investigation" not in SUB_INVESTIGATION_SYSTEM_PROMPT


def test_sub_prompt_word_count_under_limit() -> None:
    # Sharpening pass (day 5) targets ~900 words. Guard both ends so the
    # prompt does not drift back into the weak/shapeless zone (<650 words)
    # or bloat past the limit.
    words = len(SUB_INVESTIGATION_SYSTEM_PROMPT.split())
    assert 650 <= words <= 900, f"sub prompt word count off target: {words}"


def test_sub_prompt_demands_confidence_level() -> None:
    # Every return_summary MUST state confidence high/medium/low. The prompt
    # should explicitly name that requirement — "confident" alone is too
    # ambiguous.
    lower = SUB_INVESTIGATION_SYSTEM_PROMPT.lower()
    assert "confidence" in lower, "sub prompt should require a confidence level"
    # All three levels mentioned so the sub knows the axis, not just the word.
    assert "high" in lower and "medium" in lower and "low" in lower, (
        "sub prompt should enumerate high / medium / low confidence levels"
    )


def test_sub_prompt_handles_conditional_answers() -> None:
    # If the answer depends on a branch ('depends on state', etc.), the
    # sub must surface the condition and both branches, not hide one.
    lower = SUB_INVESTIGATION_SYSTEM_PROMPT.lower()
    assert "conditional" in lower or "condition" in lower, (
        "sub prompt should address conditional answers"
    )


def test_sub_prompt_warns_against_early_exit() -> None:
    # The "5 turns, 3 sources is an early exit" discipline must be explicit
    # so the sub does not return half-baked.
    lower = SUB_INVESTIGATION_SYSTEM_PROMPT.lower()
    assert "early exit" in lower or "exit early" in lower, (
        "sub prompt should name the early-exit failure mode"
    )


def test_sub_prompt_requires_pre_search_scope_check() -> None:
    # Scope discipline: before each web_search, the sub should ask whether
    # the query is inside scope. The prompt should make that check concrete.
    text = SUB_INVESTIGATION_SYSTEM_PROMPT
    assert "web_search" in text, "sub prompt should reference web_search"
    assert "scope" in text.lower(), "sub prompt should mention scope"
    # The pre-search scope check is the concrete guardrail; look for a
    # phrasing close to 'before each web_search'.
    assert "before each" in text.lower() or "before every" in text.lower(), (
        "sub prompt should demand a pre-search scope check"
    )


def test_sub_prompt_requires_findings_sections() -> None:
    # A summary-only return (no findings_section_ids) is weaker than one
    # with sections the parent can include verbatim. Prompt should say so.
    lower = SUB_INVESTIGATION_SYSTEM_PROMPT.lower()
    assert "findings_section_ids" in lower, (
        "sub prompt should reference findings_section_ids"
    )
    # Either "at least one section" or the summary-only-is-weaker framing.
    assert (
        "at least one section" in lower
        or "summary-only" in lower
        or "no sections" in lower
    ), "sub prompt should require at least one section on return"


# ---------- render_sub_scope ----------


def test_render_sub_scope_includes_scope_and_questions() -> None:
    out = render_sub_scope("test scope", ["q1", "q2"])
    assert isinstance(out, str)
    assert "test scope" in out
    assert "q1" in out
    assert "q2" in out
