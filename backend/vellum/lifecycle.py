"""Startup-time recovery for crashed-process leftovers.

Vellum runs as a single process. When that process dies mid-work, the DB can be
left holding two kinds of stale rows:

  * `work_sessions` with `ended_at IS NULL` — the agent was in a turn when the
    process went away. No-one will ever close these unless we do it here.
  * `intake_sessions` stuck in `gathering` from days ago — the user walked
    away from a conversation that never committed.

`reconcile_at_startup()` is the single entry point and is meant to be called
exactly once per process boot (from `main.py`'s lifespan hook). It is
idempotent, swallows per-step errors, and logs a one-line summary.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from . import db, storage
from . import models as m
from .intake import storage as intake_storage

logger = logging.getLogger(__name__)

STALE_INTAKE_SECONDS = 7 * 24 * 60 * 60  # 7 days


@dataclass
class LifecycleReport:
    recovered_work_sessions: int
    abandoned_stale_intakes: int


def _find_orphan_work_sessions() -> list[tuple[str, str]]:
    """Return [(work_session_id, dossier_id), ...] for sessions still open."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, dossier_id FROM work_sessions WHERE ended_at IS NULL"
        ).fetchall()
    return [(r["id"], r["dossier_id"]) for r in rows]


def _recover_one_work_session(session_id: str, dossier_id: str) -> bool:
    """End the session and append a reasoning_trail note. Returns True on full
    success, False if any step for this particular session failed (already
    logged). Never raises."""
    try:
        storage.end_work_session(session_id)
    except Exception:
        logger.error(
            "lifecycle: failed to end orphan work_session %s (dossier %s)",
            session_id,
            dossier_id,
            exc_info=True,
        )
        return False

    try:
        storage.append_reasoning(
            dossier_id,
            m.ReasoningAppend(
                note=(
                    "[lifecycle] A previous working session on this dossier "
                    "was interrupted. Nothing was lost — when the agent next "
                    "picks this up, it'll resume from the current state. "
                    "No action needed from you."
                ),
                tags=["lifecycle", "crash_recovery"],
            ),
            work_session_id=None,
        )
    except Exception:
        # The session is already closed; the trail note is best-effort. A
        # missing dossier (FK gone) or a transient DB error here shouldn't
        # undo the recovery — log and move on.
        logger.error(
            "lifecycle: ended orphan work_session %s but failed to append "
            "reasoning_trail on dossier %s",
            session_id,
            dossier_id,
            exc_info=True,
        )
        return False

    return True


def reconcile_at_startup(
    stale_intake_seconds: int = STALE_INTAKE_SECONDS,
) -> LifecycleReport:
    """Clean up crash-leftovers. Safe to call on every app boot.

    1. End every orphan `work_sessions` row (ended_at IS NULL) and drop a
       `[lifecycle]` note into the owning dossier's reasoning_trail so the
       plan-diff surfaces what happened.
    2. Mark stale `gathering` intakes as abandoned.

    Errors in any sub-step are logged and swallowed — startup must never
    abort because of this. Returns counts of what was actually recovered.
    """
    recovered = 0
    abandoned = 0

    # --- 1. Orphan work sessions ---
    try:
        orphans = _find_orphan_work_sessions()
    except Exception:
        logger.error(
            "lifecycle: failed to query orphan work_sessions; skipping step",
            exc_info=True,
        )
        orphans = []

    for session_id, dossier_id in orphans:
        if _recover_one_work_session(session_id, dossier_id):
            recovered += 1

    # --- 2. Stale intakes ---
    try:
        abandoned = intake_storage.abandon_stale_intakes(stale_intake_seconds)
    except Exception:
        logger.error(
            "lifecycle: failed to abandon stale intakes; continuing",
            exc_info=True,
        )
        abandoned = 0

    logger.info(
        "lifecycle reconcile: recovered %d work_sessions, abandoned %d stale intakes",
        recovered,
        abandoned,
    )
    return LifecycleReport(
        recovered_work_sessions=recovered,
        abandoned_stale_intakes=abandoned,
    )


# ---------- smoke test ----------


