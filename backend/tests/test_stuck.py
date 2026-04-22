"""Tests for stuck detection v2 — investigation_log emission + same_tool_no_progress.

v1 behavior is covered by stuck.py's internal self-test (`python -m vellum.agent.stuck`);
these tests focus on v2 additions:
  * every surfaced StuckSignal appends an InvestigationLogEntry of type
    stuck_declared with the correct payload;
  * the new same_tool_no_progress heuristic fires as specified;
  * dedup holds: the same signal seen twice produces only one log entry.
"""
from __future__ import annotations

import pytest


def _mk_dossier_and_session():
    """Create a throwaway dossier + work session so append_investigation_log
    can resolve dossier_id from session_id. Returns (dossier_id, session_id).
    """
    from vellum import models as m, storage
    dossier = storage.create_dossier(
        m.DossierCreate(
            title="stuck test dossier",
            problem_statement="test stuck detection v2",
            dossier_type=m.DossierType.investigation,
        )
    )
    ws = storage.start_work_session(dossier.id, m.WorkSessionTrigger.manual)
    return dossier.id, ws.id


def _stuck_declared_entries(dossier_id):
    from vellum import models as m, storage
    return [
        e
        for e in storage.list_investigation_log(dossier_id)
        if e.entry_type == m.InvestigationLogEntryType.stuck_declared
    ]


# ---------------------------------------------------------------------------
# 1. loop signal emits an investigation_log entry
# ---------------------------------------------------------------------------


def test_loop_signal_emits_investigation_log(fresh_db):
    from vellum import config, storage
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    args = {"q": "repeat me"}
    signal = None
    for _ in range(config.LOOP_DETECTION_THRESHOLD + 1):
        sig = stuck.record_tool_call(session_id, "web_search", args)
        if sig is not None:
            signal = sig

    assert signal is not None
    assert signal.kind == "loop"

    entries = _stuck_declared_entries(dossier_id)
    assert len(entries) == 1, f"expected exactly one stuck_declared entry, got {len(entries)}"
    entry = entries[0]
    assert entry.summary.startswith("[stuck:loop] ")
    assert entry.work_session_id == session_id
    assert entry.payload["kind"] == "loop"
    assert entry.payload["summary_of_attempts"] == signal.summary_of_attempts
    assert entry.payload["options"] == signal.options_for_user


# ---------------------------------------------------------------------------
# 2. section_budget signal emits a log entry
# ---------------------------------------------------------------------------


