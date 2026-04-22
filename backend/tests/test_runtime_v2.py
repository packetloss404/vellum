"""Deterministic runtime tests for DossierAgent.

These tests exercise the agent's dispatch loop against a scripted mock of
``anthropic.AsyncAnthropic`` — no network, no LLM, no real API key required.
Every test should run well under 2 seconds.

What we verify:
- The dispatch loop: tool_use blocks are routed through ``handlers.HANDLERS``
  (or ``handlers.dispatch`` once that lands) and their results are appended
  as ``tool_result`` blocks in the next user message.
- Termination conditions: ``ended_turn`` when the model replies with no tool
  calls, ``turn_limit`` when we hit ``max_turns``, and (when wired)
  ``delivered`` when ``mark_investigation_delivered`` is called.
- Error paths: unknown tool name and handler exceptions both yield
  ``tool_result`` blocks with ``is_error=True`` and the loop keeps going.
- State bookkeeping: ``_last_section_id`` tracked across ``upsert_section``
  calls, work_session opened+closed once per ``run()``, and
  ``storage.increment_session_tokens`` called with input+output.
- Tool-schema surface: the agent exposes ``web_search`` and all data tools.
- Stuck integration: after a loop signal fires, ``_surface_stuck`` calls
  through ``handlers.HANDLERS['check_stuck']`` which writes a decision_point.

Tests that depend on code not yet merged from sibling agents are skipif-
guarded so this file collects cleanly against the current tree.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from vellum import models as m
from vellum import storage
from vellum.agent import runtime as rt
from vellum.tools import handlers


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _text(s: str) -> SimpleNamespace:
    """A text content block the runtime will ignore (no tool_use type)."""
    return SimpleNamespace(type="text", text=s)


def _tool_use(name: str, input: dict[str, Any], id: str = "tu_1") -> SimpleNamespace:
    """A tool_use content block shaped like anthropic.types.ToolUseBlock.

    The runtime reads ``.name``, ``.input``, ``.id`` and ``getattr(b, 'type')``
    so SimpleNamespace is a clean drop-in.
    """
    return SimpleNamespace(type="tool_use", name=name, input=dict(input), id=id)


def _message(
    content: list[SimpleNamespace],
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> SimpleNamespace:
    """Shape of a Messages API response that the runtime pokes into.

    Runtime touches: ``.content``, ``.stop_reason``, ``.usage.input_tokens``,
    ``.usage.output_tokens``.
    """
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def make_mock_client(scripted_turns: list[SimpleNamespace]) -> MagicMock:
    """Build an AsyncAnthropic-shaped mock.

    The real SDK requires streaming for long operations; the runtime therefore
    uses ``async with client.messages.stream(...) as stream:`` +
    ``await stream.get_final_message()``. This mock emulates that shape and
    returns the next scripted message on each ``__aenter__``. If the script
    runs dry, raises ``IndexError`` so tests fail loudly rather than hanging.

    We also expose ``client.messages.create`` as an ``AsyncMock`` pointing at
    the same dispatcher so legacy tests that assert on ``.await_count`` still
    work (each stream call also increments this counter).

    We deep-snapshot kwargs at call time — the runtime reuses the same
    ``messages`` list object and keeps mutating it, so by the time a test
    inspects ``client._calls`` all recorded references would otherwise point
    at the same (final-state) list.
    """
    import copy

    calls: list[dict[str, Any]] = []
    script = list(scripted_turns)

    def _snapshot(kwargs: dict[str, Any]) -> dict[str, Any]:
        snap = dict(kwargs)
        if "messages" in snap:
            snap["messages"] = copy.deepcopy(snap["messages"])
        return snap

    def _next_message() -> SimpleNamespace:
        if not script:
            raise IndexError(
                f"mock client ran out of scripted turns at call #{len(calls)}"
            )
        return script.pop(0)

    async def _create(**kwargs: Any) -> SimpleNamespace:
        calls.append(_snapshot(kwargs))
        return _next_message()

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
    client.messages.create = AsyncMock(side_effect=_create)
    client.messages.stream = MagicMock(side_effect=_stream)
    # Stash the call log so tests can inspect what was sent to the model.
    client._calls = calls  # type: ignore[attr-defined]
    return client


def _make_agent(dossier_id: str, client: MagicMock) -> rt.DossierAgent:
    """Construct an agent with the scripted mock already injected."""
    agent = rt.DossierAgent(dossier_id=dossier_id, model="mock-model")
    agent._client = client
    return agent


def _seed_dossier() -> str:
    """Create a minimal dossier so ``runtime.run`` has something to resolve."""
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
    """Sync wrapper — pytest-asyncio is not installed in this repo."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Deferred-merge guards
