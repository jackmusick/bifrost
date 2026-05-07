"""add rate limit columns to webhook_sources

Revision ID: 20260428_webhook_rate_limit
Revises: 20260428_add_overlap_policy
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_webhook_rate_limit"
down_revision = "20260428_add_overlap_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True, server_default="60"),
    )
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_window_seconds", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "webhook_sources",
        sa.Column("rate_limit_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("webhook_sources", "rate_limit_enabled")
    op.drop_column("webhook_sources", "rate_limit_window_seconds")
    op.drop_column("webhook_sources", "rate_limit_per_minute")
