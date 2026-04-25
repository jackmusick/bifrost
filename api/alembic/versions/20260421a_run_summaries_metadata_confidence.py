"""add run summaries, metadata, confidence fields

Revision ID: 20260421a_run_summaries
Revises: 20260419_apps_repo_path
Create Date: 2026-04-21

Adds AgentRun summary/observability columns:

- ``asked`` / ``did`` — short natural-language summary of the user's request
  and what the agent did.
- ``metadata`` — JSONB bag for free-form per-run keys (ticket id, customer,
  channel-specific identifiers). Indexed with a GIN ``jsonb_path_ops``
  index so containment queries (``metadata @> '{...}'``) stay fast even
  on large run tables.
- ``confidence`` / ``confidence_reason`` — the summarizer's self-reported
  confidence in its summary (0..1, but DB does not enforce — clamping is
  the writer's responsibility so we don't reject historical data).
- ``summary_generated_at`` — when the summary fields above were last
  populated (null until the summarizer has run).
- ``summary_status`` — lifecycle of the summary background job:
  pending → generating → completed | failed | skipped. Constrained at
  the DB level so writers cannot drift.
- ``summary_error`` — human-readable failure reason when ``summary_status``
  is ``failed``.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421a_run_summaries"
down_revision = "20260419_apps_repo_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("asked", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("did", sa.Text(), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("agent_runs", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("agent_runs", sa.Column("confidence_reason", sa.Text(), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column(
            "summary_generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "summary_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column("agent_runs", sa.Column("summary_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_agent_runs_summary_status_values",
        "agent_runs",
        "summary_status IN ('pending', 'generating', 'completed', 'failed', 'skipped')",
    )
    op.create_index(
        "ix_agent_runs_metadata_gin",
        "agent_runs",
        ["metadata"],
        postgresql_using="gin",
        postgresql_ops={"metadata": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_metadata_gin", table_name="agent_runs")
    op.drop_constraint(
        "ck_agent_runs_summary_status_values", "agent_runs", type_="check"
    )
    op.drop_column("agent_runs", "summary_error")
    op.drop_column("agent_runs", "summary_status")
    op.drop_column("agent_runs", "summary_generated_at")
    op.drop_column("agent_runs", "confidence_reason")
    op.drop_column("agent_runs", "confidence")
    op.drop_column("agent_runs", "metadata")
    op.drop_column("agent_runs", "did")
    op.drop_column("agent_runs", "asked")
