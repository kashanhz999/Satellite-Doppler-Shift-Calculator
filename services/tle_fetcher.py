"""TLE fetching service for Celestrak integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from doppler_core.exceptions import CelestrakFetchError
from doppler_core.models import TLEData, parse_tle_file

logger = logging.getLogger(__name__)


def _parse_tle_epoch(line1: str) -> datetime:
    """Extract epoch datetime from TLE line 1 (chars 18-32).

    Format: YYDDD.DDDDDDDD where YY=year, DDD.DDD=day of year with fraction.
    """
    epoch_str = line1[18:32].strip()
    year_2d = int(epoch_str[:2])
    day_frac = float(epoch_str[2:])

    # Two-digit year: 57-99 → 1957-1999, 00-56 → 2000-2056
    year = 2000 + year_2d if year_2d < 57 else 1900 + year_2d

    from datetime import timedelta

    epoch = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_frac - 1)
    return epoch


class TLEFetcher:
    """Fetch TLE data from Celestrak."""

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.celestrak_base_url

    async def fetch_by_norad_id(self, norad_id: int) -> TLEData:
        """Fetch TLE for a single satellite by NORAD ID."""
        url = f"{self.base_url}/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
        return (await self._fetch_and_parse(url))[0]

    async def fetch_by_group(self, group: str) -> List[TLEData]:
        """Fetch TLEs for a satellite group (e.g., 'stations', 'active')."""
        url = f"{self.base_url}/NORAD/elements/gp.php?GROUP={group}&FORMAT=TLE"
        return await self._fetch_and_parse(url)

    async def _fetch_and_parse(self, url: str) -> List[TLEData]:
        """Fetch TLE data from URL and parse."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise CelestrakFetchError(
                f"Celestrak returned HTTP {e.response.status_code}",
                detail=str(e),
            )
        except httpx.RequestError as e:
            raise CelestrakFetchError(
                f"Failed to connect to Celestrak: {e}",
                detail=str(e),
            )

        content = response.text.strip()
        if not content or "No GP data found" in content:
            raise CelestrakFetchError("No TLE data found for the given query")

        tles = parse_tle_file(content)
        if not tles:
            raise CelestrakFetchError("Failed to parse TLE response from Celestrak")

        logger.info("Fetched %d TLE(s) from Celestrak", len(tles))
        return tles

    async def fetch_and_store(
        self, norad_ids: List[int], db: AsyncSession
    ) -> List[TLEData]:
        """Fetch TLEs by NORAD IDs and upsert into database."""
        from db.models import SatelliteORM

        results = []
        for nid in norad_ids:
            try:
                tle = await self.fetch_by_norad_id(nid)
                epoch = _parse_tle_epoch(tle.line1)

                # Upsert
                existing = await db.get(SatelliteORM, nid)
                if existing:
                    existing.name = tle.name
                    existing.tle_line1 = tle.line1
                    existing.tle_line2 = tle.line2
                    existing.tle_epoch = epoch
                else:
                    db.add(
                        SatelliteORM(
                            norad_id=nid,
                            name=tle.name,
                            tle_line1=tle.line1,
                            tle_line2=tle.line2,
                            tle_epoch=epoch,
                        )
                    )
                results.append(tle)
                logger.info("Stored TLE for %s (NORAD %d)", tle.name, nid)
            except CelestrakFetchError as e:
                logger.error("Failed to fetch TLE for NORAD %d: %s", nid, e.message)

        await db.commit()
        return results

    async def fetch_group_and_store(
        self, group: str, db: AsyncSession
    ) -> List[TLEData]:
        """Fetch all TLEs in a group and upsert into database."""
        from db.models import SatelliteORM

        tles = await self.fetch_by_group(group)
        for tle in tles:
            epoch = _parse_tle_epoch(tle.line1)
            nid = tle.norad_id

            existing = await db.get(SatelliteORM, nid)
            if existing:
                existing.name = tle.name
                existing.tle_line1 = tle.line1
                existing.tle_line2 = tle.line2
                existing.tle_epoch = epoch
            else:
                db.add(
                    SatelliteORM(
                        norad_id=nid,
                        name=tle.name,
                        tle_line1=tle.line1,
                        tle_line2=tle.line2,
                        tle_epoch=epoch,
                    )
                )

        await db.commit()
        logger.info("Stored %d TLE(s) from group '%s'", len(tles), group)
        return tles
