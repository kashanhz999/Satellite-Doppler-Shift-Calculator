"""Tests for WebSocket real-time streaming."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

ISS_TLE = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
    "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354",
}


def test_websocket_connect_and_receive():
    """Test WebSocket connection and receiving Doppler data."""
    with client.websocket_connect("/api/v1/ws/track") as ws:
        # Send tracking config
        ws.send_json({
            "tles": [ISS_TLE],
            "frequency_hz": 145.825e6,
            "ground_station": {"latitude_deg": 37.77, "longitude_deg": -122.42, "elevation_m": 0},
            "interval_seconds": 0.1,
        })

        # Should receive config acknowledgment
        msg = ws.receive_json()
        assert msg["type"] == "config_accepted"
        assert msg["tracking"] == 1

        # Should receive Doppler update
        msg = ws.receive_json()
        assert msg["type"] == "doppler_update"
        assert len(msg["results"]) == 1
        assert "doppler_shift_hz" in msg["results"][0]


def test_websocket_invalid_config():
    """Test WebSocket with invalid config."""
    with client.websocket_connect("/api/v1/ws/track") as ws:
        ws.send_json({"invalid": "config"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
