"""weather_observations

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("point_id", sa.String(32), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("precipitation_mm", sa.Float, nullable=True),
        sa.Column("is_forecast", sa.Integer, nullable=False, server_default="0"),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("ingestion_runs.id"), nullable=True),
        sa.UniqueConstraint("source", "point_id", "valid_time", name="uq_weather_point_time"),
    )
    op.create_index("ix_weather_observations_point_id", "weather_observations", ["point_id"])
    op.create_index("ix_weather_observations_valid_time", "weather_observations", ["valid_time"])


def downgrade() -> None:
    op.drop_table("weather_observations")