if __name__ == "__main__":
    import os
    import tempfile

    os.environ["VELLUM_DB_PATH"] = tempfile.mktemp(suffix=".db")

    logging.basicConfig(level=logging.INFO)

    # Re-imports after VELLUM_DB_PATH is set, so config.DB_PATH points at the
    # throwaway file. The module-level imports above already resolved
    # `db`/`storage`/`intake_storage`, but they read `config.DB_PATH` lazily
    # inside `connect()`, so the env change still takes effect.
    from . import db as _db
    from . import storage as _storage
    from .intake import storage as _intake_storage
    from .intake.models import IntakeStatus
    from . import models as _m

    _db.init_db()

    # 1. Dossier
    dossier = _storage.create_dossier(
        _m.DossierCreate(
            title="Lifecycle smoke test",
            problem_statement="Make sure reconcile_at_startup actually reconciles.",
            dossier_type=_m.DossierType.investigation,
        )
    )

    # 2. Orphan work session (started, never ended)
    ws = _storage.start_work_session(dossier.id, _m.WorkSessionTrigger.manual)

    # 3. Stale intake: create then backdate updated_at to 10 days ago
    stale_intake = _intake_storage.create_intake()
    from datetime import timedelta

    backdated = (_m.utc_now() - timedelta(days=10)).isoformat()
    with _db.connect() as _conn:
        _conn.execute(
            "UPDATE intake_sessions SET updated_at = ? WHERE id = ?",
            (backdated, stale_intake.id),
        )

    # 4. Fresh intake — should survive
    fresh_intake = _intake_storage.create_intake()

    # 5. First reconcile
    report1 = reconcile_at_startup()
    assert report1.recovered_work_sessions == 1, (
        f"expected 1 recovered, got {report1.recovered_work_sessions}"
    )
    assert report1.abandoned_stale_intakes == 1, (
        f"expected 1 abandoned, got {report1.abandoned_stale_intakes}"
    )

    # 6. Idempotence: second call finds nothing to do
    report2 = reconcile_at_startup()
    assert report2.recovered_work_sessions == 0, (
        f"expected 0 recovered on second run, got {report2.recovered_work_sessions}"
    )
    assert report2.abandoned_stale_intakes == 0, (
        f"expected 0 abandoned on second run, got {report2.abandoned_stale_intakes}"
    )

    # 7. Reasoning trail carries the [lifecycle] note
    full = _storage.get_dossier_full(dossier.id)
    assert full is not None
    lifecycle_notes = [
        e for e in full.reasoning_trail
        if e.note.startswith("[lifecycle]") and "lifecycle" in e.tags
    ]
    assert len(lifecycle_notes) == 1, (
        f"expected exactly one [lifecycle] note, got {len(lifecycle_notes)}: "
        f"{[e.note for e in full.reasoning_trail]}"
    )
    assert "interrupted" in lifecycle_notes[0].note, (
        "note should explain to the user that a previous session was interrupted"
    )
    assert "Nothing was lost" in lifecycle_notes[0].note, (
        "note should reassure the user nothing was lost"
    )
    assert "crash_recovery" in lifecycle_notes[0].tags
    # work_session_id must be None — the trail entry is not tied to the
    # dead session's change_log.
    assert lifecycle_notes[0].work_session_id is None

    # Underlying session is actually ended now
    sessions = _storage.list_work_sessions(dossier.id)
    assert len(sessions) == 1
    assert sessions[0].ended_at is not None

    # 8. Fresh intake is untouched
    still_fresh = _intake_storage.get_intake(fresh_intake.id)
    assert still_fresh is not None
    assert still_fresh.status == IntakeStatus.gathering, (
        f"fresh intake should remain gathering, got {still_fresh.status}"
    )

    # Stale intake is abandoned
    was_stale = _intake_storage.get_intake(stale_intake.id)
    assert was_stale is not None
    assert was_stale.status == IntakeStatus.abandoned

    # Dossier was NOT marked visited (user hasn't opened it)
    refetched = _storage.get_dossier(dossier.id)
    assert refetched is not None
    assert refetched.last_visited_at is None, (
        "reconcile must not mark dossier visited"
    )

    print("lifecycle reconcile OK")
