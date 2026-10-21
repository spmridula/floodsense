"""initial: data_sources, ingestion_runs

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False, server_default=""),
        sa.Column("coverage", sa.String(200), nullable=False),
        sa.Column("license", sa.String(300), nullable=False),
        sa.Column("role", sa.String(300), nullable=False),
        sa.Column("limitations", sa.Text, nullable=False),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("verification", sa.String(32), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_key", sa.String(64), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("record_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("data_sources")
