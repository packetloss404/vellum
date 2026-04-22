import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
