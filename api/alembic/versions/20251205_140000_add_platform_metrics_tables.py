"""Add platform metrics tables

Revision ID: add_platform_metrics
Revises: add_execution_metrics
Create Date: 2025-12-05

Creates two tables for efficient dashboard metrics:

1. execution_metrics_daily - Daily aggregates per organization
   - Populated by consumer on execution completion
   - Used for trend charts, org usage reports, billing

2. platform_metrics_snapshot - Current state snapshot
   - Refreshed by scheduler every 1-5 minutes
   - Used for instant dashboard loads
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_platform_metrics"
down_revision = "add_execution_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create execution_metrics_daily table
    op.create_table(
        "execution_metrics_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        # Execution counts
        sa.Column("execution_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("timeout_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancelled_count", sa.Integer(), server_default="0", nullable=False),
        # Duration metrics
        sa.Column("total_duration_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("avg_duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_duration_ms", sa.Integer(), server_default="0", nullable=False),
        # Resource metrics
        sa.Column("total_memory_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("peak_memory_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cpu_seconds", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("peak_cpu_seconds", sa.Float(), server_default="0.0", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("date", "organization_id", name="uq_metrics_daily_date_org"),
    )
    op.create_index("ix_metrics_daily_date", "execution_metrics_daily", ["date"])
    op.create_index("ix_metrics_daily_org", "execution_metrics_daily", ["organization_id"])

    # Create platform_metrics_snapshot table
    op.create_table(
        "platform_metrics_snapshot",
        sa.Column("id", sa.Integer(), nullable=False, default=1),
        # Entity counts
        sa.Column("workflow_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("form_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("data_provider_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("organization_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("user_count", sa.Integer(), server_default="0", nullable=False),
        # Execution stats (all time)
        sa.Column("total_executions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_success", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_failed", sa.Integer(), server_default="0", nullable=False),
        # Execution stats (last 24 hours)
        sa.Column("executions_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("success_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_24h", sa.Integer(), server_default="0", nullable=False),
        # Current state
        sa.Column("running_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pending_count", sa.Integer(), server_default="0", nullable=False),
        # Performance (last 24 hours)
        sa.Column("avg_duration_ms_24h", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_memory_bytes_24h", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("total_cpu_seconds_24h", sa.Float(), server_default="0.0", nullable=False),
        # Success rates
        sa.Column("success_rate_all_time", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("success_rate_24h", sa.Float(), server_default="0.0", nullable=False),
        # Timestamp
        sa.Column("refreshed_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
    )

    # Insert initial snapshot row
    op.execute(
        "INSERT INTO platform_metrics_snapshot (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("platform_metrics_snapshot")
    op.drop_index("ix_metrics_daily_org", table_name="execution_metrics_daily")
    op.drop_index("ix_metrics_daily_date", table_name="execution_metrics_daily")
    op.drop_table("execution_metrics_daily")
