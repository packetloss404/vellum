from __future__ import annotations

import hmac
from typing import Optional

from fastapi import Header, HTTPException

from .. import config


def require_api_token(
    authorization: Optional[str] = Header(default=None),
    x_vellum_api_token: Optional[str] = Header(default=None),
) -> None:
    """Optional bearer-token guard for local or tunneled API access."""
    if not config.API_TOKEN:
        if config.API_AUTH_REQUIRED:
            raise HTTPException(
                status_code=503,
                detail="API auth is required but VELLUM_API_TOKEN is not configured",
            )
        return

    supplied = x_vellum_api_token
    if not supplied and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = value

    if not supplied or not hmac.compare_digest(supplied, config.API_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing API token")
