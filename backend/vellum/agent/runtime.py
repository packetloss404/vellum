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
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from .. import models as m
from .. import storage
from ..config import ANTHROPIC_API_KEY, MODEL, cost_usd_for_turn
from ..tools import handlers
from .compactor import _estimate_tokens as _compactor_estimate_tokens, compact_messages, should_compact


# Anthropic's built-in server-side web search tool. Versioned type string —
# the agent issues queries, Anthropic fetches + returns results with citations.
_WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
}

# Prompt caching: wrap the system prompt so Anthropic caches it across turns.
def _cached_system_prompt(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


# Add a cache breakpoint on the last tool so the tool definitions are cached.
# Returns a new list — the original is never mutated.
def _tools_with_cache_breakpoint(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not tools:
        return tools
    result = [dict(t) for t in tools]
    result[-1] = dict(result[-1])
    result[-1]["cache_control"] = {"type": "ephemeral"}
    return result


# Context management: clear tool_use blocks when input tokens exceed this
# threshold. Set to 0 to disable.  Monkeypatched in tests.
CONTEXT_MANAGEMENT_THRESHOLD: int = int(os.getenv("VELLUM_CONTEXT_MANAGEMENT_THRESHOLD", "180000"))

# Tools that write dossier state — these are preserved from context clearing
# so the model keeps its place even after a big prune.
_DOSSIER_WRITE_TOOLS: list[str] = [
    "upsert_section", "update_section_state", "delete_section", "reorder_sections",
    "flag_needs_input", "flag_decision_point", "append_reasoning", "mark_ruled_out",
    "update_investigation_plan", "update_debrief", "update_working_theory",
    "record_premise_challenge", "add_artifact", "update_artifact",
    "spawn_sub_investigation", "complete_sub_investigation", "update_sub_investigation",
    "log_source_consulted", "mark_considered_and_rejected", "set_next_action",
    "declare_stuck", "schedule_wake", "mark_investigation_delivered", "summarize_session",
]


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
        # Budget soft-signal dedup — each cap emits at most once per run.
        self._budget_daily_reported: bool = False
        self._budget_session_reported: bool = False

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
        # H-19: register the session so stuck can load/persist escalation count.
        stuck_mod.init_session(session_id, self.dossier_id)
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
        # Wrap in a list with cache_control so Anthropic caches the static
        # system text across turns (prompt caching, Change A).
        cached_system = _cached_system_prompt(system_prompt)
        cached_tools = _tools_with_cache_breakpoint(self._tools)

        # Kick off with a state snapshot as the first user message. The model
        # has no other user input on a resume — the dossier is the prompt.
        state.messages.append(
            {"role": "user", "content": self._snapshot_content(prompt_mod)}
        )

        try:
            while state.turns < max_turns:
                # anthropic SDK requires streaming for operations that may
                # exceed 10 minutes. With max_tokens=32000 + web_search the
                # SDK guards against the non-streaming path. Use the stream
                # context manager and aggregate via `get_final_message`.
                stream_kwargs: dict[str, Any] = dict(
                    model=self.model,
                    max_tokens=32000,
                    system=cached_system,
                    tools=cached_tools,
                    messages=state.messages,
                )
                if CONTEXT_MANAGEMENT_THRESHOLD > 0:
                    stream_kwargs["extra_body"] = {
                        "context_management": {
                            "edits": [
                                {
                                    "type": "clear_tool_uses_20250919",
                                    "exclude_tools": _DOSSIER_WRITE_TOOLS,
                                    "trigger": {
                                        "type": "input_tokens",
                                        "value": CONTEXT_MANAGEMENT_THRESHOLD,
                                    },
                                }
                            ]
                        }
                    }
                async with self._client.messages.stream(**stream_kwargs) as stream:
                    response = await stream.get_final_message()

                if response.usage is not None:
                    input_tokens = response.usage.input_tokens or 0
                    output_tokens = response.usage.output_tokens or 0
                    cache_creation_input_tokens = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
                    cache_read_input_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
                    # Compute cost in dollars using the MODEL_PRICING table.
                    # Unknown models return 0.0; we log but don't crash.
                    turn_cost = cost_usd_for_turn(
                        self.model, input_tokens, output_tokens,
                        cache_creation_input_tokens=cache_creation_input_tokens,
                        cache_read_input_tokens=cache_read_input_tokens,
                    )
                    # Per-session and global daily rollups — power the budget
                    # soft-signal surface and the per-session UI header.
                    # Single transaction keeps session + daily counters consistent.
                    storage.record_turn_usage(
                        session_id, input_tokens, output_tokens, turn_cost,
                        cache_creation_input_tokens=cache_creation_input_tokens,
                        cache_read_input_tokens=cache_read_input_tokens,
                    )
                    # stuck-detection needs per-turn input tokens for session-
                    # and section-budget signals. Attribute to the section most
                    # recently upserted this session (if any); otherwise None.
                    stuck_mod.record_input_tokens(
                        session_id, self._last_section_id, input_tokens
                    )
                    # Budget soft-signal: check after each turn. Never hard-
                    # stops the loop; emits a decision_point if the session
                    # or daily threshold is crossed (and not yet reported).
                    self._check_budget_signals(session_id)

                # H-01: serialize Anthropic SDK objects to plain dicts before
                # storing in state.messages. The compactor's isinstance(block,
                # dict) guards must see plain dicts, not SDK TextBlock /
                # ToolUseBlock objects.
                serialized_content = [
                    b.model_dump() if hasattr(b, "model_dump") else b
                    for b in response.content
                ]
                state.messages.append(
                    {"role": "assistant", "content": serialized_content}
                )

                # Count every stream call (including pause_turn continuations)
                # so RunResult.turns matches client.messages.stream.call_count.
                state.turns += 1

                # Server-side tool (web_search) hit its per-turn iteration
                # cap; re-send to let Anthropic resume where it paused.
                if response.stop_reason == "pause_turn":
                    continue

                # Compaction: check after every logical turn and compact if the
                # message history is approaching the context limit. The compactor
                # replaces old turns with a single summary breadcrumb, keeping
                # the most recent keep_recent_turns turns verbatim.
                # Read threshold dynamically so tests can monkeypatch the env var.
                _compact_threshold = int(
                    os.getenv("VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD", "80000")
                )
                if _compact_threshold > 0:
                    est_tokens = _compactor_estimate_tokens(state.messages)
                    if should_compact(state.messages, est_tokens, _compact_threshold):
                        try:
                            state.messages = await compact_messages(
                                self._client, self.model, state.messages
                            )
                            storage.append_reasoning(
                                self.dossier_id,
                                m.ReasoningAppend(
                                    note=(
                                        "[compaction] Message history was compacted "
                                        f"(est. {est_tokens} tokens exceeded threshold "
                                        f"{_compact_threshold}). "
                                        "Earlier turns summarized into a breadcrumb."
                                    ),
                                    tags=["compaction"],
                                ),
                                work_session_id=session_id,
                            )
                        except Exception:
                            # Compaction failure must never terminate the agent.
                            pass

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
                # Per-turn single-needs_input enforcement. The prompt tells
                # the agent to batch, but it sometimes fires two in one turn
                # anyway — each would render as a separate click for the
                # user. Track the first call; short-circuit any subsequent
                # ones with a soft-reject tool_result so the agent combines
                # on the next turn. Resets each iteration of this while-loop.
                needs_input_in_turn: bool = False

                for tu in tool_uses:
                    tool_name = tu.name
                    tool_input = dict(tu.input) if tu.input else {}

                    # web_search is server-side; results are already in
                    # response.content. Skip client-side dispatch for it.
                    if tool_name == "web_search":
                        continue

                    if tool_name == "flag_needs_input":
                        if needs_input_in_turn:
                            # Second+ needs_input in the same turn. Don't
                            # dispatch — return a soft reject so the agent
                            # combines the question into the first one.
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": json.dumps({
                                    "ok": False,
                                    "reason": "one_needs_input_per_turn",
                                    "message": (
                                        "You already called flag_needs_input "
                                        "this turn. Combine your additional "
                                        "question into that first needs_input's "
                                        "`question` field (one batched ask), or "
                                        "hold it for a later turn. The user sees "
                                        "each needs_input as a separate click — "
                                        "batching them is kinder."
                                    ),
                                }),
                                "is_error": True,
                            })
                            continue
                        needs_input_in_turn = True

                    result_block = await self._dispatch_client_tool(
                        tool_name, tool_input, tu.id
                    )
                    tool_results.append(result_block)

                    # Track which section the agent is working on, so
                    # record_input_tokens can attribute budget pressure to it.
                    # Use the id storage ACTUALLY returned, not the one the
                    # agent passed — on create, the agent may pass an
                    # invented id (like 'sec_reframe') that storage ignores
                    # in favor of a DB-assigned uuid. Trusting tool_input
                    # caused all tokens across a session to pile into a
                    # phantom section id, tripping section_budget stuck
                    # signals that should have been split across the real
                    # sections. `after_section_id` is the *preceding* anchor,
                    # not the section being edited — never use it.
                    if tool_name == "upsert_section":
                        real_id = _extract_result_section_id(result_block)
                        if real_id:
                            self._last_section_id = real_id

                    # Terminal tool: the agent signals the investigation is
                    # handed off to the user. We still let any remaining
                    # tool_uses in this same turn dispatch (so their results
                    # are appended and the message shape stays valid), then
                    # break out of the loop after appending tool_results.
                    # Day-6 defense-in-depth: the handler may refuse (open
                    # needs_input, running subs, unresolved plan_approval).
                    # Only terminate when the handler signals success — on
                    # refusal the loop continues so the agent can see the
                    # refusal result_block on the next turn and react.
                    if tool_name == "mark_investigation_delivered":
                        if _handler_result_ok(result_block):
                            delivered = True

                    # After each dossier mutation, let stuck detection look
                    # at the sequence. First returned signal wins.
                    if stuck_signal is None:
                        stuck_signal = stuck_mod.record_tool_call(
                            session_id, tool_name, tool_input
                        )

                if tool_results:
                    state.messages.append({"role": "user", "content": tool_results})

                # Progress-forcing: record which tools fired this turn so
                # the no_progress counter either resets (a progress-tool
                # fired) or increments (only refinement-grade tools).
                tool_names_this_turn = [tu.name for tu in tool_uses]
                stuck_mod.record_turn_end(session_id, tool_names_this_turn)

                if delivered:
                    return RunResult(
                        reason="delivered",
                        turns=state.turns,
                        session_id=session_id,
                    )

                # Post-turn budget / revision-stall / no-progress check,
                # independent of record_tool_call's per-call looping check.
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
            # Phase 3 fallback: if the agent didn't call summarize_session,
            # write a minimal row so every session has something for the UI
            # to render. save_session_summary's UPSERT preserves real content
            # on conflict, so a real summary written mid-run won't be
            # clobbered by the empty fallback here.
            try:
                ws = storage.get_work_session(session_id)
                if ws is not None:
                    storage.save_session_summary(
                        m.SessionSummary(
                            session_id=session_id,
                            dossier_id=self.dossier_id,
                            summary="",
                            cost_usd=ws.cost_usd,
                            created_at=m.utc_now(),
                        )
                    )
            except Exception:
                # Fallback is best-effort — do not mask end_work_session.
                pass
            storage.end_work_session(session_id)
            # H-23: auto-schedule next wake from check_in_policy.cadence when
            # the agent did NOT already call schedule_wake (wake_at is still
            # null after session end).  Only fires if sleep mode is enabled.
            try:
                self._auto_schedule_cadence_wake()
            except Exception:  # noqa: BLE001 — cleanup must not mask result
                pass
            try:
                stuck_mod.reset_session(session_id)
            except Exception:  # noqa: BLE001 — cleanup must not mask result
                pass

    def _resolve_session(self) -> str:
        expected_session_id = getattr(self, "expected_session_id", None)
        if expected_session_id:
            expected = storage.get_work_session(expected_session_id)
            if expected is None:
                raise RuntimeError(f"expected work_session {expected_session_id} not found")
            if expected.dossier_id != self.dossier_id:
                raise RuntimeError(
                    f"expected work_session {expected_session_id} belongs to "
                    f"{expected.dossier_id}, not {self.dossier_id}"
                )
            if expected.ended_at is not None:
                raise RuntimeError(f"expected work_session {expected_session_id} is already ended")
            return expected.id

        existing = storage.get_active_work_session(self.dossier_id)
        if existing is not None:
            return existing.id
        try:
            return storage.start_work_session(
                self.dossier_id, m.WorkSessionTrigger.resume
            ).id
        except storage.ActiveWorkSessionExists as exc:
            return exc.session.id

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

        # Idempotency: if this tool_use_id has already been dispatched,
        # return the recorded result instead of re-running the handler.
        # Under Path A this should be rare (new sessions don't replay
        # message history), but the shim is migration-proof for Path B/C
        # and closes the "double upsert_section lies to the plan-diff"
        # failure mode if runtime dispatch ever re-iterates a response.
        prior = await asyncio.to_thread(
            storage.get_tool_invocation, tool_use_id
        )
        if prior is not None:
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": prior["result_json"],
                "is_error": prior["is_error"],
            }

        try:
            # Handlers are sync; run them off the event loop so a slow write
            # doesn't stall concurrent agents. Route through handlers.dispatch
            # so HANDLER_OVERRIDES and TOOL_HOOKS apply.
            result = await asyncio.to_thread(
                handlers.dispatch, self.dossier_id, tool_name, tool_input
            )
            result_json = _coerce_tool_result(result)
            await asyncio.to_thread(
                storage.record_tool_invocation,
                tool_use_id,
                self.dossier_id,
                tool_name,
                _hash_tool_input(tool_input),
                result_json,
                False,
            )
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_json,
            }
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't kill the loop
            err_content = f"{type(exc).__name__}: {exc}"
            # Record the error so a replay doesn't re-run a handler that
            # already errored (cheap insurance against thrashing the DB
            # on the same failure).
            try:
                await asyncio.to_thread(
                    storage.record_tool_invocation,
                    tool_use_id,
                    self.dossier_id,
                    tool_name,
                    _hash_tool_input(tool_input),
                    err_content,
                    True,
                )
            except Exception:
                pass
            return {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": err_content,
                "is_error": True,
            }

    def _check_budget_signals(self, session_id: str) -> None:
        """Soft-signal budget check — runs after each turn's usage capture.

        Emits a ``declare_stuck``-shaped decision_point via storage when the
        daily global cap or the per-session cap is crossed. Never terminates
        the loop — the agent and user decide whether to continue. Dedup is
        local to this runtime instance via the ``_budget_*_reported`` flags.
        """
        try:
            daily_cap = float(storage.get_setting("budget_daily_soft_cap_usd", 0) or 0)
            session_cap = float(storage.get_setting("budget_per_session_soft_cap_usd", 0) or 0)
        except Exception:
            return

        # Daily global signal
        if daily_cap > 0 and not self._budget_daily_reported:
            try:
                today = storage.get_budget_today()
            except Exception:
                today = None
            if today is not None and today.spent_usd >= daily_cap:
                self._budget_daily_reported = True
                self._surface_budget_signal(
                    kind="budget_daily",
                    detail=(
                        f"Daily global spend ${today.spent_usd:.2f} has reached "
                        f"the soft cap of ${daily_cap:.2f}."
                    ),
                )

        # Per-session signal
        if session_cap > 0 and not self._budget_session_reported:
            try:
                ws = storage.get_work_session(session_id)
            except Exception:
                ws = None
            if ws is not None and ws.cost_usd >= session_cap:
                self._budget_session_reported = True
                self._surface_budget_signal(
                    kind="budget_session",
                    detail=(
                        f"This work session has spent ${ws.cost_usd:.2f}, crossing "
                        f"the per-session soft cap of ${session_cap:.2f}."
                    ),
                )

    def _surface_budget_signal(self, kind: str, detail: str) -> None:
        summary = (
            f"{detail} Soft signal only — I'll keep working unless you tell "
            f"me otherwise, but this is worth a check-in."
        )
        # M-24: budget cap signals (daily_cap, session_budget) always surface
        # a decision_point, even when trust_mode is enabled. Trust mode only
        # suppresses tier-2 stuck signals; budget overruns require explicit
        # user acknowledgement because they have real cost implications.

        options = [
            {
                "label": "Keep going",
                "implications": "I continue; the cap is advisory.",
                "recommended": False,
            },
            {
                "label": "Pause for your direction",
                "implications": (
                    "I'll hand off with where I am and wait for you to "
                    "either raise the cap in settings or steer me."
                ),
                "recommended": True,
            },
            {
                "label": "Mark what I have as delivered",
                "implications": (
                    "I'll freeze the current dossier state and call "
                    "mark_investigation_delivered with what's been covered."
                ),
                "recommended": False,
            },
        ]
        try:
            handlers.dispatch(
                self.dossier_id,
                "check_stuck",
                {"summary_of_attempts": summary, "options_for_user": options},
            )
        except Exception:
            pass

    def _surface_stuck(self, signal: Any) -> None:
        """Convert a StuckSignal into the tier-appropriate user surface.

        Phase 3 part C tier policy:
          * Tier 1 — heads-up only. Append a ``stuck_L1``-tagged reasoning
            note so the agent sees it on the next state snapshot and is
            expected to narrow + continue. NO decision_point surfaced.
          * Tier 2 — standard check_stuck decision_point (prior behavior).
          * Tier 3+ — check_stuck decision_point with the first option
            already flagged ``recommended=True`` by
            stuck._assign_tier_and_emit.

        The stuck signal originated in the runtime, not the model, but the
        user-facing surface (tiers 2/3) still routes through the same
        check_stuck handler the model would have called.
        """
        tier = int(getattr(signal, "tier", 2) or 2)
        summary = (
            getattr(signal, "summary_of_attempts", None)
            or getattr(signal, "detail", None)
            or "Agent detected a stuck pattern."
        )
        if tier == 1:
            # Heads-up only — no decision_point. Agent reads the note on the
            # next turn's state snapshot and is expected to narrow + continue.
            try:
                handlers.dispatch(
                    self.dossier_id,
                    "append_reasoning",
                    {
                        "note": f"[stuck_L1] {summary}",
                        "tags": ["stuck", "stuck_L1"],
                    },
                )
            except Exception:  # noqa: BLE001 — a failed L1 note must not mask the signal
                pass
            return

        if tier == 2:
            try:
                trust_mode = bool(storage.get_setting("trust_mode_enabled", False))
            except Exception:
                trust_mode = False
            if trust_mode:
                # Trust mode is on and this is a tier-2 stall. Pick the
                # recommended option (or the first one if nothing's explicitly
                # marked recommended) and continue. Note it on the trail so the
                # user can audit what we chose for them.
                options = getattr(signal, "options_for_user", None) or []
                chosen = next(
                    (o for o in options if isinstance(o, dict) and o.get("recommended")),
                    None,
                )
                if chosen is None and options:
                    chosen = options[0]
                chosen_label = (
                    chosen.get("label") if isinstance(chosen, dict) else None
                ) or "(no option)"
                try:
                    handlers.dispatch(
                        self.dossier_id,
                        "append_reasoning",
                        {
                            "note": (
                                f"[trust_mode:auto] Tier 2 stuck — took "
                                f"recommended path: {chosen_label}. Summary: {summary}"
                            ),
                            "tags": ["stuck", "stuck_auto_dismissed", "trust_mode"],
                        },
                    )
                except Exception:
                    pass
                return

        # Tier 2 and 3: surface a decision_point via the existing handler.
        # Tier-3 options already had recommended=True forced by
        # stuck._assign_tier_and_emit.
        options = getattr(signal, "options_for_user", None) or [
            {"label": "Let the agent keep going", "implications": "", "recommended": False},
            {"label": "Pause for your direction", "implications": "", "recommended": True},
        ]
        try:
            handlers.dispatch(
                self.dossier_id,
                "check_stuck",
                {"summary_of_attempts": summary, "options_for_user": options},
            )
        except Exception:  # noqa: BLE001 — a failed stuck surface must not mask the signal
            pass


    def _auto_schedule_cadence_wake(self) -> None:
        """H-23: schedule next wake from check_in_policy.cadence.

        Only acts when:
        - sleep_mode_enabled is True
        - the dossier has a daily or weekly cadence
        - no wake_at is already set (agent didn't call schedule_wake this run)
        """
        from datetime import timedelta

        if not storage.get_setting("sleep_mode_enabled", True):
            return

        dossier = storage.get_dossier(self.dossier_id)
        if dossier is None:
            return

        cadence = dossier.check_in_policy.cadence
        if cadence not in (m.CheckInCadence.daily, m.CheckInCadence.weekly):
            return

        wake_state = storage.get_dossier_wake_state(self.dossier_id)
        if wake_state is not None and wake_state.get("wake_at") is not None:
            return

        hours = 24.0 if cadence == m.CheckInCadence.daily else 24.0 * 7
        wake_at = m.utc_now() + timedelta(hours=hours)
        storage.set_dossier_wake_at(
            self.dossier_id, wake_at, m.WakeReason.scheduled
        )


