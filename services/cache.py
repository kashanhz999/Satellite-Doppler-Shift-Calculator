"""Redis cache for orbital position data."""

from __future__ import annotations

import logging
from typing import Optional

from config import get_settings
from doppler_core.models import SatellitePosition

logger = logging.getLogger(__name__)

_redis = None


async def init_redis() -> None:
    """Initialize Redis connection pool."""
    global _redis
    settings = get_settings()
    if not settings.has_redis:
        return

    import redis.asyncio as aioredis

    _redis = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
    )
    # Verify connection
    try:
        await _redis.ping()
    except Exception as e:
        logger.warning("Redis connection failed: %s. Caching disabled.", e)
        _redis = None


async def close_redis() -> None:
    """Close Redis connection pool."""
    global _redis
    if _redis:
        await _redis.close()
        _redis = None


def _cache_key(norad_id: int, timestamp_unix: float, bucket_seconds: float) -> str:
    """Generate cache key with time bucketing."""
    bucket = int(timestamp_unix / bucket_seconds) * int(bucket_seconds * 1000)
    return f"sat:{norad_id}:{bucket}"


async def get_cached_position(norad_id: int, timestamp_unix: float) -> Optional[SatellitePosition]:
    """Retrieve a cached satellite position, or None if not cached."""
    if _redis is None:
        return None

    settings = get_settings()
    key = _cache_key(norad_id, timestamp_unix, settings.cache_ttl_seconds)

    try:
        data = await _redis.get(key)
        if data:
            logger.debug("Cache hit for %s", key)
            return SatellitePosition.model_validate_json(data)
    except Exception as e:
        logger.warning("Redis get failed: %s", e)

    return None


async def set_cached_position(
    norad_id: int, timestamp_unix: float, position: SatellitePosition
) -> None:
    """Store a satellite position in cache with TTL."""
    if _redis is None:
        return

    settings = get_settings()
    key = _cache_key(norad_id, timestamp_unix, settings.cache_ttl_seconds)
    ttl_ms = int(settings.cache_ttl_seconds * 1000)

    try:
        await _redis.set(key, position.model_dump_json(), px=max(ttl_ms, 100))
        logger.debug("Cached position for %s", key)
    except Exception as e:
        logger.warning("Redis set failed: %s", e)
