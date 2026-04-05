"""Create worker_metrics table for diagnostics time-series

Revision ID: 20260405_worker_metrics
Revises: 20260402_process_rss_bytes
Create Date: 2026-04-05

Stores periodic resource snapshots from worker heartbeats.
Used by the Process Pools diagnostics dashboard for the aggregate memory chart.
"""
import sqlalchemy as sa
from alembic import op

revision = "20260405_worker_metrics"
down_revision = "20260402_process_rss_bytes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("worker_id", sa.String(255), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("memory_current", sa.BigInteger(), nullable=False),
        sa.Column("memory_max", sa.BigInteger(), nullable=False),
        sa.Column("fork_count", sa.Integer(), nullable=False),
        sa.Column("busy_count", sa.Integer(), nullable=False),
        sa.Column("idle_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_metrics_timestamp", "worker_metrics", ["timestamp"])
    op.create_index(
        "ix_worker_metrics_worker_timestamp",
        "worker_metrics",
        ["worker_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_metrics_worker_timestamp", table_name="worker_metrics")
    op.drop_index("ix_worker_metrics_timestamp", table_name="worker_metrics")
    op.drop_table("worker_metrics")
