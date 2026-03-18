"""SGP4 orbital propagation and position computation via skyfield."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from skyfield.api import EarthSatellite, load, wgs84
from skyfield.timelib import Time

from doppler_core.exceptions import PropagationError
from doppler_core.models import GroundStation, PassInfo, SatellitePosition, TLEData

# Module-level timescale (loaded once, reused)
_ts = load.timescale()


def load_satellite(tle: TLEData) -> EarthSatellite:
    """Parse a TLE into a skyfield EarthSatellite object."""
    try:
        return EarthSatellite(tle.line1, tle.line2, tle.name, _ts)
    except Exception as e:
        raise PropagationError(f"Failed to load satellite from TLE: {e}", detail=str(e))


def _to_skyfield_time(dt: Optional[datetime] = None) -> Time:
    """Convert a datetime to skyfield Time. Uses current UTC if None."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _ts.from_datetime(dt)


def _build_topos(gs: GroundStation):
    """Build a skyfield geographic position from a GroundStation."""
    return wgs84.latlon(gs.latitude_deg, gs.longitude_deg, gs.elevation_m)


def compute_position(
    satellite: EarthSatellite,
    ground_station: GroundStation,
    time: Optional[datetime] = None,
) -> SatellitePosition:
    """Compute satellite position relative to a ground station at a given time.

    Returns topocentric (az/el/range/range-rate) and geocentric (lat/lon/alt) data.
    """
    try:
        t = _to_skyfield_time(time)
        topos = _build_topos(ground_station)

        # Geocentric position
        geocentric = satellite.at(t)
        subpoint = wgs84.subpoint(geocentric)

        # Topocentric (observer-relative)
        difference = satellite - topos
        topocentric = difference.at(t)
        alt, az, distance = topocentric.altaz()

        # Range rate via velocity projection
        pos = topocentric.position.km
        vel = topocentric.velocity.km_per_s
        range_km = distance.km

        # Radial velocity = dot(position, velocity) / |position|
        range_rate = (pos[0] * vel[0] + pos[1] * vel[1] + pos[2] * vel[2]) / range_km
    except PropagationError:
        raise
    except Exception as e:
        raise PropagationError(
            f"Failed to compute position for {satellite.name}: {e}", detail=str(e)
        )

    return SatellitePosition(
        time_utc=t.utc_datetime(),
        satellite_name=satellite.name,
        norad_id=int(satellite.model.satnum),
        azimuth_deg=round(az.degrees, 4),
        elevation_deg=round(alt.degrees, 4),
        range_km=round(range_km, 4),
        range_rate_km_s=round(range_rate, 6),
        latitude_deg=round(subpoint.latitude.degrees, 4),
        longitude_deg=round(subpoint.longitude.degrees, 4),
        altitude_km=round(subpoint.elevation.km, 4),
    )


def compute_positions(
    satellite: EarthSatellite,
    ground_station: GroundStation,
    times: List[datetime],
) -> List[SatellitePosition]:
    """Compute satellite positions at multiple times."""
    return [compute_position(satellite, ground_station, t) for t in times]


def predict_passes(
    satellite: EarthSatellite,
    ground_station: GroundStation,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    min_elevation_deg: float = 10.0,
) -> List[PassInfo]:
    """Predict satellite passes over a ground station.

    Returns passes where the satellite rises above min_elevation_deg.
    Default window: now to 3 days from now.
    """
    from datetime import timedelta

    if start is None:
        start = datetime.now(timezone.utc)
    if end is None:
        end = start + timedelta(days=3)

    t0 = _to_skyfield_time(start)
    t1 = _to_skyfield_time(end)
    topos = _build_topos(ground_station)

    t_events, events = satellite.find_events(topos, t0, t1, altitude_degrees=min_elevation_deg)

    passes = []
    i = 0
    while i < len(events):
        # find_events returns: 0=rise, 1=culmination, 2=set
        # Collect a complete rise-culminate-set triplet
        if events[i] == 0:  # rise
            aos_time = t_events[i].utc_datetime()
            max_el_time = None
            max_el_deg = min_elevation_deg
            los_time = None

            j = i + 1
            while j < len(events) and events[j] != 0:
                if events[j] == 1:  # culmination
                    max_el_time = t_events[j].utc_datetime()
                    # Compute actual max elevation
                    diff = satellite - topos
                    topo_at_max = diff.at(t_events[j])
                    alt_at_max, _, _ = topo_at_max.altaz()
                    max_el_deg = alt_at_max.degrees
                elif events[j] == 2:  # set
                    los_time = t_events[j].utc_datetime()
                    j += 1
                    break
                j += 1

            if los_time and max_el_time:
                duration = (los_time - aos_time).total_seconds()
                passes.append(
                    PassInfo(
                        satellite_name=satellite.name,
                        norad_id=int(satellite.model.satnum),
                        aos_time=aos_time,
                        los_time=los_time,
                        max_elevation_deg=round(max_el_deg, 2),
                        max_elevation_time=max_el_time,
                        duration_seconds=round(duration, 1),
                    )
                )
            i = j
        else:
            i += 1

    return passes
