"""Tests for Dossier v2 extensions: debrief, investigation_plan, next_actions.

Exercises the storage layer directly (plus a quick API smoke) with a throwaway
SQLite file driven by VELLUM_DB_PATH — same pattern lifecycle.py's __main__
block uses.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module", autouse=True)
def _isolated_db():
    """Point VELLUM_DB_PATH at a throwaway file, init schema, clean up after."""
    tmp = Path(tempfile.gettempdir()) / f"vellum_ext_{int(time.time()*1000)}.db"
    os.environ["VELLUM_DB_PATH"] = str(tmp)

    # Import after env is set so config.DB_PATH resolves to tmp.
    from vellum import config  # noqa: F401
    # Reset the cached DB_PATH in config since it's evaluated at import time.
    from importlib import reload
    from vellum import config as _config
    reload(_config)
    # Reload db so its module-level reference lines up too.
    from vellum import db as _db
    reload(_db)

    _db.init_db()
    yield
    try:
        os.remove(tmp)
    except OSError:
        pass


@pytest.fixture
def dossier_id():
    from vellum import models as m
    from vellum import storage
    d = storage.create_dossier(
        m.DossierCreate(
            title="Test dossier",
            problem_statement="Exercise v2 extensions.",
            dossier_type=m.DossierType.investigation,
        )
    )
    return d.id


@pytest.fixture
def work_session_id(dossier_id):
    from vellum import models as m
    from vellum import storage
    ws = storage.start_work_session(dossier_id, m.WorkSessionTrigger.manual)
    return ws.id


# ---------- baseline ----------


def test_new_dossier_has_null_debrief_plan_and_empty_next_actions(dossier_id):
    from vellum import storage
    dossier = storage.get_dossier(dossier_id)
    assert dossier is not None
    assert dossier.debrief is None
    assert dossier.investigation_plan is None
    full = storage.get_dossier_full(dossier_id)
    assert full is not None
    assert full.next_actions == []


# ---------- debrief ----------


def test_update_debrief_partial_merge(dossier_id, work_session_id):
    from vellum import models as m
    from vellum import storage

    # First write: only what_i_found
    updated = storage.update_debrief(
        dossier_id,
        m.DebriefUpdate(what_i_found="Creditor can't touch heirs in TX."),
        work_session_id=work_session_id,
    )
    assert updated is not None
    assert updated.debrief is not None
    assert updated.debrief.what_i_found == "Creditor can't touch heirs in TX."
    assert updated.debrief.what_i_did == ""   # untouched default
    first_last_updated = updated.debrief.last_updated

    # Second write: only what_i_did — what_i_found must survive
    time.sleep(0.01)
    updated2 = storage.update_debrief(
        dossier_id,
        m.DebriefUpdate(what_i_did="Researched FDCPA."),
        work_session_id=work_session_id,
    )
    assert updated2 is not None
    assert updated2.debrief.what_i_found == "Creditor can't touch heirs in TX."
    assert updated2.debrief.what_i_did == "Researched FDCPA."
    assert updated2.debrief.last_updated > first_last_updated

    # Change log captured both
    changes = storage.list_change_log_for_session(dossier_id, work_session_id)
    kinds = [c.kind for c in changes]
    assert kinds.count("debrief_updated") == 2


def test_update_debrief_missing_dossier_returns_none():
    from vellum import models as m
    from vellum import storage
    assert storage.update_debrief("dos_missing", m.DebriefUpdate(what_i_did="x")) is None


# ---------- investigation plan ----------


def test_investigation_plan_draft_revise_approve(dossier_id, work_session_id):
    from vellum import models as m
    from vellum import storage

    # Draft
    item1 = m.InvestigationPlanItem(id=m.new_id("pli"), question="What state?")
    d1 = storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(items=[item1], rationale="start narrow"),
        work_session_id=work_session_id,
    )
    assert d1 is not None and d1.investigation_plan is not None
    plan1 = d1.investigation_plan
    assert len(plan1.items) == 1
    assert plan1.revision_count == 0
    assert plan1.approved_at is None
    assert plan1.revised_at is None
    assert plan1.drafted_at is not None

    # Revise — adds an item
    item2 = m.InvestigationPlanItem(
        id=m.new_id("pli"),
        question="Co-signer?",
        rationale="changes liability",
    )
    d2 = storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(items=[item1, item2], rationale="broadened"),
        work_session_id=work_session_id,
    )
    plan2 = d2.investigation_plan
    assert len(plan2.items) == 2
    assert plan2.revision_count == 1
    assert plan2.revised_at is not None
    assert plan2.drafted_at == plan1.drafted_at
    assert plan2.approved_at is None

    # Approve on next revise
    d3 = storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(items=[item1, item2], rationale="finalized", approve=True),
        work_session_id=work_session_id,
    )
    plan3 = d3.investigation_plan
    assert plan3.revision_count == 2
    assert plan3.approved_at is not None

    # Re-approve is a no-op on approved_at (stays set to first approval time)
    first_approved = plan3.approved_at
    d4 = storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(items=[item1, item2], rationale="same", approve=True),
        work_session_id=work_session_id,
    )
    assert d4.investigation_plan.approved_at == first_approved

    changes = storage.list_change_log_for_session(dossier_id, work_session_id)
    assert sum(1 for c in changes if c.kind == "plan_updated") == 4


# ---------- next actions ----------


def test_next_actions_add_complete_remove_reorder(dossier_id, work_session_id):
    from vellum import models as m
    from vellum import storage

    a1 = storage.add_next_action(
        dossier_id, m.NextActionCreate(action="Call creditor"), work_session_id
    )
    a2 = storage.add_next_action(
        dossier_id, m.NextActionCreate(action="Pull credit report"), work_session_id
    )
    a3 = storage.add_next_action(
        dossier_id,
        m.NextActionCreate(action="Write draft letter", after_action_id=a1.id),
        work_session_id,
    )

    # Order: a1, a3 (inserted after a1), a2
    listed = storage.list_next_actions(dossier_id)
    assert [a.id for a in listed] == [a1.id, a3.id, a2.id]

    # Complete
    completed = storage.complete_next_action(dossier_id, a1.id, work_session_id)
    assert completed is not None
    assert completed.completed is True
    assert completed.completed_at is not None

    # include_completed=False filters it out
    open_only = storage.list_next_actions(dossier_id, include_completed=False)
    assert a1.id not in [a.id for a in open_only]

    # Remove
    assert storage.remove_next_action(dossier_id, a2.id, work_session_id) is True
    remaining = storage.list_next_actions(dossier_id)
    assert [a.id for a in remaining] == [a1.id, a3.id]

    # Reorder
    reordered = storage.reorder_next_actions(
        dossier_id, [a3.id, a1.id], work_session_id
    )
    assert [a.id for a in reordered] == [a3.id, a1.id]

    # Reorder w/ bad ids raises
    with pytest.raises(ValueError):
        storage.reorder_next_actions(dossier_id, [a3.id], work_session_id)

    # Change log counts
    changes = storage.list_change_log_for_session(dossier_id, work_session_id)
    kinds = [c.kind for c in changes]
    assert kinds.count("next_action_added") == 3
    assert kinds.count("next_action_completed") == 1
    assert kinds.count("next_action_removed") == 1


def test_complete_missing_action_returns_none(dossier_id):
    from vellum import storage
    assert storage.complete_next_action(dossier_id, "act_missing") is None


def test_remove_missing_action_returns_false(dossier_id):
    from vellum import storage
    assert storage.remove_next_action(dossier_id, "act_missing") is False


# ---------- get_dossier_full ----------


def test_get_dossier_full_includes_all_extensions(dossier_id, work_session_id):
    from vellum import models as m
    from vellum import storage

    storage.update_debrief(
        dossier_id,
        m.DebriefUpdate(what_i_did="Looked at FDCPA."),
        work_session_id=work_session_id,
    )
    storage.update_investigation_plan(
        dossier_id,
        m.InvestigationPlanUpdate(
            items=[m.InvestigationPlanItem(id=m.new_id("pli"), question="Q?")],
            rationale="first pass",
        ),
        work_session_id=work_session_id,
    )
    storage.add_next_action(
        dossier_id, m.NextActionCreate(action="Do thing"), work_session_id
    )

    full = storage.get_dossier_full(dossier_id)
    assert full is not None
    assert full.dossier.debrief is not None
    assert full.dossier.debrief.what_i_did == "Looked at FDCPA."
    assert full.dossier.investigation_plan is not None
    assert len(full.dossier.investigation_plan.items) == 1
    assert len(full.next_actions) == 1
    assert full.next_actions[0].action == "Do thing"
