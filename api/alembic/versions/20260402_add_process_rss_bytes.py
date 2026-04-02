"""Add process_rss_bytes to executions

Revision ID: 20260402_process_rss_bytes
Revises: 20260331_drop_role_is_active
Create Date: 2026-04-02

Stores current RSS (not peak) of the worker subprocess after each execution,
enabling memory-based process recycling and memory stability monitoring.
"""
import sqlalchemy as sa
from alembic import op

revision = "20260402_process_rss_bytes"
down_revision = "20260331_drop_role_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("process_rss_bytes", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("executions", "process_rss_bytes")
