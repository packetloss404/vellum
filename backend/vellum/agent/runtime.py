"""Vellum agent runtime.

SDK choice: the direct ``anthropic`` SDK's Messages API with a manual
agentic loop, not ``claude-agent-sdk``.

Rationale: ``claude-agent-sdk`` is built around Claude Code's shape — a
default Read/Write/Edit/Bash toolset, MCP-wrapped custom tools, permission
modes, and a global system prompt. Our shape is different: a closed set
of 10 Pydantic-derived dossier tools whose schemas already come from
``handlers.tool_schemas()`` in Anthropic tool-definition format; a
``dossier_id`` that must be injected server-side and never exposed to the
model; a per-turn "dossier state snapshot" prepended to each user
message; Anthropic's built-in ``web_search`` server tool; and
after-each-tool-call hooks into the stuck-detection subsystem. The direct
Messages API maps 1:1 to this; the Agent SDK would add MCP-wrapping
friction and make per-turn state injection awkward.

The agent never emits prose to the user. All user-visible content flows
through dossier tool calls into ``storage``; if a turn ends with prose
and no tool calls, the prose is discarded.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from .. import models as m
from .. import storage
from ..config import ANTHROPIC_API_KEY, MODEL
from ..tools import handlers


# Anthropic's built-in server-side web search tool. Versioned type string —
# the agent issues queries, Anthropic fetches + returns results with citations.
_WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
}


@dataclass
class RunResult:
    reason: str  # "ended_turn" | "turn_limit" | "stuck" | "error" | "delivered"
    turns: int
    session_id: str
    stuck_signal: Optional[Any] = None  # vellum.agent.stuck.StuckSignal
    error: Optional[str] = None


@dataclass
class _LoopState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0


class DossierAgent:
    """Drives one work session of durable thinking on a single dossier.

    The runtime:
      1. resolves or opens a work_session for ``dossier_id``;
      2. builds a system prompt once from the dossier;
      3. for each turn, prepends a fresh dossier state snapshot to the
         outgoing user message, calls the model, dispatches any tool
         calls through ``handlers.HANDLERS`` with ``dossier_id``
         injected, runs stuck detection after each call, appends tool
         results, and loops until the model ends the turn;
      4. ends the work_session and returns a ``RunResult``.
    """

    def __init__(self, dossier_id: str, model: Optional[str] = None) -> None:
        self.dossier_id = dossier_id
        self.model = model or MODEL
        self._client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY or None)
        self._tools = self._build_tool_definitions()
        self._last_section_id: Optional[str] = None

    @staticmethod
    def _build_tool_definitions() -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = list(handlers.tool_schemas())
        tools.append(_WEB_SEARCH_TOOL)
        return tools

    async def run(self, max_turns: int = 200) -> RunResult:
        # Defer sibling imports so partial/in-progress modules don't block
        # import of runtime itself during parallel development.
        from . import prompt as prompt_mod
        from . import stuck as stuck_mod

        session_id = self._resolve_session()
        state = _LoopState()

        dossier = storage.get_dossier(self.dossier_id)
        if dossier is None:
            storage.end_work_session(session_id)
            return RunResult(
                reason="error",
                turns=0,
                session_id=session_id,
                error=f"dossier {self.dossier_id} not found",
            )

        system_prompt = prompt_mod.build_system_prompt(dossier)

        # Kick off with a state snapshot as the first user message. The model
        # has no other user input on a resume — the dossier is the prompt.
        state.messages.append(
            {"role": "user", "content": self._snapshot_content(prompt_mod)}
        )

        try:
            while state.turns < max_turns:
                state.turns += 1

                # anthropic SDK requires streaming for operations that may
                # exceed 10 minutes. With max_tokens=32000 + web_search the
                # SDK guards against the non-streaming path. Use the stream
                # context manager and aggregate via `get_final_message`.
                async with self._client.messages.stream(
                    model=self.model,
                    max_tokens=32000,
                    system=system_prompt,
                    tools=self._tools,
                    messages=state.messages,
                ) as stream:
                    response = await stream.get_final_message()

                if response.usage is not None:
                    input_tokens = response.usage.input_tokens or 0
                    output_tokens = response.usage.output_tokens or 0
                    storage.increment_session_tokens(
                        session_id, input_tokens + output_tokens
                    )
                    # stuck-detection needs per-turn input tokens for session-
                    # and section-budget signals. Attribute to the section most
                    # recently upserted this session (if any); otherwise None.
                    stuck_mod.record_input_tokens(
                        session_id, self._last_section_id, input_tokens
                    )

                state.messages.append(
                    {"role": "assistant", "content": response.content}
                )

                # Server-side tool (web_search) hit its per-turn iteration
                # cap; re-send to let Anthropic resume where it paused.
                if response.stop_reason == "pause_turn":
                    continue

                tool_uses = [
                    b for b in response.content if getattr(b, "type", None) == "tool_use"
                ]

                if not tool_uses:
                    # Model ended the turn. Any prose is discarded — the agent
                    # speaks only through tool calls into the dossier.
                    return RunResult(
                        reason="ended_turn",
                        turns=state.turns,
                        session_id=session_id,
                    )

                tool_results: list[dict[str, Any]] = []
                stuck_signal = None
                delivered = False

                for tu in tool_uses:
                    tool_name = tu.name
                    tool_input = dict(tu.input) if tu.input else {}

                    # web_search is server-side; results are already in
                    # response.content. Skip client-side dispatch for it.
                    if tool_name == "web_search":
                        continue

                    result_block = await self._dispatch_client_tool(
                        tool_name, tool_input, tu.id
                    )
                    tool_results.append(result_block)

                    # Track which section the agent is working on, so
                    # record_input_tokens can attribute budget pressure to it.
                    # after_section_id is the *preceding* anchor, not the
                    # section being edited — don't use it as a fallback.
                    if tool_name == "upsert_section":
                        sid = tool_input.get("section_id")
                        if sid:
                            self._last_section_id = sid

                    # Terminal tool: the agent signals the investigation is
                    # handed off to the user. We still let any remaining
                    # tool_uses in this same turn dispatch (so their results
                    # are appended and the message shape stays valid), then
                    # break out of the loop after appending tool_results.
                    if tool_name == "mark_investigation_delivered":
                        delivered = True

                    # After each dossier mutation, let stuck detection look
                    # at the sequence. First returned signal wins.
                    if stuck_signal is None:
                        stuck_signal = stuck_mod.record_tool_call(
                            session_id, tool_name, tool_input
                        )

                if tool_results:
                    state.messages.append({"role": "user", "content": tool_results})

                if delivered:
                    return RunResult(
                        reason="delivered",
                        turns=state.turns,
                        session_id=session_id,
                    )

                # Post-turn budget / revision-stall check, independent of
                # record_tool_call's per-call looping check.
                if stuck_signal is None:
                    stuck_signal = stuck_mod.check_stuck_state(
                        self.dossier_id, session_id
                    )

                if stuck_signal is not None:
                    # Surface the signal as a decision_point, but do NOT
                    # terminate the loop — per stuck.py and the product
                    # memory, we detect and report, we never cut the agent
                    # off mid-thought. The agent's next state snapshot will
                    # include the new decision_point; the system prompt's
                    # "Stop when stuck" section instructs it to pause
                    # voluntarily. max_turns remains the backstop if the
                    # agent fails to self-regulate. Each stuck condition
                    # is deduped inside stuck.py's *_reported sets, so the
                    # runtime will not re-surface the same signal on a
                    # subsequent turn.
                    self._surface_stuck(stuck_signal)

                # Refresh the snapshot for the next turn by appending a
                # synthetic user message after tool results. This keeps
                # the agent's view of the dossier current without
                # rewriting earlier messages (which would bust the cache).
                state.messages.append(
                    {"role": "user", "content": self._snapshot_content(prompt_mod)}
                )

            return RunResult(
                reason="turn_limit", turns=state.turns, session_id=session_id
            )

        except Exception as exc:  # noqa: BLE001 — we promise not to re-raise
            return RunResult(
                reason="error",
                turns=state.turns,
                session_id=session_id,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            storage.end_work_session(session_id)
            try:
                stuck_mod.reset_session(session_id)
            except Exception:  # noqa: BLE001 — cleanup must not mask result
                pass

    def _resolve_session(self) -> str:
        existing = storage.get_active_work_session(self.dossier_id)
        if existing is not None:
            return existing.id
        return storage.start_work_session(
            self.dossier_id, m.WorkSessionTrigger.resume
        ).id

    def _snapshot_content(self, prompt_mod: Any) -> list[dict[str, Any]]:
        dossier_full = storage.get_dossier_full(self.dossier_id)
        snapshot_text = prompt_mod.build_state_snapshot(dossier_full)
        return [{"type": "text", "text": snapshot_text}]

    async def _dispatch_client_tool(
        self, tool_name: str, tool_input: dict[str, Any], tool_use_id: str
    ) -> dict[str, Any]:
        if (
            tool_name not in handlers.HANDLERS
            and tool_name not in handlers.HANDLER_OVERRIDES
        ):
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"unknown tool: {tool_name}",
                "is_error": True,
            }

        try:
            # Handlers are sync; run them off the event loop so a slow write
            # doesn't stall concurrent agents. Route through handlers.dispatch
            # so HANDLER_OVERRIDES and TOOL_HOOKS apply.
            result = await asyncio.to_thread(
                handlers.dispatch, self.dossier_id, tool_name, tool_input
            )
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": _coerce_tool_result(result),
            }
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't kill the loop
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"{type(exc).__name__}: {exc}",
                "is_error": True,
            }

    def _surface_stuck(self, signal: Any) -> None:
        """Convert a StuckSignal into a check_stuck tool invocation.

        The stuck signal originated in the runtime, not the model, but the
        user-facing surface still needs to be a decision_point — so we
        route through the same handler the model would have called.
        """
        summary = (
            getattr(signal, "summary_of_attempts", None)
            or getattr(signal, "detail", None)
            or "Agent detected a stuck pattern."
        )
        options = getattr(signal, "options_for_user", None) or [
            {"label": "Let the agent keep going", "implications": "", "recommended": False},
            {"label": "Pause for your direction", "implications": "", "recommended": True},
        ]
        try:
            handlers.HANDLERS["check_stuck"](
                self.dossier_id,
                {"summary_of_attempts": summary, "options_for_user": options},
            )
        except Exception:  # noqa: BLE001 — a failed stuck surface must not mask the signal
            pass


def _coerce_tool_result(result: Any) -> str:
    """Handlers return compact dicts; the API wants string or block content."""
    import json

    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


if __name__ == "__main__":
    # Structural smoke test: construct the agent and confirm RunResult is
    # importable. Running .run() requires a live API key + real dossier.
    from vellum.agent import runtime as _rt

    agent = _rt.DossierAgent(dossier_id="fake_id_wont_exist")
    assert agent.dossier_id == "fake_id_wont_exist"
    assert agent.model  # falls back to config.MODEL
    assert _rt.RunResult is not None
    assert any(t.get("name") == "upsert_section" for t in agent._tools)
    assert any(t.get("name") == "web_search" for t in agent._tools)
    print("structural OK")
