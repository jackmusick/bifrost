"""add agent_runs.answered column

Revision ID: 20260424c_answered
Revises: 20260424b_md_gin
Create Date: 2026-04-24

The summarizer prompt v3 produces three text fields — asked / did /
answered — where `did` is the work the agent did and `answered` is the
user-facing outcome. v1/v2 produced only asked + did; existing rows leave
`answered` NULL until they're re-summarized via the backfill endpoint with
``prompt_version_below="v3"``.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260424c_answered"
down_revision = "20260424b_md_gin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("answered", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "answered")
