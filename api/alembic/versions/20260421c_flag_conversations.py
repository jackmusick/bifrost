"""add per-flag tuning conversations

Revision ID: 20260421c_flag_convs
Revises: 20260421b_verdicts
Create Date: 2026-04-21

Adds the ``agent_run_flag_conversations`` table — one tuning conversation per
flagged ``AgentRun`` (1:1, enforced by a unique index on ``run_id``). The
conversation transcript lives in a JSONB ``messages`` column as an ordered
list of polymorphic turn objects (user / assistant / proposal / dryrun).
Cascade-deletes with the parent run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421c_flag_convs"
down_revision = "20260421b_verdicts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_run_flag_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_flag_conversations_run_id",
        "agent_run_flag_conversations",
        ["run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_flag_conversations_run_id", table_name="agent_run_flag_conversations"
    )
    op.drop_table("agent_run_flag_conversations")
