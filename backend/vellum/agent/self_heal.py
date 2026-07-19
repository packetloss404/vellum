"""Self-healing policy for errored and crashed sessions.

Before this module existed, a session that ended with ``end_reason=error``
went dark: the cadence auto-wake in runtime.py deliberately excludes error
ends, so nothing ever re-woke the dossier and the user found out never.
Conversely, lifecycle set ``wake_pending`` on every crashed session at boot,
so a crash-looping process retried forever with real API spend.

Policy (see also config.ERROR_RETRY_*):

  * Every failed session (``error`` from the runtime, ``crashed`` from boot
    reconcile) bumps ``dossiers.consecutive_error_count``.
  * Below the quarantine threshold, a retry wake is scheduled with
    exponential backoff: ``BASE * 2^(count-1)`` seconds, capped at ``CAP``.
    The first crash at boot keeps the historical immediate ``wake_pending``
    behavior — a single crash is usually the process dying, not the dossier.
  * At ``ERROR_RETRY_MAX`` consecutive failures the dossier is quarantined:
    wake fields are cleared, the scheduler skips it, and a loud reasoning
    trail note tells the user it needs an explicit Resume.
  * Any session that ends for a non-failure reason resets the counter, and
    an explicit user resume clears the quarantine.

Both entry points are best-effort and never raise — they run inside the
runtime's ``finally`` and lifecycle's per-session recovery, where an
exception would mask the real work of closing the session.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from .. import models as m
from .. import storage
from ..config import (
    ERROR_RETRY_BASE_SECONDS,
    ERROR_RETRY_CAP_SECONDS,
    ERROR_RETRY_MAX,
)

logger = logging.getLogger(__name__)


def backoff_seconds(count: int) -> int:
    """Delay before the Nth consecutive retry (count >= 1)."""
    return min(
        ERROR_RETRY_BASE_SECONDS * (2 ** max(0, count - 1)),
        ERROR_RETRY_CAP_SECONDS,
    )


def _append_trail_note(dossier_id: str, note: str, tags: list[str]) -> None:
    try:
        storage.append_reasoning(
            dossier_id,
            m.ReasoningAppend(note=note, tags=tags),
            work_session_id=None,
        )
    except Exception:
        logger.warning(
            "self_heal: failed to append trail note on dossier %s",
            dossier_id,
            exc_info=True,
        )


def on_session_failure(dossier_id: str, kind: str = "error") -> dict:
    """Record a failed session and schedule the retry (or quarantine).

    ``kind`` is ``"error"`` (runtime caught an exception) or ``"crash"``
    (boot reconcile found an orphan session). Returns a small descriptor of
    the action taken: ``{"action": "retry"|"quarantined"|"noop", "count": N}``.
    """
    try:
        count = storage.increment_consecutive_error_count(dossier_id)
    except Exception:
        logger.error(
            "self_heal: failed to bump error count for dossier %s; "
            "no retry will be scheduled",
            dossier_id,
            exc_info=True,
        )
        return {"action": "noop", "count": 0}

    if count >= ERROR_RETRY_MAX:
        reason = (
            f"{count} consecutive failed sessions (last: {kind}); "
            "auto-retry suspended"
        )
        try:
            storage.set_dossier_quarantined(dossier_id, reason)
        except Exception:
            logger.error(
                "self_heal: failed to quarantine dossier %s after %d failures",
                dossier_id,
                count,
                exc_info=True,
            )
            return {"action": "noop", "count": count}
        _append_trail_note(
            dossier_id,
            (
                f"[self-heal] This dossier hit {count} failed sessions in a row, "
                "so automatic retries are paused to avoid burning budget on a "
                "problem that isn't going away by itself. Nothing was lost — "
                "press Resume to try again when you're ready."
            ),
            ["lifecycle", "quarantine"],
        )
        logger.error(
            "self_heal: dossier %s QUARANTINED after %d consecutive failures (%s)",
            dossier_id,
            count,
            kind,
        )
        return {"action": "quarantined", "count": count}

    # With sleep mode off the user drives all resumes manually — keep the
    # counter (so a later re-enable still quarantines a sick dossier) but
    # don't schedule wakes, matching lifecycle's historical gating.
    try:
        sleep_enabled = storage.get_setting("sleep_mode_enabled", True)
    except Exception:
        sleep_enabled = True
    if not sleep_enabled:
        logger.info(
            "self_heal: dossier %s failure #%d (%s); sleep mode off — "
            "no retry scheduled",
            dossier_id,
            count,
            kind,
        )
        return {"action": "noop", "count": count}

    try:
        if kind == "crash" and count == 1:
            # First crash: immediate pick-up on the next scheduler tick,
            # same as the pre-self-heal behavior.
            storage.mark_wake_pending(dossier_id, m.WakeReason.crash_resume)
            delay = 0
        else:
            delay = backoff_seconds(count)
            storage.set_dossier_wake_at(
                dossier_id,
                m.utc_now() + timedelta(seconds=delay),
                m.WakeReason.error_retry,
            )
    except Exception:
        logger.error(
            "self_heal: failed to schedule retry wake for dossier %s "
            "(failure #%d, %s)",
            dossier_id,
            count,
            kind,
            exc_info=True,
        )
        return {"action": "noop", "count": count}

    if delay:
        _append_trail_note(
            dossier_id,
            (
                f"[self-heal] The last session ended with an error "
                f"(failure #{count}). A retry is scheduled in about "
                f"{delay // 60} minutes; after {ERROR_RETRY_MAX} consecutive "
                "failures retries pause and this dossier will wait for you."
            ),
            ["lifecycle", "error_retry"],
        )
    logger.info(
        "self_heal: dossier %s failure #%d (%s); retry in %ds",
        dossier_id,
        count,
        kind,
        delay,
    )
    return {"action": "retry", "count": count, "delay_seconds": delay}


def on_session_success(dossier_id: str) -> None:
    """A session ended healthy — forget the failure streak."""
    try:
        state = storage.get_dossier_error_state(dossier_id)
        if state is not None and state["consecutive_error_count"]:
            storage.reset_consecutive_error_count(dossier_id)
    except Exception:
        logger.warning(
            "self_heal: failed to reset error count for dossier %s",
            dossier_id,
            exc_info=True,
        )
