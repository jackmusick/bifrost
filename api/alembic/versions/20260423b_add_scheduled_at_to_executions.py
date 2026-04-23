"""add_scheduled_at_to_executions

Revision ID: 20260423b_sched_at
Revises: 20260423a_bf_jobs
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa


revision = "20260423b_sched_at"
down_revision = "20260423a_bf_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres forbids using a newly-added enum value in the same transaction
    # that added it. Commit the ADD VALUE via an autocommit block so the
    # subsequent partial-index CREATE (which references 'Scheduled') can see
    # the value.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE execution_status ADD VALUE IF NOT EXISTS 'Scheduled'")

    op.add_column(
        "executions",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        "CREATE INDEX ix_executions_scheduled_due "
        "ON executions (scheduled_at) "
        "WHERE status = 'Scheduled'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_executions_scheduled_due")
    op.drop_column("executions", "scheduled_at")
    # Postgres does not support removing a value from an enum; the
    # 'Scheduled' value remains on downgrade. Document this and move on.
