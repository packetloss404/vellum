"""Tests for message-history compaction."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from vellum import models as m
from vellum.agent.compactor import (
    _estimate_tokens,
    _split_turns,
    compact_messages,
    should_compact,
)


# --- should_compact ---


class TestShouldCompact:
    def test_below_threshold_returns_false(self):
        msgs = [{"role": "user", "content": "short"}]
        assert should_compact(msgs, 100, 1000) is False

    def test_at_threshold_returns_true_with_enough_messages(self):
        msgs = [{"role": "user", "content": "x" * 400}]  # ~100 tokens
        # Need 12+ messages for compaction to fire
        for i in range(14):
            msgs.append({"role": "assistant", "content": f"turn {i}"})
            msgs.append({"role": "user", "content": f"result {i}"})
        est = _estimate_tokens(msgs)
        assert should_compact(msgs, est, 1) is True

    def test_at_threshold_returns_false_with_few_messages(self):
        msgs = [{"role": "user", "content": "x" * 4000}]  # ~1000 tokens
        assert should_compact(msgs, 1000, 100) is False

    def test_exactly_at_boundary(self):
        msgs = [{"role": "user", "content": "x"}]
        for i in range(12):
            msgs.append({"role": "assistant", "content": "a"})
            msgs.append({"role": "user", "content": "u"})
        assert should_compact(msgs, 1, 0) is True


# --- _estimate_tokens ---


class TestEstimateTokens:
    def test_string_content(self):
        msgs = [{"role": "user", "content": "a" * 400}]
        est = _estimate_tokens(msgs)
        assert est >= 90  # ~100

    def test_list_content(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "b" * 400}]}]
        est = _estimate_tokens(msgs)
        assert est >= 80  # ~100 minus JSON overhead


# --- _split_turns ---


class TestSplitTurns:
    def test_basic_split(self):
        msgs = [
            {"role": "user", "content": "initial"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "r1"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "r2"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "r3"},
        ]
        old, recent = _split_turns(msgs, keep_recent_turns=1)
        # Keep 1 recent turn: last assistant + user pair
        assert len(recent) == 2
        assert recent[0]["content"] == "a3"
        assert len(old) == 5  # initial + 2 full turns

    def test_not_enough_turns(self):
        msgs = [
            {"role": "user", "content": "initial"},
            {"role": "assistant", "content": "a1"},
        ]
        old, recent = _split_turns(msgs, keep_recent_turns=5)
        assert old == []
        assert recent == msgs

    def test_preserves_first_message(self):
        msgs = [
            {"role": "user", "content": "FIRST"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "r1"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "r2"},
        ]
        old, recent = _split_turns(msgs, keep_recent_turns=1)
        assert old[0]["content"] == "FIRST"


# --- compact_messages ---


class TestCompactMessages:
    def _make_mock_client(self, summary_text: str = "Summary of past turns.") -> MagicMock:
        """Build a mock Anthropic client that returns a summary on create()."""
        text_block = SimpleNamespace(type="text", text=summary_text)
        response = SimpleNamespace(content=[text_block])
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=response)
        return client

    def test_compact_preserves_first_and_recent(self):
        """After compaction: merged first+breadcrumb message then recent turns.

        The fix for the consecutive-user-message API bug (H-04 critical)
        merges the initial snapshot and the compaction breadcrumb into a
        single user message so the resulting list never has two consecutive
        user-role messages.  The recent turns then follow immediately after.
        """
        msgs = [
            {"role": "user", "content": "INITIAL SNAPSHOT"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "r1"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "r2"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "r3"},
            {"role": "assistant", "content": "a4"},
            {"role": "user", "content": "r4"},
        ]
        client = self._make_mock_client()
        result = asyncio.run(compact_messages(client, "mock-model", msgs, keep_recent_turns=2))

        # First message is the merged anchor (initial snapshot + breadcrumb).
        assert result[0]["role"] == "user"
        assert "INITIAL SNAPSHOT" in result[0]["content"]
        assert "Compaction breadcrumb" in result[0]["content"]
        assert "Summary of past turns" in result[0]["content"]
        # No consecutive user messages — result[1] must be assistant.
        assert result[1]["role"] == "assistant"
        # Last 2 turns preserved verbatim (4 messages): a3, r3, a4, r4.
        assert len(result) == 5  # merged + 4 recent
        assert result[1]["content"] == "a3"
        assert result[2]["content"] == "r3"
        assert result[3]["content"] == "a4"
        assert result[4]["content"] == "r4"

    def test_compact_with_tool_result_pairs(self):
        """Tool_use ↔ tool_result pairs in recent turns are preserved."""
        msgs = [
            {"role": "user", "content": "INITIAL"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "name": "upsert_section", "id": "tu_1", "input": {"title": "x"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": '{"ok": true}'},
            ]},
            {"role": "assistant", "content": "done"},
        ]
        client = self._make_mock_client()
        result = asyncio.run(compact_messages(client, "mock-model", msgs, keep_recent_turns=2))
        # Not enough turns to compact (only 2 turns, keep_recent=2)
        # Should return unchanged
        assert result == msgs

    def test_compact_no_compaction_when_few_turns(self):
        """If there aren't enough turns to compact, return messages unchanged."""
        msgs = [
            {"role": "user", "content": "INITIAL"},
            {"role": "assistant", "content": "a1"},
        ]
        client = self._make_mock_client()
        result = asyncio.run(compact_messages(client, "mock-model", msgs, keep_recent_turns=5))
        assert result == msgs

    def test_compact_summary_api_called(self):
        """The mock client.messages.create should be called for summarization."""
        msgs = [
            {"role": "user", "content": "INITIAL"},
        ]
        for i in range(6):
            msgs.append({"role": "assistant", "content": f"assistant turn {i}"})
            msgs.append({"role": "user", "content": f"user response {i}"})
        client = self._make_mock_client()
        asyncio.run(compact_messages(client, "mock-model", msgs, keep_recent_turns=2))
        assert client.messages.create.call_count == 1

    def test_compact_handles_api_failure(self):
        """If the summarization API call fails, fallback breadcrumb is used."""
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=RuntimeError("API down"))

        msgs = [
            {"role": "user", "content": "INITIAL"},
        ]
        for i in range(6):
            msgs.append({"role": "assistant", "content": f"assistant turn {i}"})
            msgs.append({"role": "user", "content": f"user response {i}"})

        result = asyncio.run(compact_messages(client, "mock-model", msgs, keep_recent_turns=2))
        # Should still produce a merged anchor with fallback breadcrumb.
        assert result[0]["role"] == "user"
        assert "Compaction" in result[0]["content"]
        # No consecutive user messages after merge.
        if len(result) > 1:
            assert result[1]["role"] == "assistant"


