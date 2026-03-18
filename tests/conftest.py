"""Shared test fixtures."""

import pytest

from doppler_core.models import GroundStation, TLEData

# ISS TLE (epoch: 2024-02-14)
ISS_TLE = TLEData(
    name="ISS (ZARYA)",
    line1="1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
    line2="2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354",
)

# San Francisco ground station
SF_GROUND_STATION = GroundStation(
    name="San Francisco",
    latitude_deg=37.7749,
    longitude_deg=-122.4194,
    elevation_m=0.0,
)


@pytest.fixture
def iss_tle():
    return ISS_TLE


@pytest.fixture
def sf_station():
    return SF_GROUND_STATION


@pytest.fixture
def iss_tle_dict():
    return {
        "name": "ISS (ZARYA)",
        "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
        "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354",
    }


@pytest.fixture
def sf_station_dict():
    return {"latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0.0}
