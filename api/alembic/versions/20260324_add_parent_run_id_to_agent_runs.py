"""add parent_run_id to agent_runs for delegation tracking

Revision ID: 20260324_agent_run_parent
Revises: 20260317_integration_fk_ondelete
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260324_agent_run_parent"
down_revision = "20260317_integration_fk_ondelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("parent_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_parent_run_id",
        "agent_runs",
        "agent_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_agent_runs_parent_run_id", "agent_runs", ["parent_run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_parent_run_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_parent_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "parent_run_id")
