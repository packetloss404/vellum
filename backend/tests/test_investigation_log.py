"""Tests for the investigation_log domain (v2 day-1 storage surface).

The investigation_log is the "47 sources consulted" evidence-of-work counter:
typed, append-only, separate from reasoning_trail (v1 narrative) and change_log
(user-visit-diff). It is NOT supposed to write to change_log.
"""
from __future__ import annotations

import sqlite3

import pytest


# conftest.py owns the VELLUM_DB_PATH / init_db setup via the `fresh_db` fixture.


def _mk_dossier():
    from vellum import models as m, storage
    return storage.create_dossier(
        m.DossierCreate(
            title="test dossier",
            problem_statement="test problem",
            dossier_type=m.DossierType.investigation,
        )
    )


def test_append_and_list_in_order(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()

    types = [
        m.InvestigationLogEntryType.source_consulted,
        m.InvestigationLogEntryType.sub_investigation_spawned,
        m.InvestigationLogEntryType.section_upserted,
        m.InvestigationLogEntryType.source_consulted,
    ]
    ids = []
    for i, t in enumerate(types):
        entry = storage.append_investigation_log(
            dossier.id,
            m.InvestigationLogAppend(
                entry_type=t,
                payload={"i": i, "url": f"https://example.com/{i}"},
                summary=f"entry {i}",
            ),
        )
        assert entry.id.startswith("ilg_")
        assert entry.dossier_id == dossier.id
        assert entry.payload["i"] == i
        ids.append(entry.id)

    listed = storage.list_investigation_log(dossier.id)
    assert [e.id for e in listed] == ids
    # Payload roundtrips correctly through JSON.
    assert listed[0].payload == {"i": 0, "url": "https://example.com/0"}
    # entry_type came back as the Enum.
    assert listed[0].entry_type == m.InvestigationLogEntryType.source_consulted


def test_counts_by_type(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()

    spec = {
        m.InvestigationLogEntryType.source_consulted: 5,
        m.InvestigationLogEntryType.sub_investigation_spawned: 2,
        m.InvestigationLogEntryType.section_upserted: 3,
        m.InvestigationLogEntryType.artifact_added: 1,
    }
    for t, n in spec.items():
        for i in range(n):
            storage.append_investigation_log(
                dossier.id,
                m.InvestigationLogAppend(entry_type=t, summary=f"{t.value} {i}"),
            )

    counts = storage.count_investigation_log_by_type(dossier.id)
    assert counts == {t.value: n for t, n in spec.items()}


def test_filter_by_entry_type(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()

    storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted,
            summary="a",
        ),
    )
    storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted,
            summary="b",
        ),
    )
    storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.stuck_declared,
            summary="c",
        ),
    )

    sources = storage.list_investigation_log(
        dossier.id, entry_type=m.InvestigationLogEntryType.source_consulted
    )
    assert len(sources) == 2
    assert all(
        e.entry_type == m.InvestigationLogEntryType.source_consulted for e in sources
    )

    stuck = storage.list_investigation_log(
        dossier.id, entry_type=m.InvestigationLogEntryType.stuck_declared
    )
    assert len(stuck) == 1
    assert stuck[0].summary == "c"


def test_does_not_write_change_log(fresh_db):
    """investigation_log is evidence-of-work; change_log is user-visit-diff.
    The two surfaces are deliberately separate."""
    from vellum import models as m, storage

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id)

    storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted,
            summary="consulted a source",
        ),
        work_session_id=session.id,
    )

    # Nothing should appear in change_log from a bare investigation_log append.
    changes = storage.list_change_log_for_session(dossier.id, session.id)
    assert changes == []


def test_work_session_id_and_sub_investigation_id_persisted(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id)

    entry = storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.sub_investigation_spawned,
            summary="spawned sub",
            sub_investigation_id="sub_abc",
        ),
        work_session_id=session.id,
    )
    assert entry.work_session_id == session.id
    assert entry.sub_investigation_id == "sub_abc"

    reloaded = storage.list_investigation_log(dossier.id)[0]
    assert reloaded.work_session_id == session.id
    assert reloaded.sub_investigation_id == "sub_abc"


def test_dossier_full_includes_investigation_log(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    for i in range(3):
        storage.append_investigation_log(
            dossier.id,
            m.InvestigationLogAppend(
                entry_type=m.InvestigationLogEntryType.source_consulted,
                summary=f"s{i}",
            ),
        )
    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    assert len(full.investigation_log) == 3
    assert [e.summary for e in full.investigation_log] == ["s0", "s1", "s2"]


def test_fk_cascade_on_dossier_delete(fresh_db):
    from vellum import models as m, storage
    from vellum.db import connect

    dossier = _mk_dossier()
    storage.append_investigation_log(
        dossier.id,
        m.InvestigationLogAppend(
            entry_type=m.InvestigationLogEntryType.source_consulted, summary="x"
        ),
    )
    with connect() as conn:
        n_before = conn.execute(
            "SELECT COUNT(*) AS n FROM investigation_log WHERE dossier_id = ?",
            (dossier.id,),
        ).fetchone()["n"]
    assert n_before == 1

    storage.delete_dossier(dossier.id)

    with connect() as conn:
        n_after = conn.execute(
            "SELECT COUNT(*) AS n FROM investigation_log WHERE dossier_id = ?",
            (dossier.id,),
        ).fetchone()["n"]
    assert n_after == 0
