# Satellite Doppler Shift Calculator

A production-grade system for computing real-time Doppler frequency shifts caused by satellite motion relative to ground stations. Uses SGP4 orbital propagation with NORAD Two-Line Element (TLE) data to predict satellite positions and calculate the resulting frequency shifts for radio communications.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development Setup](#local-development-setup)
- [CLI Reference](#cli-reference)
- [API Reference](#api-reference)
- [WebSocket Streaming](#websocket-streaming)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Database & Migrations](#database--migrations)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)

---

## Features

**Core Physics**
- SGP4 orbital propagation using AFSPC-verified `python-sgp4` library
- Doppler shift calculation: `f_rx = f_tx * (1 - range_rate / c)`
- Range rate via velocity vector projection in topocentric frame
- Satellite pass prediction with AOS/LOS times and max elevation

**REST API**
- Single-point, time-series, and multi-satellite batch Doppler computation
- Satellite and ground station registries with full CRUD
- Satellite pass prediction
- Interactive API docs (Swagger UI)

**Real-Time**
- WebSocket endpoint for live Doppler tracking with configurable update intervals
- Mid-stream configuration updates without reconnecting

**TLE Management**
- Fetch live TLE data from Celestrak by NORAD ID or satellite group
- Background auto-updater refreshes TLEs on a configurable interval
- Stale TLE detection and warnings

**CLI**
- Compute Doppler shift, live-track satellites, predict passes
- Fetch TLEs from Celestrak
- Manage named ground stations locally

**Infrastructure**
- PostgreSQL persistence with async SQLAlchemy 2.0
- Redis caching for satellite position lookups
- API key authentication (disabled in dev mode)
- Per-endpoint rate limiting via slowapi
- Structured JSON logging with per-request tracing IDs
- Multi-stage Docker build with non-root user
- Docker Compose stack (API + PostgreSQL + Redis)
- GitHub Actions CI (lint + test + Docker build)
- Graceful degradation: works without DB (inline TLE mode), without Redis (no caching), without auth (dev mode)

---

## How It Works

1. **Input**: A Two-Line Element (TLE) set describes a satellite's orbit. A ground station is defined by latitude, longitude, and elevation.

2. **Propagation**: The SGP4 algorithm propagates the TLE to compute the satellite's position and velocity in Earth-Centered Inertial (ECI) coordinates at any given time.

3. **Coordinate Transform**: Skyfield converts ECI coordinates to a topocentric frame relative to the ground station, yielding azimuth, elevation, range, and range rate.

4. **Doppler Calculation**: The range rate (how fast the distance between satellite and station is changing) determines the frequency shift:
   - Satellite approaching (negative range rate) = positive frequency shift (signal compressed)
   - Satellite receding (positive range rate) = negative frequency shift (signal stretched)
   - Formula: `doppler_shift = -f_tx * range_rate / speed_of_light`

---

## Prerequisites

- **Python 3.9+** (for local development)
- **Docker & Docker Compose** (for containerized deployment)

---

## Quick Start (Docker)

This starts the complete stack: API server + PostgreSQL + Redis.

### 1. Clone and start

```bash
git clone <repository-url>
cd "Satellite Doppler Shift Tool"
docker compose up --build
```

Three containers start:

| Container | Port | Purpose |
|-----------|------|---------|
| `api` | `localhost:8000` | FastAPI application |
| `postgres` | `localhost:5432` | PostgreSQL 16 database |
| `redis` | `localhost:6379` | Redis 7 cache |

The API waits for database and Redis health checks before starting.

### 2. Run database migrations (first time only)

```bash
docker compose exec api alembic upgrade head
```

This creates the `satellites`, `ground_stations`, and `doppler_measurements` tables.

### 3. Verify it's working

```bash
# Health check
curl http://localhost:8000/health

# Open interactive API docs
open http://localhost:8000/docs
```

### 4. Compute your first Doppler shift

```bash
curl -s -X POST http://localhost:8000/api/v1/doppler/compute \
  -H "Content-Type: application/json" \
  -d '{
    "tle": {
      "name": "ISS (ZARYA)",
      "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
      "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354"
    },
    "ground_station": {
      "latitude_deg": 37.7749,
      "longitude_deg": -122.4194,
      "elevation_m": 0
    },
    "frequency_hz": 145825000
  }' | python -m json.tool
```

### 5. Managing the stack

```bash
docker compose up -d              # Start in background
docker compose up --build         # Rebuild and start (foreground)
docker compose logs -f api        # Follow API logs
docker compose down               # Stop all containers
docker compose down -v            # Stop and delete all data (DB + Redis volumes)
docker compose restart api        # Restart API only
```

---

## Local Development Setup

Run without Docker, using only the core features (no database or Redis required).

### 1. Create virtual environment and install

```bash
cd "Satellite Doppler Shift Tool"
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows

pip install -e ".[dev]"
```

### 2. Run the API server

```bash
# Minimal mode (no DB, no Redis — inline TLE only)
doppler serve --reload

# With PostgreSQL + Redis (start services first)
docker compose up postgres redis -d
cp .env.example .env
alembic upgrade head
doppler serve --reload
```

The API is available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### 3. Run tests

```bash
pytest tests/ -v
```

All 30 tests pass without needing PostgreSQL or Redis (they use mocks and in-memory backends).

---

## CLI Reference

The CLI is installed as the `doppler` command.

### `doppler compute` — Compute Doppler shift

Compute the Doppler shift for one or more satellites at the current time.

```bash
# Using inline TLE and coordinates
doppler compute \
  --tle "ISS (ZARYA)\n1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993\n2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354" \
  --lat 37.7749 --lon -122.4194 --alt 0 \
  --freq 145825000

# Using a TLE file
doppler compute --tle-file satellites.tle --lat 37.7749 --lon -122.4194 --freq 145825000

# Using a saved ground station
doppler compute --tle-file satellites.tle --ground-station home --freq 145825000
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tle TEXT` | Inline TLE data (name\nline1\nline2) |
| `--tle-file PATH` | Path to a TLE file (3-line format, can contain multiple satellites) |
| `--freq FLOAT` | Transmitted frequency in Hz (required) |
| `--lat FLOAT` | Ground station latitude in degrees |
| `--lon FLOAT` | Ground station longitude in degrees |
| `--alt FLOAT` | Ground station altitude in meters (default: 0) |
| `--ground-station NAME` | Use a saved ground station by name |

### `doppler track` — Live tracking

Continuously compute and display Doppler shift with a live-updating table.

```bash
doppler track \
  --tle-file satellites.tle \
  --ground-station home \
  --freq 145825000 \
  --interval 2.0
```

Shows a live table with azimuth, elevation, range, range rate, Doppler shift, received frequency, and visibility status. Press `Ctrl+C` to stop.

**Additional option:**
| Option | Description |
|--------|-------------|
| `--interval FLOAT` | Update interval in seconds (default: 1.0) |

### `doppler passes` — Predict satellite passes

Predict when satellites will be visible above a minimum elevation.

```bash
doppler passes \
  --tle-file satellites.tle \
  --ground-station home \
  --days 5 \
  --min-el 15
```

Shows a table with AOS time, max elevation time, LOS time, maximum elevation angle, and pass duration.

**Additional options:**
| Option | Description |
|--------|-------------|
| `--days INT` | Number of days to predict (default: 3) |
| `--min-el FLOAT` | Minimum elevation in degrees (default: 10.0) |

### `doppler fetch` — Fetch TLEs from Celestrak

Download live TLE data from Celestrak.

```bash
# Fetch a single satellite by NORAD ID
doppler fetch --norad-id 25544

# Fetch an entire group
doppler fetch --group stations

# Save to file
doppler fetch --norad-id 25544 --output iss.tle
```

**Options:**
| Option | Description |
|--------|-------------|
| `--norad-id INT` | NORAD catalog number |
| `--group TEXT` | Celestrak group name (e.g., "stations", "active", "weather") |
| `--output PATH` | Save TLE data to file |

### `doppler serve` — Start the API server

```bash
doppler serve --host 0.0.0.0 --port 8000 --reload
```

**Options:**
| Option | Description |
|--------|-------------|
| `--host TEXT` | Host to bind to (default: 0.0.0.0) |
| `--port INT` | Port to bind to (default: 8000) |
| `--reload` | Enable auto-reload for development |

### `doppler config` — Manage ground stations

Save frequently used ground stations locally in `~/.doppler/stations.json`.

```bash
# Add a ground station
doppler config add-station --name home --lat 37.7749 --lon -122.4194 --alt 10

# List saved stations
doppler config list-stations

# Remove a station
doppler config remove-station --name home
```

Once saved, use `--ground-station home` in any command instead of `--lat/--lon/--alt`.

---

## API Reference

Base URL: `http://localhost:8000`

### Health Check

```
GET /health
```

Returns `{"status": "ok", "version": "0.2.0"}`. Not rate-limited, no authentication required.

---

### Doppler Endpoints

All Doppler endpoints require authentication (if enabled) and accept JSON request bodies.

#### POST /api/v1/doppler/compute

Compute Doppler shift for a single satellite at a given time (or now).

**Rate limit:** 100 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/doppler/compute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{
    "tle": {
      "name": "ISS (ZARYA)",
      "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
      "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354"
    },
    "ground_station": {
      "latitude_deg": 37.7749,
      "longitude_deg": -122.4194,
      "elevation_m": 0
    },
    "frequency_hz": 145825000,
    "time_utc": "2024-02-14T13:10:00"
  }'
```

**Response:**
```json
{
  "result": {
    "satellite_name": "ISS (ZARYA)",
    "time_utc": "2024-02-14T13:10:00+00:00",
    "transmitted_frequency_hz": 145825000.0,
    "received_frequency_hz": 145826234.5,
    "doppler_shift_hz": 1234.5,
    "azimuth_deg": 245.3,
    "elevation_deg": 32.1,
    "range_km": 842.7,
    "range_rate_km_s": -2.54
  }
}
```

The `time_utc` field is optional. If omitted, the current time is used.

#### POST /api/v1/doppler/series

Compute Doppler shift over a time interval. Maximum 3600 data points per request.

**Rate limit:** 10 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/doppler/series \
  -H "Content-Type: application/json" \
  -d '{
    "tle": { "name": "ISS", "line1": "...", "line2": "..." },
    "ground_station": { "latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0 },
    "frequency_hz": 145825000,
    "start_utc": "2024-02-14T13:00:00",
    "end_utc": "2024-02-14T13:10:00",
    "step_seconds": 1.0
  }'
```

**Response:**
```json
{
  "results": [ { "satellite_name": "...", "doppler_shift_hz": ... }, ... ],
  "count": 601
}
```

#### POST /api/v1/doppler/batch

Compute Doppler shift for multiple satellites at a single time. Maximum 100 satellites per request.

**Rate limit:** 10 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/doppler/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tles": [
      { "name": "ISS", "line1": "...", "line2": "..." },
      { "name": "NOAA 19", "line1": "...", "line2": "..." }
    ],
    "ground_station": { "latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0 },
    "frequency_hz": 145825000,
    "time_utc": "2024-02-14T13:10:00"
  }'
```

#### POST /api/v1/passes/predict

Predict satellite passes over a ground station for the next N days.

**Rate limit:** 10 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/passes/predict \
  -H "Content-Type: application/json" \
  -d '{
    "tle": { "name": "ISS", "line1": "...", "line2": "..." },
    "ground_station": { "latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0 },
    "days": 3,
    "min_elevation_deg": 10.0
  }'
```

**Response:**
```json
{
  "passes": [
    {
      "aos_time": "2024-02-14T15:23:00+00:00",
      "max_elevation_time": "2024-02-14T15:27:30+00:00",
      "los_time": "2024-02-14T15:32:00+00:00",
      "max_elevation_deg": 45.2,
      "duration_seconds": 540
    }
  ],
  "count": 12
}
```

---

### Satellite Registry (requires database)

#### GET /api/v1/satellites

List all tracked satellites with pagination.

```bash
curl "http://localhost:8000/api/v1/satellites?page=1&page_size=20"
```

#### GET /api/v1/satellites/{norad_id}

Get a satellite by NORAD catalog number.

```bash
curl http://localhost:8000/api/v1/satellites/25544
```

#### POST /api/v1/satellites

Add satellites by providing TLE data directly.

```bash
curl -X POST http://localhost:8000/api/v1/satellites \
  -H "Content-Type: application/json" \
  -d '{
    "tles": [{
      "name": "ISS (ZARYA)",
      "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
      "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354"
    }]
  }'
```

#### POST /api/v1/satellites/fetch

Fetch TLEs from Celestrak by NORAD IDs and add to the registry.

**Rate limit:** 5 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/satellites/fetch \
  -H "Content-Type: application/json" \
  -d '{"norad_ids": [25544, 28654]}'
```

#### POST /api/v1/satellites/fetch-group

Fetch all satellites in a Celestrak group.

**Rate limit:** 5 requests/minute

```bash
curl -X POST http://localhost:8000/api/v1/satellites/fetch-group \
  -H "Content-Type: application/json" \
  -d '{"group": "stations"}'
```

#### DELETE /api/v1/satellites/{norad_id}

Remove a satellite from tracking.

```bash
curl -X DELETE http://localhost:8000/api/v1/satellites/25544
```

#### GET /api/v1/satellites/{norad_id}/position

Get the current position of a tracked satellite relative to a ground station.

```bash
curl "http://localhost:8000/api/v1/satellites/25544/position?lat=37.7749&lon=-122.4194&alt=0"
```

---

### Ground Station Registry (requires database)

#### GET /api/v1/ground-stations

List all ground stations.

#### GET /api/v1/ground-stations/{name}

Get a ground station by name.

#### POST /api/v1/ground-stations

Create a new ground station.

```bash
curl -X POST http://localhost:8000/api/v1/ground-stations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "san-francisco",
    "latitude_deg": 37.7749,
    "longitude_deg": -122.4194,
    "elevation_m": 0
  }'
```

#### PUT /api/v1/ground-stations/{name}

Update a ground station's coordinates.

```bash
curl -X PUT http://localhost:8000/api/v1/ground-stations/san-francisco \
  -H "Content-Type: application/json" \
  -d '{"elevation_m": 10.0}'
```

#### DELETE /api/v1/ground-stations/{name}

Delete a ground station.

---

## WebSocket Streaming

The WebSocket endpoint provides real-time Doppler tracking with configurable update intervals.

### Endpoint

```
WS /api/v1/ws/track
```

If authentication is enabled, pass the API key as a query parameter:

```
WS /api/v1/ws/track?api_key=your-key
```

### Connection Flow

1. Connect to the WebSocket endpoint
2. Send a JSON configuration message
3. Receive Doppler updates at the configured interval
4. Optionally send a new configuration to change tracking parameters mid-stream
5. Close the connection when done

### Configuration Message

```json
{
  "tles": [
    {
      "name": "ISS (ZARYA)",
      "line1": "1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993",
      "line2": "2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354"
    }
  ],
  "frequency_hz": 145825000,
  "ground_station": {
    "latitude_deg": 37.7749,
    "longitude_deg": -122.4194,
    "elevation_m": 0
  },
  "interval_seconds": 1.0
}
```

Alternatively, if the database is configured, you can use `satellite_ids` instead of `tles`:

```json
{
  "satellite_ids": [25544],
  "frequency_hz": 145825000,
  "ground_station": { "latitude_deg": 37.7749, "longitude_deg": -122.4194, "elevation_m": 0 },
  "interval_seconds": 1.0
}
```

### Server Messages

**Config accepted:**
```json
{ "type": "config_accepted", "tracking": 1 }
```

**Doppler update (sent every `interval_seconds`):**
```json
{
  "type": "doppler_update",
  "timestamp": "2024-02-14T13:10:00.123456+00:00",
  "results": [
    {
      "satellite_name": "ISS (ZARYA)",
      "doppler_shift_hz": 1234.5,
      "received_frequency_hz": 145826234.5,
      "azimuth_deg": 245.3,
      "elevation_deg": 32.1,
      "range_km": 842.7,
      "range_rate_km_s": -2.54
    }
  ]
}
```

### Example with wscat

```bash
npm install -g wscat
wscat -c ws://localhost:8000/api/v1/ws/track
> {"tles":[{"name":"ISS","line1":"1 25544U 98067A   24045.54896439  .00016717  00000-0  30139-3 0  9993","line2":"2 25544  51.6413 247.4627 0006703  32.7164  94.7900 15.49560843441354"}],"frequency_hz":145825000,"ground_station":{"latitude_deg":37.7749,"longitude_deg":-122.4194,"elevation_m":0},"interval_seconds":2}
```

---

## Configuration

All configuration is via environment variables with the `DOPPLER_` prefix. Copy `.env.example` to `.env` for local development:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DOPPLER_DATABASE_URL` | `""` (disabled) | PostgreSQL connection string. Format: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `DOPPLER_REDIS_URL` | `""` (disabled) | Redis connection string. Format: `redis://host:6379/0` |
| `DOPPLER_API_KEYS` | `""` (auth disabled) | Comma-separated list of valid API keys |
| `DOPPLER_CELESTRAK_BASE_URL` | `https://celestrak.org` | Celestrak API base URL |
| `DOPPLER_TLE_REFRESH_INTERVAL_MINUTES` | `30` | How often the background updater fetches new TLEs |
| `DOPPLER_TLE_STALE_THRESHOLD_HOURS` | `48` | Log warnings when TLEs are older than this |
| `DOPPLER_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DOPPLER_CORS_ORIGINS` | `["*"]` | Allowed CORS origins (JSON array) |
| `DOPPLER_CACHE_TTL_SECONDS` | `0.5` | Redis cache time-to-live for position lookups |
| `DOPPLER_HOST` | `0.0.0.0` | API server bind host |
| `DOPPLER_PORT` | `8000` | API server bind port |

### Graceful Degradation

The system works in reduced-capability mode when services are unavailable:

| Missing Service | Effect |
|----------------|--------|
| No `DOPPLER_DATABASE_URL` | Satellite/ground station registries disabled. Doppler endpoints still work with inline TLEs. |
| No `DOPPLER_REDIS_URL` | No position caching. Every request computes from scratch. |
| No `DOPPLER_API_KEYS` | Authentication disabled (development mode). All endpoints are open. |

---

## Authentication

API key authentication is controlled by the `DOPPLER_API_KEYS` environment variable.

### Enabling Authentication

Set one or more API keys (comma-separated):

```bash
DOPPLER_API_KEYS=key-one,key-two,key-three
```

### Using API Keys

Include the key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: key-one" http://localhost:8000/api/v1/doppler/compute ...
```

For WebSocket connections, pass the key as a query parameter:

```
ws://localhost:8000/api/v1/ws/track?api_key=key-one
```

### Excluded Endpoints

`GET /health` never requires authentication.

### Error Responses

Missing or invalid key returns `401 Unauthorized`:

```json
{ "detail": "Invalid or missing API key" }
```

---

## Rate Limiting

Rate limits are applied per API key (or per client IP if auth is disabled).

| Endpoint | Limit |
|----------|-------|
| `POST /api/v1/doppler/compute` | 100/minute |
| `POST /api/v1/doppler/series` | 10/minute |
| `POST /api/v1/doppler/batch` | 10/minute |
| `POST /api/v1/passes/predict` | 10/minute |
| `POST /api/v1/satellites/fetch` | 5/minute |
| `POST /api/v1/satellites/fetch-group` | 5/minute |

When exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header.

---

## Database & Migrations

### Initial Setup

With PostgreSQL running (via Docker Compose or standalone):

```bash
# Run all migrations
alembic upgrade head

# Check current migration version
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
```

### Database Schema

**satellites** — Tracked satellite TLE data
- `norad_id` (PK), `name`, `tle_line1`, `tle_line2`, `tle_epoch`, `reference_freq_hz`, `created_at`, `updated_at`

**ground_stations** — Named ground station locations
- `id` (PK auto), `name` (unique), `latitude_deg`, `longitude_deg`, `elevation_m`

**doppler_measurements** — Historical measurement records
- `id` (BigInt PK), `time_utc` (indexed), `norad_id` (FK), `ground_station_id` (FK), `azimuth_deg`, `elevation_deg`, `range_km`, `range_rate_km_s`, `doppler_shift_hz`, `frequency_hz`
- Composite index on `(norad_id, time_utc)`

### Background TLE Updater

When the database is configured, a background task automatically refreshes TLEs from Celestrak:
- Runs every `DOPPLER_TLE_REFRESH_INTERVAL_MINUTES` (default: 30)
- Updates only if the fetched TLE has a newer epoch than what's stored
- Logs warnings when any TLE is older than `DOPPLER_TLE_STALE_THRESHOLD_HOURS`

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_doppler.py -v
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ --cov=doppler_core --cov=api -v
```

All 30 tests run without external services (PostgreSQL, Redis). They use mocks and in-memory backends.

### Test Files

| File | Coverage |
|------|----------|
| `tests/test_propagator.py` | SGP4 propagation, position computation, pass prediction |
| `tests/test_doppler.py` | Doppler formula, sign convention, series computation |
| `tests/test_api.py` | All REST API endpoints, error handling |
| `tests/test_auth.py` | API key authentication, health bypass |
| `tests/test_cache.py` | Cache key generation, time bucketing |
| `tests/test_tle_fetcher.py` | Celestrak fetch, TLE epoch parsing, error handling |
| `tests/test_websocket.py` | WebSocket connect, receive, invalid config |

---

## Project Structure

```
Satellite Doppler Shift Tool/
├── doppler_core/              # Framework-free physics library
│   ├── __init__.py
│   ├── doppler.py             # Doppler shift computation
│   ├── exceptions.py          # Custom exception hierarchy
│   ├── models.py              # Pydantic data models (TLE, GroundStation, DopplerResult)
│   └── propagator.py          # SGP4 propagation + coordinate transforms
├── api/                       # FastAPI REST API
│   ├── __init__.py
│   ├── main.py                # App factory, lifespan, exception handlers
│   ├── auth.py                # API key authentication
│   ├── middleware.py           # Request ID tracking middleware
│   ├── rate_limit.py          # Rate limiter configuration
│   └── routes/
│       ├── __init__.py
│       ├── doppler.py         # Doppler computation endpoints
│       ├── satellites.py      # Satellite registry CRUD
│       ├── ground_stations.py # Ground station registry CRUD
│       └── websocket.py       # Real-time WebSocket streaming
├── cli/                       # Click CLI application
│   ├── __init__.py
│   └── main.py                # All CLI commands
├── db/                        # Database layer
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy ORM models
│   ├── session.py             # Async engine + session management
│   └── migrations/            # Alembic migrations
│       ├── env.py
│       ├── script.py.mako
│       └── versions/
│           └── 001_initial.py
├── services/                  # Business logic services
│   ├── __init__.py
│   ├── cache.py               # Redis position cache
│   ├── tle_fetcher.py         # Celestrak TLE fetcher
│   └── tle_updater.py         # Background TLE auto-updater
├── tests/                     # Test suite (30 tests)
│   ├── conftest.py
│   ├── fixtures/
│   │   └── iss.tle
│   ├── test_api.py
│   ├── test_auth.py
│   ├── test_cache.py
│   ├── test_doppler.py
│   ├── test_propagator.py
│   ├── test_tle_fetcher.py
│   └── test_websocket.py
├── config.py                  # pydantic-settings configuration
├── logging_config.py          # Structured JSON logging setup
├── alembic.ini                # Alembic configuration
├── pyproject.toml             # Project metadata + dependencies
├── Dockerfile                 # Multi-stage production build
├── docker-compose.yml         # Full stack (API + Postgres + Redis)
├── .env.example               # Environment variable template
├── .gitignore
└── .github/
    └── workflows/
        └── ci.yml             # GitHub Actions CI pipeline
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| Orbital Propagation | python-sgp4, skyfield |
| Numerical Computing | NumPy |
| Data Validation | Pydantic v2 |
| Web Framework | FastAPI + Uvicorn |
| CLI Framework | Click + Rich |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache | Redis 7 |
| HTTP Client | httpx (async) |
| Authentication | API key (custom) |
| Rate Limiting | slowapi |
| Logging | python-json-logger |
| Containerization | Docker (multi-stage) + Docker Compose |
| CI/CD | GitHub Actions |
| Testing | pytest + pytest-asyncio |

---

## License

MIT
