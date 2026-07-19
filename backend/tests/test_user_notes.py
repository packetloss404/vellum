"""User notes: "tell the agent something" mid-investigation.

Covers vellum/storage/user_note_store.py and its wiring:

  * create_user_note rides the reactive-wake pipeline (wake_pending flips in
    the same transaction, gated on sleep_mode_enabled)
  * build_state_snapshot surfaces unseen notes and hides seen ones
  * runtime marks surfaced notes seen on a healthy end, leaves them unseen
    on an errored end (so the self-heal retry re-surfaces them)
  * POST/GET /api/dossiers/{id}/notes
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------- helpers ----------


def _mk_dossier(title: str = "User notes test dossier") -> str:
    from vellum import models as m, storage

    return storage.create_dossier(
        m.DossierCreate(
            title=title,
            problem_statement="Exercise the user-note path.",
            dossier_type=m.DossierType.investigation,
        )
    ).id


def _add_note(dossier_id: str, content: str):
    from vellum import models as m, storage

    return storage.create_user_note(dossier_id, m.UserNoteCreate(content=content))


def _wake_state(dossier_id: str) -> dict:
    from vellum import storage

    state = storage.get_dossier_wake_state(dossier_id)
    assert state is not None
    return state


def _snapshot(dossier_id: str) -> str:
    from vellum import storage
    from vellum.agent import prompt as prompt_mod

    return prompt_mod.build_state_snapshot(storage.get_dossier_full(dossier_id))


def _make_scripted_agent(dossier_id: str, *, error: bool = False):
    """DossierAgent whose model either ends the turn cleanly or raises."""
    from vellum.agent import runtime as rt

    def _stream(**kwargs: Any) -> Any:
        if error:
            raise RuntimeError("simulated transient API failure")
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

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
    agent = rt.DossierAgent(dossier_id=dossier_id, model="mock-model")
    agent._client = client
    return agent


# ---------- storage ----------


def test_create_note_persists_and_wakes(fresh_db):
    from vellum import models as m, storage

    did = _mk_dossier()
    note = _add_note(did, "I found the original loan letter — it says 4.2%, not 6%.")

    assert note.id.startswith("un")
    assert note.seen_at is None

    listed = storage.list_user_notes(did)
    assert [n.id for n in listed] == [note.id]

    wake = _wake_state(did)
    assert wake["wake_pending"] is True
    assert wake["wake_reason"] == m.WakeReason.user_note.value

    # The visit diff sees it too.
    full = storage.get_dossier_full(did)
    assert [n.id for n in full.user_notes] == [note.id]


def test_create_note_sleep_mode_off_does_not_wake(fresh_db):
    from vellum import storage

    storage.set_setting("sleep_mode_enabled", False)
    did = _mk_dossier()
    _add_note(did, "note while sleep mode is off")

    wake = _wake_state(did)
    assert wake["wake_pending"] is False


def test_mark_seen_only_stamps_unseen(fresh_db):
    from vellum import storage

    did = _mk_dossier()
    a = _add_note(did, "first")
    b = _add_note(did, "second")

    assert storage.mark_user_notes_seen([a.id]) == 1
    first_seen = storage.list_user_notes(did)[0].seen_at
    assert first_seen is not None

    # Re-stamping a seen note is a no-op; the unseen one still stamps.
    assert storage.mark_user_notes_seen([a.id, b.id]) == 1
    assert storage.list_user_notes(did)[0].seen_at == first_seen

    assert storage.list_user_notes(did, unseen_only=True) == []


# ---------- prompt snapshot ----------


def test_snapshot_surfaces_unseen_notes_only(fresh_db):
    from vellum import storage

    did = _mk_dossier()
    assert "New notes from the user" not in _snapshot(did)

    note = _add_note(did, "The creditor called back and offered a settlement.")
    snap = _snapshot(did)
    assert "New notes from the user (1)" in snap
    assert "The creditor called back" in snap
    assert note.id in snap

    storage.mark_user_notes_seen([note.id])
    assert "New notes from the user" not in _snapshot(did)


# ---------- runtime wiring ----------


def test_healthy_session_marks_surfaced_notes_seen(fresh_db):
    from vellum import storage

    did = _mk_dossier()
    note = _add_note(did, "new fact")

    agent = _make_scripted_agent(did)
    result = asyncio.run(agent.run(max_turns=3))

    assert result.reason == "ended_turn"
    assert storage.list_user_notes(did)[0].seen_at is not None
    assert note.id in agent._surfaced_note_ids


def test_errored_session_leaves_notes_unseen(fresh_db):
    from vellum import storage

    did = _mk_dossier()
    _add_note(did, "new fact")

    agent = _make_scripted_agent(did, error=True)
    result = asyncio.run(agent.run(max_turns=3))

    assert result.reason == "error"
    # The note survives for the self-heal retry to re-surface.
    assert storage.list_user_notes(did)[0].seen_at is None


# ---------- API ----------


@pytest.fixture
def client(fresh_db):
    from fastapi.testclient import TestClient
    from vellum.main import create_app

    app = create_app()
    with TestClient(app) as tc:
        yield tc


def test_post_and_get_notes(client):
    did = _mk_dossier()

    resp = client.post(
        f"/api/dossiers/{did}/notes",
        json={"content": "Also check the state statute of limitations."},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"].startswith("Also check")
    assert body["seen_at"] is None

    listed = client.get(f"/api/dossiers/{did}/notes")
    assert listed.status_code == 200
    assert [n["id"] for n in listed.json()] == [body["id"]]


def test_post_note_missing_dossier_404(client):
    resp = client.post("/api/dossiers/dos_nope/notes", json={"content": "hi"})
    assert resp.status_code == 404


def test_post_note_empty_content_422(client):
    did = _mk_dossier()
    resp = client.post(f"/api/dossiers/{did}/notes", json={"content": ""})
    assert resp.status_code == 422
