"""Bounded post-session transitions for versioned autonomous research."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .. import models as m, storage


@dataclass(frozen=True)
class AutonomyDecision:
    action: str
    reason: str | None = None


def after_session(dossier_id: str, session_id: str, end_reason: m.WorkSessionEndReason) -> AutonomyDecision:
    session = storage.get_work_session(session_id)
    if session is None or not session.research_run_id:
        return AutonomyDecision("noop", "session_not_linked_to_research_run")
    progress = storage.get_research_progress(dossier_id)
    if progress is None or not progress.active_run_id:
        return AutonomyDecision("noop")
    run = storage.get_research_run(progress.active_run_id)
    if run is None or run.id != session.research_run_id:
        return AutonomyDecision("noop", "session_run_mismatch")

    storage.sync_run_cost_from_session(session_id)
    progress = storage.get_research_progress(dossier_id) or progress

    if run.status is m.ResearchRunStatus.pause_requested:
        storage.transition_run_after_session(dossier_id, session_id, "paused", "paused_by_user")
        return AutonomyDecision("paused", "paused_by_user")
    if run.status in {m.ResearchRunStatus.cap_reached, m.ResearchRunStatus.quarantined}:
        return AutonomyDecision("paused", run.stop_reason or run.status.value)
    if end_reason in {m.WorkSessionEndReason.error, m.WorkSessionEndReason.crashed}:
        # Self-heal owns retry/backoff and quarantine. Its wake is linked to
        # this same immutable run by dossier_lifecycle.mark_wake_pending.
        return AutonomyDecision("noop", end_reason.value)
    if end_reason is m.WorkSessionEndReason.stopped:
        storage.transition_run_after_session(dossier_id, session_id, "paused", "stopped_by_user")
        return AutonomyDecision("paused", "stopped_by_user")
    if end_reason is m.WorkSessionEndReason.delivered:
        storage.transition_run_after_session(dossier_id, session_id, "completed", "dossier_delivered", notify=True)
        return AutonomyDecision("completed", "dossier_delivered")

    # Coverage completion wins over caps: hitting the final source/plan target
    # in the last allowed session is success, not a misleading cap failure.
    if progress.completion_report.ready:
        storage.transition_run_after_session(dossier_id, session_id, "completed", "coverage_targets_met", notify=True)
        return AutonomyDecision("completed", "coverage_targets_met")
    if progress.open_needs_input_count or progress.open_decision_point_count:
        storage.transition_run_after_session(dossier_id, session_id, "waiting_for_user", "waiting_for_user", notify=True)
        return AutonomyDecision("waiting", "waiting_for_user")
    if progress.sessions_used >= progress.policy.max_sessions:
        storage.transition_run_after_session(dossier_id, session_id, "cap_reached", "session_cap_reached", notify=True)
        _record_checkpoint(dossier_id, session_id, "session_cap_reached", progress)
        return AutonomyDecision("paused", "session_cap_reached")
    if progress.cost_usd >= progress.policy.max_cost_usd:
        storage.transition_run_after_session(dossier_id, session_id, "cap_reached", "cost_cap_reached", notify=True)
        _record_checkpoint(dossier_id, session_id, "cost_cap_reached", progress)
        return AutonomyDecision("paused", "cost_cap_reached")
    if not bool(storage.get_setting("sleep_mode_enabled", True)):
        storage.transition_run_after_session(dossier_id, session_id, "blocked_sleep", "sleep_mode_disabled")
        return AutonomyDecision("paused", "sleep_mode_disabled")

    storage.transition_run_after_session(dossier_id, session_id, "queued")
    refreshed = storage.get_research_progress(dossier_id)
    if refreshed and refreshed.active_run_id:
        try:
            storage.schedule_research_wake(
                dossier_id, refreshed.active_run_id, m.WakeReason.autonomous_continue,
                m.utc_now() + timedelta(minutes=refreshed.policy.continuation_delay_minutes),
            )
        except ValueError:
            # Pause/restart won the race after the session transition.
            return AutonomyDecision("noop", "run_state_changed")
    return AutonomyDecision("scheduled")


def _record_checkpoint(dossier_id: str, session_id: str, reason: str, progress: m.ResearchProgress) -> None:
    try:
        storage.append_reasoning(
            dossier_id,
            m.ReasoningAppend(note=f"[autonomy:{reason}] {progress.sessions_used}/{progress.policy.max_sessions} sessions, ${progress.cost_usd:.2f}/${progress.policy.max_cost_usd:.2f}; coverage incomplete.", tags=["autonomy", "research_checkpoint", reason]),
            work_session_id=session_id,
        )
    except Exception:
        pass
