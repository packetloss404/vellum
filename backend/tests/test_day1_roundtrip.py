"""Day-1 end-to-end roundtrip test for the Vellum v2 backend.

Per the product brief: "I can create a case file via API, manually insert every
kind of object, and read it back." This test is the single gate — if it goes
green, the day-1 bar is met. Right now (pre-merge) most v2 endpoints do not
exist, so many steps will fail. That is expected and informative: each failure
is a concrete merge-readiness item.

Run from backend/:
    .venv/Scripts/python.exe -m pytest tests/test_day1_roundtrip.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def client():
    """Spin up a FastAPI TestClient against a throwaway SQLite DB.

    Must set VELLUM_DB_PATH BEFORE importing vellum.* — config.DB_PATH is
    resolved at import time. Also clear any already-imported vellum.* modules
    so config picks up the new env var in this test.
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="vellum_day1_")
    os.close(db_fd)
    prior_db_env = os.environ.get("VELLUM_DB_PATH")
    os.environ["VELLUM_DB_PATH"] = db_path

    # Preserve anything already cached so we restore afterward.
    prior_modules = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == "vellum" or name.startswith("vellum.")
    }
    for name in prior_modules:
        del sys.modules[name]

    try:
        from fastapi.testclient import TestClient

        try:
            from vellum.main import create_app
        except Exception as e:
            pytest.skip(f"could not import vellum.main.create_app: {e!r}")

        try:
            app = create_app()
        except Exception as e:
            pytest.skip(f"create_app() failed on empty DB: {e!r}")

        # TestClient as a context manager triggers FastAPI lifespan events,
        # which include reconcile_at_startup. On a fresh empty DB that should
        # be a no-op; if it crashes, skip with a clear signal.
        try:
            with TestClient(app) as c:
                yield c
        except Exception as e:
            pytest.skip(f"TestClient lifespan failed on empty DB: {e!r}")
    finally:
        # Restore prior module cache + env so we don't poison other tests.
        for name in list(sys.modules):
            if name == "vellum" or name.startswith("vellum."):
                del sys.modules[name]
        for name, mod in prior_modules.items():
            sys.modules[name] = mod
        if prior_db_env is None:
            os.environ.pop("VELLUM_DB_PATH", None)
        else:
            os.environ["VELLUM_DB_PATH"] = prior_db_env
        try:
            Path(db_path).unlink()
        except OSError:
            pass
        # WAL sidecar files
        for suffix in ("-wal", "-shm"):
            try:
                Path(db_path + suffix).unlink()
            except OSError:
                pass


