"""Vellum sub-investigation runtime.

The main agent invokes ``spawn_sub_investigation`` when a scoped question
deserves its own attention (jurisdictional questions, specific legal
mechanisms, head-to-head comparisons). Rather than a stub row, that tool
call must kick off a real sub-agent loop that runs synchronously to
completion and returns findings before the parent's tool call returns.

This module provides:

- ``run_sub_investigation(...)`` — the async loop. Mirrors ``DossierAgent``
  in ``runtime.py`` but with a narrower tool surface, the sub-agent system
  prompt from ``sub_prompt.py``, a dedicated work_session for token
  accounting, and a single exit call (``complete_sub_investigation``).
- ``spawn_handler(...)`` — the HANDLER_OVERRIDES entry for
  ``spawn_sub_investigation``. Creates the sub row, drives the sub-agent
  synchronously, and returns the final state + return_summary to the
  parent.
- A ContextVar ``CURRENT_SUB_INVESTIGATION_ID`` + thin handler wrapper that
  stamps ``sub_investigation_id`` onto the args of tools that support it
  (``log_source_consulted``, ``mark_considered_and_rejected``). This
  threads the sub-id through without touching each handler's call site.

Depth cap: 1. A sub-agent cannot spawn further subs — its tool set omits
``spawn_sub_investigation`` entirely, and the sub prompt forbids it.

On import: registers ``spawn_handler`` as
``handlers.HANDLER_OVERRIDES["spawn_sub_investigation"]`` so the runtime's
dispatch picks it up transparently.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
from typing import Any, Optional

import anthropic

from .. import models as m
from .. import storage
from ..config import ANTHROPIC_API_KEY, MODEL, SUB_AGENT_MAX_TURNS, cost_usd_for_turn
from ..tools import handlers
from . import sub_prompt


logger = logging.getLogger(__name__)


# Same shape the main runtime uses so Anthropic's web_search server tool
# is available to sub-agents.
_WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
}


# Tools exposed to a sub-agent. Tight by design — no plan/debrief, no
# further spawning. The exit call is ``complete_sub_investigation``.
SUB_TOOL_ALLOWLIST: frozenset[str] = frozenset({
    "upsert_section",
    "add_artifact",
    "log_source_consulted",
    "mark_considered_and_rejected",
    "flag_needs_input",
    "complete_sub_investigation",
})


# Tools whose args shape accepts an optional ``sub_investigation_id`` field.
# When a sub-agent calls one of these, we stamp the current sub id so the
# resulting DB row attributes correctly (InvestigationLogAppend,
# ConsideredAndRejectedCreate both support this field).
_SUB_ID_INJECT_TOOLS: frozenset[str] = frozenset({
    "log_source_consulted",
    "mark_considered_and_rejected",
})


# Module-level contextvar carrying the currently-running sub-investigation
# id. Set by ``run_sub_investigation`` before each dispatch; read by the
# handler wrapper so tools that support ``sub_investigation_id`` get it
# stamped automatically without touching the call site.
CURRENT_SUB_INVESTIGATION_ID: contextvars.ContextVar[Optional[str]] = (
    contextvars.ContextVar("CURRENT_SUB_INVESTIGATION_ID", default=None)
)


# How many times we prod the model with a synthetic "you haven't called
# complete_sub_investigation yet" nudge before force-completing on its
# behalf. Two prods matches the spec.
_MAX_PRODS: int = 2


def _build_sub_tool_definitions() -> list[dict[str, Any]]:
    """Filter ``handlers.tool_schemas()`` to the sub-agent's allowlist.

    Derived (not hand-written) so if a schema shape changes in handlers.py
    the sub-agent picks it up automatically. web_search is appended the
    same way the main runtime does it.
    """
    full = handlers.tool_schemas()
    filtered = [t for t in full if t.get("name") in SUB_TOOL_ALLOWLIST]
    filtered.append(_WEB_SEARCH_TOOL)
    return filtered


def _coerce_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)


def _extract_result_section_id(result_block: dict[str, Any]) -> Optional[str]:
    if result_block.get("is_error"):
        return None
    content = result_block.get("content")
    if not isinstance(content, str) or not content:
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, dict):
        section_id = parsed.get("section_id")
        if isinstance(section_id, str) and section_id:
            return section_id
    return None


def _inject_sub_id(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Stamp the contextvar's sub_id onto tool args when applicable.

    Pure — returns a new dict. Tools that don't support the field get the
    args back unchanged.
    """
    if tool_name not in _SUB_ID_INJECT_TOOLS:
        return args
    sub_id = CURRENT_SUB_INVESTIGATION_ID.get()
    if sub_id is None:
        return args
    # Don't clobber an id the model explicitly supplied (defensive — the
    # model shouldn't see its own sub_id anywhere, but be safe).
    if args.get("sub_investigation_id"):
        return args
    new_args = dict(args)
    new_args["sub_investigation_id"] = sub_id
    return new_args


