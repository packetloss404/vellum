"""Tests for the considered_and_rejected domain (v2 day-1 storage surface).

considered_and_rejected is the richer cousin of ruled_out: the agent records the
path it considered, why it was compelling, why it was rejected, and the
cost-of-error if the rejection turns out wrong. Every add also appends a
`path_rejected` investigation_log entry so the counts-of-work surface stays
in sync.
"""
from __future__ import annotations

import pytest


def _mk_dossier():
    from vellum import models as m, storage
    return storage.create_dossier(
        m.DossierCreate(
            title="test dossier",
            problem_statement="test problem",
            dossier_type=m.DossierType.investigation,
        )
    )


def test_add_and_roundtrip_preserves_all_fields(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()

    sources = [
        m.Source(
            kind=m.SourceKind.web,
            url="https://example.com/article",
            title="The paper that almost fooled me",
            snippet="claims X without evidence",
        ),
        m.Source(
            kind=m.SourceKind.reasoning,
            title="my own prior",
        ),
    ]
    item = storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path="Treat X as the load-bearing assumption",
            why_compelling="Elegant, fits the data at first glance, common framing in literature",
            why_rejected="X fails on 3 of the 7 edge cases; assumption is not load-bearing after all",
            cost_of_error="If X really is load-bearing, we under-weight the whole analysis by ~30%",
            sources=sources,
            sub_investigation_id="sub_123",
        ),
    )

    assert item.id.startswith("crj_")
    assert item.dossier_id == dossier.id
    assert item.path == "Treat X as the load-bearing assumption"
    assert item.cost_of_error.startswith("If X really is load-bearing")
    assert item.sub_investigation_id == "sub_123"
    assert len(item.sources) == 2
    assert item.sources[0].url == "https://example.com/article"
    assert item.sources[1].kind == m.SourceKind.reasoning

    # Reload via list — everything should roundtrip.
    listed = storage.list_considered_and_rejected(dossier.id)
    assert len(listed) == 1
    got = listed[0]
    assert got.id == item.id
    assert got.path == item.path
    assert got.why_compelling == item.why_compelling
    assert got.why_rejected == item.why_rejected
    assert got.cost_of_error == item.cost_of_error
    assert got.sub_investigation_id == "sub_123"
    assert [s.model_dump() for s in got.sources] == [s.model_dump() for s in sources]


def test_list_ordered_by_created_at(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()

    paths = ["first path", "second path", "third path"]
    for p in paths:
        storage.add_considered_and_rejected(
            dossier.id,
            m.ConsideredAndRejectedCreate(
                path=p, why_compelling="c", why_rejected="r"
            ),
        )

    listed = storage.list_considered_and_rejected(dossier.id)
    assert [c.path for c in listed] == paths


def test_cost_of_error_defaults_to_empty(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    item = storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path="p", why_compelling="c", why_rejected="r"
        ),
    )
    assert item.cost_of_error == ""
    assert item.sources == []


def test_adding_cr_also_appends_investigation_log(fresh_db):
    """Each C&R add should also push a `path_rejected` entry into the
    investigation_log so the "paths considered" counter stays in sync."""
    from vellum import models as m, storage

    dossier = _mk_dossier()
    path = "reframe around X instead"
    storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path=path, why_compelling="c", why_rejected="r"
        ),
    )

    log = storage.list_investigation_log(dossier.id)
    assert len(log) == 1
    entry = log[0]
    assert entry.dossier_id == dossier.id
    assert entry.entry_type == m.InvestigationLogEntryType.path_rejected
    assert path in entry.summary

    # And the counts endpoint sees it.
    counts = storage.count_investigation_log_by_type(dossier.id)
    assert counts.get("path_rejected") == 1


def test_change_log_written_when_work_session_supplied(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    session = storage.start_work_session(dossier.id)

    storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path="p1", why_compelling="c", why_rejected="r"
        ),
        work_session_id=session.id,
    )

    changes = storage.list_change_log_for_session(dossier.id, session.id)
    kinds = [c.kind for c in changes]
    assert "considered_and_rejected_added" in kinds


def test_change_log_skipped_without_work_session(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path="p", why_compelling="c", why_rejected="r"
        ),
    )
    # No session → no change_log entry. (This mirrors v1 behavior in
    # storage._log_change — without a session, nothing is written.)
    from vellum.db import connect
    with connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM change_log WHERE dossier_id = ?",
            (dossier.id,),
        ).fetchone()["n"]
    assert n == 0


def test_dossier_full_includes_considered_and_rejected(fresh_db):
    from vellum import models as m, storage

    dossier = _mk_dossier()
    storage.add_considered_and_rejected(
        dossier.id,
        m.ConsideredAndRejectedCreate(
            path="p", why_compelling="c", why_rejected="r"
        ),
    )
    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    assert len(full.considered_and_rejected) == 1
    assert full.considered_and_rejected[0].path == "p"
