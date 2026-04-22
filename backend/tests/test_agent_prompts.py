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


# ---------- render_sub_scope ----------


def test_render_sub_scope_includes_scope_and_questions() -> None:
    out = render_sub_scope("test scope", ["q1", "q2"])
    assert isinstance(out, str)
    assert "test scope" in out
    assert "q1" in out
    assert "q2" in out