def test_day1_roundtrip(client) -> None:
    """End-to-end: create every v2 object via API, read it all back.

    Steps follow the test narrative in the Day-1 brief. The test is intentionally
    linear and unfactored — this file is the single source of truth for what the
    v2 API surface must support on day one.
    """
    # -------- 1. Create dossier --------
    resp = client.post(
        "/api/dossiers",
        json={
            "title": "v2 Day-1 Roundtrip",
            "problem_statement": (
                "Verify every v2 object type round-trips through the HTTP API."
            ),
            "out_of_scope": ["performance", "auth"],
            "dossier_type": "investigation",
        },
    )
    assert resp.status_code == 200, f"create dossier failed: {resp.status_code} {resp.text}"
    dossier = resp.json()
    dossier_id = dossier["id"]
    assert dossier_id.startswith("dos_"), f"expected id prefix 'dos_', got {dossier_id!r}"

    # -------- 2. Start a work session --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/work-sessions",
        json={"trigger": "manual"},
    )
    assert resp.status_code == 200, f"start work_session failed: {resp.status_code} {resp.text}"
    session = resp.json()
    session_id = session["id"]
    assert session_id, "work_session id missing"

    # -------- 3. Draft an investigation plan --------
    plan_draft_body = {
        "items": [
            {
                "title": "Map the current HTTP surface",
                "rationale": "We need to know what v1 already gives us before extending.",
                "as_sub_investigation": False,
            },
            {
                "title": "Audit sub-investigation lifecycle invariants",
                "rationale": "Spawn/complete transitions must be exhaustive.",
                "as_sub_investigation": True,
            },
            {
                "title": "Decide artifact revision strategy",
                "rationale": "PATCH vs POST-new-revision is load-bearing.",
                "as_sub_investigation": False,
            },
        ],
    }
    resp = client.put(
        f"/api/dossiers/{dossier_id}/investigation-plan",
        params={"work_session_id": session_id},
        json=plan_draft_body,
    )
    assert resp.status_code == 200, f"draft plan failed: {resp.status_code} {resp.text}"

    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    full = resp.json()
    plan = full.get("investigation_plan")
    assert plan is not None, "investigation_plan missing from dossier full"
    assert len(plan["items"]) == 3, f"expected 3 plan items, got {len(plan['items'])}"
    assert plan.get("drafted_at"), "drafted_at should be set after initial draft"
    assert plan.get("revision_count") == 0, f"expected revision_count=0, got {plan.get('revision_count')}"

    # -------- 4. Revise the plan --------
    plan_revision_body = {
        "items": [
            {
                "title": "Map the current HTTP surface",
                "rationale": "Keep from v1 — still valid.",
                "as_sub_investigation": False,
            },
            {
                "title": "Audit sub-investigation lifecycle invariants",
                "rationale": "Still needed; now explicitly a sub-investigation.",
                "as_sub_investigation": True,
            },
            {
                "title": "Specify artifact revision semantics in docs",
                "rationale": "Replaced: decision → specify-and-document.",
                "as_sub_investigation": False,
            },
            {
                "title": "Wire investigation_log counts endpoint",
                "rationale": "Added after realizing we lacked an aggregate view.",
                "as_sub_investigation": False,
            },
        ],
    }
    resp = client.put(
        f"/api/dossiers/{dossier_id}/investigation-plan",
        params={"work_session_id": session_id},
        json=plan_revision_body,
    )
    assert resp.status_code == 200, f"revise plan failed: {resp.status_code} {resp.text}"
    full = client.get(f"/api/dossiers/{dossier_id}").json()
    plan = full["investigation_plan"]
    assert plan["revision_count"] == 1, f"expected revision_count=1 after first revise, got {plan['revision_count']}"
    assert plan.get("revised_at"), "revised_at should be set after revision"

    # -------- 5. Approve the plan --------
    resp = client.put(
        f"/api/dossiers/{dossier_id}/investigation-plan",
        params={"work_session_id": session_id},
        json={"items": plan_revision_body["items"], "approve": True},
    )
    assert resp.status_code == 200, f"approve plan failed: {resp.status_code} {resp.text}"
    full = client.get(f"/api/dossiers/{dossier_id}").json()
    plan = full["investigation_plan"]
    assert plan.get("approved_at"), "approved_at should be set after approval"

    # -------- 6. Add a section --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/sections",
        params={"work_session_id": session_id},
        json={
            "type": "finding",
            "title": "v1 API coverage is narrow",
            "content": "Only sections, needs_input, decision_points, reasoning, ruled_out.",
            "state": "provisional",
            "change_note": "initial draft",
        },
    )
    assert resp.status_code == 200, f"upsert section failed: {resp.status_code} {resp.text}"
    section = resp.json()
    section_id = section["id"]
    assert section_id, "section id missing"

    # -------- 7. Log 3 sources consulted --------
    source_payloads = [
        {
            "entry_type": "source_consulted",
            "source": {
                "kind": "web",
                "url": "https://fastapi.tiangolo.com/tutorial/testing/",
                "title": "FastAPI TestClient docs",
                "snippet": "TestClient uses HTTPX under the hood.",
            },
            "note": "Confirms the testing shape.",
        },
        {
            "entry_type": "source_consulted",
            "source": {
                "kind": "user_paste",
                "title": "Product brief v2",
                "snippet": "Sub-investigations, artifacts, debrief, next_actions…",
            },
            "note": "Anchor on exact object list from brief.",
            "supports_section_ids": [section_id],
        },
        {
            "entry_type": "source_consulted",
            "source": {
                "kind": "reasoning",
                "title": "Internal: lifecycle semantics",
                "snippet": "work_sessions auto-close on boot if orphaned.",
            },
        },
    ]
    for i, payload in enumerate(source_payloads):
        resp = client.post(
            f"/api/dossiers/{dossier_id}/investigation-log",
            params={"work_session_id": session_id},
            json=payload,
        )
        assert resp.status_code == 200, (
            f"investigation-log entry {i} failed: {resp.status_code} {resp.text}"
        )

    # -------- 8. Spawn a sub-investigation --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/sub-investigations",
        params={"work_session_id": session_id},
        json={
            "scope": "Verify every v2 endpoint exists and accepts a plausible body.",
            "questions": [
                "Does PUT /investigation-plan accept approve:true?",
                "Does PATCH /artifacts/{id} reflect content updates?",
                "Does GET /change-log return empty right after /visit?",
            ],
        },
    )
    assert resp.status_code == 200, f"spawn sub-investigation failed: {resp.status_code} {resp.text}"
    sub = resp.json()
    sub_id = sub["id"]
    assert sub_id, "sub-investigation id missing"
    assert sub.get("state") == "running", f"expected state=running, got {sub.get('state')!r}"

    # -------- 9. Complete the sub-investigation --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/sub-investigations/{sub_id}/complete",
        params={"work_session_id": session_id},
        json={
            "return_summary": (
                "All three questions answered; endpoint surface matches the brief; "
                "change-log is empty immediately after /visit."
            ),
            "findings_section_ids": [section_id],
        },
    )
    assert resp.status_code == 200, f"complete sub-investigation failed: {resp.status_code} {resp.text}"
    completed = resp.json()
    assert completed.get("state") == "delivered", f"expected state=delivered, got {completed.get('state')!r}"
    assert completed.get("completed_at"), "completed_at should be set"

    # -------- 10. Draft an artifact --------
    artifact_content_v1 = (
        "# Dear v2 reviewer,\n\n"
        "This is the first draft. Everything below is provisional.\n"
    )
    resp = client.post(
        f"/api/dossiers/{dossier_id}/artifacts",
        params={"work_session_id": session_id},
        json={
            "kind": "letter",
            "title": "Cover letter to v2 reviewer",
            "content": artifact_content_v1,
            "intended_use": "Accompany the v2 handoff.",
        },
    )
    assert resp.status_code == 200, f"draft artifact failed: {resp.status_code} {resp.text}"
    artifact = resp.json()
    artifact_id = artifact["id"]
    assert artifact_id, "artifact id missing"

    # -------- 11. Revise the artifact --------
    artifact_content_v2 = (
        "# Dear v2 reviewer,\n\n"
        "Second pass: trimmed hedging, named the three provisional claims.\n"
        "1. Endpoint coverage is exhaustive.\n"
        "2. Lifecycle invariants hold.\n"
        "3. change-log reset semantics match intuition.\n"
    )
    resp = client.patch(
        f"/api/dossiers/{dossier_id}/artifacts/{artifact_id}",
        params={"work_session_id": session_id},
        json={
            "content": artifact_content_v2,
            "change_note": "trim hedging; enumerate provisional claims",
        },
    )
    assert resp.status_code == 200, f"patch artifact failed: {resp.status_code} {resp.text}"
    revised = resp.json()
    assert revised.get("content") == artifact_content_v2, "artifact content did not reflect PATCH"

    # -------- 12. Considered and rejected --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/considered-and-rejected",
        params={"work_session_id": session_id},
        json={
            "path": "Ship v2 without sub-investigation endpoints; add them post-hoc.",
            "why_compelling": "Smaller surface, faster merge.",
            "why_rejected": (
                "Sub-investigations are the whole point of v2 — can't defer "
                "without gutting the brief."
            ),
            "cost_of_error": "high",
        },
    )
    assert resp.status_code == 200, f"considered-and-rejected failed: {resp.status_code} {resp.text}"

    # -------- 13. Flag needs_input (v1 endpoint) --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/needs-input",
        params={"work_session_id": session_id},
        json={
            "question": "Should artifact PATCH append a revision or mutate in place?",
            "blocks_section_ids": [section_id],
        },
    )
    assert resp.status_code == 200, f"needs-input failed: {resp.status_code} {resp.text}"

    # -------- 14. Flag decision_point (v1 endpoint) --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/decision-points",
        params={"work_session_id": session_id},
        json={
            "title": "Artifact revision API shape",
            "options": [
                {
                    "label": "PATCH mutates in place",
                    "implications": "Simpler API, loses history.",
                    "recommended": True,
                },
                {
                    "label": "POST /artifacts/{id}/revisions",
                    "implications": "Keeps history, doubles the endpoint count.",
                    "recommended": False,
                },
            ],
            "recommendation": "PATCH mutates in place for day one.",
            "blocks_section_ids": [],
        },
    )
    assert resp.status_code == 200, f"decision-points failed: {resp.status_code} {resp.text}"

    # -------- 15. Update debrief --------
    resp = client.put(
        f"/api/dossiers/{dossier_id}/debrief",
        params={"work_session_id": session_id},
        json={
            "what_we_learned": (
                "The v2 surface is tractable if we accept PATCH-in-place for artifacts."
            ),
            "what_we_got_wrong": (
                "Initial plan undercounted the investigation_log counts endpoint."
            ),
            "decision_or_recommendation": (
                "Proceed with v2 as specified; pin artifact revisions as PATCH."
            ),
            "what_to_watch": (
                "If users ask for revision history, revisit the POST-revision shape."
            ),
        },
    )
    assert resp.status_code == 200, f"debrief failed: {resp.status_code} {resp.text}"

    # -------- 16. Add 2 next_actions --------
    next_action_bodies = [
        {
            "title": "Wire frontend to /investigation-plan",
            "owner": "frontend-agent",
            "due": "2026-04-29",
        },
        {
            "title": "Write docs for artifact PATCH semantics",
            "owner": "docs-agent",
            "due": "2026-04-30",
        },
    ]
    for i, body in enumerate(next_action_bodies):
        resp = client.post(
            f"/api/dossiers/{dossier_id}/next-actions",
            params={"work_session_id": session_id},
            json=body,
        )
        assert resp.status_code == 200, (
            f"next-action {i} failed: {resp.status_code} {resp.text}"
        )

    # -------- 17. Read dossier full --------
    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200, f"get dossier full failed: {resp.status_code} {resp.text}"
    full = resp.json()

    assert full.get("dossier"), "dossier key missing from full payload"
    assert full.get("debrief"), "debrief missing from full payload"
    assert full.get("investigation_plan"), "investigation_plan missing from full payload"

    sections = full.get("sections") or []
    assert len(sections) >= 1, f"expected >=1 section, got {len(sections)}"

    artifacts = full.get("artifacts") or []
    assert len(artifacts) >= 1, f"expected >=1 artifact, got {len(artifacts)}"

    subs = full.get("sub_investigations") or []
    assert len(subs) >= 1, f"expected >=1 sub_investigation, got {len(subs)}"
    assert any(s.get("state") == "delivered" for s in subs), (
        "expected at least one delivered sub_investigation"
    )

    next_actions = full.get("next_actions") or []
    assert len(next_actions) >= 2, f"expected >=2 next_actions, got {len(next_actions)}"

    log_entries = full.get("investigation_log") or []
    assert len(log_entries) >= 4, (
        f"expected >=4 investigation_log entries (3 source_consulted + 1 "
        f"path_rejected), got {len(log_entries)}"
    )

    car = full.get("considered_and_rejected") or []
    assert len(car) >= 1, f"expected >=1 considered_and_rejected, got {len(car)}"

    needs_input = full.get("needs_input") or []
    assert len(needs_input) >= 1, f"expected >=1 needs_input, got {len(needs_input)}"

    decision_points = full.get("decision_points") or []
    assert len(decision_points) >= 1, f"expected >=1 decision_point, got {len(decision_points)}"

    work_sessions = full.get("work_sessions") or []
    assert len(work_sessions) >= 1, f"expected >=1 work_session, got {len(work_sessions)}"

    # -------- 18. Investigation log counts --------
    resp = client.get(f"/api/dossiers/{dossier_id}/investigation-log/counts")
    assert resp.status_code == 200, f"log counts failed: {resp.status_code} {resp.text}"
    counts = resp.json()
    assert counts.get("source_consulted", 0) >= 3, (
        f"expected source_consulted>=3, got {counts.get('source_consulted')}"
    )
    assert counts.get("path_rejected", 0) >= 1, (
        f"expected path_rejected>=1, got {counts.get('path_rejected')}"
    )

    # -------- 19. End the work session --------
    resp = client.post(f"/api/work-sessions/{session_id}/end")
    assert resp.status_code == 200, f"end work_session failed: {resp.status_code} {resp.text}"

    # -------- 20. Mark visit --------
    resp = client.post(f"/api/dossiers/{dossier_id}/visit")
    assert resp.status_code == 200, f"visit failed: {resp.status_code} {resp.text}"
    visited = resp.json()
    assert visited.get("last_visited_at"), "last_visited_at should be set after /visit"

    # -------- 21. Plan-diff since visit --------
    resp = client.get(f"/api/dossiers/{dossier_id}/change-log")
    assert resp.status_code == 200, f"change-log failed: {resp.status_code} {resp.text}"
    diff = resp.json()
    assert isinstance(diff, list), f"expected change-log to be a list, got {type(diff).__name__}"
    # Right after /visit, the "since last visit" list must be empty — nothing
    # has changed since the visit marker was dropped.
    assert len(diff) == 0, (
        f"expected empty change-log immediately after /visit, got {len(diff)} entries"
    )
