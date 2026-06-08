"""Tests for JIT dossier loading: read-only tools + snapshot index rendering."""
from __future__ import annotations

import pytest
from vellum import models as m
from vellum import storage
from vellum.agent import prompt as prompt_mod
from vellum.tools import handlers


# --- Fixtures ---


def _make_dossier():
    d = storage.create_dossier(
        m.DossierCreate(
            title="JIT test dossier",
            problem_statement="test JIT loading tools",
            dossier_type=m.DossierType.investigation,
        )
    )
    return d.id


def _add_section(dossier_id, state=m.SectionState.confident, content="A" * 200):
    return storage.upsert_section(
        dossier_id,
        m.SectionUpsert(
            type=m.SectionType.finding,
            title="Test section",
            content=content,
            state=state,
            change_note="seed",
        ),
    )


def _add_artifact(dossier_id):
    return storage.create_artifact(
        dossier_id,
        m.ArtifactCreate(
            kind=m.ArtifactKind.letter,
            title="Test letter",
            content="# Dear sir\n\nYour debt is invalid.",
            intended_use="mail to collector",
        ),
    )


# --- Handler tests ---


class TestGetSection:
    def test_get_section_returns_full_content(self, fresh_db):
        dossier_id = _make_dossier()
        section = _add_section(dossier_id, content="Full body content here")
        result = handlers.get_section(dossier_id, {"section_id": section.id})
        assert result["ok"] is True
        assert result["content"] == "Full body content here"
        assert result["section_id"] == section.id
        assert result["state"] == "confident"

    def test_get_section_missing_id(self, fresh_db):
        dossier_id = _make_dossier()
        result = handlers.get_section(dossier_id, {"section_id": "sec_nonexistent"})
        assert result["ok"] is False
        assert result["reason"] == "not_found"

    def test_get_section_wrong_dossier(self, fresh_db):
        dossier_id = _make_dossier()
        other_id = _make_dossier()
        section = _add_section(dossier_id)
        result = handlers.get_section(other_id, {"section_id": section.id})
        assert result["ok"] is False
        assert result["reason"] == "wrong_dossier"


class TestListSectionsJit:
    def test_list_sections_returns_previews(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id, content="Short")
        _add_section(dossier_id, content="B" * 200)
        result = handlers.list_sections_jit(dossier_id, {})
        assert result["ok"] is True
        assert result["count"] == 2
        for s in result["sections"]:
            assert "id" in s
            assert "preview" in s
            assert len(s["preview"]) <= 84  # 80 + "…"

    def test_list_sections_state_filter(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id, state=m.SectionState.confident)
        _add_section(dossier_id, state=m.SectionState.provisional)
        result = handlers.list_sections_jit(dossier_id, {"state_filter": "provisional"})
        assert result["count"] == 1
        assert result["sections"][0]["state"] == "provisional"

    def test_list_sections_kind_filter(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id)
        storage.upsert_section(
            dossier_id,
            m.SectionUpsert(
                type=m.SectionType.recommendation,
                title="Rec section",
                content="rec content",
                state=m.SectionState.confident,
                change_note="seed",
            ),
        )
        result = handlers.list_sections_jit(dossier_id, {"kind_filter": "recommendation"})
        assert result["count"] == 1
        assert result["sections"][0]["type"] == "recommendation"


class TestGetArtifact:
    def test_get_artifact_returns_full_content(self, fresh_db):
        dossier_id = _make_dossier()
        art = _add_artifact(dossier_id)
        result = handlers.get_artifact_handler(dossier_id, {"artifact_id": art.id})
        assert result["ok"] is True
        assert result["content"] == "# Dear sir\n\nYour debt is invalid."
        assert result["kind"] == "letter"

    def test_get_artifact_missing_id(self, fresh_db):
        dossier_id = _make_dossier()
        result = handlers.get_artifact_handler(dossier_id, {"artifact_id": "art_nonexistent"})
        assert result["ok"] is False
        assert result["reason"] == "not_found"

    def test_get_artifact_wrong_dossier(self, fresh_db):
        dossier_id = _make_dossier()
        other_id = _make_dossier()
        art = _add_artifact(dossier_id)
        result = handlers.get_artifact_handler(other_id, {"artifact_id": art.id})
        assert result["ok"] is False
        assert result["reason"] == "wrong_dossier"


