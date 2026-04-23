"""HTTP endpoints for the DB-backed settings surface and budget rollup.

Settings are JSON-valued; the UI owns validation shape per key (types are
not checked at write time beyond JSON-encodability). Ian's call to keep
sprint scope honest — settings are intentionally untyped at the API layer
and the Python consumers use storage.get_setting(key, default) with
sensible fallbacks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import storage


router = APIRouter(prefix="/api")


class SettingOut(BaseModel):
    key: str
    value: Any
    updated_at: datetime


class SettingUpdateBody(BaseModel):
    value: Any


@router.get("/settings", response_model=list[SettingOut])
def list_settings() -> list[SettingOut]:
    return [SettingOut(key=s.key, value=s.value, updated_at=s.updated_at) for s in storage.list_settings()]


@router.get("/settings/{key}", response_model=SettingOut)
def get_setting(key: str) -> SettingOut:
    for s in storage.list_settings():
        if s.key == key:
            return SettingOut(key=s.key, value=s.value, updated_at=s.updated_at)
    raise HTTPException(404, f"setting {key!r} not found")


@router.put("/settings/{key}", response_model=SettingOut)
def put_setting(key: str, body: SettingUpdateBody) -> SettingOut:
    s = storage.set_setting(key, body.value)
    return SettingOut(key=s.key, value=s.value, updated_at=s.updated_at)


# ---------- Budget ----------


@router.get("/budget/today")
def budget_today() -> dict:
    roll = storage.get_budget_today()
    daily_cap = float(storage.get_setting("budget_daily_soft_cap_usd", 0) or 0)
    warn_fraction = float(storage.get_setting("budget_daily_warn_fraction", 0.8) or 0.8)
    state = "ok"
    if daily_cap > 0:
        if roll.spent_usd >= daily_cap:
            state = "soft_cap_crossed"
        elif roll.spent_usd >= daily_cap * warn_fraction:
            state = "warn"
    return {
        "day": roll.day,
        "spent_usd": roll.spent_usd,
        "input_tokens": roll.input_tokens,
        "output_tokens": roll.output_tokens,
        "updated_at": roll.updated_at.isoformat(),
        "daily_cap_usd": daily_cap,
        "warn_fraction": warn_fraction,
        "state": state,
    }


@router.get("/budget/range")
def budget_range(days: int = 7) -> list[dict]:
    """Last `days` days ending today (UTC), inclusive. Clamped to [1, 90]."""
    days = max(1, min(int(days), 90))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    rows = storage.list_budget_range(start.isoformat(), today.isoformat())
    return [
        {
            "day": r.day,
            "spent_usd": r.spent_usd,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]
