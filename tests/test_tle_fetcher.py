"""Tests for TLE fetcher service."""

import pytest
import respx
from httpx import Response

from doppler_core.exceptions import CelestrakFetchError
from services.tle_fetcher import TLEFetcher, _parse_tle_epoch


SAMPLE_TLE_RESPONSE = """ISS (ZARYA)
1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993
2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354
"""


def test_parse_tle_epoch():
    """Verify TLE epoch parsing from line 1."""
    line1 = "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993"
    epoch = _parse_tle_epoch(line1)
    # 2024, day 45.549 → February 14, 2024
    assert epoch.year == 2024
    assert epoch.month == 2
    assert epoch.day == 14


@pytest.mark.asyncio
@respx.mock
async def test_fetch_by_norad_id():
    """Test fetching a single satellite by NORAD ID."""
    respx.get("https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE").mock(
        return_value=Response(200, text=SAMPLE_TLE_RESPONSE)
    )

    fetcher = TLEFetcher(base_url="https://celestrak.org")
    tle = await fetcher.fetch_by_norad_id(25544)

    assert tle.name == "ISS (ZARYA)"
    assert tle.norad_id == 25544


@pytest.mark.asyncio
@respx.mock
async def test_fetch_by_group():
    """Test fetching multiple satellites by group."""
    respx.get("https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=TLE").mock(
        return_value=Response(200, text=SAMPLE_TLE_RESPONSE)
    )

    fetcher = TLEFetcher(base_url="https://celestrak.org")
    tles = await fetcher.fetch_by_group("stations")

    assert len(tles) >= 1
    assert tles[0].norad_id == 25544


@pytest.mark.asyncio
@respx.mock
async def test_fetch_not_found():
    """Test error handling when no TLE data found."""
    respx.get("https://celestrak.org/NORAD/elements/gp.php?CATNR=99999&FORMAT=TLE").mock(
        return_value=Response(200, text="No GP data found")
    )

    fetcher = TLEFetcher(base_url="https://celestrak.org")
    with pytest.raises(CelestrakFetchError):
        await fetcher.fetch_by_norad_id(99999)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_http_error():
    """Test error handling for HTTP errors."""
    respx.get("https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE").mock(
        return_value=Response(500, text="Internal Server Error")
    )

    fetcher = TLEFetcher(base_url="https://celestrak.org")
    with pytest.raises(CelestrakFetchError):
        await fetcher.fetch_by_norad_id(25544)
