"""Custom exception hierarchy for satellite Doppler shift computation."""


class DopplerError(Exception):
    """Base exception for all Doppler-related errors."""

    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(message)


class TLEParseError(DopplerError):
    """Raised when a TLE string cannot be parsed or is malformed."""

    pass


class PropagationError(DopplerError):
    """Raised when SGP4/skyfield orbital propagation fails."""

    pass


class StaleTLEError(PropagationError):
    """Raised when a TLE is older than the configured threshold."""

    def __init__(self, message: str, tle_age_hours: float, detail: str = ""):
        self.tle_age_hours = tle_age_hours
        super().__init__(message, detail)


class SatelliteNotFoundError(DopplerError):
    """Raised when a satellite NORAD ID is not found in the registry."""

    def __init__(self, norad_id: int, detail: str = ""):
        self.norad_id = norad_id
        super().__init__(f"Satellite with NORAD ID {norad_id} not found", detail)


class CelestrakFetchError(DopplerError):
    """Raised when fetching TLE data from Celestrak fails."""

    pass