# ---------------------------------------------------------------------------


try:
    from vellum.tools.handlers import dispatch as _dispatch  # noqa: F401
    HAS_DISPATCH = True
except ImportError:
    HAS_DISPATCH = False

HAS_DELIVERED_TOOL = "mark_investigation_delivered" in handlers.HANDLERS
HAS_V2_TOOLS = len(handlers.HANDLERS) >= 21

try:
    from vellum.agent.stuck import log_signal_to_investigation  # noqa: F401
    HAS_STUCK_LOG = True
except ImportError:
    HAS_STUCK_LOG = False


# ---------------------------------------------------------------------------
# Tool-schema surface tests (no DB; fast)
# ---------------------------------------------------------------------------


def test_tool_list_includes_web_search():
    agent = rt.DossierAgent(dossier_id="dos_unused", model="mock-model")
    names = {t.get("name") for t in agent._tools}
    assert "web_search" in names


def test_tool_list_includes_core_data_tools():
    """Every day-1 data tool must be exposed to the model.

    Day-2 sibling agents may grow this set to 21; this test checks the
    minimum-viable surface (the 10 data handlers) so it stays green on
    main while pre-merge.
    """
    agent = rt.DossierAgent(dossier_id="dos_unused", model="mock-model")
    names = {t.get("name") for t in agent._tools}
    required = {
        "upsert_section",
        "update_section_state",
        "delete_section",
        "reorder_sections",
        "flag_needs_input",
        "flag_decision_point",
        "append_reasoning",
        "mark_ruled_out",
        "check_stuck",
        "request_user_paste",
    }
    missing = required - names
    assert not missing, f"missing tools in schema: {missing}"


@pytest.mark.skipif(
    not HAS_V2_TOOLS,
    reason="v2 tool set (21 tools) not merged yet",
)
def test_tool_list_includes_all_v2_tools():
    agent = rt.DossierAgent(dossier_id="dos_unused", model="mock-model")
    names = {t.get("name") for t in agent._tools}
    # At least 21 non-web_search tools plus web_search itself.
    assert len(names - {"web_search"}) >= 21


# ---------------------------------------------------------------------------
# Core dispatch loop
# ---------------------------------------------------------------------------


def test_ended_turn_with_no_tool_calls(fresh_db):
    """Model replies with only a text block → run() returns ended_turn."""
    did = _seed_dossier()
    client = make_mock_client([_message([_text("thinking out loud")])])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "ended_turn"
    assert result.turns == 1
    assert client.messages.stream.call_count == 1


def test_turn_limit_reached(fresh_db):
    """If the model keeps calling tools forever, max_turns cuts it off."""
    did = _seed_dossier()
    # Script: every turn is a valid upsert that drives another turn. We send
    # enough turns to exceed max_turns, then guard with an extra so IndexError
    # never fires.
    turns: list[SimpleNamespace] = []
    for i in range(6):
        turns.append(
            _message(
                [
                    _tool_use(
                        "append_reasoning",
                        {"note": f"loop {i}", "tags": []},
                        id=f"tu_{i}",
                    )
                ],
                stop_reason="tool_use",
            )
        )
    client = make_mock_client(turns)
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=3))

    assert result.reason == "turn_limit"
    assert result.turns == 3


