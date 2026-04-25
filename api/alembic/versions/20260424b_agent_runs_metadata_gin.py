"""add GIN index on agent_runs.metadata

Revision ID: 20260424b_md_gin
Revises: 20260424a_sum_ver
Create Date: 2026-04-24

Speeds up the ``metadata_filter`` query on the agent runs list endpoint.
Equality predicates on ``metadata ->> 'key'`` can use the default JSONB GIN
index for key-containment short-circuits; the ``contains`` (ILIKE) path is
still sequential per-row but per-agent scoping keeps the row count bounded.
"""
from alembic import op


revision = "20260424b_md_gin"
down_revision = "20260424a_sum_ver"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_metadata_gin "
        "ON agent_runs USING GIN (metadata)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_runs_metadata_gin")
