"""Shared pytest fixtures for Vellum's backend tests.

The DB path is an env var read by ``vellum.config`` at import time. We have to
point ``VELLUM_DB_PATH`` at a throwaway SQLite file BEFORE any ``vellum.*``
modules get imported, and we have to reset the module-level ``config.DB_PATH``
between tests so ``db.connect()`` picks up the new path.
"""
from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Point vellum.config.DB_PATH at a fresh tempfile and re-init the schema."""
    tmpdir = Path(tempfile.gettempdir()) / "vellum_tests"
    tmpdir.mkdir(parents=True, exist_ok=True)
    db_path = tmpdir / f"test_{os.getpid()}_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}.db"

    monkeypatch.setenv("VELLUM_DB_PATH", str(db_path))

    from vellum import config as _config
    from vellum import db as _db

    monkeypatch.setattr(_config, "DB_PATH", db_path)
    _db.init_db(db_path)

    yield db_path

    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suffix)
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
