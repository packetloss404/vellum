"""Tests for the Artifacts domain (models + storage + routes + change_log)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Point VELLUM_DB_PATH at a throwaway file and reinit the schema for this test."""
    tmp = Path(tempfile.mkdtemp()) / "vellum_test.db"
    monkeypatch.setenv("VELLUM_DB_PATH", str(tmp))

    # Re-import config so DB_PATH is recomputed from env. Then rebind the module
    # globals in db/storage that captured config at import time.
    import importlib
    from vellum import config, db, storage
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(storage)

    db.init_db()
    yield storage, db
    # Cleanup
    try:
        tmp.unlink()
    except OSError:
        pass


def _make_dossier(storage):
    from vellum import models as m
    return storage.create_dossier(
        m.DossierCreate(
            title="Test dossier",
            problem_statement="Test problem",
            dossier_type=m.DossierType.investigation,
        )
    )


def test_artifact_roundtrip(fresh_db):
    """create -> list -> get -> update -> delete."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)

    # Create
    art = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(
            kind=m.ArtifactKind.letter,
            title="Hardship letter to Citibank",
            content="# Draft letter\n\nDear Citibank...",
            intended_use="Send after initial call; CC'd to friend.",
            state=m.ArtifactState.draft,
        ),
    )
    assert art.id.startswith("art_")
    assert art.dossier_id == dossier.id
    assert art.kind == m.ArtifactKind.letter
    assert art.state == m.ArtifactState.draft
    assert art.created_at == art.last_updated

    # List
    listed = storage.list_artifacts(dossier.id)
    assert len(listed) == 1
    assert listed[0].id == art.id

    # Get
    got = storage.get_artifact(art.id)
    assert got is not None
    assert got.title == "Hardship letter to Citibank"
    assert got.content.startswith("# Draft letter")

    # Update
    updated = storage.update_artifact(
        dossier.id,
        art.id,
        m.ArtifactUpdate(
            content="# Revised letter\n\nDear Citibank...",
            state=m.ArtifactState.ready,
            change_note="Tightened opening paragraph; promoted to ready.",
        ),
    )
    assert updated is not None
    assert updated.content.startswith("# Revised letter")
    assert updated.state == m.ArtifactState.ready
    assert updated.last_updated >= updated.created_at

    # Delete
    assert storage.delete_artifact(dossier.id, art.id) is True
    assert storage.get_artifact(art.id) is None
    assert storage.list_artifacts(dossier.id) == []


def test_artifact_added_change_log(fresh_db):
    """change_log gets an `artifact_added` entry when work_session_id is supplied on create."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)
    ws = storage.start_work_session(dossier.id)

    storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(
            kind=m.ArtifactKind.checklist,
            title="Call prep checklist",
        ),
        work_session_id=ws.id,
    )

    entries = storage.list_change_log_for_session(dossier.id, ws.id)
    added = [e for e in entries if e.kind == "artifact_added"]
    assert len(added) == 1
    assert "Call prep checklist" in added[0].change_note


def test_artifact_updated_change_log_uses_change_note(fresh_db):
    """change_log's artifact_updated entry uses the user-supplied change_note verbatim."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)
    ws = storage.start_work_session(dossier.id)

    art = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(kind=m.ArtifactKind.script, title="Opening script"),
        work_session_id=ws.id,
    )

    storage.update_artifact(
        dossier.id,
        art.id,
        m.ArtifactUpdate(
            content="Hello, I'm calling about my mother's account...",
            change_note="Added opening two sentences per spouse feedback.",
        ),
        work_session_id=ws.id,
    )

    entries = storage.list_change_log_for_session(dossier.id, ws.id)
    updated = [e for e in entries if e.kind == "artifact_updated"]
    assert len(updated) == 1
    assert updated[0].change_note == "Added opening two sentences per spouse feedback."


def test_get_dossier_full_includes_artifacts(fresh_db):
    """DossierFull aggregate includes the artifacts collection."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)
    art = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(kind=m.ArtifactKind.timeline, title="Contact timeline"),
    )

    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    assert len(full.artifacts) == 1
    assert full.artifacts[0].id == art.id
    assert full.artifacts[0].kind == m.ArtifactKind.timeline


def test_fk_cascade_on_dossier_delete(fresh_db):
    """Deleting a dossier removes its artifacts via ON DELETE CASCADE."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)
    art = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(kind=m.ArtifactKind.offer, title="Opening offer"),
    )
    assert storage.get_artifact(art.id) is not None

    assert storage.delete_dossier(dossier.id) is True
    assert storage.get_artifact(art.id) is None


def test_kind_other_persists_kind_note_and_supersedes(fresh_db):
    """kind=other persists kind_note; supersedes pointer persists."""
    storage, _ = fresh_db
    from vellum import models as m

    dossier = _make_dossier(storage)

    first = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(
            kind=m.ArtifactKind.letter,
            title="V1 letter",
        ),
    )

    second = storage.create_artifact(
        dossier.id,
        m.ArtifactCreate(
            kind=m.ArtifactKind.other,
            title="Hybrid FAQ/letter combo",
            kind_note="Doubles as an FAQ handed over at the meeting.",
            supersedes=first.id,
        ),
    )

    refetched = storage.get_artifact(second.id)
    assert refetched is not None
    assert refetched.kind == m.ArtifactKind.other
    assert refetched.kind_note == "Doubles as an FAQ handed over at the meeting."
    assert refetched.supersedes == first.id
