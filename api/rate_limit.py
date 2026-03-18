"""Rate limiting configuration."""

from fastapi import Request
from slowapi import Limiter


def _rate_limit_key(request: Request) -> str:
    """Use API key as rate limit key, falling back to client IP."""
    api_key = request.headers.get("X-API-Key")
    return api_key or (request.client.host if request.client else "unknown")


limiter = Limiter(key_func=_rate_limit_key)