def test_section_budget_signal_emits_investigation_log(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    stuck.record_input_tokens(session_id, "sec_alpha", config.SECTION_TOKEN_BUDGET + 1)
    signal = stuck.check_section_budget(dossier_id, session_id)
    assert signal is not None and signal.kind == "section_budget"

    entries = _stuck_declared_entries(dossier_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.payload["kind"] == "section_budget"
    assert entry.summary.startswith("[stuck:section_budget] ")
    assert entry.work_session_id == session_id
    assert "options" in entry.payload and entry.payload["options"]


# ---------------------------------------------------------------------------
# 3. session_budget signal emits a log entry
# ---------------------------------------------------------------------------


def test_session_budget_signal_emits_investigation_log(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # Day 5: use config.STUCK_SESSION_BUDGET_MULT (default 15) rather than
    # hard-coding. The private constant in stuck.py mirrors the config val.
    over = config.STUCK_SESSION_BUDGET_MULT * config.SECTION_TOKEN_BUDGET + 1
    stuck.record_input_tokens(session_id, None, over)
    signal = stuck.check_session_budget(session_id)
    assert signal is not None and signal.kind == "session_budget"

    entries = _stuck_declared_entries(dossier_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.payload["kind"] == "session_budget"
    assert entry.summary.startswith("[stuck:session_budget] ")


# ---------------------------------------------------------------------------
# 4. revision_stall signal emits a log entry
# ---------------------------------------------------------------------------


def test_revision_stall_signal_emits_investigation_log(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # Strictly more than STUCK_REVISION_STALL_THRESHOLD upserts on the same
    # section fires revision_stall. Use distinct args each call so we don't
    # also trip the `loop` signal (identical args at LOOP_DETECTION_THRESHOLD
    # would ALSO emit).
    for i in range(config.STUCK_REVISION_STALL_THRESHOLD + 1):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_open", "i": i}
        )

    signal = stuck.check_revision_stall(dossier_id, session_id)
    assert signal is not None and signal.kind == "revision_stall"

    entries = _stuck_declared_entries(dossier_id)
    revision_entries = [e for e in entries if e.payload.get("kind") == "revision_stall"]
    assert len(revision_entries) == 1
    entry = revision_entries[0]
    assert entry.summary.startswith("[stuck:revision_stall] ")
    assert entry.work_session_id == session_id
    assert "summary_of_attempts" in entry.payload


# ---------------------------------------------------------------------------
# 5. same_tool_no_progress: new heuristic
# ---------------------------------------------------------------------------


def test_same_tool_no_progress_fires_at_eighth_call(fresh_db):
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # 8 calls to the SAME tool name with DIFFERENT args (to avoid tripping
    # the exact-args loop signal), no section creation in between.
    # Day 5: source-reading tools are exempt; use a synthesis tool instead
    # (``mark_considered_and_rejected`` is not exempt).
    signal = None
    for i in range(8):
        sig = stuck.record_tool_call(
            session_id,
            "mark_considered_and_rejected",
            {"hypothesis": f"H{i}", "reason": "ruled out"},
        )
        if sig is not None and sig.kind == "same_tool_no_progress":
            signal = sig

    assert signal is not None, "same_tool_no_progress should fire on 8th call with no section creation"
    assert signal.kind == "same_tool_no_progress"

    entries = _stuck_declared_entries(dossier_id)
    matching = [e for e in entries if e.payload.get("kind") == "same_tool_no_progress"]
    assert len(matching) == 1
    entry = matching[0]
    assert entry.summary.startswith("[stuck:same_tool_no_progress] ")
    assert entry.payload["kind"] == "same_tool_no_progress"
    assert entry.work_session_id == session_id
    # Options must be non-empty and include a "pause" option as recommended.
    options = entry.payload["options"]
    assert options and any(o.get("recommended") for o in options)


def test_same_tool_no_progress_does_not_fire_if_section_created(fresh_db):
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # Start with an upsert_section that CREATES a section (no section_id
    # provided). The same_tool_no_progress baseline for "upsert_section"
    # gets captured at this call before the increment, so sections_created
    # (=1 after) > baseline (=0) → no fire even at 8 calls.
    for i in range(8):
        stuck.record_tool_call(
            session_id, "upsert_section",
            {"title": f"new section {i}", "i": i},  # no section_id → creation
        )

    # No same_tool_no_progress should have fired: sections are being created.
    entries = _stuck_declared_entries(dossier_id)
    matching = [e for e in entries if e.payload.get("kind") == "same_tool_no_progress"]
    assert len(matching) == 0


def test_same_tool_no_progress_dedupes_per_tool_name(fresh_db):
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # 10 calls should fire exactly once at call 8; calls 9 and 10 must not
    # produce additional log entries. Use a non-exempt tool (day 5:
    # log_source_consulted is exempt from same_tool_no_progress).
    for i in range(10):
        stuck.record_tool_call(
            session_id,
            "mark_considered_and_rejected",
            {"hypothesis": f"H{i}", "reason": "ruled out"},
        )

    entries = _stuck_declared_entries(dossier_id)
    matching = [e for e in entries if e.payload.get("kind") == "same_tool_no_progress"]
    assert len(matching) == 1, f"expected exactly one same_tool_no_progress entry, got {len(matching)}"


# ---------------------------------------------------------------------------
# 6. Dedup: same signal surfaced twice produces only one log entry
# ---------------------------------------------------------------------------


def test_loop_signal_log_emission_is_deduped(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # 10 identical calls — the first threshold crossing fires, further calls
    # return None and must NOT re-append to investigation_log.
    for _ in range(config.LOOP_DETECTION_THRESHOLD + 7):
        stuck.record_tool_call(session_id, "web_search", {"q": "same"})

    entries = _stuck_declared_entries(dossier_id)
    loop_entries = [e for e in entries if e.payload.get("kind") == "loop"]
    assert len(loop_entries) == 1, (
        f"loop signal must emit exactly one log entry even when re-probed; got {len(loop_entries)}"
    )


def test_section_budget_log_emission_is_deduped(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    stuck.record_input_tokens(session_id, "sec_alpha", config.SECTION_TOKEN_BUDGET + 1)
    # Call the check multiple times — it should only emit once.
    assert stuck.check_section_budget(dossier_id, session_id) is not None
    assert stuck.check_section_budget(dossier_id, session_id) is None
    assert stuck.check_section_budget(dossier_id, session_id) is None

    entries = _stuck_declared_entries(dossier_id)
    section_budget_entries = [e for e in entries if e.payload.get("kind") == "section_budget"]
    assert len(section_budget_entries) == 1


# ---------------------------------------------------------------------------
# Sanity: check_stuck_state composite also emits (no regression for v1 users)
# ---------------------------------------------------------------------------


def test_check_stuck_state_composite_emits_log(fresh_db):
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    stuck.record_input_tokens(session_id, "sec_beta", config.SECTION_TOKEN_BUDGET + 1)
    signal = stuck.check_stuck_state(dossier_id, session_id)
    assert signal is not None and signal.kind == "section_budget"

    entries = _stuck_declared_entries(dossier_id)
    assert len(entries) == 1
    assert entries[0].payload["kind"] == "section_budget"


# ---------------------------------------------------------------------------
# Day 5 calibration: exempt tools + mutation-based stall resets
# ---------------------------------------------------------------------------


def test_update_debrief_is_exempt_from_loop(fresh_db):
    """update_debrief is iterative by design — 5 identical calls should
    not trip the exact-args loop detector."""
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    args = {"text": "debrief snapshot"}
    for _ in range(5):
        sig = stuck.record_tool_call(session_id, "update_debrief", args)
        assert sig is None, "update_debrief must not fire a loop signal (exempt)"

    entries = _stuck_declared_entries(dossier_id)
    loop_entries = [e for e in entries if e.payload.get("kind") == "loop"]
    assert loop_entries == [], (
        f"update_debrief should produce no loop log entries; got {len(loop_entries)}"
    )


def test_update_investigation_plan_is_exempt_from_loop(fresh_db):
    """update_investigation_plan is iterative by design — 5 identical calls
    should not trip the loop detector."""
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    args = {"plan": "same plan"}
    for _ in range(5):
        sig = stuck.record_tool_call(session_id, "update_investigation_plan", args)
        assert sig is None

    entries = _stuck_declared_entries(dossier_id)
    loop_entries = [e for e in entries if e.payload.get("kind") == "loop"]
    assert loop_entries == []


def test_log_source_consulted_exempt_from_same_tool_no_progress(fresh_db):
    """12 log_source_consulted calls with different citations must NOT
    trip same_tool_no_progress — source-reading is work, not spin."""
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    for i in range(12):
        sig = stuck.record_tool_call(
            session_id,
            "log_source_consulted",
            {"url": f"https://example.com/log-{i}", "citation": f"L{i}"},
        )
        # Args differ per call, so no exact-args loop. And the tool is
        # exempted from same_tool_no_progress, so no signal at all.
        assert sig is None, f"no signal expected for reading bursts (got {sig})"

    entries = _stuck_declared_entries(dossier_id)
    matching = [
        e for e in entries if e.payload.get("kind") == "same_tool_no_progress"
    ]
    assert matching == [], (
        "log_source_consulted must be exempt from same_tool_no_progress"
    )


def test_web_search_exempt_from_same_tool_no_progress(fresh_db):
    """10 web_search calls with different queries do not trip the
    same-tool-no-progress heuristic either."""
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    for i in range(10):
        sig = stuck.record_tool_call(
            session_id, "web_search", {"query": f"unique query {i}"}
        )
        assert sig is None

    entries = _stuck_declared_entries(dossier_id)
    matching = [
        e for e in entries if e.payload.get("kind") == "same_tool_no_progress"
    ]
    assert matching == []


def test_revision_stall_default_threshold_is_five(fresh_db):
    """With the default STUCK_REVISION_STALL_THRESHOLD of 5, five upserts
    on the same section must NOT trip revision_stall; six must."""
    from vellum import config
    from vellum.agent import stuck

    assert config.STUCK_REVISION_STALL_THRESHOLD == 5, (
        "day-5 default revision-stall threshold should be 5"
    )

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # Five upserts: at threshold, NOT past it — should not fire.
    for i in range(5):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_x", "i": i}
        )
    assert stuck.check_revision_stall(dossier_id, session_id) is None, (
        "5 upserts must not fire revision_stall at threshold=5"
    )

    # One more pushes past threshold → should fire.
    stuck.record_tool_call(
        session_id, "upsert_section", {"section_id": "sec_x", "i": 99}
    )
    sig = stuck.check_revision_stall(dossier_id, session_id)
    assert sig is not None and sig.kind == "revision_stall"


def test_add_artifact_resets_revision_stall_counter(fresh_db):
    """add_artifact within the same session counts as analytic progress and
    resets the per-section upsert counter. A subsequent batch of upserts
    must therefore not immediately trip revision_stall."""
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    # Push upsert count for sec_y up to threshold (5 at default).
    for i in range(config.STUCK_REVISION_STALL_THRESHOLD):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_y", "i": i}
        )
    # Not past threshold yet.
    assert stuck.check_revision_stall(dossier_id, session_id) is None

    # An artifact gets added — that's progress. Counters reset.
    stuck.record_tool_call(
        session_id, "add_artifact", {"title": "Draft letter", "body": "..."}
    )

    # After reset, threshold-1 more upserts on the same section must NOT
    # fire, because the counter is back to zero.
    for i in range(config.STUCK_REVISION_STALL_THRESHOLD):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_y", "j": i}
        )
    assert stuck.check_revision_stall(dossier_id, session_id) is None, (
        "add_artifact should have reset the revision_stall counter"
    )


def test_spawn_sub_investigation_resets_revision_stall_counter(fresh_db):
    """spawn_sub_investigation similarly resets the per-section upsert counter."""
    from vellum import config
    from vellum.agent import stuck

    dossier_id, session_id = _mk_dossier_and_session()
    stuck.reset_session(session_id)

    for i in range(config.STUCK_REVISION_STALL_THRESHOLD):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_z", "i": i}
        )
    assert stuck.check_revision_stall(dossier_id, session_id) is None

    stuck.record_tool_call(
        session_id,
        "spawn_sub_investigation",
        {"title": "branch question", "scope": "narrow"},
    )

    for i in range(config.STUCK_REVISION_STALL_THRESHOLD):
        stuck.record_tool_call(
            session_id, "upsert_section", {"section_id": "sec_z", "j": i}
        )
    assert stuck.check_revision_stall(dossier_id, session_id) is None, (
        "spawn_sub_investigation should have reset the revision_stall counter"
    )
