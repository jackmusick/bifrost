"""add agent prompt history

Revision ID: 20260421d_prompt_history
Revises: 20260421c_flag_convs
Create Date: 2026-04-21

Adds the ``agent_prompt_history`` table — append-only audit log of agent
prompt changes. Each row captures the previous and new prompt, who changed
it, when, an optional tuning session reference, and a free-text reason.
Cascade-deletes with the parent agent; ``changed_by`` SET NULL on user
deletion to preserve historical context.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421d_prompt_history"
down_revision = "20260421c_flag_convs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_prompt_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_prompt", sa.Text(), nullable=False),
        sa.Column("new_prompt", sa.Text(), nullable=False),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tuning_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_prompt_history_agent_id_changed_at",
        "agent_prompt_history",
        ["agent_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_history_agent_id_changed_at", table_name="agent_prompt_history"
    )
    op.drop_table("agent_prompt_history")
