import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# SQLite's CREATE TABLE IF NOT EXISTS does not add new columns to a table that
# already exists from an earlier schema. _REQUIRED_COLUMNS lists every column
# added after the initial schema; init_db applies ALTER TABLE for each missing
# one. Each entry is (table, column, type_and_default_sql). Keep additive: this
# is a one-way ratchet — we never drop or rename here.
_REQUIRED_COLUMNS: list[tuple[str, str, str]] = [
    ("dossiers", "wake_at", "TEXT"),
    ("dossiers", "wake_pending", "INTEGER NOT NULL DEFAULT 0"),
    ("dossiers", "wake_reason", "TEXT"),
    ("work_sessions", "input_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("work_sessions", "output_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("work_sessions", "cost_usd", "REAL NOT NULL DEFAULT 0"),
    ("work_sessions", "end_reason", "TEXT"),
    ("decision_points", "kind", "TEXT NOT NULL DEFAULT 'generic'"),
    # Day-4 (phase 1): sub-investigation identity.
    ("sub_investigations", "title", "TEXT"),
    ("sub_investigations", "blocked_reason", "TEXT"),
    # Phase 4 SA2: linked-question richness on sub-investigations.
    ("sub_investigations", "why_it_matters", "TEXT"),
    ("sub_investigations", "known_facts", "TEXT NOT NULL DEFAULT '[]'"),
    ("sub_investigations", "missing_facts", "TEXT NOT NULL DEFAULT '[]'"),
    ("sub_investigations", "current_finding", "TEXT"),
    ("sub_investigations", "recommended_next_step", "TEXT"),
    ("sub_investigations", "confidence", "TEXT NOT NULL DEFAULT 'unknown'"),
    # Day-4 (phase 2): working theory — JSON-encoded WorkingTheory model.
    ("dossiers", "working_theory", "TEXT"),
    ("dossiers", "premise_challenge", "TEXT"),
    # Phase 4 SA3: per-session summary — sub_investigation ids whose state or
    # current_finding moved during this session.
    ("session_summaries", "questions_advanced", "TEXT NOT NULL DEFAULT '[]'"),
    # Day-4 post-Phase-4: plan-item ↔ sub-investigation linkage so spawning
    # a sub flips the source plan item from `planned` to `in_progress`,
    # completing flips to `completed`, and abandoning flips to `abandoned`.
    ("sub_investigations", "plan_item_id", "TEXT"),
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, column, decl in _REQUIRED_COLUMNS:
        if column in _existing_columns(conn, table):
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _backfill_decision_point_kinds(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE decision_points
           SET kind = 'plan_approval'
         WHERE kind = 'generic'
           AND (
                lower(title) LIKE '%plan_approval%'
             OR lower(title) LIKE '%plan approval%'
             OR (
                    lower(title) LIKE '%plan%'
                AND (
                       lower(title) LIKE '%approve%'
                    OR lower(title) LIKE '%approval%'
                )
             )
           )
        """
    )


def _close_duplicate_active_work_sessions(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY dossier_id
                       ORDER BY started_at DESC, id DESC
                   ) AS rn
              FROM work_sessions
             WHERE ended_at IS NULL
        )
        UPDATE work_sessions
           SET ended_at = ?,
               end_reason = COALESCE(end_reason, 'crashed')
         WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """,
        (now,),
    )


def _close_duplicate_unresolved_plan_approvals(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY dossier_id
                       ORDER BY created_at DESC, id DESC
                   ) AS rn
              FROM decision_points
             WHERE kind = 'plan_approval'
               AND resolved_at IS NULL
        )
        UPDATE decision_points
           SET resolved_at = ?
         WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """,
        (now,),
    )


# Indices that reference columns added via ensure_columns must be created
# AFTER the ALTER TABLE pass — otherwise executescript sees the CREATE INDEX
# against a column that does not yet exist on a pre-sleep-mode DB and bails.
_REQUIRED_INDICES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_dossiers_wake ON dossiers(wake_pending, wake_at)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_work_sessions_one_active_per_dossier
    ON work_sessions(dossier_id)
    WHERE ended_at IS NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_points_one_open_plan_approval_per_dossier
    ON decision_points(dossier_id)
    WHERE kind = 'plan_approval' AND resolved_at IS NULL
    """,
]


def _ensure_indices(conn: sqlite3.Connection) -> None:
    for sql in _REQUIRED_INDICES:
        conn.execute(sql)


def _migrate_plan_items(conn: sqlite3.Connection) -> None:
    """One-time migration: copy plan items from the JSON blob in
    dossiers.investigation_plan into the first-class plan_items table.

    Guarded by the 'plan_items_migrated' settings sentinel so the bulk of
    the work is skipped on subsequent init_db calls.  INSERT OR IGNORE
    makes every individual row insertion idempotent, so the migration is
    safe to re-run even if the sentinel is absent (e.g. in tests that
    manually clear it).
    """
    row = conn.execute(
        "SELECT value_json FROM settings WHERE key = 'plan_items_migrated'",
    ).fetchone()
    if row is not None:
        return

    now_s = datetime.now(timezone.utc).isoformat()
    dossiers = conn.execute(
        "SELECT id, investigation_plan FROM dossiers WHERE investigation_plan IS NOT NULL",
    ).fetchall()
    for dossier in dossiers:
        dossier_id = dossier[0]
        try:
            plan = json.loads(dossier[1])
        except (json.JSONDecodeError, TypeError):
            continue
        items = plan.get("items") or []
        for idx, item in enumerate(items):
            item_id = item.get("id") or f"pli_migrated_{dossier_id}_{idx}"
            conn.execute(
                """
                INSERT OR IGNORE INTO plan_items
                    (id, dossier_id, plan_item_id, question, rationale,
                     expected_sources, as_sub_investigation, status,
                     order_key, sub_investigation_id, blocked_reason,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    dossier_id,
                    item_id,
                    item.get("question") or "",
                    item.get("rationale") or "",
                    json.dumps(item.get("expected_sources") or []),
                    int(bool(item.get("as_sub_investigation"))),
                    item.get("status") or "planned",
                    float((idx + 1) * 10),
                    item.get("sub_investigation_id"),
                    item.get("blocked_reason"),
                    now_s,
                    now_s,
                ),
            )

    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
        ("plan_items_migrated", "true", now_s),
    )


def init_db(db_path: Path | None = None) -> None:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # WAL allows concurrent readers + single writer — needed because
        # the runtime dispatches handlers in asyncio.to_thread across
        # parallel dossiers, and default rollback journal serializes harshly.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA_PATH.read_text())
        _ensure_columns(conn)
        _backfill_decision_point_kinds(conn)
        _close_duplicate_unresolved_plan_approvals(conn)
        _close_duplicate_active_work_sessions(conn)
        _ensure_indices(conn)
        _migrate_plan_items(conn)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path | None = None):
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
