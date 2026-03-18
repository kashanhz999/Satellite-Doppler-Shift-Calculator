"""Doppler shift computation for satellite signals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional


from doppler_core.models import DopplerResult, GroundStation, TLEData
from doppler_core.propagator import compute_position, load_satellite

# Speed of light in km/s
SPEED_OF_LIGHT_KM_S = 299792.458


def compute_doppler(
    tle: TLEData,
    ground_station: GroundStation,
    frequency_hz: float,
    time: Optional[datetime] = None,
) -> DopplerResult:
    """Compute Doppler shift for a satellite signal at a given time.

    The Doppler shift formula:
        f_received = f_transmitted * (1 - range_rate / c)

    Sign convention: range_rate > 0 means satellite is moving away (receding),
    which produces a negative Doppler shift (lower received frequency).
    range_rate < 0 means satellite is approaching, producing positive shift.
    """
    satellite = load_satellite(tle)
    pos = compute_position(satellite, ground_station, time)

    # Doppler formula: negative range_rate means approaching
    doppler_ratio = -pos.range_rate_km_s / SPEED_OF_LIGHT_KM_S
    doppler_shift_hz = frequency_hz * doppler_ratio
    received_frequency_hz = frequency_hz + doppler_shift_hz

    return DopplerResult(
        # Position fields
        time_utc=pos.time_utc,
        satellite_name=pos.satellite_name,
        norad_id=pos.norad_id,
        azimuth_deg=pos.azimuth_deg,
        elevation_deg=pos.elevation_deg,
        range_km=pos.range_km,
        range_rate_km_s=pos.range_rate_km_s,
        latitude_deg=pos.latitude_deg,
        longitude_deg=pos.longitude_deg,
        altitude_km=pos.altitude_km,
        # Doppler fields
        transmitted_frequency_hz=frequency_hz,
        received_frequency_hz=round(received_frequency_hz, 3),
        doppler_shift_hz=round(doppler_shift_hz, 3),
    )


def compute_doppler_series(
    tle: TLEData,
    ground_station: GroundStation,
    frequency_hz: float,
    start: datetime,
    end: datetime,
    step_seconds: float = 1.0,
) -> List[DopplerResult]:
    """Compute Doppler shift over a time interval.

    Useful for plotting Doppler curves during satellite passes.
    """
    satellite = load_satellite(tle)
    results = []

    current = start
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    step = timedelta(seconds=step_seconds)

    while current <= end:
        pos = compute_position(satellite, ground_station, current)
        doppler_ratio = -pos.range_rate_km_s / SPEED_OF_LIGHT_KM_S
        doppler_shift_hz = frequency_hz * doppler_ratio
        received_frequency_hz = frequency_hz + doppler_shift_hz

        results.append(
            DopplerResult(
                time_utc=pos.time_utc,
                satellite_name=pos.satellite_name,
                norad_id=pos.norad_id,
                azimuth_deg=pos.azimuth_deg,
                elevation_deg=pos.elevation_deg,
                range_km=pos.range_km,
                range_rate_km_s=pos.range_rate_km_s,
                latitude_deg=pos.latitude_deg,
                longitude_deg=pos.longitude_deg,
                altitude_km=pos.altitude_km,
                transmitted_frequency_hz=frequency_hz,
                received_frequency_hz=round(received_frequency_hz, 3),
                doppler_shift_hz=round(doppler_shift_hz, 3),
            )
        )
        current += step

    return results


def compute_doppler_batch(
    tles: List[TLEData],
    ground_station: GroundStation,
    frequency_hz: float,
    time: Optional[datetime] = None,
) -> List[DopplerResult]:
    """Compute Doppler shift for multiple satellites at a single time instant."""
    return [compute_doppler(tle, ground_station, frequency_hz, time) for tle in tles]
