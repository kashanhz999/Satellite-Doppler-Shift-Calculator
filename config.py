"""Application configuration via environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPLER_", env_file=".env", extra="ignore")

    # Database
    database_url: str = ""

    # Redis
    redis_url: str = ""

    # Authentication (empty list = auth disabled)
    api_keys: List[str] = []

    # Celestrak
    celestrak_base_url: str = "https://celestrak.org"

    # TLE management
    tle_refresh_interval_minutes: int = 30
    tle_stale_threshold_hours: int = 48

    # Logging
    log_level: str = "INFO"

    # CORS
    cors_origins: List[str] = ["*"]

    # Cache
    cache_ttl_seconds: float = 0.5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def has_database(self) -> bool:
        return bool(self.database_url)

    @property
    def has_redis(self) -> bool:
        return bool(self.redis_url)

    @property
    def auth_enabled(self) -> bool:
        return len(self.api_keys) > 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
