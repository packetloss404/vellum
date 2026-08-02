"""Linter: every name previously exported from the per-entity storage
modules is still importable from ``vellum.storage``.

The cleanup-2 storage consolidation merged 7 thin files (wake_store,
user_note_store, next_action_store, turn_store, budget_store,
settings_store, idempotency_store) into 3 new modules
(``dossier_lifecycle``, ``audit``, ``settings``). The public surface
must be unchanged — every consumer of ``from vellum import storage``
still finds the same names. This file pins that contract.

If you add a new public storage function, add it to
``vellum/storage/__init__.py`` AND optionally extend the
``_EXPECTED_NAMES`` set below (the assertion that follows catches
missing entries, not extra ones).
"""
from __future__ import annotations

from vellum import storage


def test_all_documented_storage_names_importable():
    """Every name in the post-consolidation public surface is importable
    from ``vellum.storage``. The list mirrors the ``__all__`` from
    ``vellum/storage/__init__.py``; if a new function is added there,
    add it here too (or drop this test's whitelist).
    """
    expected = {
        # Dossier
        "create_dossier", "get_dossier", "list_dossiers", "update_dossier",
        "delete_dossier", "get_dossier_resume_state", "mark_dossier_visited",
        "get_dossier_full", "update_debrief", "update_working_theory",
        "update_premise_challenge", "update_investigation_plan",
        "approve_investigation_plan", "replan_dossier", "get_dossier_status",
        # Section
        "list_sections", "get_section", "upsert_section",
        "update_section_state", "delete_section", "reorder_sections",
        # Artifact
        "create_artifact", "get_artifact", "list_artifacts",
        "update_artifact", "delete_artifact",
        # Budget (now in audit.py)
        "record_budget_usage", "get_budget_today", "list_budget_range",
        # Decision point
        "add_decision_point", "get_decision_point",
        "resolve_decision_point", "list_decision_points",
        # Idempotency (now in settings.py)
        "get_tool_invocation", "record_tool_invocation",
        # Log
        "append_reasoning", "list_reasoning_trail", "add_ruled_out",
        "list_ruled_out", "append_investigation_log", "list_investigation_log",
        "count_investigation_log_by_type", "add_considered_and_rejected",
        "list_considered_and_rejected", "list_change_log_for_session",
        "list_change_log_since_last_visit",
        # Needs input
        "add_needs_input", "resolve_needs_input", "list_needs_input",
        # Next action (now in dossier_lifecycle.py)
        "add_next_action", "list_next_actions", "complete_next_action",
        "remove_next_action", "reorder_next_actions",
        # Session
        "start_work_session", "get_work_session", "end_work_session",
        "get_active_work_session", "list_work_sessions",
        "increment_session_tokens", "record_session_usage",
        "record_turn_usage", "end_work_session_with_reason",
        "end_orphan_session_as_crashed", "save_session_summary",
        "get_session_summary", "list_session_summaries_for_dossier",
        # Settings (now in settings.py)
        "get_setting", "set_setting", "list_settings", "seed_default_settings",
        # Sub-investigation
        "finalize_plan_on_delivery", "spawn_sub_investigation",
        "get_sub_investigation", "list_sub_investigations",
        "update_sub_investigation_state", "update_sub_investigation",
        "complete_sub_investigation", "abandon_sub_investigation",
        # Wake (now in dossier_lifecycle.py)
        "set_dossier_wake_at", "mark_wake_pending", "clear_dossier_wake",
        "list_dossiers_ready_to_wake", "get_dossier_wake_state",
        "increment_consecutive_error_count", "reset_consecutive_error_count",
        "set_dossier_quarantined", "clear_dossier_quarantine",
        "get_dossier_error_state",
        # H-20: last stuck signal kind (dossier_lifecycle.py)
        "set_dossier_last_signal_kind",
        "get_dossier_last_signal_kind",
        # User notes (now in dossier_lifecycle.py)
        "create_user_note", "list_user_notes", "mark_user_notes_seen",
        # Plan items
        "list_plan_items", "get_plan_item", "get_plan_item_by_id",
        "upsert_plan_item", "bulk_replace_plan_items", "set_plan_item_status",
        "delete_plan_items_for_dossier",
        # Agent turns (now in audit.py)
        "create_agent_turn", "list_agent_turns_for_dossier",
        "list_agent_turns_for_session", "list_agent_turns_for_trace",
        "get_turn_cost_summary_for_dossier",
        # Exceptions
        "ActiveWorkSessionExists",
    }
    missing = expected - set(dir(storage))
    assert not missing, f"missing from vellum.storage: {sorted(missing)}"


def test_no_spurious_modules_importable_from_storage():
    """The old per-entity modules (wake_store, etc.) are gone. Pin their
    absence so a future refactor that re-introduces them catches it here.
    """
    import vellum.storage
    # The old modules' names are reachable only if someone re-imports them.
    # Check the public __all__ does not include the module attributes.
    public = getattr(vellum.storage, "__all__", None)
    assert public is not None
    forbidden = {
        "wake_store", "user_note_store", "next_action_store",
        "turn_store", "budget_store", "settings_store", "idempotency_store",
    }
    leaked = forbidden & set(public)
    assert not leaked, (
        f"vellum.storage.__all__ leaks old module names: {sorted(leaked)}"
    )


