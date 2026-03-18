"""Tests for SGP4 orbital propagation."""

from datetime import datetime, timezone

from doppler_core.propagator import compute_position, load_satellite, predict_passes


def test_load_satellite(iss_tle):
    """Verify TLE parsing produces a valid EarthSatellite."""
    sat = load_satellite(iss_tle)
    assert sat.name == "ISS (ZARYA)"
    assert sat.model.satnum == 25544


def test_compute_position_returns_valid_data(iss_tle, sf_station):
    """Verify position computation returns physically plausible values."""
    sat = load_satellite(iss_tle)
    # Use the TLE epoch time for a known-good propagation point
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    pos = compute_position(sat, sf_station, t)

    # Azimuth: 0-360
    assert 0 <= pos.azimuth_deg <= 360

    # Elevation: -90 to +90
    assert -90 <= pos.elevation_deg <= 90

    # ISS altitude: ~400-420 km
    assert 350 < pos.altitude_km < 500

    # Range: must be positive
    assert pos.range_km > 0

    # Sub-satellite latitude: ISS inclination is ~51.6 deg
    assert -52 <= pos.latitude_deg <= 52

    # NORAD ID
    assert pos.norad_id == 25544
    assert pos.satellite_name == "ISS (ZARYA)"


def test_compute_position_range_rate_sign(iss_tle, sf_station):
    """Verify range rate has a reasonable magnitude for ISS."""
    sat = load_satellite(iss_tle)
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    pos = compute_position(sat, sf_station, t)

    # ISS velocity is ~7.7 km/s; range rate should be at most this
    assert abs(pos.range_rate_km_s) < 8.0


def test_predict_passes_returns_list(iss_tle, sf_station):
    """Verify pass prediction returns a list of passes."""
    sat = load_satellite(iss_tle)
    start = datetime(2024, 2, 14, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 2, 17, 0, 0, 0, tzinfo=timezone.utc)

    pass_list = predict_passes(sat, sf_station, start, end, min_elevation_deg=10.0)

    # ISS should have multiple passes over SF in 3 days
    assert len(pass_list) > 0

    for p in pass_list:
        assert p.max_elevation_deg >= 10.0
        assert p.aos_time < p.los_time
        assert p.duration_seconds > 0
        assert p.norad_id == 25544
