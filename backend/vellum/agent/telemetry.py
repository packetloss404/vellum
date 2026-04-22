"""Telemetry + observability for agent runs.

Day-2 deliverable verification: "did the agent actually spawn 3 subs?
consult 20+ sources? produce an artifact?". Two surfaces:

1. `log_tool_call(dossier_id, tool_name, args, result)` — a per-tool-call
   JSON-line hook. Truncates long strings so logs stay tailable. Registers
   itself into ``handlers.TOOL_HOOKS`` at import time (guarded so this
   module imports cleanly on branches where the hook list doesn't exist
   yet).

2. `session_stats(session_id)` — per-work-session aggregate: tool counts,
   source count, sub-investigation count, artifact count, tokens used,
   duration. Powers the ``GET /api/work-sessions/{id}/stats`` endpoint.

Design notes
------------
* **Logging**: stdlib ``logging`` only (per Day-2 constraint — no second
  framework). A dedicated ``vellum.agent.telemetry`` logger at INFO level.
  Defaults to stderr; redirect to a file via ``VELLUM_TOOL_LOG_PATH``.
* **Truncation**: string values in args/result truncate to 200 chars; the
  verbose-payload key ``content`` (used by ``upsert_section`` and
  ``create_artifact``) truncates to 120 chars because section bodies are
  long-form prose and flood any log otherwise.
* **duration_ms**: set to ``None`` in v2. The hook fires post-dispatch,
  so we don't have a start time. Adding a pre-dispatch hook is the
  runtime-hooks agent's call; we wire up the field shape now so the
  downstream log format doesn't break when they add it.
* **Defensive queries**: ``session_stats`` reads from tables that ship
  with other Day-2 merges (investigation_log, sub_investigations,
  artifacts). We catch ``sqlite3.OperationalError`` around each and
  return 0 when the table is absent, so this module works both before
  and after those merges land.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from .. import storage
from ..db import connect


# ---------- logger setup ----------


_LOG_PATH_ENV = "VELLUM_TOOL_LOG_PATH"
_TRUNCATE_DEFAULT = 200
_TRUNCATE_VERBOSE = 120
# Keys whose value is known to be long-form prose. Truncate these harder.
_VERBOSE_KEYS = frozenset({"content", "body", "text"})


def _build_logger() -> logging.Logger:
    """Return a dedicated logger; attach a FileHandler if env var is set,
    otherwise rely on the root stderr handler. Idempotent — safe across
    re-imports and test reloads."""
    lg = logging.getLogger("vellum.agent.telemetry")
    lg.setLevel(logging.INFO)
    lg.propagate = True  # also emit via root handler (stderr by default)

    log_path = os.getenv(_LOG_PATH_ENV)
    if log_path:
        # Avoid attaching duplicate file handlers on re-import / reload.
        already = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None) == os.path.abspath(log_path)
            for h in lg.handlers
        )
        if not already:
            fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            fh.setLevel(logging.INFO)
            fh.setFormatter(logging.Formatter("%(message)s"))
            lg.addHandler(fh)
    return lg


_logger = _build_logger()


# ---------- helpers ----------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: Any, limit: int) -> Any:
    """Shrink string-valued fields; leave non-strings untouched so numeric
    IDs, bools, nested dicts still render truthfully. Dicts and lists get a
    one-level walk so a verbose `content` string inside args gets clipped.
    """
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"…[+{len(value) - limit} chars]"
    if isinstance(value, dict):
        return {
            k: _truncate(v, _TRUNCATE_VERBOSE if k in _VERBOSE_KEYS else limit)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value]
    return value


def _preview(value: Any) -> Any:
    """Top-level preview wrapper — dicts walk with per-key limits, strings
    clip at the default, everything else passes through."""
    return _truncate(value, _TRUNCATE_DEFAULT)


# ---------- the hook ----------


def log_tool_call(
    dossier_id: str,
    tool_name: str,
    args: Any,
    result: Any,
) -> None:
    """Hook into handlers.dispatch — writes a JSON-line record per call.

    Keys: ts, dossier_id, tool_name, args_preview, result_preview, duration_ms.
    duration_ms is None in v2 (see module docstring). Never raises — a
    failed log line must not take out an agent turn.
    """
    try:
        record = {
            "ts": _utc_now_iso(),
            "dossier_id": dossier_id,
            "tool_name": tool_name,
            "args_preview": _preview(args),
            "result_preview": _preview(result),
            "duration_ms": None,
        }
        _logger.info(json.dumps(record, default=str))
    except Exception:  # noqa: BLE001 — logging must never explode
        # Log the failure through the root logger without exc_info so we
        # don't recurse; the hook stays silent by contract.
        logging.getLogger(__name__).exception(
            "telemetry.log_tool_call failed for tool=%s", tool_name
        )


# ---------- session stats ----------


def _safe_fetchall(conn: sqlite3.Connection, sql: str, params: tuple) -> list:
    """Execute a query; return [] if the referenced table doesn't exist.
    This lets session_stats run on branches where investigation_log /
    sub_investigations / artifacts haven't been merged yet."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def session_stats(session_id: str) -> Optional[dict[str, Any]]:
    """Aggregate per-work-session stats for the `/stats` endpoint.

    Returns None if no work_session row has this ``session_id``. Otherwise
    returns a dict with:
      - tool_counts: dict[str, int]
      - source_count: int
      - sub_investigation_count: int
      - artifact_count: int
      - tokens_used: int
      - duration_seconds: float
      - started_at / ended_at: ISO strings
    """
    with connect() as conn:
        session_row = conn.execute(
            "SELECT * FROM work_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session_row is None:
            return None

        dossier_id: str = session_row["dossier_id"]
        started_at_s: str = session_row["started_at"]
        ended_at_s: Optional[str] = session_row["ended_at"]
        tokens_used: int = session_row["token_budget_used"] or 0

        started_at = datetime.fromisoformat(started_at_s)
        ended_at = (
            datetime.fromisoformat(ended_at_s)
            if ended_at_s
            else datetime.now(timezone.utc)
        )

        # --- tool_counts: change_log.kind per session + investigation_log.entry_type per session.
        # change_log is always present in the schema.
        tool_counts: dict[str, int] = {}
        for r in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM change_log WHERE work_session_id = ? GROUP BY kind",
            (session_id,),
        ).fetchall():
            tool_counts[r["kind"]] = tool_counts.get(r["kind"], 0) + r["n"]

        # investigation_log may not be present pre-merge; _safe_fetchall degrades gracefully.
        for r in _safe_fetchall(
            conn,
            "SELECT entry_type, COUNT(*) AS n FROM investigation_log "
            "WHERE work_session_id = ? GROUP BY entry_type",
            (session_id,),
        ):
            tool_counts[r["entry_type"]] = tool_counts.get(r["entry_type"], 0) + r["n"]

        # --- source_count: investigation_log rows typed source_consulted in this session.
        source_rows = _safe_fetchall(
            conn,
            "SELECT COUNT(*) AS n FROM investigation_log "
            "WHERE work_session_id = ? AND entry_type = ?",
            (session_id, "source_consulted"),
        )
        source_count = source_rows[0]["n"] if source_rows else 0

        # --- sub_investigation_count: sub_investigations started inside this session's window.
        # We don't have a work_session_id column on sub_investigations (day-2
        # schema doesn't add one); instead, count rows on the same dossier
        # whose started_at falls within [session.started_at, session.ended_at
        # or now]. This matches the task wording "started within this
        # session's active window".
        end_window = ended_at_s or _utc_now_iso()
        sub_rows = _safe_fetchall(
            conn,
            "SELECT COUNT(*) AS n FROM sub_investigations "
            "WHERE dossier_id = ? AND started_at >= ? AND started_at <= ?",
            (dossier_id, started_at_s, end_window),
        )
        sub_count = sub_rows[0]["n"] if sub_rows else 0

        # --- artifact_count: change_log entries of kind artifact_added for this session.
        art_rows = conn.execute(
            "SELECT COUNT(*) AS n FROM change_log "
            "WHERE work_session_id = ? AND kind = ?",
            (session_id, "artifact_added"),
        ).fetchall()
        artifact_count = art_rows[0]["n"] if art_rows else 0

    duration_seconds = max(0.0, (ended_at - started_at).total_seconds())

    return {
        "session_id": session_id,
        "dossier_id": dossier_id,
        "tool_counts": tool_counts,
        "source_count": source_count,
        "sub_investigation_count": sub_count,
        "artifact_count": artifact_count,
        "tokens_used": tokens_used,
        "duration_seconds": duration_seconds,
        "started_at": started_at_s,
        "ended_at": ended_at_s,
    }


# ---------- hook registration ----------
#
# Register into handlers.TOOL_HOOKS at import time. Guarded because the
# runtime-hooks agent adds ``TOOL_HOOKS`` / ``dispatch()`` in parallel —
# this module must import cleanly before or after that merge.


def _register_hook() -> bool:
    try:
        from ..tools import handlers as _handlers  # noqa: WPS433
    except ImportError:
        return False
    hooks = getattr(_handlers, "TOOL_HOOKS", None)
    if hooks is None:
        return False
    if log_tool_call not in hooks:
        hooks.append(log_tool_call)
    return True


# Do the registration at import; success/failure is silent by design.
_HOOK_REGISTERED = _register_hook()


# Re-exported for tests and dev helpers.
__all__ = ["log_tool_call", "session_stats"]
