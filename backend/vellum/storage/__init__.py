"""Storage layer for Vellum, split into per-domain modules.

This module re-exports all public storage functions from their respective
domain-specific modules, maintaining the same API as the original monolithic storage.py.
"""

# Dossier operations
from .dossier_store import (
    create_dossier,
    get_dossier,
    list_dossiers,
    update_dossier,
    delete_dossier,
    get_dossier_resume_state,
    mark_dossier_visited,
    get_dossier_full,
    update_debrief,
    update_working_theory,
    update_premise_challenge,
    update_investigation_plan,
    approve_investigation_plan,
    replan_dossier,
    get_dossier_status,
)

# Section operations
from .section_store import (
    list_sections,
    get_section,
    upsert_section,
    update_section_state,
    delete_section,
    reorder_sections,
)

# Artifact operations
from .artifact_store import (
    create_artifact,
    get_artifact,
    list_artifacts,
    update_artifact,
    delete_artifact,
)

# Budget operations
from .budget_store import (
    record_budget_usage,
    get_budget_today,
    list_budget_range,
)

# Decision point operations
from .decision_point_store import (
    add_decision_point,
    resolve_decision_point,
    list_decision_points,
)

# Idempotency operations
from .idempotency_store import (
    get_tool_invocation,
    record_tool_invocation,
)

# Log operations (reasoning, ruled out, investigation log, considered & rejected, change log)
from .log_store import (
    append_reasoning,
    list_reasoning_trail,
    add_ruled_out,
    list_ruled_out,
    append_investigation_log,
    list_investigation_log,
    count_investigation_log_by_type,
    add_considered_and_rejected,
    list_considered_and_rejected,
    list_change_log_for_session,
    list_change_log_since_last_visit,
)

# Needs input operations
from .needs_input_store import (
    add_needs_input,
    resolve_needs_input,
    list_needs_input,
)

# Next action operations
from .next_action_store import (
    add_next_action,
    list_next_actions,
    complete_next_action,
    remove_next_action,
    reorder_next_actions,
)

# Work session operations
from .session_store import (
    start_work_session,
    get_work_session,
    end_work_session,
    get_active_work_session,
    list_work_sessions,
    increment_session_tokens,
    record_session_usage,
    end_work_session_with_reason,
    end_orphan_session_as_crashed,
    save_session_summary,
    get_session_summary,
    list_session_summaries_for_dossier,
)

# Settings operations
from .settings_store import (
    get_setting,
    set_setting,
    list_settings,
    seed_default_settings,
)

# Sub-investigation operations
from .sub_investigation_store import (
    finalize_plan_on_delivery,
    spawn_sub_investigation,
    get_sub_investigation,
    list_sub_investigations,
    update_sub_investigation_state,
    update_sub_investigation,
    complete_sub_investigation,
    abandon_sub_investigation,
)

# Wake/sleep-mode operations
from .wake_store import (
    set_dossier_wake_at,
    mark_wake_pending,
    clear_dossier_wake,
    list_dossiers_ready_to_wake,
    get_dossier_wake_state,
)

# Plan items operations (Phase 4B)
from .plan_items_store import (
    list_plan_items,
    get_plan_item,
    get_plan_item_by_id,
    upsert_plan_item,
    bulk_replace_plan_items,
    set_plan_item_status,
    delete_plan_items_for_dossier,
)

# Agent turn operations (Phase 4A)
from .turn_store import (
    create_agent_turn,
    list_agent_turns_for_dossier,
    list_agent_turns_for_session,
    list_agent_turns_for_trace,
    get_turn_cost_summary_for_dossier,
)

# Exception from helpers (raised by session operations)
from ._helpers import ActiveWorkSessionExists

__all__ = [
    # Dossier
    "create_dossier",
    "get_dossier",
    "list_dossiers",
    "update_dossier",
    "delete_dossier",
    "get_dossier_resume_state",
    "mark_dossier_visited",
    "get_dossier_full",
    "update_debrief",
    "update_working_theory",
    "update_premise_challenge",
    "update_investigation_plan",
    "approve_investigation_plan",
    "replan_dossier",
    "get_dossier_status",
    # Section
    "list_sections",
    "get_section",
    "upsert_section",
    "update_section_state",
    "delete_section",
    "reorder_sections",
    # Artifact
    "create_artifact",
    "get_artifact",
    "list_artifacts",
    "update_artifact",
    "delete_artifact",
    # Budget
    "record_budget_usage",
    "get_budget_today",
    "list_budget_range",
    # Decision point
    "add_decision_point",
    "resolve_decision_point",
    "list_decision_points",
    # Idempotency
    "get_tool_invocation",
    "record_tool_invocation",
    # Log
    "append_reasoning",
    "list_reasoning_trail",
    "add_ruled_out",
    "list_ruled_out",
    "append_investigation_log",
    "list_investigation_log",
    "count_investigation_log_by_type",
    "add_considered_and_rejected",
    "list_considered_and_rejected",
    "list_change_log_for_session",
    "list_change_log_since_last_visit",
    # Needs input
    "add_needs_input",
    "resolve_needs_input",
    "list_needs_input",
    # Next action
    "add_next_action",
    "list_next_actions",
    "complete_next_action",
    "remove_next_action",
    "reorder_next_actions",
    # Session
    "start_work_session",
    "get_work_session",
    "end_work_session",
    "get_active_work_session",
    "list_work_sessions",
    "increment_session_tokens",
    "record_session_usage",
    "end_work_session_with_reason",
    "end_orphan_session_as_crashed",
    "save_session_summary",
    "get_session_summary",
    "list_session_summaries_for_dossier",
    # Settings
    "get_setting",
    "set_setting",
    "list_settings",
    "seed_default_settings",
    # Sub-investigation
    "finalize_plan_on_delivery",
    "spawn_sub_investigation",
    "get_sub_investigation",
    "list_sub_investigations",
    "update_sub_investigation_state",
    "update_sub_investigation",
    "complete_sub_investigation",
    "abandon_sub_investigation",
    # Wake
    "set_dossier_wake_at",
    "mark_wake_pending",
    "clear_dossier_wake",
    "list_dossiers_ready_to_wake",
    "get_dossier_wake_state",
    # Plan items (Phase 4B)
    "list_plan_items",
    "get_plan_item",
    "get_plan_item_by_id",
    "upsert_plan_item",
    "bulk_replace_plan_items",
    "set_plan_item_status",
    "delete_plan_items_for_dossier",
    # Agent turns (Phase 4A)
    "create_agent_turn",
    "list_agent_turns_for_dossier",
    "list_agent_turns_for_session",
    "list_agent_turns_for_trace",
    "get_turn_cost_summary_for_dossier",
    # Exceptions
    "ActiveWorkSessionExists",
]
