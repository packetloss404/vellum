"""Settings CRUD."""
from __future__ import annotations

import json

from .. import models as m
from ..db import connect
from ._helpers import _dt, _dt_str


def get_setting(key: str, default=None):
    """Return the JSON-decoded value for `key`, or `default` if not set."""
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return default
    return json.loads(row["value_json"])


def set_setting(key: str, value) -> m.Setting:
    """UPSERT a setting. Value is JSON-encoded. Returns the stored row."""
    now_s = _dt_str(m.utc_now())
    blob = json.dumps(value)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, blob, now_s),
        )
    return m.Setting(key=key, value=value, updated_at=m.utc_now())


def list_settings() -> list[m.Setting]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json, updated_at FROM settings ORDER BY key"
        ).fetchall()
    return [
        m.Setting(
            key=r["key"],
            value=json.loads(r["value_json"]),
            updated_at=_dt(r["updated_at"]),
        )
        for r in rows
    ]


def seed_default_settings(defaults: dict) -> None:
    """Insert missing defaults only — never overwrite an edited value."""
    with connect() as conn:
        for key, value in defaults.items():
            row = conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                continue
            conn.execute(
                "INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), _dt_str(m.utc_now())),
            )
