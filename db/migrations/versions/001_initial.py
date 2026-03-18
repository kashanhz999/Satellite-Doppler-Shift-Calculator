"""Initial schema: satellites, ground_stations, doppler_measurements

Revision ID: 001
Revises:
Create Date: 2026-03-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "satellites",
        sa.Column("norad_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tle_line1", sa.String(69), nullable=False),
        sa.Column("tle_line2", sa.String(69), nullable=False),
        sa.Column("tle_epoch", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_freq_hz", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ground_stations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("latitude_deg", sa.Float(), nullable=False),
        sa.Column("longitude_deg", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "doppler_measurements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("time_utc", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column(
            "norad_id",
            sa.Integer(),
            sa.ForeignKey("satellites.norad_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("azimuth_deg", sa.Float(), nullable=False),
        sa.Column("elevation_deg", sa.Float(), nullable=False),
        sa.Column("range_km", sa.Float(), nullable=False),
        sa.Column("range_rate_km_s", sa.Float(), nullable=False),
        sa.Column("doppler_shift_hz", sa.Float(), nullable=False),
        sa.Column("frequency_hz", sa.Float(), nullable=False),
        sa.Column(
            "ground_station_id",
            sa.Integer(),
            sa.ForeignKey("ground_stations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_index("ix_doppler_norad_time", "doppler_measurements", ["norad_id", "time_utc"])


def downgrade() -> None:
    op.drop_index("ix_doppler_norad_time", table_name="doppler_measurements")
    op.drop_table("doppler_measurements")
    op.drop_table("ground_stations")
    op.drop_table("satellites")
