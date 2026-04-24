import sqlite3
from contextlib import contextmanager
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
]


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, column, decl in _REQUIRED_COLUMNS:
        if column in _existing_columns(conn, table):
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# Indices that reference columns added via ensure_columns must be created
# AFTER the ALTER TABLE pass — otherwise executescript sees the CREATE INDEX
# against a column that does not yet exist on a pre-sleep-mode DB and bails.
_REQUIRED_INDICES: list[tuple[str, str, str]] = [
    ("idx_dossiers_wake", "dossiers", "wake_pending, wake_at"),
]


def _ensure_indices(conn: sqlite3.Connection) -> None:
    for name, table, columns in _REQUIRED_INDICES:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})")


def init_db(db_path: Path | None = None) -> None:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        # WAL allows concurrent readers + single writer — needed because
        # the runtime dispatches handlers in asyncio.to_thread across
        # parallel dossiers, and default rollback journal serializes harshly.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA_PATH.read_text())
        _ensure_columns(conn)
        _ensure_indices(conn)
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
