"""Shared test fixtures: per-test throwaway SQLite DB via VELLUM_DB_PATH.

Each test gets a fresh DB so tests are order-independent and don't pollute the
real `vellum.db`. We set the env var BEFORE importing vellum modules so
`config.DB_PATH` picks it up.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def fresh_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "vellum_test.db"
    monkeypatch.setenv("VELLUM_DB_PATH", str(db_path))

    # Re-import config + db so DB_PATH picks up the env var. storage imports
    # config at module load, so reloading it is enough — connect() reads
    # config.DB_PATH at call time.
    from vellum import config, db
    importlib.reload(config)
    importlib.reload(db)

    db.init_db()
    yield db_path
