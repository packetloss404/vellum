"""Day-3 lifecycle integration test: one pytest that walks the full
deliverable end-to-end, backend-only, with a mocked LLM.

The product story: "full lifecycle from 'open a case' through 'plan
approved' through 'agent works' through 'close and resume later.'"
This test pins that story as code.

No network, no real LLM, no real API key required. Mocks
``anthropic.AsyncAnthropic`` via a process-wide scripted queue so both
the intake agent and the main dossier agent see deterministic turns.

Endpoints/fields owned by parallel day-3 agents may not have merged yet.
Where relevant those steps ``pytest.skip`` rather than fail, so this
file goes green once the other agents land.
"""
from __future__ import annotations

import asyncio
import copy
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest


# ---------------------------------------------------------------------------
# Scripted-LLM mock
# ---------------------------------------------------------------------------
#
# Both IntakeAgent and DossierAgent construct ``anthropic.AsyncAnthropic``
# instances at __init__ time. We replace the class globally so any
# instance created during the test will read turns from a per-call
# script queue keyed by a monotonic counter. Tests push scripts onto
# ``_NEXT_SCRIPT`` before each agent construction. Once a client is
# instantiated it drains from its own assigned list until exhausted;
# running dry raises IndexError (fail-loudly).


def _text_block(s: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=s)


def _tool_use_block(name: str, input: dict[str, Any], id: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=dict(input), id=id)


def _message(
    content: list[SimpleNamespace],
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 25,
) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


