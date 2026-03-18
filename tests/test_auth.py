"""Tests for API key authentication."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _make_client(api_keys=None):
    """Create a test client with specific API key settings."""
    env = {}
    if api_keys:
        env["DOPPLER_API_KEYS"] = str(api_keys)

    # Clear cached settings
    from config import get_settings
    get_settings.cache_clear()

    with patch.dict(os.environ, env, clear=False):
        get_settings.cache_clear()
        # Re-import to pick up new settings
        from api.main import app
        return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_settings():
    from config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_always_accessible():
    """Health endpoint should work regardless of auth."""
    from api.main import app
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_no_auth_when_keys_empty():
    """When no API keys configured, endpoints should work without auth."""
    from api.main import app
    client = TestClient(app)
    response = client.post(
        "/api/v1/doppler/compute",
        json={
            "tle": {
                "name": "ISS",
                "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
                "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354",
            },
            "ground_station": {"latitude_deg": 37.77, "longitude_deg": -122.42},
            "frequency_hz": 145825000,
            "time_utc": "2024-02-14T13:10:00",
        },
    )
    assert response.status_code == 200
