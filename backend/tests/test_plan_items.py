"""Phase 4B: plan_items normalization tests.

Covers:
- CRUD on plan_items table
- Status transitions (set_plan_item_status)
- bulk_replace_plan_items (full replacement semantics)
- Migration: legacy JSON blob → plan_items table
- get_dossier / get_dossier_full populate items from plan_items table
- _set_plan_item_status direct UPDATE (replaces read-modify-write)
- finalize_plan_on_delivery operates on plan_items table
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

from vellum import models as m


@pytest.fixture
def fresh_db(monkeypatch):
    tmpdir = Path(tempfile.gettempdir()) / "vellum_tests"
    tmpdir.mkdir(parents=True, exist_ok=True)
    import uuid, time
    db_path = tmpdir / f"test_plan_{os.getpid()}_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("VELLUM_DB_PATH", str(db_path))

    from vellum import config as _config
    from vellum import db as _db
    monkeypatch.setattr(_config, "DB_PATH", db_path)
    _db.init_db(db_path)

    from vellum import storage
    yield storage, _db, db_path

    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suffix)
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def _make_dossier(storage):
    return storage.create_dossier(
        m.DossierCreate(
            title="Plan items test",
            problem_statement="Test plan items CRUD",
            dossier_type=m.DossierType.investigation,
        )
    )


def _draft_plan(storage, dossier_id: str, session_id: str | None = None, n: int = 2):
    items = [
        m.PlanItem(question=f"Q{i+1}", rationale=f"why{i+1}", id=f"pli_test_{i+1}")
        for i in range(n)
    ]
    return storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(items=items, rationale="test plan", approve=False),
        session_id,
    )


# ---------- CRUD ----------


def test_list_plan_items_empty(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    items = storage.list_plan_items(dossier.id)
    assert items == []


def test_update_investigation_plan_creates_plan_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=3)

    items = storage.list_plan_items(dossier.id)
    assert len(items) == 3
    assert items[0].question == "Q1"
    assert items[1].question == "Q2"
    assert items[2].question == "Q3"
    # Items should be ordered by order_key
    assert items[0].order_key < items[1].order_key < items[2].order_key


def test_get_plan_item(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    item = storage.get_plan_item(dossier.id, "pli_test_1")
    assert item is not None
    assert item.question == "Q1"
    assert item.rationale == "why1"

    missing = storage.get_plan_item(dossier.id, "nonexistent")
    assert missing is None


def test_get_plan_item_by_id(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    item = storage.get_plan_item_by_id("pli_test_2")
    assert item is not None
    assert item.question == "Q2"


def test_upsert_plan_item(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)

    item = m.PlanItem(id="pli_upsert_1", dossier_id=dossier.id, question="Upsert Q")
    storage.upsert_plan_item(dossier.id, item)
    fetched = storage.get_plan_item(dossier.id, "pli_upsert_1")
    assert fetched is not None
    assert fetched.question == "Upsert Q"

    # Upsert (update)
    updated = m.PlanItem(id="pli_upsert_1", dossier_id=dossier.id, question="Updated Q", rationale="new")
    storage.upsert_plan_item(dossier.id, updated)
    fetched2 = storage.get_plan_item(dossier.id, "pli_upsert_1")
    assert fetched2.question == "Updated Q"
    assert fetched2.rationale == "new"


def test_bulk_replace_plan_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)

    # Create initial items
    _draft_plan(storage, dossier.id, session.id, n=3)
    assert len(storage.list_plan_items(dossier.id)) == 3

    # Bulk replace with 2 new items
    new_items = [
        m.PlanItem(id="pli_new_1", question="New Q1", rationale="new1"),
        m.PlanItem(id="pli_new_2", question="New Q2", rationale="new2"),
    ]
    result = storage.bulk_replace_plan_items(dossier.id, new_items)
    assert len(result) == 2

    # Old items are gone
    items = storage.list_plan_items(dossier.id)
    assert len(items) == 2
    assert items[0].question == "New Q1"
    assert items[1].question == "New Q2"

    # Old plan item IDs no longer exist
    assert storage.get_plan_item(dossier.id, "pli_test_1") is None


# ---------- Status transitions ----------


def test_set_plan_item_status(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    # Flip to in_progress
    result = storage.set_plan_item_status(dossier.id, "pli_test_1", "in_progress")
    assert result is not None
    assert result.status == m.PlanItemStatus.in_progress

    # Flip to completed
    result2 = storage.set_plan_item_status(dossier.id, "pli_test_1", "completed")
    assert result2.status == m.PlanItemStatus.completed

    # Flip to abandoned
    result3 = storage.set_plan_item_status(dossier.id, "pli_test_2", "abandoned")
    assert result3.status == m.PlanItemStatus.abandoned

    # Nonexistent item
    result4 = storage.set_plan_item_status(dossier.id, "nonexistent", "completed")
    assert result4 is None


def test_set_plan_item_status_with_blocked_reason(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=1)

    result = storage.set_plan_item_status(
        dossier.id, "pli_test_1", "blocked", blocked_reason="Missing data"
    )
    assert result is not None
    assert result.status == m.PlanItemStatus.blocked
    assert result.blocked_reason == "Missing data"


# ---------- get_dossier / get_dossier_full populate from plan_items ----------


def test_get_dossier_populates_plan_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    fetched = storage.get_dossier(dossier.id)
    assert fetched is not None
    assert fetched.investigation_plan is not None
    assert len(fetched.investigation_plan.items) == 2
    assert fetched.investigation_plan.items[0].question == "Q1"


def test_get_dossier_full_populates_plan_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    full = storage.get_dossier_full(dossier.id)
    assert full is not None
    assert full.dossier.investigation_plan is not None
    assert len(full.dossier.investigation_plan.items) == 2


def test_update_investigation_plan_replaces_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    # Replace with 1 item
    new_items = [m.PlanItem(id="pli_replaced_1", question="Replaced Q", rationale="r")]
    storage.update_investigation_plan(
        dossier.id,
        m.InvestigationPlanUpdate(items=new_items, rationale="revised", approve=False),
        session.id,
    )

    fetched = storage.get_dossier(dossier.id)
    assert len(fetched.investigation_plan.items) == 1
    assert fetched.investigation_plan.items[0].question == "Replaced Q"

    # Old items gone from table
    assert storage.get_plan_item(dossier.id, "pli_test_1") is None


# ---------- _set_plan_item_status via sub-investigation ----------


def test_spawn_sub_flips_plan_item_to_in_progress(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(
            scope="Test sub",
            plan_item_id="pli_test_1",
        ),
        session.id,
    )

    item = storage.get_plan_item(dossier.id, "pli_test_1")
    assert item is not None
    assert item.status == m.PlanItemStatus.in_progress


def test_complete_sub_flips_plan_item_to_completed(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="Test sub", plan_item_id="pli_test_1"),
        session.id,
    )

    storage.complete_sub_investigation(
        dossier.id,
        sub.id,
        m.SubInvestigationComplete(return_summary="Done"),
        session.id,
    )

    item = storage.get_plan_item(dossier.id, "pli_test_1")
    assert item.status == m.PlanItemStatus.completed


def test_abandon_sub_flips_plan_item_to_abandoned(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=2)

    sub = storage.spawn_sub_investigation(
        dossier.id,
        m.SubInvestigationSpawn(scope="Test sub", plan_item_id="pli_test_1"),
        session.id,
    )

    storage.abandon_sub_investigation(dossier.id, sub.id, "Not needed", session.id)

    item = storage.get_plan_item(dossier.id, "pli_test_1")
    assert item.status == m.PlanItemStatus.abandoned


# ---------- finalize_plan_on_delivery ----------


def test_finalize_plan_on_delivery_sweeps_items(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=3)

    # Flip one to in_progress
    storage.set_plan_item_status(dossier.id, "pli_test_1", "in_progress")
    # Flip one to completed
    storage.set_plan_item_status(dossier.id, "pli_test_2", "completed")

    result = storage.finalize_plan_on_delivery(dossier.id, session.id)
    # pli_test_1: in_progress → completed (1 from_in_progress)
    # pli_test_2: already completed (no change)
    # pli_test_3: planned → completed (1 from_planned)
    assert result["items_flipped"] == 2
    assert result["from_planned"] == 1
    assert result["from_in_progress"] == 1

    items = storage.list_plan_items(dossier.id)
    for item in items:
        assert item.status in (m.PlanItemStatus.completed, m.PlanItemStatus.abandoned)


def test_finalize_plan_on_delivery_no_plan(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    # No plan drafted — finalize should be a no-op
    result = storage.finalize_plan_on_delivery(dossier.id, session.id)
    assert result["items_flipped"] == 0


# ---------- Migration: legacy JSON → plan_items ----------


def test_migration_from_json_blob(fresh_db):
    storage, db_mod, db_path = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)

    # Write plan directly to the JSON blob (bypassing update_investigation_plan)
    plan = m.InvestigationPlan(
        items=[
            m.PlanItem(id="pli_old_1", question="Old Q1", rationale="old1"),
            m.PlanItem(id="pli_old_2", question="Old Q2", rationale="old2", status=m.PlanItemStatus.in_progress),
        ],
        rationale="legacy plan",
        drafted_at=m.utc_now(),
    )
    from vellum.db import connect
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (plan.model_dump_json(), dossier.id),
        )
        # Clear the migration flag so it re-runs
        conn.execute("DELETE FROM settings WHERE key = 'plan_items_migrated'")

    # Verify plan_items is empty
    assert len(storage.list_plan_items(dossier.id)) == 0

    # Run migration by re-calling init_db
    db_mod.init_db(db_path)

    # Now plan_items should have the migrated items
    items = storage.list_plan_items(dossier.id)
    assert len(items) == 2
    assert items[0].question == "Old Q1"
    assert items[1].question == "Old Q2"
    assert items[1].status == m.PlanItemStatus.in_progress


def test_migration_idempotent(fresh_db):
    storage, db_mod, db_path = fresh_db
    dossier = _make_dossier(storage)

    # Write plan directly to the JSON blob, then clear migration flag
    plan = m.InvestigationPlan(
        items=[m.PlanItem(id="pli_idem_1", question="Q1", rationale="r1")],
        rationale="idem plan",
        drafted_at=m.utc_now(),
    )
    from vellum.db import connect
    with connect() as conn:
        conn.execute(
            "UPDATE dossiers SET investigation_plan = ? WHERE id = ?",
            (plan.model_dump_json(), dossier.id),
        )
        conn.execute("DELETE FROM settings WHERE key = 'plan_items_migrated'")

    # Run migration twice (second time flag is already set)
    db_mod.init_db(db_path)
    items_after_first = storage.list_plan_items(dossier.id)
    assert len(items_after_first) == 1

    db_mod.init_db(db_path)
    items_after_second = storage.list_plan_items(dossier.id)
    assert len(items_after_second) == 1  # Not duplicated


# ---------- delete_plan_items_for_dossier ----------


def test_delete_plan_items_for_dossier(fresh_db):
    storage, _, _ = fresh_db
    dossier = _make_dossier(storage)
    session = storage.start_work_session(dossier.id)
    _draft_plan(storage, dossier.id, session.id, n=3)

    count = storage.delete_plan_items_for_dossier(dossier.id)
    assert count == 3
    assert len(storage.list_plan_items(dossier.id)) == 0