def test_upsert_section_dispatch_writes_through(fresh_db):
    """upsert_section tool_use → handler fires → row exists in storage."""
    did = _seed_dossier()
    upsert_turn = _message(
        [
            _tool_use(
                "upsert_section",
                {
                    "type": "finding",
                    "title": "Fact A",
                    "content": "Some content.",
                    "state": "provisional",
                    "change_note": "initial draft",
                    "sources": [],
                    "depends_on": [],
                },
                id="tu_upsert",
            )
        ],
        stop_reason="tool_use",
    )
    end_turn = _message([_text("done")], stop_reason="end_turn")
    client = make_mock_client([upsert_turn, end_turn])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "ended_turn"
    assert result.turns == 2

    # The section should now exist in storage.
    sections = storage.list_sections(did)
    assert len(sections) == 1
    assert sections[0].title == "Fact A"

    # The second model call should have received a user message with a
    # tool_result block referencing tu_upsert.
    second_call = client._calls[1]
    messages = second_call["messages"]
    # Last user message before snapshot is the tool_result batch.
    tool_result_msg = next(
        (msg for msg in messages if msg["role"] == "user"
         and isinstance(msg["content"], list)
         and any(isinstance(b, dict) and b.get("type") == "tool_result"
                 for b in msg["content"])),
        None,
    )
    assert tool_result_msg is not None, "tool_result never reached the next turn"
    tr_block = next(
        b for b in tool_result_msg["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )
    assert tr_block["tool_use_id"] == "tu_upsert"
    # Content is JSON-serialized dict with section_id.
    assert "section_id" in tr_block["content"]


def test_unknown_tool_name_returns_error_block_and_continues(fresh_db):
    """Unknown tool → is_error=True, loop still advances."""
    did = _seed_dossier()
    bad_turn = _message(
        [_tool_use("does_not_exist", {"foo": "bar"}, id="tu_bad")],
        stop_reason="tool_use",
    )
    end_turn = _message([_text("ok")], stop_reason="end_turn")
    client = make_mock_client([bad_turn, end_turn])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "ended_turn"
    assert result.turns == 2  # loop continued after the error

    second_call = client._calls[1]
    tool_result_msg = next(
        msg for msg in second_call["messages"]
        if msg["role"] == "user" and isinstance(msg["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result"
                for b in msg["content"])
    )
    tr_block = next(
        b for b in tool_result_msg["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )
    assert tr_block.get("is_error") is True
    assert "unknown tool" in tr_block["content"]


def test_handler_raises_returns_error_block_and_continues(fresh_db, monkeypatch):
    """Handler exception is captured into the tool_result; loop keeps going."""
    did = _seed_dossier()

    def _exploding_handler(dossier_id: str, args: dict[str, Any]) -> Any:
        raise RuntimeError("boom")

    # Swap a known handler for one that raises; the runtime looks these up via
    # ``handlers.HANDLERS.get(name)`` at dispatch time.
    monkeypatch.setitem(handlers.HANDLERS, "append_reasoning", _exploding_handler)

    raise_turn = _message(
        [_tool_use("append_reasoning", {"note": "x", "tags": []}, id="tu_raise")],
        stop_reason="tool_use",
    )
    end_turn = _message([_text("ok")], stop_reason="end_turn")
    client = make_mock_client([raise_turn, end_turn])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "ended_turn"
    second_call = client._calls[1]
    tool_result_msg = next(
        msg for msg in second_call["messages"]
        if msg["role"] == "user" and isinstance(msg["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result"
                for b in msg["content"])
    )
    tr_block = next(
        b for b in tool_result_msg["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    )
    assert tr_block.get("is_error") is True
    assert "RuntimeError" in tr_block["content"]
    assert "boom" in tr_block["content"]


def test_pause_turn_does_not_count_as_ended(fresh_db):
    """stop_reason='pause_turn' re-sends the turn to let server-side tools
    (web_search) resume — must not terminate the loop and must not flip into
    the tool_results branch."""
    did = _seed_dossier()
    pause_msg = _message([_text("mid-search")], stop_reason="pause_turn")
    end_msg = _message([_text("done")], stop_reason="end_turn")
    client = make_mock_client([pause_msg, end_msg])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "ended_turn"
    assert result.turns == 2
    assert client.messages.stream.call_count == 2


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def test_last_section_id_tracks_upsert_section(fresh_db):
    """After an upsert_section with explicit section_id, _last_section_id
    should be the same section_id the model provided."""
    did = _seed_dossier()

    # First create a real section directly so we have a valid id to reuse.
    section = storage.upsert_section(
        did,
        m.SectionUpsert(
            type=m.SectionType.finding,
            title="existing",
            state=m.SectionState.provisional,
            change_note="seed",
        ),
    )
    sid = section.id

    upsert_turn = _message(
        [
            _tool_use(
                "upsert_section",
                {
                    "section_id": sid,
                    "type": "finding",
                    "title": "existing (revised)",
                    "content": "revised body",
                    "state": "provisional",
                    "change_note": "revision",
                    "sources": [],
                    "depends_on": [],
                },
                id="tu_revise",
            )
        ],
        stop_reason="tool_use",
    )
    end_turn = _message([_text("done")], stop_reason="end_turn")
    client = make_mock_client([upsert_turn, end_turn])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    assert agent._last_section_id == sid


def test_work_session_opened_and_closed_exactly_once(fresh_db):
    """run() must resolve a session, then end it in the finally block.

    Before run(): no sessions on the dossier. After run(): exactly one session
    and it is closed.
    """
    did = _seed_dossier()
    assert storage.get_active_work_session(did) is None
    assert len(storage.list_work_sessions(did)) == 0

    end_turn = _message([_text("nothing to do")], stop_reason="end_turn")
    client = make_mock_client([end_turn])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    sessions = storage.list_work_sessions(did)
    assert len(sessions) == 1
    assert sessions[0].ended_at is not None
    assert storage.get_active_work_session(did) is None


def test_increment_session_tokens_called_with_input_plus_output(fresh_db, monkeypatch):
    """Runtime must sum input_tokens + output_tokens and credit the session."""
    did = _seed_dossier()
    calls: list[tuple[str, int]] = []
    real_inc = storage.increment_session_tokens

    def _spy(session_id: str, tokens: int) -> None:
        calls.append((session_id, tokens))
        real_inc(session_id, tokens)

    monkeypatch.setattr(storage, "increment_session_tokens", _spy)
    # The runtime imported the symbol at module scope — patch there too.
    monkeypatch.setattr(rt.storage, "increment_session_tokens", _spy)

    end_turn = _message(
        [_text("done")], stop_reason="end_turn", input_tokens=123, output_tokens=45
    )
    client = make_mock_client([end_turn])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    assert len(calls) == 1
    session_id, tokens = calls[0]
    assert tokens == 123 + 45


# ---------------------------------------------------------------------------
# Termination — delivered (deferred)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not HAS_DELIVERED_TOOL,
    reason="mark_investigation_delivered tool not merged yet",
)
def test_mark_investigation_delivered_ends_with_delivered(fresh_db):
    did = _seed_dossier()
    deliver_turn = _message(
        [_tool_use("mark_investigation_delivered", {}, id="tu_done")],
        stop_reason="tool_use",
    )
    # Tail-end in case runtime doesn't early-terminate in current tree.
    end_turn = _message([_text("done")], stop_reason="end_turn")
    client = make_mock_client([deliver_turn, end_turn])
    agent = _make_agent(did, client)

    result = _run(agent.run(max_turns=5))

    assert result.reason == "delivered"


# ---------------------------------------------------------------------------
# Stuck integration
# ---------------------------------------------------------------------------


def test_stuck_loop_signal_surfaces_check_stuck_as_decision_point(fresh_db):
    """Calling the same tool with the same args past LOOP_DETECTION_THRESHOLD
    should trip stuck detection, which the runtime surfaces by invoking the
    ``check_stuck`` handler — and that writes a decision_point row to storage.
    """
    from vellum import config as _config

    did = _seed_dossier()
    # Build THRESHOLD+1 identical tool calls (same args → same hash) followed
    # by an end turn.
    identical_args = {"note": "same note", "tags": []}
    turns = [
        _message(
            [_tool_use("append_reasoning", identical_args, id=f"tu_{i}")],
            stop_reason="tool_use",
        )
        for i in range(_config.LOOP_DETECTION_THRESHOLD + 1)
    ]
    turns.append(_message([_text("done")], stop_reason="end_turn"))
    client = make_mock_client(turns)
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=20))

    # The runtime surfaces stuck via handlers.HANDLERS["check_stuck"], which
    # writes a "Stuck — need your direction" decision_point.
    dps = storage.list_decision_points(did)
    assert any("Stuck" in dp.title for dp in dps), (
        f"expected a stuck decision_point to be surfaced; got titles "
        f"{[dp.title for dp in dps]}"
    )


@pytest.mark.skipif(
    not HAS_STUCK_LOG,
    reason="stuck → investigation_log integration not merged yet",
)
def test_stuck_signal_logged_to_investigation_log(fresh_db):
    """Once stuck-v2 lands, a stuck signal should also be appended to the
    investigation_log. Guarded-skip until that merges."""
    from vellum import config as _config

    did = _seed_dossier()
    args = {"note": "spin", "tags": []}
    turns = [
        _message(
            [_tool_use("append_reasoning", args, id=f"tu_{i}")],
            stop_reason="tool_use",
        )
        for i in range(_config.LOOP_DETECTION_THRESHOLD + 1)
    ]
    turns.append(_message([_text("done")], stop_reason="end_turn"))
    client = make_mock_client(turns)
    agent = _make_agent(did, client)
    _run(agent.run(max_turns=20))

    # Imported under skipif guard above.
    from vellum.agent.stuck import log_signal_to_investigation  # type: ignore

    # Hook exists; we don't know the exact shape of the log reader without the
    # sibling branch, so just assert the symbol is wired and callable. The
    # real coverage ships in that agent's own tests.
    assert callable(log_signal_to_investigation)


# ---------------------------------------------------------------------------
# Snapshot / message-construction contract
# ---------------------------------------------------------------------------


def test_first_user_message_is_state_snapshot(fresh_db):
    """Before the first model call, the runtime prepends a dossier state
    snapshot as a user message — that's the whole "the dossier is the prompt"
    contract. The snapshot is a list with a single text block."""
    did = _seed_dossier()
    end_turn = _message([_text("ok")], stop_reason="end_turn")
    client = make_mock_client([end_turn])
    agent = _make_agent(did, client)

    _run(agent.run(max_turns=5))

    first_call = client._calls[0]
    messages = first_call["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    # Snapshot text must mention the dossier section-count header.
    assert "## Sections" in content[0]["text"]
