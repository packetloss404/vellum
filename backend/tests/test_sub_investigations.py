"""Tests for the sub-investigations domain.

Uses the VELLUM_DB_PATH tempfile pattern (see lifecycle.py __main__): a fresh
throwaway DB per test module so we don't pollute the real vellum.db.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Must be set BEFORE importing vellum modules so config.DB_PATH picks it up.
os.environ["VELLUM_DB_PATH"] = tempfile.mktemp(suffix=".db")

from vellum import db, storage  # noqa: E402
from vellum import models as m  # noqa: E402


@pytest.fixture(autouse=True)
def _init_db():
    """Re-init the DB schema before each test and wipe tables clean.

    Each test needs a fresh state, but re-pointing VELLUM_DB_PATH on every
    test is fragile because sqlite creates WAL files; instead we truncate.
    """
    db.init_db()
    with db.connect() as conn:
        # ORDER matters only insofar as FK cascades need parents present;
        # for DELETE we can just wipe leaves first.
        for table in (
            "change_log",
            "sub_investigations",
            "reasoning_trail",
            "ruled_out",
            "decision_points",
            "needs_input",
            "sections",
            "work_sessions",
            "dossiers",
            "intake_messages",
            "intake_sessions",
        ):
            conn.execute(f"DELETE FROM {table}")
    yield


def _make_dossier() -> m.Dossier:
    return storage.create_dossier(
        m.DossierCreate(
            title="Estate debt question",
            problem_statement="Sub-investigations test dossier.",
            dossier_type=m.DossierType.investigation,
        )
    )


def _start_session(dossier_id: str) -> m.WorkSession:
    return storage.start_work_session(dossier_id, m.WorkSessionTrigger.manual)


def test_spawn_list_get_roundtrip():
    dossier = _make_dossier()
    session = _start_session(dossier.id)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(
            scope="What does Texas law say about unsecured debt passing to heirs?",
            questions=[
                "Is TX a community-property state for debt?",
                "Does surviving-spouse status matter here?",
            ],
            parent_section_id=None,
        ),
        work_session_id=session.id,
    )
    assert sub.id.startswith("sub_")
    assert sub.state == m.SubInvestigationState.running
    assert sub.completed_at is None
    assert sub.return_summary is None
    assert len(sub.questions) == 2

    # list: running-only filter returns it
    running = storage.list_sub_investigations(
        dossier.id, state=m.SubInvestigationState.running
    )
    assert [s.id for s in running] == [sub.id]

    # list: unfiltered also contains it
    allsubs = storage.list_sub_investigations(dossier.id)
    assert [s.id for s in allsubs] == [sub.id]

    # list: delivered-only filter is empty
    delivered = storage.list_sub_investigations(
        dossier.id, state=m.SubInvestigationState.delivered
    )
    assert delivered == []

    # get: roundtrip matches
    got = storage.get_sub_investigation(sub.id)
    assert got is not None
    assert got.id == sub.id
    assert got.scope == sub.scope
    assert got.questions == sub.questions
    assert got.state == m.SubInvestigationState.running


def test_complete_sub_investigation():
    dossier = _make_dossier()
    session = _start_session(dossier.id)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="FDCPA + estate debt interaction"),
        work_session_id=session.id,
    )

    completed = storage.complete_sub_investigation(
        dossier.id,
        sub.id,
        m.SubInvestigationComplete(
            return_summary=(
                "Heirs are not personally liable absent co-signing; FDCPA bars collectors "
                "from implying they are."
            ),
            findings_section_ids=["sec_abc", "sec_def"],
            findings_artifact_ids=["art_123"],
        ),
        work_session_id=session.id,
    )
    assert completed is not None
    assert completed.state == m.SubInvestigationState.delivered
    assert completed.return_summary.startswith("Heirs are not personally liable")
    assert completed.findings_section_ids == ["sec_abc", "sec_def"]
    assert completed.findings_artifact_ids == ["art_123"]
    assert completed.completed_at is not None

    # persisted
    fetched = storage.get_sub_investigation(sub.id)
    assert fetched is not None
    assert fetched.state == m.SubInvestigationState.delivered
    assert fetched.return_summary == completed.return_summary
    assert fetched.completed_at is not None


def test_update_state_to_blocked():
    dossier = _make_dossier()
    session = _start_session(dossier.id)
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="Compare scenarios A/B/C"),
        work_session_id=session.id,
    )

    updated = storage.update_sub_investigation_state(
        dossier.id,
        sub.id,
        m.SubInvestigationStateUpdate(
            new_state=m.SubInvestigationState.blocked,
            reason="Need user to decide scenario weighting before proceeding.",
        ),
        work_session_id=session.id,
    )
    assert updated is not None
    assert updated.state == m.SubInvestigationState.blocked
    # blocked is not a terminal state — completed_at should NOT be set here.
    assert updated.completed_at is None

    # Change log recorded the state change (as `state_changed`).
    changes = storage.list_change_log_for_session(dossier.id, session.id)
    state_changes = [c for c in changes if c.kind == "state_changed"]
    assert any("blocked" in c.change_note for c in state_changes)


def test_abandon_sub_investigation():
    dossier = _make_dossier()
    session = _start_session(dossier.id)
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="Explore obscure state-specific carveout"),
        work_session_id=session.id,
    )

    abandoned = storage.abandon_sub_investigation(
        dossier.id,
        sub.id,
        reason="No longer in scope after reframing.",
        work_session_id=session.id,
    )
    assert abandoned is not None
    assert abandoned.state == m.SubInvestigationState.abandoned
    assert abandoned.completed_at is not None

    fetched = storage.get_sub_investigation(sub.id)
    assert fetched is not None
    assert fetched.state == m.SubInvestigationState.abandoned


def test_change_log_entries():
    dossier = _make_dossier()
    session = _start_session(dossier.id)

    sub1 = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="scope-1"),
        work_session_id=session.id,
    )
    sub2 = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="scope-2"),
        work_session_id=session.id,
    )

    storage.complete_sub_investigation(
        dossier.id,
        sub1.id,
        m.SubInvestigationComplete(return_summary="done"),
        work_session_id=session.id,
    )
    storage.abandon_sub_investigation(
        dossier.id,
        sub2.id,
        reason="out of scope",
        work_session_id=session.id,
    )

    kinds = [c.kind for c in storage.list_change_log_for_session(dossier.id, session.id)]
    assert kinds.count("sub_investigation_spawned") == 2
    assert kinds.count("sub_investigation_completed") == 1
    assert kinds.count("sub_investigation_abandoned") == 1


def test_get_dossier_full_includes_sub_investigations():
    dossier = _make_dossier()
    session = _start_session(dossier.id)
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="scope-in-full"),
        work_session_id=session.id,
    )

    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    assert hasattr(full, "sub_investigations")
    assert [s.id for s in full.sub_investigations] == [sub.id]


def test_fk_cascade_on_dossier_delete():
    dossier = _make_dossier()
    session = _start_session(dossier.id)
    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="will-be-cascaded"),
        work_session_id=session.id,
    )
    assert storage.get_sub_investigation(sub.id) is not None

    ok = storage.delete_dossier(dossier.id)
    assert ok is True

    # Sub-investigation row should be gone via ON DELETE CASCADE.
    assert storage.get_sub_investigation(sub.id) is None
    assert storage.list_sub_investigations(dossier.id) == []


def test_list_ordered_by_started_at():
    dossier = _make_dossier()
    session = _start_session(dossier.id)

    s1 = storage.spawn_sub_investigation(
        dossier.id, m.SubInvestigationSpawn(scope="first"), work_session_id=session.id
    )
    s2 = storage.spawn_sub_investigation(
        dossier.id, m.SubInvestigationSpawn(scope="second"), work_session_id=session.id
    )
    s3 = storage.spawn_sub_investigation(
        dossier.id, m.SubInvestigationSpawn(scope="third"), work_session_id=session.id
    )

    ordered = storage.list_sub_investigations(dossier.id)
    assert [s.id for s in ordered] == [s1.id, s2.id, s3.id]


def test_spawn_without_work_session_does_not_log():
    """Matches v1 convention: no work_session_id => no change_log row."""
    dossier = _make_dossier()
    sub = storage.spawn_sub_investigation(
        dossier.id, m.SubInvestigationSpawn(scope="sessionless")
    )
    assert sub.state == m.SubInvestigationState.running

    # No session => no change_log entry for this spawn.
    with db.connect() as conn:
        row_count = conn.execute(
            "SELECT COUNT(*) AS c FROM change_log WHERE dossier_id = ?",
            (dossier.id,),
        ).fetchone()["c"]
    assert row_count == 0


def test_operations_on_wrong_dossier_return_none():
    dossier_a = _make_dossier()
    dossier_b = _make_dossier()
    session_a = _start_session(dossier_a.id)

    sub = storage.spawn_sub_investigation(
        dossier_a.id,
        m.SubInvestigationSpawn(scope="belongs-to-a"),
        work_session_id=session_a.id,
    )

    # complete/update/abandon scoped to the wrong dossier must return None
    assert storage.complete_sub_investigation(
        dossier_b.id,
        sub.id,
        m.SubInvestigationComplete(return_summary="nope"),
    ) is None
    assert storage.update_sub_investigation_state(
        dossier_b.id,
        sub.id,
        m.SubInvestigationStateUpdate(
            new_state=m.SubInvestigationState.blocked, reason="x"
        ),
    ) is None
    assert storage.abandon_sub_investigation(dossier_b.id, sub.id, reason="x") is None
