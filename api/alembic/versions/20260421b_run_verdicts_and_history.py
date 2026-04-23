"""add verdict columns + audit history

Revision ID: 20260421b_verdicts
Revises: 20260421a_run_summaries
Create Date: 2026-04-21

Adds reviewer-verdict tracking on AgentRun and an immutable change log:

- ``verdict`` — nullable up/down thumbs ('up', 'down', or NULL = unreviewed).
  Constrained at the DB level so writers cannot drift.
- ``verdict_note`` — optional reviewer comment captured at vote time.
- ``verdict_set_at`` / ``verdict_set_by`` — when and by whom (FK to users,
  ON DELETE SET NULL so deleting a reviewer keeps the verdict but unsets
  authorship).
- Composite index on ``(agent_id, verdict, status)`` for the agent dashboard
  filter "show me the down-voted completed runs for agent X".
- ``agent_run_verdict_history`` — append-only audit trail, one row per
  verdict change. Cascade-deletes with the parent run.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260421b_verdicts"
down_revision = "20260421a_run_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("verdict", sa.String(length=10), nullable=True))
    op.add_column("agent_runs", sa.Column("verdict_note", sa.Text(), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("verdict_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "verdict_set_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_agent_runs_verdict_values",
        "agent_runs",
        "verdict IS NULL OR verdict IN ('up', 'down')",
    )
    op.create_index(
        "ix_agent_runs_agent_verdict_status",
        "agent_runs",
        ["agent_id", "verdict", "status"],
    )

    op.create_table(
        "agent_run_verdict_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_verdict", sa.String(length=10), nullable=True),
        sa.Column("new_verdict", sa.String(length=10), nullable=True),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_verdict_history_run_id", "agent_run_verdict_history", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_verdict_history_run_id", table_name="agent_run_verdict_history")
    op.drop_table("agent_run_verdict_history")
    op.drop_index("ix_agent_runs_agent_verdict_status", table_name="agent_runs")
    op.drop_constraint("ck_agent_runs_verdict_values", "agent_runs", type_="check")
    op.drop_column("agent_runs", "verdict_set_by")
    op.drop_column("agent_runs", "verdict_set_at")
    op.drop_column("agent_runs", "verdict_note")
    op.drop_column("agent_runs", "verdict")
