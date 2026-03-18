"""API key authentication."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from config import get_settings

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    api_key: Optional[str] = Security(_api_key_header),
) -> Optional[str]:
    """FastAPI dependency that validates API key.

    If no API keys are configured (dev mode), authentication is skipped.
    """
    settings = get_settings()

    if not settings.auth_enabled:
        return None

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"type": "authentication_error", "message": "Missing API key"}},
        )

    if api_key not in settings.api_keys:
        logger.warning("Invalid API key attempt from %s", request.client.host if request.client else "unknown")
        raise HTTPException(
            status_code=401,
            detail={"error": {"type": "authentication_error", "message": "Invalid API key"}},
        )

    return api_key
