"""Drop is_system column from agents table

Revision ID: 20260326_drop_agent_is_system
Revises: 20260324_agent_run_timeout
Create Date: 2026-03-26

System agents are no longer auto-created; the is_system flag is unused.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260326_drop_agent_is_system"
down_revision = "20260324_agent_run_timeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agents", "is_system")


def downgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
    )
