"""SQLAlchemy ORM models for database persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SatelliteORM(Base):
    __tablename__ = "satellites"

    norad_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tle_line1: Mapped[str] = mapped_column(String(69), nullable=False)
    tle_line2: Mapped[str] = mapped_column(String(69), nullable=False)
    tle_epoch: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reference_freq_hz: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    measurements: Mapped[list[DopplerMeasurementORM]] = relationship(back_populates="satellite")

    def __repr__(self) -> str:
        return f"<Satellite {self.norad_id} '{self.name}'>"


class GroundStationORM(Base):
    __tablename__ = "ground_stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    latitude_deg: Mapped[float] = mapped_column(Float, nullable=False)
    longitude_deg: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_m: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    measurements: Mapped[list[DopplerMeasurementORM]] = relationship(
        back_populates="ground_station"
    )

    def __repr__(self) -> str:
        return f"<GroundStation '{self.name}'>"


class DopplerMeasurementORM(Base):
    __tablename__ = "doppler_measurements"
    __table_args__ = (Index("ix_doppler_norad_time", "norad_id", "time_utc"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    norad_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("satellites.norad_id", ondelete="CASCADE"), nullable=False
    )
    azimuth_deg: Mapped[float] = mapped_column(Float, nullable=False)
    elevation_deg: Mapped[float] = mapped_column(Float, nullable=False)
    range_km: Mapped[float] = mapped_column(Float, nullable=False)
    range_rate_km_s: Mapped[float] = mapped_column(Float, nullable=False)
    doppler_shift_hz: Mapped[float] = mapped_column(Float, nullable=False)
    frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)
    ground_station_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ground_stations.id", ondelete="SET NULL"), nullable=True
    )

    satellite: Mapped[SatelliteORM] = relationship(back_populates="measurements")
    ground_station: Mapped[GroundStationORM | None] = relationship(back_populates="measurements")

    def __repr__(self) -> str:
        return f"<DopplerMeasurement sat={self.norad_id} t={self.time_utc}>"