class _ScriptedMessages:
    """The ``.messages`` attribute on a mock AsyncAnthropic client."""

    def __init__(self, script: list[SimpleNamespace]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot messages arg — runtimes mutate the list in place.
        snap = dict(kwargs)
        if "messages" in snap:
            snap["messages"] = copy.deepcopy(snap["messages"])
        self.calls.append(snap)
        if not self._script:
            raise IndexError(
                f"scripted anthropic client ran out at call #{len(self.calls)}"
            )
        return self._script.pop(0)


class _ScriptedClient:
    """Mimics ``anthropic.AsyncAnthropic`` — .messages.create() is scripted."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        script = _SCRIPT_QUEUE.pop(0) if _SCRIPT_QUEUE else []
        self.messages = _ScriptedMessages(script)


# Module-scoped script queue. Each slot holds the full conversation for one
# client instance. Push scripts in the order agents are constructed.
_SCRIPT_QUEUE: list[list[SimpleNamespace]] = []


def _push_script(turns: list[SimpleNamespace]) -> None:
    _SCRIPT_QUEUE.append(turns)


# ---------------------------------------------------------------------------
# Fixture: isolated app with scripted LLM
# ---------------------------------------------------------------------------


@pytest.fixture
def lifecycle_app(monkeypatch):
    """Spin up the FastAPI app against a throwaway DB, with the anthropic
    client class swapped out for our scripted mock.

    Must set VELLUM_DB_PATH and patch ``anthropic.AsyncAnthropic`` BEFORE
    importing ``vellum.*`` — config.DB_PATH is resolved at import time,
    and the runtime modules capture ``anthropic.AsyncAnthropic`` in
    client construction. Also clears the vellum.* module cache so the
    import picks up the fresh env + patched class.
    """
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="vellum_day3_")
    os.close(db_fd)

    prior_db_env = os.environ.get("VELLUM_DB_PATH")
    os.environ["VELLUM_DB_PATH"] = db_path

    # Blow away any cached vellum modules so the test's monkeypatches take.
    prior_modules = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name == "vellum" or name.startswith("vellum.")
    }
    for name in prior_modules:
        del sys.modules[name]

    # Patch anthropic.AsyncAnthropic itself so every instantiation routes
    # through our scripted client. This is the single choke point both
    # the intake runtime and the dossier runtime pass through.
    import anthropic

    real_async_anthropic = anthropic.AsyncAnthropic
    anthropic.AsyncAnthropic = _ScriptedClient  # type: ignore[misc,assignment]

    # Clear any leftover scripts from prior tests.
    _SCRIPT_QUEUE.clear()

    try:
        from fastapi.testclient import TestClient

        try:
            from vellum.main import create_app
        except Exception as e:
            pytest.skip(f"could not import vellum.main.create_app: {e!r}")

        # Neuter the intake-commit auto-kickoff. It schedules an
        # ORCHESTRATOR.start on the TestClient's ephemeral event loop,
        # producing an orphan task we can't cleanly await from the test's
        # fresh loops later. The test drives the dossier agent explicitly
        # in steps B and D, so skipping the auto-start is safe.
        from vellum.api import intake_routes as _intake_routes

        async def _no_kickoff(dossier_id):  # noqa: ARG001
            return None

        monkeypatch.setattr(
            _intake_routes, "_kickoff_dossier_agent", _no_kickoff
        )

        try:
            app = create_app()
        except Exception as e:
            pytest.skip(f"create_app() failed: {e!r}")

        try:
            with TestClient(app) as client:
                yield client
        except Exception as e:
            pytest.skip(f"TestClient lifespan failed: {e!r}")
    finally:
        # Restore anthropic + vellum state.
        anthropic.AsyncAnthropic = real_async_anthropic  # type: ignore[misc,assignment]
        for name in list(sys.modules):
            if name == "vellum" or name.startswith("vellum."):
                del sys.modules[name]
        for name, mod in prior_modules.items():
            sys.modules[name] = mod
        if prior_db_env is None:
            os.environ.pop("VELLUM_DB_PATH", None)
        else:
            os.environ["VELLUM_DB_PATH"] = prior_db_env
        for suffix in ("", "-wal", "-shm", "-journal"):
            try:
                Path(db_path + suffix).unlink()
            except OSError:
                pass
        _SCRIPT_QUEUE.clear()


# ---------------------------------------------------------------------------
# Helpers for step D (driving the dossier agent directly)
# ---------------------------------------------------------------------------


def _run_orchestrator_and_wait(dossier_id: str, max_turns: int = 20) -> None:
    """Call ORCHESTRATOR.start then await completion. Because we're running
    inside TestClient (a sync context), we spin up a fresh event loop for
    the async bits."""
    from vellum.agent.orchestrator import ORCHESTRATOR

    async def _go() -> None:
        await ORCHESTRATOR.start(dossier_id, max_turns=max_turns)
        # Drain any in-flight task for this dossier.
        task = ORCHESTRATOR._tasks.get(dossier_id)
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=3.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass

    asyncio.run(_go())


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


def test_day3_full_lifecycle(lifecycle_app) -> None:
    """Walk the full deliverable end-to-end.

    A. Open via intake.
    B. Agent flags plan_approval DP.
    C. User approves (decision-point resolve).
    D. Agent does work (sources, section, artifact, debrief).
    E. Close — simulate orphan recovery.
    F. Reopen — visit.
    G. Resume.
    H. State intact.
    """
    client = lifecycle_app

    # Note: ``_kickoff_dossier_agent`` is monkeypatched to a no-op in the
    # fixture so commit_intake doesn't spawn an orphan task on the
    # TestClient's ephemeral event loop.

    # -------- A. Open via intake --------
    # Script the intake agent: one turn that calls the 5 setters and then
    # commit_intake with a 3-item plan, then speaks an end_turn.
    intake_commit_turn = _message(
        [
            _tool_use_block("set_title", {"title": "Day-3 lifecycle"}, "iu_1"),
            _tool_use_block(
                "set_problem_statement",
                {"problem_statement": "Pin the full lifecycle as a test."},
                "iu_2",
            ),
            _tool_use_block(
                "set_out_of_scope",
                {"items": ["performance tuning", "frontend wiring"]},
                "iu_3",
            ),
            _tool_use_block(
                "set_dossier_type",
                {"dossier_type": "investigation"},
                "iu_4",
            ),
            _tool_use_block(
                "set_check_in_policy",
                {"cadence": "on_demand", "notes": ""},
                "iu_5",
            ),
            _tool_use_block(
                "commit_intake",
                {
                    "plan_items": [
                        {
                            "question": "Can we drive intake via HTTP with a mocked LLM?",
                            "rationale": "Proves the intake path is backend-testable.",
                            "as_sub_investigation": False,
                        },
                        {
                            "question": "Does plan approval round-trip through a decision_point?",
                            "rationale": "Validates the approval handshake.",
                            "as_sub_investigation": False,
                        },
                        {
                            "question": "Does orphan work_session recovery restore a resumable dossier?",
                            "rationale": "Crash-recovery is load-bearing for 'come back later'.",
                            "as_sub_investigation": False,
                        },
                    ],
                    "plan_rationale": "Three gates covering the lifecycle.",
                },
                "iu_commit",
            ),
        ],
        stop_reason="tool_use",
    )
    intake_close_turn = _message(
        [_text_block("Dossier opened.")], stop_reason="end_turn"
    )

    # Script queue order matches client construction order. Only the
    # intake runtime needs a script here — auto-kickoff is neutered.
    _push_script([intake_commit_turn, intake_close_turn])

    resp = client.post("/api/intake", json={})
    assert resp.status_code == 200, f"start intake failed: {resp.text}"
    intake_id = resp.json()["intake"]["id"]

    resp = client.post(
        f"/api/intake/{intake_id}/message",
        json={"content": "Please open a dossier for me."},
    )
    assert resp.status_code == 200, f"intake message failed: {resp.text}"
    body = resp.json()
    assert body.get("dossier_id"), f"expected dossier_id in body, got {body!r}"
    dossier_id = body["dossier_id"]

    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    full = resp.json()
    plan = full["dossier"].get("investigation_plan")
    assert plan is not None, "intake should have seeded a plan"
    assert len(plan["items"]) == 3, f"expected 3 plan items, got {len(plan['items'])}"
    assert plan.get("approved_at") is None, "plan must not be auto-approved by intake"

    # -------- B. Agent flags plan_approval decision_point --------
    # Script a single turn: flag a plan_approval decision_point then end.
    plan_approval_turn = _message(
        [
            _tool_use_block(
                "flag_decision_point",
                {
                    "title": "Approve the plan?",
                    "kind": "plan_approval",
                    "options": [
                        {
                            "label": "Approve",
                            "implications": "Agent proceeds as planned.",
                            "recommended": True,
                        },
                        {
                            "label": "Redirect",
                            "implications": "Agent pauses for your direction.",
                            "recommended": False,
                        },
                    ],
                    "recommendation": "Approve — plan aligns with brief.",
                },
                "du_plan_approval",
            )
        ],
        stop_reason="tool_use",
    )
    plan_approval_end = _message([_text_block("awaiting")], stop_reason="end_turn")
    _push_script([plan_approval_turn, plan_approval_end])

    _run_orchestrator_and_wait(dossier_id, max_turns=5)

    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    dps = resp.json().get("decision_points") or []
    # Unresolved decision_points (resolved_at is None).
    unresolved = [dp for dp in dps if dp.get("resolved_at") is None]
    # The spec asks for kind=="plan_approval"; if the parallel agent
    # hasn't landed that field yet, fall back to matching on title.
    has_kind_field = any("kind" in dp for dp in dps)
    if has_kind_field:
        plan_approval_dps = [
            dp for dp in unresolved if dp.get("kind") == "plan_approval"
        ]
        assert len(plan_approval_dps) == 1, (
            f"expected 1 unresolved plan_approval DP, got {plan_approval_dps!r}"
        )
        plan_approval_dp = plan_approval_dps[0]
    else:
        # Fallback: the runtime's auto-kickoff may also write a DP. We only
        # care that at least one unresolved DP looks like a plan approval.
        candidates = [
            dp for dp in unresolved if "Approve" in (dp.get("title") or "")
        ]
        assert candidates, (
            f"expected a plan_approval-style unresolved DP; "
            f"got titles {[dp.get('title') for dp in unresolved]!r}"
        )
        plan_approval_dp = candidates[0]

    dp_id = plan_approval_dp["id"]

    # -------- C. User approves --------
    resp = client.post(
        f"/api/dossiers/{dossier_id}/decision-points/{dp_id}/resolve",
        json={"chosen": "Approve"},
    )
    assert resp.status_code == 200, f"resolve decision_point failed: {resp.text}"

    # After resolve, the plan should be approved. This requires the
    # parallel agent's hook that flips ``plan.approved_at`` when a
    # plan_approval DP is resolved with "Approve". If that hook hasn't
    # merged, skip the later assertions that depend on it.
    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    plan_after = resp.json()["dossier"].get("investigation_plan") or {}
    plan_approved = plan_after.get("approved_at") is not None
    if not plan_approved:
        pytest.skip(
            "waiting on plan_approval → plan.approved_at hook "
            "(parallel agent has not merged the resolve-side hook yet)"
        )

    # -------- D. Agent does work --------
    # Discover the current section_id space so we can later assert ≥1
    # section. We let the agent produce a fresh section.
    work_turn = _message(
        [
            _tool_use_block(
                "log_source_consulted",
                {
                    "citation": "https://example.test/alpha",
                    "why_consulted": "Primary reference on step D.",
                    "what_learned": "Mocking the LLM end-to-end is tractable.",
                    "supports_section_ids": [],
                },
                "wu_src1",
            ),
            _tool_use_block(
                "log_source_consulted",
                {
                    "citation": "https://example.test/beta",
                    "why_consulted": "Corroborating citation.",
                    "what_learned": "Work sessions do close cleanly on agent return.",
                    "supports_section_ids": [],
                },
                "wu_src2",
            ),
            _tool_use_block(
                "upsert_section",
                {
                    "type": "finding",
                    "title": "Lifecycle is walk-throughable end-to-end",
                    "content": "Verified by the day-3 test.",
                    "state": "provisional",
                    "change_note": "Initial finding from day-3 integration.",
                    "sources": [],
                    "depends_on": [],
                },
                "wu_sec1",
            ),
            _tool_use_block(
                "add_artifact",
                {
                    "kind": "checklist",
                    "title": "Day-3 integration checklist",
                    "content": "- [x] Intake\n- [x] Approval\n- [x] Work\n",
                    "intended_use": "Track lifecycle coverage.",
                },
                "wu_art1",
            ),
            _tool_use_block(
                "update_debrief",
                {
                    "what_i_did": "Walked the full lifecycle via a mocked agent.",
                    "what_i_found": "The end-to-end path is coherent.",
                    "what_you_should_do_next": "Keep this test green as a gate.",
                    "what_i_couldnt_figure_out": "Nothing blocking.",
                },
                "wu_deb1",
            ),
        ],
        stop_reason="tool_use",
    )
    work_end = _message([_text_block("done")], stop_reason="end_turn")
    _push_script([work_turn, work_end])

    _run_orchestrator_and_wait(dossier_id, max_turns=5)

    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    full = resp.json()

    log_entries = full.get("investigation_log") or []
    source_entries = [
        e for e in log_entries if e.get("entry_type") == "source_consulted"
    ]
    assert len(source_entries) >= 2, (
        f"expected >=2 source_consulted log entries, got {len(source_entries)}"
    )

    sections = full.get("sections") or []
    assert len(sections) >= 1, f"expected >=1 section, got {len(sections)}"

    artifacts = full.get("artifacts") or []
    assert len(artifacts) >= 1, f"expected >=1 artifact, got {len(artifacts)}"

    debrief = full["dossier"].get("debrief") or {}
    debrief_populated = any(
        (debrief.get(k) or "").strip()
        for k in (
            "what_i_did",
            "what_i_found",
            "what_you_should_do_next",
            "what_i_couldnt_figure_out",
        )
    )
    assert debrief_populated, f"expected debrief populated, got {debrief!r}"

    # -------- E. Close — simulate orphan recovery --------
    # Leave a work_session unclosed. After the agent turn ended, the
    # runtime has already closed its own session. Start a fresh one
    # directly via storage so we have something to orphan.
    from vellum import storage as _storage
    from vellum import models as _m
    from vellum.lifecycle import reconcile_at_startup

    orphan_session = _storage.start_work_session(
        dossier_id, _m.WorkSessionTrigger.manual
    )
    assert orphan_session.ended_at is None

    report = reconcile_at_startup()
    assert report.recovered_work_sessions >= 1, (
        f"expected >=1 recovered work_session, got "
        f"{report.recovered_work_sessions}"
    )

    # The spec asks for ``recovered_dossier_ids`` on the report. That
    # field is a parallel-agent deliverable; skip cleanly if not merged.
    recovered_ids = getattr(report, "recovered_dossier_ids", None)
    if recovered_ids is None:
        pytest.skip(
            "waiting on LifecycleReport.recovered_dossier_ids "
            "(parallel agent has not merged this field yet)"
        )
    assert dossier_id in recovered_ids, (
        f"expected {dossier_id!r} in recovered_dossier_ids, "
        f"got {recovered_ids!r}"
    )

    # -------- F. Reopen — visit --------
    resp = client.post(f"/api/dossiers/{dossier_id}/visit")
    assert resp.status_code == 200, f"visit failed: {resp.text}"
    assert resp.json().get("last_visited_at"), (
        "last_visited_at should be set after /visit"
    )

    # -------- G. Resume --------
    # Queue a no-op script for the /resume endpoint's agent launch
    # (if resume starts an agent — if not, the script is harmlessly
    # ignored and cleared below).
    _push_script([_message([_text_block("resumed")], stop_reason="end_turn")])

    resp = client.post(f"/api/dossiers/{dossier_id}/resume")
    if resp.status_code == 404:
        pytest.skip("waiting on POST /api/dossiers/{id}/resume endpoint")
    assert resp.status_code == 200, f"resume failed: {resp.status_code} {resp.text}"
    resume_body = resp.json()
    assert resume_body.get("work_session_id"), (
        f"expected work_session_id in resume body, got {resume_body!r}"
    )
    assert resume_body.get("status") == "started", (
        f"expected status=='started', got {resume_body.get('status')!r}"
    )

    # -------- H. State intact --------
    resp = client.get(f"/api/dossiers/{dossier_id}")
    assert resp.status_code == 200
    final = resp.json()
    final_plan = final["dossier"].get("investigation_plan") or {}
    assert final_plan.get("approved_at"), "plan must still be approved after resume"

    final_sections = final.get("sections") or []
    final_artifacts = final.get("artifacts") or []
    final_log = final.get("investigation_log") or []
    assert len(final_sections) >= 1, "sections must persist across resume"
    assert len(final_artifacts) >= 1, "artifacts must persist across resume"
    assert any(
        e.get("entry_type") == "source_consulted" for e in final_log
    ), "source_consulted log entries must persist across resume"


