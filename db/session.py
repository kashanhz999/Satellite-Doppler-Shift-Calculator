"""Async database engine and session management."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings

_engine = None
_session_factory = None


async def init_db() -> None:
    """Initialize the async database engine and session factory."""
    global _engine, _session_factory
    settings = get_settings()

    if not settings.has_database:
        return

    _engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        echo=settings.log_level == "DEBUG",
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def close_db() -> None:
    """Close the database engine."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Set DOPPLER_DATABASE_URL.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory():
    """Return the session factory for use by background tasks."""
    return _session_factory
