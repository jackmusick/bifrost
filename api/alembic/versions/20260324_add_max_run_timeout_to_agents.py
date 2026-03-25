"""add max_run_timeout to agents for configurable run timeouts

Revision ID: 20260324_agent_run_timeout
Revises: 20260324_agent_run_parent
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260324_agent_run_timeout"
down_revision = "20260324_agent_run_parent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("max_run_timeout", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "max_run_timeout")