def test_all_public_names_are_in_expected_set():
    """Inverse of test_all_documented_storage_names_importable: every name
    in ``vellum.storage.__all__`` must also appear in the test's ``expected``
    set. The first test catches a name that's *expected* but not in storage;
    this one catches a name that's *in storage* but not expected.

    Without this guard, adding a new public storage function would silently
    slip into the public surface (because nothing in the test suite would
    notice) and a future ``__init__.py`` cleanup that imports by whitelist
    could drop it.
    """
    from vellum import storage
    public = set(getattr(storage, "__all__", []))
    # Re-declare the expected set here so this test is self-contained.
    # If you add a new public storage function, add it here AND in
    # test_all_documented_storage_names_importable.
    expected = {
        # Dossier
        "create_dossier", "get_dossier", "list_dossiers", "update_dossier",
        "delete_dossier", "get_dossier_resume_state", "mark_dossier_visited",
        "get_dossier_full", "update_debrief", "update_working_theory",
        "update_premise_challenge", "update_investigation_plan",
        "approve_investigation_plan", "replan_dossier", "get_dossier_status",
        # Section
        "list_sections", "get_section", "upsert_section",
        "update_section_state", "delete_section", "reorder_sections",
        # Artifact
        "create_artifact", "get_artifact", "list_artifacts",
        "update_artifact", "delete_artifact",
        # Budget
        "record_budget_usage", "get_budget_today", "list_budget_range",
        # Decision point
        "add_decision_point", "get_decision_point",
        "resolve_decision_point", "list_decision_points",
        # Idempotency
        "get_tool_invocation", "record_tool_invocation",
        # Log
        "append_reasoning", "list_reasoning_trail", "add_ruled_out",
        "list_ruled_out", "append_investigation_log", "list_investigation_log",
        "count_investigation_log_by_type", "add_considered_and_rejected",
        "list_considered_and_rejected", "list_change_log_for_session",
        "list_change_log_since_last_visit",
        # Needs input
        "add_needs_input", "resolve_needs_input", "list_needs_input",
        # Next action
        "add_next_action", "list_next_actions", "complete_next_action",
        "remove_next_action", "reorder_next_actions",
        # Session
        "start_work_session", "get_work_session", "end_work_session",
        "get_active_work_session", "list_work_sessions",
        "increment_session_tokens", "record_session_usage",
        "record_turn_usage", "end_work_session_with_reason",
        "end_orphan_session_as_crashed", "save_session_summary",
        "get_session_summary", "list_session_summaries_for_dossier",
        # Settings
        "get_setting", "set_setting", "list_settings", "seed_default_settings",
        # Sub-investigation
        "finalize_plan_on_delivery", "spawn_sub_investigation",
        "get_sub_investigation", "list_sub_investigations",
        "update_sub_investigation_state", "update_sub_investigation",
        "complete_sub_investigation", "abandon_sub_investigation",
        # Wake
        "set_dossier_wake_at", "mark_wake_pending", "clear_dossier_wake",
        "list_dossiers_ready_to_wake", "get_dossier_wake_state",
        "increment_consecutive_error_count", "reset_consecutive_error_count",
        "set_dossier_quarantined", "clear_dossier_quarantine",
        "get_dossier_error_state",
        # H-20: last stuck signal kind
        "set_dossier_last_signal_kind",
        "get_dossier_last_signal_kind",
        # User notes
        "create_user_note", "list_user_notes", "mark_user_notes_seen",
        # Plan items
        "list_plan_items", "get_plan_item", "get_plan_item_by_id",
        "upsert_plan_item", "bulk_replace_plan_items", "set_plan_item_status",
        "delete_plan_items_for_dossier",
        # Agent turns
        "create_agent_turn", "list_agent_turns_for_dossier",
        "list_agent_turns_for_session", "list_agent_turns_for_trace",
        "get_turn_cost_summary_for_dossier",
        # Exceptions
        "ActiveWorkSessionExists",
    }
    extra = public - expected
    assert not extra, (
        f"vellum.storage.__all__ has names not in the test's expected set: "
        f"{sorted(extra)}. Add them to BOTH the importable-names test and "
        f"this one, or remove them from __all__ if they were never meant to be public."
    )


def test_no_old_storage_submodule_attribute():
    """Direct attribute access to the old modules must not work — the
    storage package is a flat namespace, not a directory of submodules.
    """
    from vellum import storage
    forbidden = {
        "wake_store", "user_note_store", "next_action_store",
        "turn_store", "budget_store", "settings_store", "idempotency_store",
    }
    for name in forbidden:
        assert not hasattr(storage, name), (
            f"vellum.storage.{name} still exists after the cleanup-2 consolidation"
        )