def _log_source_consulted_with_sub(
    dossier_id: str, args: dict[str, Any], session_id: str, sub_id: str
) -> dict[str, Any]:
    """Sub-runtime-local handler for log_source_consulted.

    The default handler in ``handlers.py`` doesn't propagate
    ``sub_investigation_id`` into the ``InvestigationLogAppend`` row (its
    signature drops the field). Rather than edit handlers.py (forbidden
    by scope), we call storage directly from the sub-runtime with the
    sub_id explicitly set. Same observable behavior, plus the
    attribution the product expects.
    """
    citation: str = args["citation"]
    why_consulted: str = args["why_consulted"]
    what_learned: str = args["what_learned"]
    supports_section_ids: list[str] = args.get("supports_section_ids") or []
    summary = f"{citation[:80]} — {what_learned[:120]}"
    entry = storage.append_investigation_log(
        dossier_id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted,
            payload={
                "citation": citation,
                "why_consulted": why_consulted,
                "what_learned": what_learned,
                "supports_section_ids": supports_section_ids,
            },
            summary=summary,
            sub_investigation_id=sub_id,
        ),
        session_id,
    )
    return {"log_entry_id": getattr(entry, "id", None)}


async def _dispatch_sub_tool(
    dossier_id: str,
    sub_id: str,
    session_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Run a client-side tool for the sub-agent.

    Returns ``(tool_result_block, completion_args)``. When the model calls
    ``complete_sub_investigation``, the second element carries the args it
    passed so the loop can capture them as its return value.
    """
    if tool_name not in SUB_TOOL_ALLOWLIST:
        return (
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": (
                    f"tool '{tool_name}' is not available inside a "
                    "sub-investigation"
                ),
                "is_error": True,
            },
            None,
        )

    stamped_input = _inject_sub_id(tool_name, tool_input)

    # complete_sub_investigation needs the sub_id alongside whatever args
    # the model sent. The model is NOT told its own sub_id, so inject it
    # server-side.
    if tool_name == "complete_sub_investigation":
        stamped_input = dict(stamped_input)
        stamped_input["sub_investigation_id"] = sub_id

    try:
        # log_source_consulted: route through the sub-local variant so the
        # resulting investigation_log row carries sub_investigation_id. The
        # default handlers.log_source_consulted drops the field; we can't
        # edit that file (scope fence), so we call storage directly here.
        if tool_name == "log_source_consulted":
            result = await asyncio.to_thread(
                _log_source_consulted_with_sub,
                dossier_id,
                stamped_input,
                session_id,
                sub_id,
            )
        else:
            handler = handlers.HANDLERS.get(tool_name)
            if handler is None:
                return (
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"unknown tool: {tool_name}",
                        "is_error": True,
                    },
                    None,
                )
            # Handlers resolve their own session via _ensure_session; since
            # our sub session is the dossier's active session, they pick
            # it up. For tools that accept sub_investigation_id as a model
            # field (mark_considered_and_rejected), _inject_sub_id stamped
            # it onto stamped_input above.
            result = await asyncio.to_thread(handler, dossier_id, stamped_input)

        block = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": _coerce_tool_result(result),
        }
    except Exception as exc:  # noqa: BLE001 — surface to model, don't kill loop
        return (
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": f"{type(exc).__name__}: {exc}",
                "is_error": True,
            },
            None,
        )

    completion_args: Optional[dict[str, Any]] = None
    if tool_name == "complete_sub_investigation":
        completion_args = stamped_input

    return block, completion_args


def _build_initial_user_content(
    parent_dossier_id: str, scope: str, questions: list[str]
) -> list[dict[str, Any]]:
    """First user turn: parent dossier snapshot + rendered sub-scope.

    The main agent's state snapshot gives the sub broader context without
    widening its scope — the sub can see why it was spawned and what the
    parent cares about. ``render_sub_scope`` is the authoritative framing
    of the narrow job.
    """
    from . import prompt as prompt_mod

    parts: list[str] = []

    dossier_full = storage.get_dossier_full(parent_dossier_id)
    if dossier_full is not None:
        parts.append("# Parent dossier state (for context only — do not widen scope)")
        parts.append(prompt_mod.build_state_snapshot(dossier_full))

    parts.append(sub_prompt.render_sub_scope(scope, questions))

    return [{"type": "text", "text": "\n\n".join(parts)}]


async def run_sub_investigation(
    parent_dossier_id: str,
    sub_id: str,
    scope: str,
    questions: list[str],
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
) -> dict[str, Any]:
    """Drive one sub-agent loop to completion.

    Reuses the parent active work_session when present; otherwise opens and
    owns a temporary session. Walks the sub-agent through turns until it calls
    ``complete_sub_investigation`` or we force it to complete.

    Returns a dict shaped like the ``complete_sub_investigation`` handler
    result plus a ``return_summary`` mirror — the parent's
    ``spawn_handler`` hands this back up to the main agent.
    """
    logger.info(
        "sub_runtime: starting sub %s scope=%r", sub_id, scope,
    )
    resolved_model = model or MODEL
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY or None)

    effective_max_turns = max(
        1, min(int(max_turns or SUB_AGENT_MAX_TURNS), SUB_AGENT_MAX_TURNS)
    )

    # Preserve the invariant that a dossier has at most one active session.
    # When called inside the parent runtime, reuse its session; when invoked
    # standalone, create and own a temporary session for this sub run.
    owns_session = False
    session = storage.get_active_work_session(parent_dossier_id)
    if session is None:
        try:
            session = storage.start_work_session(
                parent_dossier_id, m.WorkSessionTrigger.resume
            )
            owns_session = True
        except storage.ActiveWorkSessionExists as exc:
            session = exc.session
    session_id = session.id

    tools = _build_sub_tool_definitions()
    system_prompt = sub_prompt.SUB_INVESTIGATION_SYSTEM_PROMPT

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": _build_initial_user_content(parent_dossier_id, scope, questions),
        }
    ]

    # Set the contextvar for the duration of this sub's run so tool
    # dispatches inside it carry sub_investigation_id on applicable args.
    token = CURRENT_SUB_INVESTIGATION_ID.set(sub_id)

    turns = 0
    completion_args: Optional[dict[str, Any]] = None
    prods = 0
    force_completed = False
    last_section_id: Optional[str] = None
    from . import stuck as stuck_mod

    try:
        while turns < effective_max_turns:
            turns += 1

            # Streaming is required for long operations (see runtime.py).
            async with client.messages.stream(
                model=resolved_model,
                max_tokens=32000,
                system=system_prompt,
                tools=tools,
                messages=messages,
            ) as stream:
                response = await stream.get_final_message()

            if response.usage is not None:
                input_tokens = getattr(response.usage, "input_tokens", 0) or 0
                output_tokens = getattr(response.usage, "output_tokens", 0) or 0
                turn_cost = cost_usd_for_turn(
                    resolved_model, input_tokens, output_tokens
                )
                storage.record_session_usage(
                    session_id, input_tokens, output_tokens, turn_cost
                )
                storage.record_budget_usage(
                    input_tokens, output_tokens, turn_cost
                )
                stuck_mod.record_input_tokens(
                    session_id, last_section_id, input_tokens
                )

            messages.append({"role": "assistant", "content": response.content})

            if getattr(response, "stop_reason", None) == "pause_turn":
                # web_search hit its per-turn iteration cap — resume.
                continue

            tool_uses = [
                b for b in response.content
                if getattr(b, "type", None) == "tool_use"
            ]

            if not tool_uses:
                # Model ended the turn without calling any tool. If we've
                # already been prodding, escalate to a force-complete.
                if prods >= _MAX_PRODS:
                    force_completed = True
                    break
                prods += 1
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "You have not yet called "
                                    "complete_sub_investigation. If you "
                                    "have a substantive answer, call it "
                                    "now. If you need more context, call "
                                    "flag_needs_input and then "
                                    "complete_sub_investigation with a "
                                    "brief explanation."
                                ),
                            }
                        ],
                    }
                )
                continue

            tool_results: list[dict[str, Any]] = []

            for tu in tool_uses:
                tool_name = tu.name
                tool_input = dict(tu.input) if tu.input else {}

                if tool_name == "web_search":
                    # Server-side; results are inlined in response.content.
                    continue

                block, maybe_completion = await _dispatch_sub_tool(
                    parent_dossier_id,
                    sub_id,
                    session_id,
                    tool_name,
                    tool_input,
                    tu.id,
                )
                tool_results.append(block)
                if tool_name == "upsert_section":
                    real_id = _extract_result_section_id(block)
                    if real_id:
                        last_section_id = real_id
                if maybe_completion is not None and completion_args is None:
                    completion_args = maybe_completion

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            if completion_args is not None:
                # Clean exit: the model called complete_sub_investigation
                # and the handler already persisted the update.
                summary_text = completion_args.get("return_summary") or ""
                logger.info(
                    "sub_runtime: sub %s completed via model call, "
                    "return_summary_len=%d",
                    sub_id, len(summary_text),
                )
                break

        if completion_args is None:
            # Either max_turns hit or the prod escalation fell through.
            # Force a completion so the parent sees a resolved sub row.
            force_completed = True

        if force_completed and completion_args is None:
            logger.warning(
                "sub_runtime: sub %s force-completing at max_turns=%d",
                sub_id, effective_max_turns,
            )
            fallback_summary = "[incomplete — max_turns reached]"
            try:
                handlers.HANDLERS["complete_sub_investigation"](
                    parent_dossier_id,
                    {
                        "sub_investigation_id": sub_id,
                        "return_summary": fallback_summary,
                        "findings_section_ids": [],
                        "findings_artifact_ids": [],
                    },
                )
            except Exception:  # noqa: BLE001 — log + continue; parent still needs a reply
                logger.exception(
                    "sub_runtime: force-complete storage call failed for sub %s",
                    sub_id,
                )
            completion_args = {
                "sub_investigation_id": sub_id,
                "return_summary": fallback_summary,
                "findings_section_ids": [],
                "findings_artifact_ids": [],
            }
            logger.warning(
                "sub_runtime: forced completion on sub %s after %d turns",
                sub_id, turns,
            )

        return {
            "sub_investigation_id": sub_id,
            "return_summary": completion_args.get("return_summary", ""),
            "findings_section_ids": list(
                completion_args.get("findings_section_ids") or []
            ),
            "findings_artifact_ids": list(
                completion_args.get("findings_artifact_ids") or []
            ),
            "terminated_without_completion": force_completed,
            "turns": turns,
        }

    except Exception as exc:  # noqa: BLE001 — log + persist, then re-raise
        # Sub-agent errored mid-turn (streaming exception, tool dispatch
        # error, etc.). Critical: ensure the sub row does NOT stay in
        # `running`, then re-raise so spawn_handler can surface the error
        # to the main agent as a tool_result. The original day-5 bug was
        # that both this completion AND the force-complete fallback
        # silently failed, leaving subs pristine in `running`.
        logger.exception(
            "sub_runtime: unexpected error in sub %s — persisting failure row",
            sub_id,
        )
        error_summary = f"[sub-agent errored: {type(exc).__name__}: {exc}]"
        try:
            storage.complete_sub_investigation(
                parent_dossier_id,
                sub_id,
                m.SubInvestigationComplete(
                    return_summary=error_summary,
                    findings_section_ids=[],
                    findings_artifact_ids=[],
                ),
                session_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "sub_runtime: storage.complete_sub_investigation also failed "
                "for sub %s — attempting abandon_sub_investigation fallback",
                sub_id,
            )
            try:
                storage.abandon_sub_investigation(
                    parent_dossier_id,
                    sub_id,
                    error_summary,
                    session_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sub_runtime: abandon_sub_investigation also failed "
                    "for sub %s — sub row may remain in `running`",
                    sub_id,
                )
        raise

    finally:
        CURRENT_SUB_INVESTIGATION_ID.reset(token)
        if owns_session:
            try:
                storage.end_work_session(session_id)
            except Exception:  # noqa: BLE001 — cleanup must not mask result
                pass
            try:
                from . import stuck as stuck_mod
                stuck_mod.reset_session(session_id)
            except Exception:  # noqa: BLE001
                pass


def spawn_handler(parent_dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """HANDLER_OVERRIDES entry for ``spawn_sub_investigation``.

    Replaces the stub handler. Creates the sub row, runs the sub-agent
    synchronously to completion, and returns the final state plus the
    sub's return_summary so the main agent can continue from a resolved
    tool result.
    """
    # Defer session resolution to the default handler's convention: use
    # the active session if present, otherwise open one. The storage
    # spawn call will log the change against the parent's session.
    parent_session = storage.get_active_work_session(parent_dossier_id)
    parent_session_created = False
    if parent_session is None:
        try:
            parent_session = storage.start_work_session(
                parent_dossier_id, m.WorkSessionTrigger.resume
            )
            parent_session_created = True
        except storage.ActiveWorkSessionExists as exc:
            parent_session = exc.session
    parent_session_id = parent_session.id

    spawn_data = m.SubInvestigationSpawn(**args)
    sub = storage.spawn_sub_investigation(
        parent_dossier_id, spawn_data, parent_session_id
    )

    # Run the sub-agent loop synchronously. The parent handler call is
    # sync-from-the-agent's-POV but the underlying dispatch already runs
    # handlers in asyncio.to_thread, so we need a fresh event loop if
    # there's no running one.
    result: Optional[dict[str, Any]] = None
    spawn_error: Optional[BaseException] = None
    try:
        try:
            result = asyncio.run(
                run_sub_investigation(
                    parent_dossier_id,
                    sub.id,
                    spawn_data.scope,
                    list(spawn_data.questions or []),
                )
            )
        except RuntimeError as exc:
            # If we're already inside a running loop (e.g. the main runtime
            # called us without asyncio.to_thread), fall back to nesting. We
            # don't expect this in normal operation — handlers are dispatched
            # via to_thread — but guard against it.
            if "asyncio.run() cannot be called" in str(exc):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        run_sub_investigation(
                            parent_dossier_id,
                            sub.id,
                            spawn_data.scope,
                            list(spawn_data.questions or []),
                        )
                    )
                finally:
                    loop.close()
            else:
                raise
    except Exception as exc:  # noqa: BLE001 — surface to main agent
        logger.exception(
            "sub_runtime: spawn_handler caught error running sub %s",
            sub.id,
        )
        spawn_error = exc
        # Defense in depth: run_sub_investigation already attempted to
        # persist a failure row before re-raising, but double-check here.
        # If the sub is still in `running`, abandon it so the parent never
        # sees a zombie.
        try:
            fetched = storage.get_sub_investigation(sub.id)
            if (
                fetched is not None
                and fetched.state == m.SubInvestigationState.running
            ):
                storage.abandon_sub_investigation(
                    parent_dossier_id,
                    sub.id,
                    f"[sub-agent errored: {type(exc).__name__}: {exc}]",
                    parent_session_id,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "sub_runtime: failed to abandon stuck sub %s after error",
                sub.id,
            )
    finally:
        if parent_session_created:
            try:
                storage.end_work_session(parent_session_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "sub_runtime: failed to close temporary parent session %s",
                    parent_session_id,
                )

    fetched = storage.get_sub_investigation(sub.id)
    final_state = (
        fetched.state.value
        if fetched is not None
        else "running"
    )

    if spawn_error is not None:
        # Return a structured error so the main agent can see it, rather
        # than letting the exception bubble out of the tool dispatch
        # (which would become an is_error=True string and lose structure).
        return {
            "sub_investigation_id": sub.id,
            "state": final_state,
            "return_summary": (
                f"[sub-agent errored: {type(spawn_error).__name__}: "
                f"{spawn_error}]"
            ),
            "findings_section_ids": [],
            "findings_artifact_ids": [],
            "terminated_without_completion": True,
            "error": f"{type(spawn_error).__name__}: {spawn_error}",
        }

    assert result is not None  # unreachable: success path always sets result
    return {
        "sub_investigation_id": sub.id,
        "state": final_state,
        "return_summary": result.get("return_summary", ""),
        "findings_section_ids": result.get("findings_section_ids", []),
        "findings_artifact_ids": result.get("findings_artifact_ids", []),
        "terminated_without_completion": result.get(
            "terminated_without_completion", False
        ),
    }


# --- Registration -------------------------------------------------------
#
# The runtime-hooks agent adds HANDLER_OVERRIDES as a dict on the handlers
# module. Register on import so the main runtime's dispatch picks up our
# handler transparently. On branches where HANDLER_OVERRIDES hasn't landed
# yet, we attach it — keeps the registration idempotent and forward-
# compatible with whatever final dispatch shape lands.

if not hasattr(handlers, "HANDLER_OVERRIDES"):
    handlers.HANDLER_OVERRIDES = {}  # type: ignore[attr-defined]

handlers.HANDLER_OVERRIDES["spawn_sub_investigation"] = spawn_handler  # type: ignore[attr-defined]
