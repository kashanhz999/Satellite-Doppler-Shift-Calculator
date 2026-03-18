"""Background TLE auto-updater service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from config import get_settings
from services.tle_fetcher import TLEFetcher, _parse_tle_epoch

logger = logging.getLogger(__name__)


async def _update_cycle() -> None:
    """Run a single TLE update cycle for all tracked satellites."""
    from db.models import SatelliteORM
    from db.session import get_session_factory

    settings = get_settings()
    factory = get_session_factory()
    if factory is None:
        return

    fetcher = TLEFetcher()

    async with factory() as db:
        # Get all tracked satellites
        result = await db.execute(select(SatelliteORM))
        satellites = result.scalars().all()

        if not satellites:
            logger.debug("No satellites to update")
            return

        logger.info("Updating TLEs for %d satellite(s)", len(satellites))

        now = datetime.now(timezone.utc)
        stale_count = 0

        for sat in satellites:
            try:
                tle = await fetcher.fetch_by_norad_id(sat.norad_id)
                new_epoch = _parse_tle_epoch(tle.line1)

                # Only update if the fetched TLE is newer
                if sat.tle_epoch is None or new_epoch > sat.tle_epoch:
                    sat.tle_line1 = tle.line1
                    sat.tle_line2 = tle.line2
                    sat.tle_epoch = new_epoch
                    sat.name = tle.name
                    logger.info("Updated TLE for %s (NORAD %d)", sat.name, sat.norad_id)

                # Check staleness
                age_hours = (now - new_epoch).total_seconds() / 3600
                if age_hours > settings.tle_stale_threshold_hours:
                    stale_count += 1
                    logger.warning(
                        "Stale TLE: %s (NORAD %d) is %.1f hours old (threshold: %d)",
                        sat.name,
                        sat.norad_id,
                        age_hours,
                        settings.tle_stale_threshold_hours,
                    )

            except Exception as e:
                logger.error("Failed to update TLE for NORAD %d: %s", sat.norad_id, e)

        await db.commit()

        if stale_count > 0:
            logger.warning("%d satellite(s) have stale TLEs", stale_count)


async def _tle_update_loop(interval_minutes: int) -> None:
    """Continuously run TLE update cycles at the configured interval."""
    while True:
        try:
            await _update_cycle()
        except Exception as e:
            logger.error("TLE update cycle failed: %s", e)

        await asyncio.sleep(interval_minutes * 60)


async def start_tle_updater() -> asyncio.Task:
    """Start the background TLE updater task."""
    settings = get_settings()
    task = asyncio.create_task(
        _tle_update_loop(settings.tle_refresh_interval_minutes),
        name="tle-updater",
    )
    return task
