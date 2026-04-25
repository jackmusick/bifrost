"""add summary_prompt_version to agent_runs

Revision ID: 20260424a_sum_ver
Revises: 20260423b_exec_sched
Create Date: 2026-04-24

Adds ``summary_prompt_version`` so we can distinguish runs summarized under
different iterations of ``SUMMARIZE_SYSTEM_PROMPT``. Existing completed
summaries are backfilled to ``'v1'`` (the shipped prompt at the time of this
migration). Pending / failed / unsummarized rows stay NULL and get tagged on
the next successful summarization.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260424a_sum_ver"
down_revision = "20260423b_sched_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("summary_prompt_version", sa.String(length=20), nullable=True),
    )
    op.execute(
        "UPDATE agent_runs "
        "SET summary_prompt_version = 'v1' "
        "WHERE summary_status = 'completed' AND summary_prompt_version IS NULL"
    )
    op.create_index(
        "ix_agent_runs_summary_prompt_version",
        "agent_runs",
        ["summary_prompt_version"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_runs_summary_prompt_version", table_name="agent_runs"
    )
    op.drop_column("agent_runs", "summary_prompt_version")