def _coerce_tool_result(result: Any) -> str:
    """Handlers return compact dicts; the API wants string or block content."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _extract_result_section_id(result_block: dict[str, Any]) -> Optional[str]:
    """Pull the DB-assigned section_id out of an upsert_section tool_result.

    Returns None when the handler errored, when content isn't parseable
    JSON, or when the payload doesn't carry a section_id. Callers should
    only overwrite their cached id on a truthy return value; a miss leaves
    the previous attribution in place, which is safer than attributing to
    a phantom.
    """
    if result_block.get("is_error"):
        return None
    content = result_block.get("content")
    if not isinstance(content, str) or not content:
        return None
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        sid = parsed.get("section_id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def _hash_tool_input(tool_input: dict[str, Any]) -> str:
    """Stable hash of a tool_input dict for the tool_invocations audit column.

    The hash is informational — the idempotency key is tool_use_id. Hashing
    the input lets us notice later if a replay ever arrives with a mutated
    payload (it shouldn't, but the data is cheap to record).
    """
    try:
        blob = json.dumps(tool_input, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(sorted(tool_input.items(), key=lambda kv: str(kv[0])))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _handler_result_ok(result_block: dict[str, Any]) -> bool:
    """Inspect a tool_result block to decide if the handler succeeded.

    Used for terminal-tool handling: if ``mark_investigation_delivered``
    refuses (returns ``{"ok": False, ...}``), we do NOT want the runtime
    to treat the dossier as delivered. A result is "ok" unless:

    - the block is explicitly ``is_error=True``, or
    - the parsed content is a JSON object containing ``"ok": false``.

    Any other shape (string content, dict without an ``ok`` key) is
    treated as ok — preserves backwards compatibility with handlers
    that don't opt into the ``ok`` protocol.
    """
    if result_block.get("is_error"):
        return False
    content = result_block.get("content")
    if isinstance(content, str) and content:
        import json
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return True
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return False
    return True


if __name__ == "__main__":
    # Structural smoke test: construct the agent and confirm RunResult is
    # importable. Running .run() requires a live API key + real dossier.
    import inspect as _inspect

    from vellum.agent import runtime as _rt

    agent = _rt.DossierAgent(dossier_id="fake_id_wont_exist")
    assert agent.dossier_id == "fake_id_wont_exist"
    assert agent.model  # falls back to config.MODEL
    assert _rt.RunResult is not None
    assert any(t.get("name") == "upsert_section" for t in agent._tools)
    assert any(t.get("name") == "web_search" for t in agent._tools)

    # Per-turn one-needs_input enforcement: the tracker must exist in run()
    # and the reject payload must carry the documented shape. Running the
    # full loop requires a live Anthropic call, so we verify structurally.
    run_src = _inspect.getsource(_rt.DossierAgent.run)
    assert "needs_input_in_turn" in run_src, (
        "runtime.run() missing per-turn needs_input tracker"
    )
    assert "one_needs_input_per_turn" in run_src, (
        "runtime.run() missing soft-reject reason code"
    )
    # Tracker must be declared inside the turn loop so it resets per-turn,
    # not at function scope. Simplest check: it appears AFTER the while.
    assert run_src.index("while state.turns") < run_src.index(
        "needs_input_in_turn: bool = False"
    ), "tracker must reset inside the per-turn while loop"
    print("structural OK")
