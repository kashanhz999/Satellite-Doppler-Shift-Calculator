"""Tests for Redis cache service."""

from datetime import datetime, timezone

from doppler_core.models import SatellitePosition
from services.cache import _cache_key


def test_cache_key_generation():
    """Verify cache key generation with time bucketing."""
    key = _cache_key(25544, 1708000000.0, 0.5)
    assert key.startswith("sat:25544:")
    assert isinstance(key, str)


def test_cache_key_same_bucket():
    """Timestamps in the same bucket should produce the same key."""
    key1 = _cache_key(25544, 1708000000.0, 1.0)
    key2 = _cache_key(25544, 1708000000.5, 1.0)
    assert key1 == key2


def test_cache_key_different_bucket():
    """Timestamps in different buckets should produce different keys."""
    key1 = _cache_key(25544, 1708000000.0, 1.0)
    key2 = _cache_key(25544, 1708000001.0, 1.0)
    assert key1 != key2


def test_cache_key_different_satellites():
    """Different satellites should produce different keys."""
    key1 = _cache_key(25544, 1708000000.0, 1.0)
    key2 = _cache_key(12345, 1708000000.0, 1.0)
    assert key1 != key2
