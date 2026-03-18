"""Tests for FastAPI REST API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

ISS_TLE = {
    "name": "ISS (ZARYA)",
    "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
    "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354",
}

SF_STATION = {"latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0.0}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_doppler_compute():
    response = client.post(
        "/api/v1/doppler/compute",
        json={
            "tle": ISS_TLE,
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
            "time_utc": "2024-02-14T13:10:00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    result = data["result"]

    assert result["transmitted_frequency_hz"] == 145.825e6
    assert "doppler_shift_hz" in result
    assert "received_frequency_hz" in result
    assert "azimuth_deg" in result
    assert "elevation_deg" in result
    assert "range_km" in result
    assert abs(result["doppler_shift_hz"]) < 5000


def test_doppler_compute_without_time():
    """Should default to current time when time_utc is omitted."""
    response = client.post(
        "/api/v1/doppler/compute",
        json={
            "tle": ISS_TLE,
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
        },
    )
    assert response.status_code == 200


def test_doppler_series():
    response = client.post(
        "/api/v1/doppler/series",
        json={
            "tle": ISS_TLE,
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
            "start_utc": "2024-02-14T13:00:00",
            "end_utc": "2024-02-14T13:00:05",
            "step_seconds": 1.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 6
    assert len(data["results"]) == 6


def test_doppler_batch():
    response = client.post(
        "/api/v1/doppler/batch",
        json={
            "tles": [ISS_TLE],
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
            "time_utc": "2024-02-14T13:10:00",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert len(data["results"]) == 1


def test_passes_predict():
    response = client.post(
        "/api/v1/passes/predict",
        json={
            "tle": ISS_TLE,
            "ground_station": SF_STATION,
            "days": 3,
            "min_elevation_deg": 10.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "passes" in data
    assert "count" in data
    assert data["count"] >= 0


def test_invalid_tle():
    response = client.post(
        "/api/v1/doppler/compute",
        json={
            "tle": {"name": "BAD", "line1": "bad data", "line2": "bad data"},
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
        },
    )
    assert response.status_code in (400, 422)  # TLEParseError (400) or Pydantic (422)


def test_series_too_many_points():
    response = client.post(
        "/api/v1/doppler/series",
        json={
            "tle": ISS_TLE,
            "ground_station": SF_STATION,
            "frequency_hz": 145.825e6,
            "start_utc": "2024-02-14T00:00:00",
            "end_utc": "2024-02-15T00:00:00",
            "step_seconds": 1.0,  # 86400 points > 3600 limit
        },
    )
    assert response.status_code == 400
    assert "Too many data points" in response.json()["detail"]
