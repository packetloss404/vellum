"""Tests for the sub-investigation runtime (day 2).

The sub-runtime drives a synchronous sub-agent loop when the main agent
calls ``spawn_sub_investigation``. Tests here mock Anthropic's client with
scripted tool_use sequences — no live LLM calls.

Covers:
    - spawn_handler persists a sub_investigation row via storage
    - run_sub_investigation terminates cleanly on complete_sub_investigation
    - run_sub_investigation force-completes when max_turns is hit
    - tool filter excludes spawn_sub_investigation + main-only tools
    - log_source_consulted inside a sub attributes sub_investigation_id
    - module import registers HANDLER_OVERRIDES["spawn_sub_investigation"]
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    """Stand-in for an Anthropic content block (text or tool_use)."""
    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict | None = None


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _Response:
    content: list
    stop_reason: str = "end_turn"
    usage: _Usage | None = None


def _text_block(text: str) -> _Block:
    return _Block(type="text", text=text)


def _tool_use(name: str, input_: dict, id_: str = "tu_1") -> _Block:
    return _Block(type="tool_use", name=name, input=input_, id=id_)


def _make_mock_client(responses: list[_Response]) -> AsyncMock:
    """Return a mock AsyncAnthropic client that yields ``responses`` in order.

    Emulates the streaming API the runtime now uses: ``async with
    client.messages.stream(...) as stream:`` then
    ``await stream.get_final_message()``.

    When responses run out, it repeats an empty-turn (no tool_use) so the
    loop's prod-then-force-complete path exercises predictably.
    """
    iterator = iter(responses)
    fallback = _Response(
        content=[_text_block("done thinking")],
        stop_reason="end_turn",
        usage=_Usage(),
    )

    def _next() -> _Response:
        try:
            return next(iterator)
        except StopIteration:
            return fallback

    def _stream(**kwargs):
        msg = _next()

        class _StreamCM:
            async def __aenter__(self):
                class _Stream:
                    async def get_final_message(self_inner):
                        return msg
                return _Stream()

            async def __aexit__(self, *exc):
                return False

        return _StreamCM()

    async def _create(**kwargs) -> _Response:
        # Legacy fallback — keep so any test that mocks .create directly
        # still works. The runtime uses stream() in production.
        return _next()

    client = AsyncMock()
    client.messages = AsyncMock()
    client.messages.create = _create
    client.messages.stream = _stream
    return client


def _mk_dossier():
    from vellum import models as m, storage
    return storage.create_dossier(
        m.DossierCreate(
            title="sub-runtime test dossier",
            problem_statement="Runtime tests.",
            dossier_type=m.DossierType.investigation,
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_registration_on_import():
    """Importing sub_runtime wires spawn_handler into HANDLER_OVERRIDES.

    The conftest's ``_isolate_tool_hooks`` fixture clears
    ``HANDLER_OVERRIDES`` between tests to prevent leakage. If this test
    runs after a test that imported sub_runtime for the first time, the
    snapshot taken by the fixture will have been empty (no overrides)
    and the override entry will have been cleared. Force a reimport so
    the module-level registration runs again under the fresh snapshot.
    """
    import importlib
    from vellum.agent import sub_runtime
    from vellum.tools import handlers

    # Force re-run of module-level registration if it was cleared by the
    # test-isolation fixture.
    if "spawn_sub_investigation" not in handlers.HANDLER_OVERRIDES:
        importlib.reload(sub_runtime)

    assert hasattr(handlers, "HANDLER_OVERRIDES")
    assert "spawn_sub_investigation" in handlers.HANDLER_OVERRIDES
    assert (
        handlers.HANDLER_OVERRIDES["spawn_sub_investigation"]
        is sub_runtime.spawn_handler
    )


def test_tool_filter_excludes_main_only_and_spawn(fresh_db):
    """Sub-agent's tool set must exclude spawn + main-agent-only tools.

    Explicitly checks: no spawn_sub_investigation, no update_investigation_plan,
    no update_debrief, no declare_stuck. Includes the six required tools plus
    web_search.
    """
    from vellum.agent.sub_runtime import _build_sub_tool_definitions

    tools = _build_sub_tool_definitions()
    names = {t.get("name") for t in tools}

    # Present
    for required in (
        "upsert_section",
        "add_artifact",
        "log_source_consulted",
        "mark_considered_and_rejected",
        "flag_needs_input",
        "complete_sub_investigation",
        "web_search",
    ):
        assert required in names, f"missing expected tool {required}"

    # Excluded
    for forbidden in (
        "spawn_sub_investigation",
        "update_investigation_plan",
        "update_debrief",
        "declare_stuck",
        "mark_investigation_delivered",
        "set_next_action",
        "update_section_state",
        "delete_section",
        "reorder_sections",
        "flag_decision_point",
        "append_reasoning",
        "mark_ruled_out",
        "check_stuck",
        "request_user_paste",
        "update_artifact",
    ):
        assert forbidden not in names, f"tool {forbidden} leaked into sub-agent set"


def test_spawn_handler_inserts_sub_row(fresh_db):
    """spawn_handler must persist a sub_investigation row before returning."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    # Open an active session so spawn uses it for change_log attribution.
    storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)

    # Scripted sub-agent: call complete_sub_investigation on turn 1.
    responses = [
        _Response(
            content=[
                _text_block("answering"),
                _tool_use(
                    "complete_sub_investigation",
                    {
                        "return_summary": "Answer: the sub scope is answered.",
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                    id_="tu_complete",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
    ]

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        result = sub_runtime.spawn_handler(
            dossier.id,
            {
                "scope": "Does Texas treat unsecured debt as community debt?",
                "questions": ["Is TX a community property state for debt?"],
            },
        )

    assert result["sub_investigation_id"].startswith("sub_")
    assert result["state"] == "delivered"
    assert "return_summary" in result

    # Row actually persisted.
    sub = storage.get_sub_investigation(result["sub_investigation_id"])
    assert sub is not None
    assert sub.scope.startswith("Does Texas")


def test_run_sub_investigation_clean_exit_on_complete(fresh_db):
    """Loop terminates as soon as complete_sub_investigation is called."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="clean-exit scope", questions=["Q1?"]),
    )

    responses = [
        _Response(
            content=[
                _tool_use(
                    "upsert_section",
                    {
                        "type": m.SectionType.finding.value,
                        "title": "Mid-investigation finding",
                        "content": "Intermediate finding body.",
                        "state": m.SectionState.provisional.value,
                        "change_note": "sub wrote a finding",
                    },
                    id_="tu_upsert",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
        _Response(
            content=[
                _tool_use(
                    "complete_sub_investigation",
                    {
                        "return_summary": "Concise answer wrapping the scope.",
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                    id_="tu_complete",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
    ]

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        result = asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id,
                sub.id,
                sub.scope,
                sub.questions,
                max_turns=10,
            )
        )

    assert result["sub_investigation_id"] == sub.id
    assert result["terminated_without_completion"] is False
    assert result["return_summary"].startswith("Concise answer")
    # Only 2 turns consumed (upsert + complete); no prodding.
    assert result["turns"] == 2

    # Sub row reflects delivered state.
    fetched = storage.get_sub_investigation(sub.id)
    assert fetched.state == m.SubInvestigationState.delivered


def test_run_sub_investigation_records_usage_cost_and_daily_budget(fresh_db):
    """Sub-agent usage must roll into session and daily budget accounting."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime
    from vellum.config import cost_usd_for_turn

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="usage scope", questions=["Q1?"]),
    )
    responses = [
        _Response(
            content=[
                _tool_use(
                    "complete_sub_investigation",
                    {
                        "return_summary": "Answer with usage accounting.",
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                    id_="tu_complete_usage",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(input_tokens=123, output_tokens=45),
        ),
    ]

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id,
                sub.id,
                sub.scope,
                sub.questions,
                model="claude-sonnet-4-6",
                max_turns=5,
            )
        )

    [session] = storage.list_work_sessions(dossier.id)
    expected_cost = cost_usd_for_turn("claude-sonnet-4-6", 123, 45)
    assert session.input_tokens == 123
    assert session.output_tokens == 45
    assert session.token_budget_used == 168
    assert session.cost_usd == pytest.approx(expected_cost)

    budget = storage.get_budget_today()
    assert budget.input_tokens == 123
    assert budget.output_tokens == 45
    assert budget.spent_usd == pytest.approx(expected_cost)


def test_run_sub_investigation_force_completes_at_max_turns(fresh_db):
    """When max_turns is reached, force-complete with the incomplete marker."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="never-completes", questions=["Q?"]),
    )

    # Scripted responses always produce a tool_use that isn't
    # complete_sub_investigation, so the loop can't exit cleanly.
    # max_turns is small so the test finishes quickly.
    busy_turn = _Response(
        content=[
            _tool_use(
                "log_source_consulted",
                {
                    "citation": "https://example.com",
                    "why_consulted": "still thinking",
                    "what_learned": "need more time",
                },
                id_="tu_log",
            ),
        ],
        stop_reason="tool_use",
        usage=_Usage(),
    )

    responses = [busy_turn for _ in range(5)]

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        result = asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id,
                sub.id,
                sub.scope,
                sub.questions,
                max_turns=3,
            )
        )

    assert result["terminated_without_completion"] is True
    assert result["return_summary"] == "[incomplete — max_turns reached]"
    assert result["turns"] == 3

    # Row updated to delivered with the incomplete marker.
    fetched = storage.get_sub_investigation(sub.id)
    assert fetched.state == m.SubInvestigationState.delivered
    assert fetched.return_summary == "[incomplete — max_turns reached]"


def test_log_source_consulted_carries_sub_investigation_id(fresh_db):
    """Inside a sub, log_source_consulted should stamp sub_investigation_id.

    Done via the CURRENT_SUB_INVESTIGATION_ID ContextVar + _inject_sub_id
    wrapper. The resulting investigation_log row must carry the sub id.
    """
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="attribution-test", questions=["Q?"]),
    )

    responses = [
        _Response(
            content=[
                _tool_use(
                    "log_source_consulted",
                    {
                        "citation": "https://example.com/source",
                        "why_consulted": "core question",
                        "what_learned": "a real fact",
                    },
                    id_="tu_log",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
        _Response(
            content=[
                _tool_use(
                    "complete_sub_investigation",
                    {
                        "return_summary": "Done.",
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                    id_="tu_complete",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
    ]

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id,
                sub.id,
                sub.scope,
                sub.questions,
                max_turns=10,
            )
        )

    entries = storage.list_investigation_log(
        dossier.id, entry_type=m.InvestigationLogEntryType.source_consulted
    )
    assert len(entries) == 1, f"expected 1 source_consulted entry, got {len(entries)}"
    assert entries[0].sub_investigation_id == sub.id


def test_contextvar_cleared_outside_sub(fresh_db):
    """After run_sub_investigation returns, CURRENT_SUB_INVESTIGATION_ID is None."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="ctx-clear", questions=[]),
    )

    responses = [
        _Response(
            content=[
                _tool_use(
                    "complete_sub_investigation",
                    {
                        "return_summary": "ctx-clear done",
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                    id_="tu_c",
                ),
            ],
            stop_reason="tool_use",
            usage=_Usage(),
        ),
    ]

    assert sub_runtime.CURRENT_SUB_INVESTIGATION_ID.get() is None

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client(responses),
    ):
        asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id, sub.id, sub.scope, sub.questions, max_turns=5,
            )
        )

    assert sub_runtime.CURRENT_SUB_INVESTIGATION_ID.get() is None


def test_prod_after_empty_turn_then_force_complete(fresh_db):
    """Empty model turns trigger a prod; after 2 prods we force-complete."""
    from vellum import models as m, storage
    from vellum.agent import sub_runtime

    dossier = _mk_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="keeps-prose-only", questions=[]),
    )

    # Three empty turns in a row. Two prods allowed; the third triggers
    # force-complete.
    empty_turn = _Response(
        content=[_text_block("I would like to continue thinking.")],
        stop_reason="end_turn",
        usage=_Usage(),
    )

    with patch(
        "vellum.agent.sub_runtime.anthropic.AsyncAnthropic",
        return_value=_make_mock_client([empty_turn, empty_turn, empty_turn]),
    ):
        result = asyncio.run(
            sub_runtime.run_sub_investigation(
                dossier.id, sub.id, sub.scope, sub.questions, max_turns=10,
            )
        )

    assert result["terminated_without_completion"] is True
    assert "[incomplete" in result["return_summary"]
