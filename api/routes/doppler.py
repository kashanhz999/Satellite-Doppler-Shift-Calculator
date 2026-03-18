"""Doppler shift API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import require_api_key
from api.rate_limit import limiter
from doppler_core.doppler import compute_doppler, compute_doppler_batch, compute_doppler_series
from doppler_core.models import DopplerResult, GroundStation, PassInfo, TLEData
from doppler_core.propagator import load_satellite, predict_passes

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


# --- Request models ---


class GroundStationRequest(BaseModel):
    latitude_deg: float
    longitude_deg: float
    elevation_m: float = 0.0


class ComputeRequest(BaseModel):
    tle: TLEData
    ground_station: GroundStationRequest
    frequency_hz: float
    time_utc: Optional[str] = None


class SeriesRequest(BaseModel):
    tle: TLEData
    ground_station: GroundStationRequest
    frequency_hz: float
    start_utc: str
    end_utc: str
    step_seconds: float = 1.0


class BatchRequest(BaseModel):
    tles: List[TLEData]
    ground_station: GroundStationRequest
    frequency_hz: float
    time_utc: Optional[str] = None


class PredictPassesRequest(BaseModel):
    tle: TLEData
    ground_station: GroundStationRequest
    days: int = Field(default=3, ge=1, le=14)
    min_elevation_deg: float = Field(default=10.0, ge=0, le=90)


# --- Response models ---


class ComputeResponse(BaseModel):
    result: DopplerResult


class SeriesResponse(BaseModel):
    results: List[DopplerResult]
    count: int


class BatchResponse(BaseModel):
    results: List[DopplerResult]
    count: int


class PassesResponse(BaseModel):
    passes: List[PassInfo]
    count: int


# --- Helpers ---


def _parse_time(time_str: Optional[str]) -> Optional[datetime]:
    if time_str is None:
        return None
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {time_str}")


def _to_ground_station(req: GroundStationRequest) -> GroundStation:
    return GroundStation(
        latitude_deg=req.latitude_deg,
        longitude_deg=req.longitude_deg,
        elevation_m=req.elevation_m,
    )


# --- Endpoints ---


@router.post("/doppler/compute", response_model=ComputeResponse)
@limiter.limit("100/minute")
async def doppler_compute(request: Request, req: ComputeRequest):
    """Compute Doppler shift for a single satellite at a given time (or now)."""
    gs = _to_ground_station(req.ground_station)
    t = _parse_time(req.time_utc)
    result = compute_doppler(req.tle, gs, req.frequency_hz, t)
    return ComputeResponse(result=result)


@router.post("/doppler/series", response_model=SeriesResponse)
@limiter.limit("10/minute")
async def doppler_series(request: Request, req: SeriesRequest):
    """Compute Doppler shift over a time interval."""
    gs = _to_ground_station(req.ground_station)
    start = _parse_time(req.start_utc)
    end = _parse_time(req.end_utc)

    if start is None or end is None:
        raise HTTPException(status_code=400, detail="start_utc and end_utc are required")
    if end <= start:
        raise HTTPException(status_code=400, detail="end_utc must be after start_utc")

    num_points = (end - start).total_seconds() / req.step_seconds
    if num_points > 3600:
        raise HTTPException(
            status_code=400,
            detail=f"Too many data points ({int(num_points)}). Max 3600. Increase step_seconds.",
        )

    results = compute_doppler_series(req.tle, gs, req.frequency_hz, start, end, req.step_seconds)
    return SeriesResponse(results=results, count=len(results))


@router.post("/doppler/batch", response_model=BatchResponse)
@limiter.limit("10/minute")
async def doppler_batch(request: Request, req: BatchRequest):
    """Compute Doppler shift for multiple satellites at a single time."""
    if len(req.tles) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 satellites per batch request")

    gs = _to_ground_station(req.ground_station)
    t = _parse_time(req.time_utc)
    results = compute_doppler_batch(req.tles, gs, req.frequency_hz, t)
    return BatchResponse(results=results, count=len(results))


@router.post("/passes/predict", response_model=PassesResponse)
@limiter.limit("10/minute")
async def passes_predict(request: Request, req: PredictPassesRequest):
    """Predict satellite passes over a ground station."""
    gs = _to_ground_station(req.ground_station)
    sat = load_satellite(req.tle)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=req.days)
    pass_list = predict_passes(sat, gs, now, end, min_elevation_deg=req.min_elevation_deg)
    return PassesResponse(passes=pass_list, count=len(pass_list))
