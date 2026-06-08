"""Tests for prompt caching (Change A) and context editing (Change B).

Covers:
    - system param is a list with cache_control on the text block
    - tools param last element has cache_control
    - cache token counts from a mocked usage block flow into cost_usd_for_turn
    - context_management block is included when threshold > 0
    - context_management block is omitted when threshold == 0
    - sub_runtime also applies cache_control on system and tools
"""
from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from vellum import models as m
from vellum import storage
from vellum.agent import runtime as rt
from vellum.agent import sub_runtime
from vellum.config import cost_usd_for_turn


# ---------------------------------------------------------------------------
# Mock helpers (mirrors test_runtime_v2.py patterns)
# ---------------------------------------------------------------------------


def _text(s: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=s)


def _tool_use(name: str, input: dict[str, Any], id: str = "tu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=dict(input), id=id)


def _message(
    content: list[SimpleNamespace],
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def make_mock_client(scripted_turns: list[SimpleNamespace]) -> MagicMock:
    import copy as _copy

    calls: list[dict[str, Any]] = []
    script = list(scripted_turns)

    def _snapshot(kwargs: dict[str, Any]) -> dict[str, Any]:
        snap = dict(kwargs)
        if "messages" in snap:
            snap["messages"] = _copy.deepcopy(snap["messages"])
        return snap

    def _next_message() -> SimpleNamespace:
        if not script:
            raise IndexError("mock client ran out of scripted turns")
        return script.pop(0)

    def _stream(**kwargs: Any) -> Any:
        calls.append(_snapshot(kwargs))
        msg = _next_message()

        class _StreamCM:
            async def __aenter__(self):
                class _Stream:
                    async def get_final_message(self_inner):
                        return msg
                return _Stream()

            async def __aexit__(self, *exc):
                return False

        return _StreamCM()

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=_stream)
    client._calls = calls
    return client


def _make_agent(dossier_id: str, client: MagicMock) -> rt.DossierAgent:
    agent = rt.DossierAgent(dossier_id=dossier_id, model="claude-opus-4-7")
    agent._client = client
    return agent


def _seed_dossier() -> str:
    dossier = storage.create_dossier(
        m.DossierCreate(
            title="t",
            problem_statement="p",
            out_of_scope=[],
            dossier_type=m.DossierType.investigation,
        )
    )
    return dossier.id


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Change A: Prompt caching on system + tools
# ---------------------------------------------------------------------------


def test_system_param_has_cache_control(fresh_db):
    """The system param passed to stream() must be a list with one
    text block carrying cache_control: {type: ephemeral}."""
    did = _seed_dossier()
    client = make_mock_client([_message([_text("done")])])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    first_call = client._calls[0]
    system = first_call["system"]
    assert isinstance(system, list), f"system must be a list, got {type(system)}"
    assert len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block.get("cache_control") == {"type": "ephemeral"}


def test_last_tool_has_cache_control(fresh_db):
    """The last element of the tools list must carry cache_control."""
    did = _seed_dossier()
    client = make_mock_client([_message([_text("done")])])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    first_call = client._calls[0]
    tools = first_call["tools"]
    assert isinstance(tools, list)
    assert len(tools) > 0
    last_tool = tools[-1]
    assert last_tool.get("cache_control") == {"type": "ephemeral"}, (
        f"last tool missing cache_control; got keys {list(last_tool.keys())}"
    )
    # Only the last tool should have cache_control.
    tools_with_cc = [t for t in tools if "cache_control" in t]
    assert len(tools_with_cc) == 1, (
        f"expected exactly 1 tool with cache_control, got {len(tools_with_cc)}"
    )


def test_original_tools_list_not_mutated(fresh_db):
    """_tools_with_cache_breakpoint must not mutate the module-level list."""
    agent = rt.DossierAgent(dossier_id="unused", model="claude-opus-4-7")
    original_last = dict(agent._tools[-1])
    _ = rt._tools_with_cache_breakpoint(agent._tools)
    assert "cache_control" not in agent._tools[-1], (
        "module-level tools list was mutated"
    )
    assert agent._tools[-1] == original_last


def test_cache_tokens_flow_into_cost(fresh_db, monkeypatch):
    """Cache token counts from usage are passed to cost_usd_for_turn."""
    did = _seed_dossier()
    calls: list[dict[str, Any]] = []
    real_fn = cost_usd_for_turn

    def _spy(model, input_tokens, output_tokens, **kwargs):
        calls.append({"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, **kwargs})
        return real_fn(model, input_tokens, output_tokens, **kwargs)

    monkeypatch.setattr("vellum.agent.runtime.cost_usd_for_turn", _spy)

    client = make_mock_client([
        _message(
            [_text("done")],
            input_tokens=1000,
            output_tokens=200,
            cache_creation_input_tokens=5000,
            cache_read_input_tokens=50000,
        ),
    ])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    assert len(calls) == 1
    c = calls[0]
    assert c["input_tokens"] == 1000
    assert c["output_tokens"] == 200
    assert c["cache_creation_input_tokens"] == 5000
    assert c["cache_read_input_tokens"] == 50000


# ---------------------------------------------------------------------------
# Change A: Sub-runtime prompt caching
# ---------------------------------------------------------------------------


def test_sub_runtime_system_has_cache_control():
    """_cached_system_prompt is used in sub_runtime stream calls."""
    result = sub_runtime._cached_system_prompt("hello")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["cache_control"] == {"type": "ephemeral"}


def test_sub_runtime_tools_with_cache_breakpoint():
    """_tools_with_cache_breakpoint adds cache_control to last tool."""
    tools = [
        {"type": "custom", "name": "tool_a", "input_schema": {}},
        {"type": "custom", "name": "tool_b", "input_schema": {}},
    ]
    cached = sub_runtime._tools_with_cache_breakpoint(tools)
    assert len(cached) == 2
    assert "cache_control" not in cached[0]
    assert cached[-1]["cache_control"] == {"type": "ephemeral"}
    # Original not mutated
    assert "cache_control" not in tools[-1]


# ---------------------------------------------------------------------------
# Change B: Context editing
# ---------------------------------------------------------------------------


def test_context_management_included_when_threshold_positive(fresh_db, monkeypatch):
    """When CONTEXT_MANAGEMENT_THRESHOLD > 0, stream call should include
    extra_body with context_management."""
    monkeypatch.setattr("vellum.agent.runtime.CONTEXT_MANAGEMENT_THRESHOLD", 50000)

    did = _seed_dossier()
    client = make_mock_client([_message([_text("done")])])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    first_call = client._calls[0]
    assert "extra_body" in first_call
    cm = first_call["extra_body"]["context_management"]
    assert "edits" in cm
    edit = cm["edits"][0]
    assert edit["type"] == "clear_tool_uses_20250919"
    assert edit["trigger"]["type"] == "input_tokens"
    assert edit["trigger"]["value"] == 50000
    # web_search is NOT in exclude_tools (so it can be cleared)
    assert "web_search" not in edit["exclude_tools"]
    # Dossier tools ARE in exclude_tools (preserved from clearing)
    assert "upsert_section" in edit["exclude_tools"]


def test_context_management_omitted_when_threshold_zero(fresh_db, monkeypatch):
    """When CONTEXT_MANAGEMENT_THRESHOLD == 0, no extra_body is sent."""
    monkeypatch.setattr("vellum.agent.runtime.CONTEXT_MANAGEMENT_THRESHOLD", 0)

    did = _seed_dossier()
    client = make_mock_client([_message([_text("done")])])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    first_call = client._calls[0]
    assert "extra_body" not in first_call
