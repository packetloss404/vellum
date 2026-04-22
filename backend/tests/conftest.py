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
    """Point vellum.config.DB_PATH at a fresh tempfile and re-init the schema.

    Each test that touches storage should depend on this fixture. We patch both
    the env var (for any late-reading code) and ``vellum.config.DB_PATH``
    directly (since config already read the env var on first import).
    """
    # Isolate sqlite files across tests — temp dir + pid + uuid avoids collisions
    # if pytest runs in parallel or a previous run left WAL sidecar files.
    tmpdir = Path(tempfile.gettempdir()) / "vellum_tests"
    tmpdir.mkdir(parents=True, exist_ok=True)
    db_path = tmpdir / f"test_{os.getpid()}_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}.db"

    monkeypatch.setenv("VELLUM_DB_PATH", str(db_path))

    # Late import so we don't cache at collection time.
    from vellum import config as _config
    from vellum import db as _db

    monkeypatch.setattr(_config, "DB_PATH", db_path)
    _db.init_db(db_path)

    yield db_path

    # Best-effort cleanup — WAL/SHM sidecars tag along.
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(db_path) + suffix)
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
