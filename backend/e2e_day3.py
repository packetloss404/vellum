"""Day-3 end-to-end persistence test.

Runs without an ANTHROPIC_API_KEY. We skip the live agent loops and
directly manipulate state via storage + tool handlers. The test proves:

1. Intake session persists and commits into a dossier.
2. The FastAPI app can be torn down and rebuilt against the same SQLite
   file, and all state is intact.
3. lifecycle.reconcile_at_startup() cleans up orphan work_sessions and
   writes a reasoning_trail note the user will see.

Run from backend/:
    python e2e_day3.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Set DB path BEFORE importing anything in vellum — config.DB_PATH resolves
# at module import time from this env var.
_tmp = Path(tempfile.gettempdir()) / f"vellum_e2e_{int(time.time())}.db"
os.environ["VELLUM_DB_PATH"] = str(_tmp)

from fastapi.testclient import TestClient  # noqa: E402
from vellum import db  # noqa: E402
from vellum import storage as dossier_storage  # noqa: E402
from vellum import models as m  # noqa: E402
from vellum.intake import storage as intake_storage  # noqa: E402
from vellum.intake.tools import HANDLERS as INTAKE_HANDLERS  # noqa: E402
from vellum.intake.models import IntakeState, IntakeStatus  # noqa: E402
from vellum.lifecycle import reconcile_at_startup  # noqa: E402
# main.py does NOT currently include the intake router, so the test mounts
def hr(label: str) -> None:
    print(f"\n=== {label} ===")


def _build_app():
    """create_app() — main.py registers crud + agent + intake routers."""
    from vellum.main import create_app
    return create_app()


def main() -> int:
    db.init_db()

    # ------------------------------------------------------------------
    # Step 1 — Import the app and get a TestClient.
    # ------------------------------------------------------------------
    hr("Step 1: build app v1")
    app_v1 = _build_app()
    client_v1 = TestClient(app_v1)
    r = client_v1.get("/health").json()
    assert r == {"ok": True}
    print("  /health ok")

    # ------------------------------------------------------------------
    # Step 2 — Create an intake via the API (no opening message; we skip
    # the agent so no API key is needed).
    # ------------------------------------------------------------------
    hr("Step 2: create intake via API")
    r = client_v1.post("/api/intake", json={}).json()
    print(f"  response: {r}")
    intake_id = r["intake"]["id"]
    assert r["intake"]["status"] == "gathering"
    assert r["first_reply"] is None

    # ------------------------------------------------------------------
    # Step 3 — Directly populate the intake state via storage (skipping
    # the agent loop). This is what the agent would have accumulated
    # across a real multi-turn conversation.
    # ------------------------------------------------------------------
    hr("Step 3: populate intake state directly (no agent)")
    state = IntakeState(
        title="Credit card debt negotiation - friend's mother",
        problem_statement=(
            "Friend's mother passed with ~$40k credit card debt across 3 accounts. "
            "No estate. Friend wants the opening percentage for negotiations."
        ),
        dossier_type=m.DossierType.decision_memo,
        out_of_scope=["tax implications"],
        check_in_policy=m.CheckInPolicy(cadence=m.CheckInCadence.daily),
    )
    intake_storage.update_intake_state(intake_id, state)
    intake = intake_storage.get_intake(intake_id)
    assert intake is not None
    assert intake.state.title is not None
    print(f"  intake state populated; is_complete={intake.state.is_complete()}")
    assert intake.state.is_complete()

    # ------------------------------------------------------------------
    # Step 4 — Force-commit the intake via the tool handler -> dossier.
    # ------------------------------------------------------------------
    hr("Step 4: commit intake -> dossier")
    result = INTAKE_HANDLERS["commit_intake"](intake_id, {})
    assert "dossier_id" in result, f"commit returned error: {result}"
    dossier_id = result["dossier_id"]
    print(f"  dossier_id: {dossier_id}")

    # Verify the dossier exists via API.
    dossier_json = client_v1.get(f"/api/dossiers/{dossier_id}").json()
    assert dossier_json["dossier"]["title"] == state.title
    assert dossier_json["dossier"]["dossier_type"] == "decision_memo"
    print(f"  /api/dossiers/{dossier_id} -> title matches")

    # ------------------------------------------------------------------
    # Step 5 — Simulate "mid-work crash": start a work_session, add one
    # reasoning entry bound to that session, then abandon the app without
    # closing the session.
    # ------------------------------------------------------------------
    hr("Step 5: open a work_session (simulate agent running)")
    session = dossier_storage.start_work_session(
        dossier_id, m.WorkSessionTrigger.manual
    )
    print(f"  work_session started: {session.id}")

    dossier_storage.append_reasoning(
        dossier_id,
        m.ReasoningAppend(
            note="Mid-thought when the process died.",
            tags=["pre_crash"],
        ),
        work_session_id=session.id,
    )
    print("  reasoning entry bound to live session")

    # ------------------------------------------------------------------
    # Step 6 — Dispose the client and the app ref. The DB file persists.
    # ------------------------------------------------------------------
    hr("Step 6: dispose app (simulated crash)")
    client_v1.close()
    del app_v1, client_v1
    print("  app_v1 + client_v1 disposed; DB remains on disk")

    # ------------------------------------------------------------------
    # Step 7 — Build a fresh app against the same DB file - like a
    # restart. In production the lifespan hook would call
    # reconcile_at_startup for us; today main.py's lifespan only handles
    # shutdown, so the test calls reconcile_at_startup explicitly to
    # assert what it does.
    # ------------------------------------------------------------------
    hr("Step 7: build app v2 (restart)")
    report = reconcile_at_startup()
    print(
        "  lifecycle report: "
        f"recovered={report.recovered_work_sessions}  "
        f"abandoned_stale={report.abandoned_stale_intakes}"
    )
    assert report.recovered_work_sessions >= 1

    app_v2 = _build_app()
    client_v2 = TestClient(app_v2)
    r = client_v2.get("/health").json()
    assert r == {"ok": True}
    print("  /health ok (v2)")

    # ------------------------------------------------------------------
    # Step 8 — Verify: dossier + intake + reasoning_trail all persisted.
    # ------------------------------------------------------------------
    hr("Step 8: verify persistence across restart")
    dossier_json = client_v2.get(f"/api/dossiers/{dossier_id}").json()
    assert dossier_json["dossier"]["title"] == state.title

    trail_notes = [entry["note"] for entry in dossier_json["reasoning_trail"]]
    has_lifecycle = any("[lifecycle]" in n for n in trail_notes)
    assert has_lifecycle, (
        f"expected lifecycle entry in reasoning_trail, got: {trail_notes}"
    )
    # The pre-crash reasoning note must also still be there — crashing
    # must not have rolled back committed work.
    assert any("Mid-thought" in n for n in trail_notes), (
        f"pre-crash note missing after restart: {trail_notes}"
    )
    print(
        f"  reasoning_trail has {len(trail_notes)} entries, "
        f"lifecycle entry present: {has_lifecycle}"
    )

    # The work_session is now ended (ended_at set).
    sessions_after = dossier_storage.list_work_sessions(dossier_id)
    assert len(sessions_after) == 1
    assert sessions_after[0].ended_at is not None, (
        "orphan session should have been closed by reconcile"
    )
    print(f"  work_session {sessions_after[0].id} ended_at set post-recovery")

    # And the intake is still there, committed, and linked to the dossier.
    intake_json = client_v2.get(f"/api/intake/{intake_id}").json()
    assert intake_json["status"] == "committed"
    assert intake_json["dossier_id"] == dossier_id
    print(
        "  intake persisted as committed, "
        f"dossier_id={intake_json['dossier_id']}"
    )

    # ------------------------------------------------------------------
    # Step 9 — Second reconcile is idempotent.
    # ------------------------------------------------------------------
    hr("Step 9: second reconcile is idempotent")
    report2 = reconcile_at_startup()
    assert report2.recovered_work_sessions == 0
    print(
        f"  second reconcile: recovered={report2.recovered_work_sessions} "
        "(expected 0)"
    )

    # ------------------------------------------------------------------
    # Step 10 — Visit + plan-diff still work after restart. The lifecycle
    # reasoning note was written after the last visit, so the diff before
    # /visit is non-empty; after /visit it drains to zero.
    # ------------------------------------------------------------------
    hr("Step 10: visit + plan-diff post-restart")
    client_v2.post(f"/api/dossiers/{dossier_id}/visit")
    changes = client_v2.get(f"/api/dossiers/{dossier_id}/change-log").json()
    assert isinstance(changes, list)
    assert len(changes) == 0, (
        f"expected empty change-log immediately after visit, got {len(changes)}"
    )
    print(
        f"  change-log returned {len(changes)} entries (expected 0 after visit)"
    )

    hr("SUCCESS")
    print(f"  db: {_tmp}")
    client_v2.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
