"""Message-history compaction for long agent sessions.

When input tokens approach the context budget, older turns are summarized
into a single synthetic user message (a "compaction breadcrumb") while
the most recent turns are preserved verbatim. This keeps the agent
functional on multi-hour sessions without blowing the token budget.

Critical constraint: tool_use ↔ tool_result pairs must be kept intact.
Compaction operates on whole turns (a turn = assistant message + following
user message containing tool_result blocks, if any). Partially truncating
a pair would cause Anthropic's API to return a 400.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..config import SUMMARY_MODEL

logger = logging.getLogger(__name__)


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: ~4 chars per token for English-ish content."""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                # H-01: Anthropic SDK objects (TextBlock, ToolUseBlock, etc.)
                # expose model_dump() — serialize them before falling through to
                # the isinstance(block, dict) branch.
                if hasattr(block, "model_dump"):
                    total += len(json.dumps(block.model_dump(), default=str))
                elif isinstance(block, dict):
                    total += len(json.dumps(block, default=str))
                elif isinstance(block, str):
                    total += len(block)
        total += 4  # role overhead
    return max(1, total // 4)


def should_compact(
    messages: list[dict[str, Any]],
    estimated_input_tokens: int,
    threshold: int,
) -> bool:
    """Return True when compaction should fire this turn.

    Compaction fires when the estimated input tokens exceed the threshold
    AND there are enough messages to make compaction worthwhile (at least
    ``keep_recent_turns * 2 + 1`` messages — the first user message plus
    enough turns to have something to compact).
    """
    if estimated_input_tokens < threshold:
        return False
    # Need enough history that compaction actually reduces tokens.
    # A "turn" is an assistant message + the following user message.
    # Minimum: 1 (first user) + keep_recent (5) * 2 + 1 (something to compact).
    if len(messages) < 12:
        return False
    return True


def _split_turns(
    messages: list[dict[str, Any]],
    keep_recent_turns: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split messages into old (to compact) and recent (to keep verbatim).

    A turn boundary is an assistant message. We count back from the end
    to find the split point. The first user message is always preserved
    as the anchor for the message array.
    """
    # Find turn boundaries: each assistant message starts a new turn.
    # The first message is always the initial user snapshot.
    turn_starts = [0]  # index 0 is the first user message
    for i, msg in enumerate(messages):
        if i > 0 and msg.get("role") == "assistant":
            turn_starts.append(i)

    # If we have fewer turns than keep_recent_turns + 1, nothing to compact.
    if len(turn_starts) <= keep_recent_turns + 1:
        return [], messages

    # Split: turns 1..K go to old, turns K+1..end stay recent.
    # turn_starts[0] = first user msg (index 0)
    # turn_starts[1] = turn 1 start (first assistant)
    # turn_starts[N] = turn N start
    split_at = len(turn_starts) - keep_recent_turns
    split_idx = turn_starts[split_at]

    old = messages[:split_idx]
    recent = messages[split_idx:]
    return old, recent


async def compact_messages(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    keep_recent_turns: int = 5,
) -> list[dict[str, Any]]:
    """Compact old turns into a single synthetic summary message.

    1. Preserve the first user message (the initial state snapshot).
    2. Summarize turns 1..K via a one-off Anthropic API call.
    3. Replace those turns with a single synthetic user message containing
       the compaction breadcrumb.
    4. Preserve the last ``keep_recent_turns`` turns verbatim.
    """
    old, recent = _split_turns(messages, keep_recent_turns)
    if not old:
        return messages

    # Build a summary of the old turns via a one-off API call.
    summary_prompt = (
        "Summarize the following conversation turns into a structured handoff note. "
        "Include: (1) key facts established, (2) decisions made, (3) tool calls completed "
        "and their outcomes, (4) open questions or unresolved items. Be concise — "
        "this summary replaces the original turns for context-management purposes."
    )
    # Flatten old messages into a readable format for the summarizer.
    old_text_parts: list[str] = []
    for msg in old:
        role = msg.get("role", "unknown")
        content = msg.get("content")
        if isinstance(content, str):
            old_text_parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                # H-01: normalize Anthropic SDK objects to plain dicts so the
                # isinstance(block, dict) dispatch below works on all paths.
                if hasattr(block, "model_dump"):
                    block = block.model_dump()
                if isinstance(block, dict):
                    btype = block.get("type", "unknown")
                    if btype == "text":
                        old_text_parts.append(f"[{role}/text]: {block.get('text', '')}")
                    elif btype == "tool_use":
                        old_text_parts.append(
                            f"[{role}/tool_use]: {block.get('name', '')}({json.dumps(block.get('input', {}), default=str)})"
                        )
                    elif btype == "tool_result":
                        old_text_parts.append(
                            f"[{role}/tool_result id={block.get('tool_use_id', '')}]: {block.get('content', '')}"
                        )
                    else:
                        old_text_parts.append(f"[{role}/{btype}]: {json.dumps(block, default=str)}")
                elif isinstance(block, str):
                    old_text_parts.append(f"[{role}]: {block}")

    old_text = "\n".join(old_text_parts)

    # H-11: use the SUMMARY_MODEL constant (already handles env-var fallback to
    # Haiku) instead of an os.getenv that would default to the main Opus model
    # when the env var is unset — making compaction prohibitively expensive.
    summary_model = SUMMARY_MODEL

    try:
        resp = await client.messages.create(
            model=summary_model,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": f"{summary_prompt}\n\n---\n\n{old_text}"},
            ],
        )
        summary_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                summary_text += block.text
    except Exception:
        # L-43: log the failure so operators can see compaction degraded to
        # truncation rather than silently losing context quality.
        logger.exception("Compaction API call failed, falling back to truncation")
        summary_text = f"[Compaction fallback: {len(old)} messages compressed. Key details may be lost.]"

    # Build the compacted message list.
    # Critical: do NOT prepend first_msg as a separate message then add a
    # second user-role breadcrumb — that produces two consecutive user
    # messages which the Anthropic API rejects with a 400.  Instead, merge
    # the first message's content with the breadcrumb into a single user
    # message that opens the compacted list.  This preserves the first-turn
    # anchor while keeping the alternating-role invariant intact.
    first_content = ""
    if messages:
        raw = messages[0].get("content", "")
        if isinstance(raw, str):
            first_content = raw
        elif isinstance(raw, list):
            # Flatten block list to plain text for the merged anchor.
            parts: list[str] = []
            for blk in raw:
                if hasattr(blk, "model_dump"):
                    blk = blk.model_dump()
                if isinstance(blk, dict) and blk.get("type") == "text":
                    parts.append(blk.get("text", ""))
                elif isinstance(blk, str):
                    parts.append(blk)
            first_content = "\n".join(parts)

    breadcrumb = (
        f"[Compaction breadcrumb: {len(old)} earlier messages summarized]\n\n{summary_text}"
    )
    merged_content = f"{first_content}\n\n{breadcrumb}" if first_content else breadcrumb

    compacted = [{"role": "user", "content": merged_content}]
    compacted.extend(recent)
    return compacted
