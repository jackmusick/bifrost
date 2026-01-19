"""Remove file_path columns from forms and agents tables.

These fields are no longer used now that forms/agents are fully virtual.
Their paths are computed from their IDs (e.g., forms/{uuid}.form.json).

Revision ID: 7c0ge41f5e79
Revises: 6b9fd30e4d68
Create Date: 2026-01-19
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7c0ge41f5e79"
down_revision = "6b9fd30e4d68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove file_path columns and their unique indexes."""
    # Drop indexes first
    op.drop_index("ix_forms_file_path_unique", table_name="forms", if_exists=True)
    op.drop_index("ix_agents_file_path_unique", table_name="agents", if_exists=True)

    # Drop columns
    op.drop_column("forms", "file_path")
    op.drop_column("agents", "file_path")


def downgrade() -> None:
    """Re-add file_path columns and their unique indexes."""
    # Re-add columns
    op.add_column("forms", sa.Column("file_path", sa.String(1000), nullable=True))
    op.add_column("agents", sa.Column("file_path", sa.String(1000), nullable=True))

    # Re-create unique indexes (partial indexes on non-null values)
    op.create_index(
        "ix_forms_file_path_unique",
        "forms",
        ["file_path"],
        unique=True,
        postgresql_where=sa.text("file_path IS NOT NULL"),
    )
    op.create_index(
        "ix_agents_file_path_unique",
        "agents",
        ["file_path"],
        unique=True,
        postgresql_where=sa.text("file_path IS NOT NULL"),
    )
