"""Vellum intake agent runtime.

SDK choice: the direct ``anthropic`` SDK's Messages API with a manual
tool-use loop — same as ``vellum.agent.runtime``. We deliberately do NOT
use ``claude-agent-sdk``: intake has a closed 7-tool surface whose
schemas already come from ``intake.tools.tool_schemas()`` in Anthropic
format, and the ``intake_id`` must be injected server-side and never
exposed to the model. The direct Messages API maps 1:1 to that shape.

CRITICAL difference from the dossier agent:
  * Intake DOES speak to the user in prose. The final text content of
    each turn IS the user-facing reply, returned in
    ``IntakeTurnResult.assistant_message`` and persisted as an
    ``assistant`` message in the intake transcript.
  * No per-turn dossier state snapshot — messages are short and the
    gathered-so-far block is surfaced via the system prompt.
  * No stuck detection — intake conversations are bounded to ~10 turns
    of internal tool-use iteration per user turn.
  * No work_sessions — the intake_session itself is the unit.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import anthropic

from ..config import ANTHROPIC_API_KEY, MODEL
from . import storage
from .models import IntakeState, IntakeStatus, IntakeTurnResult


# Hard cap on how many internal model<->tool iterations we'll run in a
# single user turn. Intake turns are short: a typical turn is one
# ``update_intake_field`` call followed by an end_turn with the next
# question, or an end_turn with only prose. 10 is generous headroom for
# pathological cases; exceeding it short-circuits to a safe reply.
INTERNAL_MAX_ITERATIONS = 10


class IntakeAgent:
    """Drives a single user turn of the intake conversation.

    One instance handles one user message -> one assistant reply. The
    runtime:
      1. persists the inbound user message;
      2. rebuilds the Anthropic messages array from the full transcript;
      3. rebuilds the system prompt from the *current* intake state
         (so the gathered-so-far block reflects any prior-turn updates);
      4. runs the tool-use loop until the model ends the turn or we hit
         ``INTERNAL_MAX_ITERATIONS``;
      5. persists the assistant text and returns a fresh state snapshot.
    """

    def __init__(self, intake_id: str, model: Optional[str] = None) -> None:
        self.intake_id = intake_id
        self.model = model or MODEL
        self._client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY or None)

    async def process_turn(self, user_message: str) -> IntakeTurnResult:
        """One user turn -> one assistant reply.

        On any exception we return an ``IntakeTurnResult`` with the
        current status/state and ``error`` populated; we never re-raise.
        """
        # Defer sibling imports so partial/in-progress modules don't
        # block import of runtime itself during parallel development
        # (mirrors the dossier runtime's pattern).
        from . import prompt as prompt_mod
        from . import tools as tools_mod

        # Snapshot the current state up-front so the exception branch has
        # something sane to report if we blow up before the final refetch.
        current_status = IntakeStatus.gathering
        current_state = IntakeState()
        try:
            pre = storage.get_intake(self.intake_id)
            if pre is not None:
                current_status = pre.status
                current_state = pre.state
        except Exception:  # noqa: BLE001 — best-effort snapshot
            pass

        try:
            # 1. Persist the user message first so it shows up in the
            #    transcript we're about to load.
            storage.append_intake_message(self.intake_id, "user", user_message)

            # 2. Load the full transcript and build the Anthropic messages
            #    array. We send role + content only; IDs and timestamps
            #    are ours, not the model's.
            session = storage.get_intake(self.intake_id)
            if session is None:
                return IntakeTurnResult(
                    intake_status=current_status,
                    state=current_state,
                    assistant_message="",
                    error=f"KeyError: intake session {self.intake_id} not found",
                )

            current_status = session.status
            current_state = session.state

            messages: list[dict[str, Any]] = [
                {"role": msg.role, "content": msg.content}
                for msg in session.messages
            ]

            # 3. System prompt is rebuilt from the *current* state so the
            #    gathered-so-far block reflects reality on every turn.
            system_prompt = prompt_mod.build_system_prompt(session.state)
            tool_defs = tools_mod.tool_schemas()

            # 4. Tool-use loop. Accumulates user-facing prose across any
            #    text blocks emitted before end_turn.
            assistant_message_parts: list[str] = []
            iterations = 0
            truncated_by_cap = False

            while iterations < INTERNAL_MAX_ITERATIONS:
                iterations += 1

                response = await self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=tool_defs,
                    messages=messages,
                )

                # Mirror the assistant turn back into the history so the
                # next create() sees a well-formed tool_use/tool_result
                # alternation.
                messages.append({"role": "assistant", "content": response.content})

                # Collect any text blocks this turn produced — they're
                # the user-facing reply regardless of whether the model
                # is about to call more tools (in practice the model
                # either speaks OR calls tools, but we accumulate
                # defensively in case it does both).
                for block in response.content:
                    if getattr(block, "type", None) == "text":
                        text = getattr(block, "text", "") or ""
                        if text:
                            assistant_message_parts.append(text)

                stop_reason = response.stop_reason

                if stop_reason == "end_turn":
                    break

                if stop_reason == "pause_turn":
                    # Server-tool pause — doesn't apply here (we only use
                    # client tools) but handle defensively: re-send the
                    # current transcript so Anthropic can resume.
                    continue

                if stop_reason == "tool_use":
                    tool_uses = [
                        b for b in response.content
                        if getattr(b, "type", None) == "tool_use"
                    ]
                    if not tool_uses:
                        # Stop reason said tool_use but no blocks — bail
                        # rather than spin.
                        break

                    tool_results = await self._dispatch_tools(tool_uses, tools_mod)
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Any other stop_reason (e.g. "max_tokens", "refusal",
                # "stop_sequence"): end the loop. We return whatever
                # prose we've accumulated — possibly empty.
                break
            else:
                # Loop exited by hitting INTERNAL_MAX_ITERATIONS without
                # a natural end_turn. Surface a safe fallback so the
                # user sees *something* rather than silence.
                truncated_by_cap = True

            assistant_message = "\n\n".join(
                p.strip() for p in assistant_message_parts if p.strip()
            )

            if not assistant_message:
                # Either the cap fired with no prose, or the model ended its
                # turn with tool calls only. Either way, the user sees
                # silence otherwise — give them a sensible reply.
                assistant_message = (
                    "I got tangled up working through that. Could you say "
                    "that again, or rephrase what you're after?"
                    if truncated_by_cap
                    else "Got that — anything else to add, or want me to open the dossier?"
                )

            # 6. Persist the assistant reply. Even empty replies are
            #    persisted as empty strings only if we actually have
            #    something to say; otherwise skip to avoid polluting
            #    the transcript with blanks.
            if assistant_message:
                storage.append_intake_message(
                    self.intake_id, "assistant", assistant_message
                )

            # 7. Refetch — status and dossier_id may have changed
            #    mid-turn if commit_intake/abandon_intake fired.
            fresh = storage.get_intake(self.intake_id)
            if fresh is None:
                return IntakeTurnResult(
                    intake_status=current_status,
                    state=current_state,
                    assistant_message=assistant_message,
                    error="KeyError: intake disappeared after turn",
                )

            return IntakeTurnResult(
                intake_status=fresh.status,
                state=fresh.state,
                assistant_message=assistant_message,
                dossier_id=fresh.dossier_id,
            )

        except Exception as exc:  # noqa: BLE001 — we promise not to re-raise
            return IntakeTurnResult(
                intake_status=current_status,
                state=current_state,
                assistant_message="",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _dispatch_tools(
        self,
        tool_uses: list[Any],
        tools_mod: Any,
    ) -> list[dict[str, Any]]:
        """Dispatch each tool_use block through ``HANDLERS`` and return
        a list of ``tool_result`` content blocks, in order.

        Handlers are sync; run them off the event loop so a slow write
        doesn't stall concurrent intake agents. On handler exception,
        surface the error to the model via ``is_error=True`` rather than
        killing the loop — the model can recover (e.g. retry with a
        corrected arg).
        """
        results: list[dict[str, Any]] = []
        for tu in tool_uses:
            name = tu.name
            args = dict(tu.input) if tu.input else {}
            use_id = tu.id

            handler = tools_mod.HANDLERS.get(name)
            if handler is None:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": f"unknown tool: {name}",
                    "is_error": True,
                })
                continue

            try:
                result = await asyncio.to_thread(handler, self.intake_id, args)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": _coerce_tool_result(result),
                })
            except Exception as exc:  # noqa: BLE001 — surface, don't kill the loop
                results.append({
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": f"{type(exc).__name__}: {exc}",
                    "is_error": True,
                })
        return results


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
    # Structural smoke test only — no API call, no DB dependency on the
    # runtime module itself. Exercising process_turn() requires a live
    # API key, an initialized DB, and a real intake session.
    from vellum.intake import runtime as _rt
    from vellum.intake.models import IntakeTurnResult as _Result

    agent = _rt.IntakeAgent(intake_id="fake")
    assert agent.intake_id == "fake"
    assert agent.model  # falls back to config.MODEL
    assert _Result is not None
    print("intake runtime structural OK")
