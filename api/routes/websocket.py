"""WebSocket endpoint for real-time satellite Doppler tracking."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from config import get_settings
from doppler_core.doppler import compute_doppler
from doppler_core.models import GroundStation, TLEData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class TrackConfig(BaseModel):
    """Client-sent tracking configuration."""

    satellite_ids: Optional[List[int]] = None
    tles: Optional[List[TLEData]] = None
    frequency_hz: float
    ground_station: dict
    interval_seconds: float = 1.0


@router.websocket("/ws/track")
async def websocket_track(
    ws: WebSocket,
    api_key: Optional[str] = Query(None),
):
    """Real-time Doppler tracking via WebSocket.

    Client sends a JSON config, server streams DopplerResult every interval.
    Client can send updated config mid-stream.
    """
    # Auth check
    settings = get_settings()
    if settings.auth_enabled:
        if not api_key or api_key not in settings.api_keys:
            await ws.close(code=4001, reason="Invalid or missing API key")
            return

    await ws.accept()
    logger.info("WebSocket client connected")

    config: Optional[TrackConfig] = None
    tles: List[TLEData] = []

    try:
        while True:
            # Check for new config (non-blocking if already have config)
            try:
                if config is None:
                    # First message must be config
                    raw = await ws.receive_json()
                else:
                    # Check for config updates with a short timeout
                    raw = await asyncio.wait_for(ws.receive_json(), timeout=0.01)

                config = TrackConfig(**raw)
                tles = await _resolve_tles(config)
                gs = GroundStation(**config.ground_station)
                await ws.send_json({"type": "config_accepted", "tracking": len(tles)})
                logger.info("Tracking config updated: %d satellite(s)", len(tles))

            except asyncio.TimeoutError:
                pass  # No new config, continue streaming
            except ValidationError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                if config is None:
                    continue  # Wait for valid config

            if config is None or not tles:
                continue

            # Compute and stream Doppler results
            gs = GroundStation(**config.ground_station)
            results = []
            for tle in tles:
                try:
                    result = compute_doppler(tle, gs, config.frequency_hz)
                    results.append(result.model_dump(mode="json"))
                except Exception as e:
                    logger.error("Doppler computation error: %s", e)

            if results:
                await ws.send_json(
                    {
                        "type": "doppler_update",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "results": results,
                    }
                )

            await asyncio.sleep(config.interval_seconds)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await ws.close(code=1011, reason="Internal error")
        except Exception:
            pass


async def _resolve_tles(config: TrackConfig) -> List[TLEData]:
    """Resolve TLEs from config — either inline TLEs or lookup by satellite IDs from DB."""
    if config.tles:
        return config.tles

    if config.satellite_ids:
        settings = get_settings()
        if settings.has_database:
            from db.models import SatelliteORM
            from db.session import get_session_factory

            factory = get_session_factory()
            if factory:
                async with factory() as db:
                    tles = []
                    for nid in config.satellite_ids:
                        sat = await db.get(SatelliteORM, nid)
                        if sat:
                            tles.append(
                                TLEData(name=sat.name, line1=sat.tle_line1, line2=sat.tle_line2)
                            )
                    return tles

    return []
