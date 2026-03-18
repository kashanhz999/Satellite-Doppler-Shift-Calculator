"""FastAPI application for satellite Doppler shift computation."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from api.middleware import RequestIDMiddleware
from api.rate_limit import limiter
from config import get_settings
from doppler_core.exceptions import (
    CelestrakFetchError,
    DopplerError,
    PropagationError,
    SatelliteNotFoundError,
    StaleTLEError,
    TLEParseError,
)
from logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init/close DB, Redis, background tasks."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting Satellite Doppler Shift API", extra={"version": "0.2.0"})

    # Database
    if settings.has_database:
        from db.session import close_db, init_db

        await init_db()
        logger.info("Database connected")

    # Redis
    if settings.has_redis:
        from services.cache import init_redis

        await init_redis()
        logger.info("Redis connected")

    # Background TLE updater
    updater_task = None
    if settings.has_database:
        from services.tle_updater import start_tle_updater

        updater_task = await start_tle_updater()
        logger.info(
            "TLE auto-updater started",
            extra={"interval_minutes": settings.tle_refresh_interval_minutes},
        )

    yield

    # Shutdown
    if updater_task:
        updater_task.cancel()
        try:
            await updater_task
        except asyncio.CancelledError:
            pass
        logger.info("TLE auto-updater stopped")

    if settings.has_redis:
        from services.cache import close_redis

        await close_redis()
        logger.info("Redis disconnected")

    if settings.has_database:
        from db.session import close_db

        await close_db()
        logger.info("Database disconnected")

    logger.info("Shutdown complete")


app = FastAPI(
    title="Satellite Doppler Shift API",
    description="Real-time satellite Doppler shift computation using SGP4 orbital propagation",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

# --- Middleware ---

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)


# --- Exception handlers ---


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "type": "rate_limit_exceeded",
                "message": "Too many requests",
                "detail": str(exc.detail),
            }
        },
        headers={"Retry-After": str(exc.detail)},
    )


@app.exception_handler(TLEParseError)
async def tle_parse_error_handler(request: Request, exc: TLEParseError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {"type": "tle_parse_error", "message": exc.message, "detail": exc.detail}
        },
    )


@app.exception_handler(SatelliteNotFoundError)
async def satellite_not_found_handler(request: Request, exc: SatelliteNotFoundError):
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "type": "satellite_not_found",
                "message": exc.message,
                "detail": exc.detail,
            }
        },
    )


@app.exception_handler(StaleTLEError)
async def stale_tle_handler(request: Request, exc: StaleTLEError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "type": "stale_tle",
                "message": exc.message,
                "detail": exc.detail,
                "tle_age_hours": exc.tle_age_hours,
            }
        },
    )


@app.exception_handler(PropagationError)
async def propagation_error_handler(request: Request, exc: PropagationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {"type": "propagation_error", "message": exc.message, "detail": exc.detail}
        },
    )


@app.exception_handler(CelestrakFetchError)
async def celestrak_error_handler(request: Request, exc: CelestrakFetchError):
    return JSONResponse(
        status_code=502,
        content={
            "error": {"type": "celestrak_fetch_error", "message": exc.message, "detail": exc.detail}
        },
    )


@app.exception_handler(DopplerError)
async def doppler_error_handler(request: Request, exc: DopplerError):
    return JSONResponse(
        status_code=500,
        content={"error": {"type": "doppler_error", "message": exc.message, "detail": exc.detail}},
    )


# --- Routers ---

from api.routes.doppler import router as doppler_router  # noqa: E402

app.include_router(doppler_router, prefix="/api/v1")

# Conditionally include DB-dependent routers
if settings.has_database:
    from api.routes.ground_stations import router as gs_router  # noqa: E402
    from api.routes.satellites import router as sat_router  # noqa: E402

    app.include_router(sat_router, prefix="/api/v1")
    app.include_router(gs_router, prefix="/api/v1")

from api.routes.websocket import router as ws_router  # noqa: E402

app.include_router(ws_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}
