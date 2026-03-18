"""Satellite registry API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.rate_limit import limiter
from db.models import SatelliteORM
from db.session import get_db
from doppler_core.exceptions import CelestrakFetchError, SatelliteNotFoundError
from doppler_core.models import DopplerResult, GroundStation, TLEData
from doppler_core.propagator import compute_position, load_satellite
from services.tle_fetcher import TLEFetcher, _parse_tle_epoch

logger = logging.getLogger(__name__)

router = APIRouter(tags=["satellites"])


# --- Request/Response models ---


class SatelliteResponse(BaseModel):
    norad_id: int
    name: str
    tle_line1: str
    tle_line2: str
    tle_epoch: datetime
    reference_freq_hz: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class SatelliteListResponse(BaseModel):
    satellites: List[SatelliteResponse]
    total: int
    page: int
    page_size: int


class AddSatellitesByNoradRequest(BaseModel):
    norad_ids: List[int] = Field(..., min_length=1, max_length=50)


class AddSatellitesByTLERequest(BaseModel):
    tles: List[TLEData] = Field(..., min_length=1, max_length=50)


class FetchGroupRequest(BaseModel):
    group: str = Field(..., description="Celestrak group name (e.g., 'stations', 'active')")


class AddSatellitesResponse(BaseModel):
    added: int
    satellites: List[SatelliteResponse]


# --- Endpoints ---


@router.get("/satellites", response_model=SatelliteListResponse)
async def list_satellites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all tracked satellites with pagination."""
    offset = (page - 1) * page_size

    total_result = await db.execute(select(func.count()).select_from(SatelliteORM))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(SatelliteORM).order_by(SatelliteORM.name).offset(offset).limit(page_size)
    )
    sats = result.scalars().all()

    return SatelliteListResponse(
        satellites=[
            SatelliteResponse(
                norad_id=s.norad_id,
                name=s.name,
                tle_line1=s.tle_line1,
                tle_line2=s.tle_line2,
                tle_epoch=s.tle_epoch,
                reference_freq_hz=s.reference_freq_hz,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sats
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/satellites/{norad_id}", response_model=SatelliteResponse)
async def get_satellite(norad_id: int, db: AsyncSession = Depends(get_db)):
    """Get satellite detail by NORAD ID."""
    sat = await db.get(SatelliteORM, norad_id)
    if not sat:
        raise SatelliteNotFoundError(norad_id)
    return SatelliteResponse(
        norad_id=sat.norad_id,
        name=sat.name,
        tle_line1=sat.tle_line1,
        tle_line2=sat.tle_line2,
        tle_epoch=sat.tle_epoch,
        reference_freq_hz=sat.reference_freq_hz,
        created_at=sat.created_at,
        updated_at=sat.updated_at,
    )


@router.post("/satellites", response_model=AddSatellitesResponse)
async def add_satellites_by_tle(req: AddSatellitesByTLERequest, db: AsyncSession = Depends(get_db)):
    """Add satellites by providing TLE data directly."""
    added = []
    for tle in req.tles:
        epoch = _parse_tle_epoch(tle.line1)
        existing = await db.get(SatelliteORM, tle.norad_id)
        if existing:
            existing.name = tle.name
            existing.tle_line1 = tle.line1
            existing.tle_line2 = tle.line2
            existing.tle_epoch = epoch
            sat = existing
        else:
            sat = SatelliteORM(
                norad_id=tle.norad_id,
                name=tle.name,
                tle_line1=tle.line1,
                tle_line2=tle.line2,
                tle_epoch=epoch,
            )
            db.add(sat)

        await db.flush()
        added.append(
            SatelliteResponse(
                norad_id=sat.norad_id,
                name=sat.name,
                tle_line1=sat.tle_line1,
                tle_line2=sat.tle_line2,
                tle_epoch=sat.tle_epoch,
                reference_freq_hz=sat.reference_freq_hz,
                created_at=sat.created_at,
                updated_at=sat.updated_at,
            )
        )

    return AddSatellitesResponse(added=len(added), satellites=added)


@router.post("/satellites/fetch", response_model=AddSatellitesResponse)
@limiter.limit("5/minute")
async def fetch_satellites(request: Request, req: AddSatellitesByNoradRequest, db: AsyncSession = Depends(get_db)):
    """Fetch TLEs from Celestrak by NORAD IDs and add to registry."""
    fetcher = TLEFetcher()
    tles = await fetcher.fetch_and_store(req.norad_ids, db)

    # Re-read the stored satellites
    sats = []
    for tle in tles:
        sat = await db.get(SatelliteORM, tle.norad_id)
        if sat:
            sats.append(
                SatelliteResponse(
                    norad_id=sat.norad_id,
                    name=sat.name,
                    tle_line1=sat.tle_line1,
                    tle_line2=sat.tle_line2,
                    tle_epoch=sat.tle_epoch,
                    reference_freq_hz=sat.reference_freq_hz,
                    created_at=sat.created_at,
                    updated_at=sat.updated_at,
                )
            )

    return AddSatellitesResponse(added=len(sats), satellites=sats)


@router.post("/satellites/fetch-group", response_model=AddSatellitesResponse)
@limiter.limit("5/minute")
async def fetch_satellite_group(request: Request, req: FetchGroupRequest, db: AsyncSession = Depends(get_db)):
    """Fetch all TLEs in a Celestrak group and add to registry."""
    fetcher = TLEFetcher()
    tles = await fetcher.fetch_group_and_store(req.group, db)

    sats = []
    for tle in tles:
        sat = await db.get(SatelliteORM, tle.norad_id)
        if sat:
            sats.append(
                SatelliteResponse(
                    norad_id=sat.norad_id,
                    name=sat.name,
                    tle_line1=sat.tle_line1,
                    tle_line2=sat.tle_line2,
                    tle_epoch=sat.tle_epoch,
                    reference_freq_hz=sat.reference_freq_hz,
                    created_at=sat.created_at,
                    updated_at=sat.updated_at,
                )
            )

    return AddSatellitesResponse(added=len(sats), satellites=sats)


@router.delete("/satellites/{norad_id}")
async def delete_satellite(norad_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a satellite from tracking."""
    sat = await db.get(SatelliteORM, norad_id)
    if not sat:
        raise SatelliteNotFoundError(norad_id)
    await db.delete(sat)
    return {"status": "deleted", "norad_id": norad_id}


@router.get("/satellites/{norad_id}/position")
async def get_satellite_position(
    norad_id: int,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    alt: float = Query(0.0),
    db: AsyncSession = Depends(get_db),
):
    """Get current position of a tracked satellite."""
    sat = await db.get(SatelliteORM, norad_id)
    if not sat:
        raise SatelliteNotFoundError(norad_id)

    tle = TLEData(name=sat.name, line1=sat.tle_line1, line2=sat.tle_line2)
    gs = GroundStation(latitude_deg=lat, longitude_deg=lon, elevation_m=alt)
    satellite = load_satellite(tle)
    pos = compute_position(satellite, gs)

    return pos.model_dump()
