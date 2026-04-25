"""add tsvector full-text search column on agent_runs

Revision ID: 20260421e_tsv_search
Revises: 20260421d_prompt_history
Create Date: 2026-04-21

Adds a generated ``search_tsv`` ``tsvector`` column on ``agent_runs`` that
indexes the searchable surface of a run (asked / did / error / caller info /
metadata json). Backed by a GIN index for fast full-text queries from the
runs page filter bar.
"""
from alembic import op


revision = "20260421e_tsv_search"
down_revision = "20260421d_prompt_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_runs ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(asked, '') || ' ' ||
                coalesce(did, '') || ' ' ||
                coalesce(error, '') || ' ' ||
                coalesce(caller_email, '') || ' ' ||
                coalesce(caller_name, '') || ' ' ||
                coalesce(metadata::text, '')
            )
        ) STORED
    """)
    op.create_index(
        "ix_agent_runs_search_tsv_gin",
        "agent_runs",
        ["search_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_search_tsv_gin", table_name="agent_runs")
    op.execute("ALTER TABLE agent_runs DROP COLUMN search_tsv")
