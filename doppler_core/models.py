"""Pydantic data models for satellite Doppler shift computation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from doppler_core.exceptions import TLEParseError


class TLEData(BaseModel):
    """Two-Line Element set for a satellite."""

    name: str
    line1: str
    line2: str

    @field_validator("line1")
    @classmethod
    def validate_line1(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("1 "):
            raise TLEParseError("TLE line 1 must start with '1 '")
        if len(v) != 69:
            raise TLEParseError(f"TLE line 1 must be 69 characters, got {len(v)}")
        return v

    @field_validator("line2")
    @classmethod
    def validate_line2(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("2 "):
            raise TLEParseError("TLE line 2 must start with '2 '")
        if len(v) != 69:
            raise TLEParseError(f"TLE line 2 must be 69 characters, got {len(v)}")
        return v

    @property
    def norad_id(self) -> int:
        """Extract NORAD catalog number from TLE line 1."""
        return int(self.line1[2:7].strip())


class GroundStation(BaseModel):
    """Observer ground station location."""

    name: str = "default"
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0

    @field_validator("latitude_deg")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {v}")
        return v

    @field_validator("longitude_deg")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {v}")
        return v


class SatellitePosition(BaseModel):
    """Satellite position and motion relative to a ground station."""

    time_utc: datetime
    satellite_name: str
    norad_id: int

    # Topocentric (observer-relative)
    azimuth_deg: float
    elevation_deg: float
    range_km: float
    range_rate_km_s: float

    # Geocentric (sub-satellite point)
    latitude_deg: float
    longitude_deg: float
    altitude_km: float


class DopplerResult(SatellitePosition):
    """Doppler shift computation result, extending satellite position."""

    transmitted_frequency_hz: float
    received_frequency_hz: float
    doppler_shift_hz: float


class PassInfo(BaseModel):
    """Information about a satellite pass over a ground station."""

    satellite_name: str
    norad_id: int
    aos_time: datetime
    los_time: datetime
    max_elevation_deg: float
    max_elevation_time: datetime
    duration_seconds: float


def parse_tle_file(content: str) -> list[TLEData]:
    """Parse a TLE file containing one or more satellites.

    Supports standard 3-line TLE format (name + line1 + line2).
    """
    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
    tles = []

    i = 0
    while i < len(lines):
        # If current line starts with "1 ", it's line1 without a name
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            norad_id = lines[i][2:7].strip()
            tles.append(TLEData(name=f"SAT-{norad_id}", line1=lines[i], line2=lines[i + 1]))
            i += 2
        # Standard 3-line format: name, line1, line2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            tles.append(TLEData(name=lines[i], line1=lines[i + 1], line2=lines[i + 2]))
            i += 3
        else:
            i += 1  # Skip unrecognized lines

    return tles