# --- Integration: runtime compaction trigger ---


class TestRuntimeCompaction:
    def test_compaction_fires_when_threshold_exceeded(self, fresh_db, monkeypatch):
        """Simulate a runtime turn where the message array crosses the
        compaction threshold. Verify compaction fires and a reasoning
        entry is appended."""
        from vellum import storage
        from vellum.agent import runtime as rt
        from vellum.agent import compactor as compactor_mod

        dossier = storage.create_dossier(
            m.DossierCreate(
                title="compaction test",
                problem_statement="test",
                dossier_type=m.DossierType.investigation,
            )
        )
        dossier_id = dossier.id

        # Set a very low threshold so compaction fires on our small message list.
        # runtime.py reads this dynamically via os.getenv so we set the env var.
        monkeypatch.setenv("VELLUM_COMPACT_INPUT_TOKEN_THRESHOLD", "1")

        # Build a scripted client with many turns to create enough messages.
        from tests.test_runtime_v2 import make_mock_client, _message, _text, _tool_use

        turns = []
        for i in range(7):
            turns.append(
                _message(
                    [_tool_use("append_reasoning", {"note": f"turn {i}", "tags": []}, id=f"tu_{i}")],
                    stop_reason="tool_use",
                )
            )
        turns.append(_message([_text("done")], stop_reason="end_turn"))

        client = make_mock_client(turns)
        agent = rt.DossierAgent(dossier_id=dossier_id, model="mock-model")
        agent._client = client

        # Patch the mock client's .create to return a summary response
        # for the compaction summarization call.
        text_block = SimpleNamespace(type="text", text="Summary of past turns.")
        summary_resp = SimpleNamespace(content=[text_block])
        client.messages.create = AsyncMock(return_value=summary_resp)

        result = asyncio.run(agent.run(max_turns=20))

        # The run should complete (not crash from compaction).
        assert result.reason in ("ended_turn", "turn_limit")

        # A compaction-tagged reasoning entry should exist.
        trail = storage.list_reasoning_trail(dossier_id)
        compaction_notes = [e for e in trail if "compaction" in e.tags]
        assert len(compaction_notes) >= 1, (
            f"Expected compaction reasoning note; tags found: {[e.tags for e in trail]}"
        )
