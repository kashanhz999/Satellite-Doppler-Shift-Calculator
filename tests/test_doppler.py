"""Tests for Doppler shift computation."""

from datetime import datetime, timedelta, timezone

from doppler_core.doppler import SPEED_OF_LIGHT_KM_S, compute_doppler, compute_doppler_series


ISS_FREQ_HZ = 145.825e6  # 145.825 MHz amateur radio downlink


def test_compute_doppler_returns_valid_result(iss_tle, sf_station):
    """Verify Doppler computation returns physically plausible values."""
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    result = compute_doppler(iss_tle, sf_station, ISS_FREQ_HZ, t)

    # Check fields exist and are populated
    assert result.transmitted_frequency_hz == ISS_FREQ_HZ
    assert result.received_frequency_hz > 0
    assert result.doppler_shift_hz != 0  # very unlikely to be exactly 0

    # For ISS at 145.825 MHz, max Doppler shift is approximately +/- 3500 Hz
    assert abs(result.doppler_shift_hz) < 5000

    # Received = transmitted + shift
    expected_rx = ISS_FREQ_HZ + result.doppler_shift_hz
    assert abs(result.received_frequency_hz - expected_rx) < 0.01


def test_doppler_sign_convention(iss_tle, sf_station):
    """Verify: approaching satellite -> positive Doppler shift (higher freq)."""
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    result = compute_doppler(iss_tle, sf_station, ISS_FREQ_HZ, t)

    if result.range_rate_km_s < 0:
        # Approaching: Doppler should be positive
        assert result.doppler_shift_hz > 0
    elif result.range_rate_km_s > 0:
        # Receding: Doppler should be negative
        assert result.doppler_shift_hz < 0


def test_doppler_formula_consistency(iss_tle, sf_station):
    """Verify the Doppler formula is applied correctly."""
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    result = compute_doppler(iss_tle, sf_station, ISS_FREQ_HZ, t)

    # Manual Doppler calculation from range rate
    expected_shift = ISS_FREQ_HZ * (-result.range_rate_km_s / SPEED_OF_LIGHT_KM_S)
    assert abs(result.doppler_shift_hz - expected_shift) < 0.1


def test_compute_doppler_series(iss_tle, sf_station):
    """Verify series computation returns correct number of points."""
    start = datetime(2024, 2, 14, 13, 0, 0, tzinfo=timezone.utc)
    end = datetime(2024, 2, 14, 13, 0, 10, tzinfo=timezone.utc)

    results = compute_doppler_series(iss_tle, sf_station, ISS_FREQ_HZ, start, end, step_seconds=1.0)

    assert len(results) == 11  # 0, 1, 2, ..., 10 seconds
    assert all(r.transmitted_frequency_hz == ISS_FREQ_HZ for r in results)

    # Timestamps should be monotonically increasing
    for i in range(1, len(results)):
        assert results[i].time_utc > results[i - 1].time_utc


def test_doppler_zero_frequency(iss_tle, sf_station):
    """Doppler shift should be 0 when transmitted frequency is 0."""
    t = datetime(2024, 2, 14, 13, 10, 0, tzinfo=timezone.utc)
    result = compute_doppler(iss_tle, sf_station, 0.0, t)
    assert result.doppler_shift_hz == 0.0
    assert result.received_frequency_hz == 0.0
