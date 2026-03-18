"""Ground station registry API routes."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GroundStationORM
from db.session import get_db
from doppler_core.models import GroundStation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ground-stations"])


# --- Request/Response models ---


class GroundStationResponse(BaseModel):
    id: int
    name: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float


class GroundStationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    latitude_deg: float = Field(..., ge=-90, le=90)
    longitude_deg: float = Field(..., ge=-180, le=180)
    elevation_m: float = Field(default=0.0)


class GroundStationUpdateRequest(BaseModel):
    latitude_deg: Optional[float] = Field(None, ge=-90, le=90)
    longitude_deg: Optional[float] = Field(None, ge=-180, le=180)
    elevation_m: Optional[float] = None


# --- Endpoints ---


@router.get("/ground-stations", response_model=List[GroundStationResponse])
async def list_ground_stations(db: AsyncSession = Depends(get_db)):
    """List all ground stations."""
    result = await db.execute(select(GroundStationORM).order_by(GroundStationORM.name))
    stations = result.scalars().all()
    return [
        GroundStationResponse(
            id=gs.id,
            name=gs.name,
            latitude_deg=gs.latitude_deg,
            longitude_deg=gs.longitude_deg,
            elevation_m=gs.elevation_m,
        )
        for gs in stations
    ]


@router.get("/ground-stations/{name}", response_model=GroundStationResponse)
async def get_ground_station(name: str, db: AsyncSession = Depends(get_db)):
    """Get a ground station by name."""
    result = await db.execute(select(GroundStationORM).where(GroundStationORM.name == name))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(status_code=404, detail=f"Ground station '{name}' not found")
    return GroundStationResponse(
        id=gs.id,
        name=gs.name,
        latitude_deg=gs.latitude_deg,
        longitude_deg=gs.longitude_deg,
        elevation_m=gs.elevation_m,
    )


@router.post("/ground-stations", response_model=GroundStationResponse, status_code=201)
async def create_ground_station(
    req: GroundStationCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Create a new ground station."""
    # Check for duplicate name
    result = await db.execute(select(GroundStationORM).where(GroundStationORM.name == req.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ground station '{req.name}' already exists")

    gs = GroundStationORM(
        name=req.name,
        latitude_deg=req.latitude_deg,
        longitude_deg=req.longitude_deg,
        elevation_m=req.elevation_m,
    )
    db.add(gs)
    await db.flush()

    return GroundStationResponse(
        id=gs.id,
        name=gs.name,
        latitude_deg=gs.latitude_deg,
        longitude_deg=gs.longitude_deg,
        elevation_m=gs.elevation_m,
    )


@router.put("/ground-stations/{name}", response_model=GroundStationResponse)
async def update_ground_station(
    name: str, req: GroundStationUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """Update a ground station."""
    result = await db.execute(select(GroundStationORM).where(GroundStationORM.name == name))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(status_code=404, detail=f"Ground station '{name}' not found")

    if req.latitude_deg is not None:
        gs.latitude_deg = req.latitude_deg
    if req.longitude_deg is not None:
        gs.longitude_deg = req.longitude_deg
    if req.elevation_m is not None:
        gs.elevation_m = req.elevation_m

    return GroundStationResponse(
        id=gs.id,
        name=gs.name,
        latitude_deg=gs.latitude_deg,
        longitude_deg=gs.longitude_deg,
        elevation_m=gs.elevation_m,
    )


@router.delete("/ground-stations/{name}")
async def delete_ground_station(name: str, db: AsyncSession = Depends(get_db)):
    """Delete a ground station."""
    result = await db.execute(select(GroundStationORM).where(GroundStationORM.name == name))
    gs = result.scalar_one_or_none()
    if not gs:
        raise HTTPException(status_code=404, detail=f"Ground station '{name}' not found")
    await db.delete(gs)
    return {"status": "deleted", "name": name}


async def resolve_ground_station(
    name: Optional[str], lat: Optional[float], lon: Optional[float], alt: float, db: AsyncSession
) -> GroundStation:
    """Resolve a ground station from either a name (DB lookup) or coordinates."""
    if name:
        result = await db.execute(select(GroundStationORM).where(GroundStationORM.name == name))
        gs = result.scalar_one_or_none()
        if not gs:
            raise HTTPException(status_code=404, detail=f"Ground station '{name}' not found")
        return GroundStation(
            name=gs.name,
            latitude_deg=gs.latitude_deg,
            longitude_deg=gs.longitude_deg,
            elevation_m=gs.elevation_m,
        )
    elif lat is not None and lon is not None:
        return GroundStation(latitude_deg=lat, longitude_deg=lon, elevation_m=alt)
    else:
        raise HTTPException(
            status_code=400, detail="Provide either ground station name or lat/lon coordinates"
        )