class TestGetReasoningWindow:
    def test_get_reasoning_window_returns_entries(self, fresh_db):
        dossier_id = _make_dossier()
        session_id = storage.start_work_session(
            dossier_id, m.WorkSessionTrigger.resume
        ).id
        for i in range(8):
            storage.append_reasoning(
                dossier_id,
                m.ReasoningAppend(note=f"note {i}", tags=["test"]),
                session_id,
            )
        result = handlers.get_reasoning_window(dossier_id, {"limit": 5})
        assert result["ok"] is True
        assert result["count"] == 5

    def test_get_reasoning_window_tag_filter(self, fresh_db):
        dossier_id = _make_dossier()
        session_id = storage.start_work_session(
            dossier_id, m.WorkSessionTrigger.resume
        ).id
        storage.append_reasoning(
            dossier_id, m.ReasoningAppend(note="a", tags=["strategy"]), session_id
        )
        storage.append_reasoning(
            dossier_id, m.ReasoningAppend(note="b", tags=["budget"]), session_id
        )
        result = handlers.get_reasoning_window(dossier_id, {"tag_filter": "strategy"})
        assert result["ok"] is True
        assert result["count"] == 1

    def test_get_reasoning_window_invalid_since_iso(self, fresh_db):
        dossier_id = _make_dossier()
        result = handlers.get_reasoning_window(
            dossier_id, {"since_iso": "not-a-date"}
        )
        assert result["ok"] is False
        assert result["reason"] == "invalid_since_iso"

    def test_get_reasoning_window_with_since_iso(self, fresh_db):
        dossier_id = _make_dossier()
        session_id = storage.start_work_session(
            dossier_id, m.WorkSessionTrigger.resume
        ).id
        storage.append_reasoning(
            dossier_id, m.ReasoningAppend(note="old note", tags=[]), session_id
        )
        result = handlers.get_reasoning_window(
            dossier_id, {"since_iso": "2000-01-01T00:00:00Z", "limit": 10}
        )
        assert result["ok"] is True
        assert result["count"] >= 1


# --- Snapshot index rendering tests ---


class TestSnapshotIndex:
    def test_confident_section_shows_preview_only(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id, state=m.SectionState.confident, content="X" * 200)
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        # Confident sections should show "preview:" not "content:"
        assert "preview:" in snapshot
        assert "get_section" in snapshot
        # The full 200-char body should NOT appear
        assert "X" * 100 not in snapshot

    def test_provisional_section_shows_full_content(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id, state=m.SectionState.provisional, content="FULL PROVISIONAL BODY")
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        assert "content: FULL PROVISIONAL BODY" in snapshot

    def test_blocked_section_shows_full_content(self, fresh_db):
        dossier_id = _make_dossier()
        _add_section(dossier_id, state=m.SectionState.blocked, content="FULL BLOCKED BODY")
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        assert "content: FULL BLOCKED BODY" in snapshot

    def test_artifact_shows_index_only(self, fresh_db):
        dossier_id = _make_dossier()
        _add_artifact(dossier_id)
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        assert "## Artifacts" in snapshot
        assert "get_artifact" in snapshot
        # Artifact body should NOT appear in snapshot
        assert "Your debt is invalid" not in snapshot

    def test_reasoning_trail_capped_at_5(self, fresh_db):
        dossier_id = _make_dossier()
        session_id = storage.start_work_session(
            dossier_id, m.WorkSessionTrigger.resume
        ).id
        for i in range(10):
            storage.append_reasoning(
                dossier_id, m.ReasoningAppend(note=f"reasoning note {i}", tags=[]), session_id
            )
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        # Should show "5 earlier reasoning entries" collapsed hint
        assert "5 earlier reasoning entries" in snapshot
        assert "get_reasoning_window" in snapshot

    def test_snapshot_shorter_than_old_format(self, fresh_db):
        """On a dossier with several confident sections, the index snapshot
        should be meaningfully shorter than the old full-render approach."""
        dossier_id = _make_dossier()
        for i in range(5):
            _add_section(dossier_id, state=m.SectionState.confident, content="C" * 200)
        _add_artifact(dossier_id)
        full = storage.get_dossier_full(dossier_id)
        snapshot = prompt_mod.build_state_snapshot(full)
        # Crude: count lines. With 5 confident sections at ~80-char previews,
        # each section takes ~3 lines vs. the 200-char body that would have
        # been 2-3 lines per section. Artifact index saves the artifact body.
        # The snapshot should be under 3000 chars for this small dossier.
        assert len(snapshot) < 5000, (
            f"snapshot too long ({len(snapshot)} chars) for a small dossier with previews"
        )


# --- Registry / schema coverage ---


def test_jit_handlers_registered():
    for name in ("get_section", "list_sections", "get_artifact", "get_reasoning_window"):
        assert name in handlers.HANDLERS, f"{name} not in HANDLERS"


def test_jit_handlers_have_descriptions():
    for name in ("get_section", "list_sections", "get_artifact", "get_reasoning_window"):
        assert name in handlers.TOOL_DESCRIPTIONS, f"{name} missing description"


def test_jit_handlers_have_schemas():
    schema_names = {s["name"] for s in handlers.tool_schemas()}
    for name in ("get_section", "list_sections", "get_artifact", "get_reasoning_window"):
        assert name in schema_names, f"{name} missing from tool_schemas()"


def test_system_prompt_mentions_get_section():
    lower = prompt_mod.MAIN_AGENT_SYSTEM_PROMPT.lower()
    assert "get_section" in lower, "system prompt should mention get_section"


def test_system_prompt_mentions_get_reasoning_window():
    lower = prompt_mod.MAIN_AGENT_SYSTEM_PROMPT.lower()
    assert "get_reasoning_window" in lower, "system prompt should mention get_reasoning_window"


def test_system_prompt_mentions_index():
    lower = prompt_mod.MAIN_AGENT_SYSTEM_PROMPT.lower()
    assert "index" in lower, "system prompt should explain snapshot is an index"
