"""add summary_backfill_jobs table

Revision ID: 20260423a_bf_jobs
Revises: 20260421e_tsv_search
Create Date: 2026-04-23

Orchestration row for bulk agent-run summary backfills triggered by admins.
Each row tracks total / succeeded / failed counts and the estimated vs.
actual cost in USD so the UI can show progress + let us post-hoc analyse
how accurate the cost estimate was.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260423a_bf_jobs"
down_revision = "20260421e_tsv_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "summary_backfill_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(10, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "actual_cost_usd",
            sa.Numeric(10, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_summary_backfill_jobs_agent_id",
        "summary_backfill_jobs",
        ["agent_id"],
    )
    op.create_index(
        "ix_summary_backfill_jobs_status",
        "summary_backfill_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_summary_backfill_jobs_status", table_name="summary_backfill_jobs"
    )
    op.drop_index(
        "ix_summary_backfill_jobs_agent_id", table_name="summary_backfill_jobs"
    )
    op.drop_table("summary_backfill_jobs")
