"""Add content column to workspace_files for module storage

Revision ID: 20260108_000000
Revises: 04d2e6fc1522
Create Date: 2026-01-08

This migration adds support for storing Python module source code directly
in the workspace_files table. This enables:
- Fast module lookups for virtual import hooks
- No S3 dependency for Python module content
- Simplified caching strategy (content in DB + Redis cache)

Modules are Python files without @workflow or @data_provider decorators.
They're stored in workspace_files.content instead of S3.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "20260108_000000"
down_revision: Union[str, None] = "04d2e6fc1522"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content column for storing Python module source code
    # TEXT type supports up to 1GB - more than enough for any module
    op.add_column(
        "workspace_files",
        sa.Column("content", sa.Text(), nullable=True),
    )

    # Partial index for efficient module lookups by path
    # Only indexes rows where entity_type='module' AND NOT is_deleted
    # This optimizes the virtual import hook's query pattern:
    #   SELECT content FROM workspace_files
    #   WHERE path = ? AND entity_type = 'module' AND NOT is_deleted
    op.create_index(
        "ix_workspace_files_modules",
        "workspace_files",
        ["path"],
        postgresql_where=text("entity_type = 'module' AND NOT is_deleted"),
    )


def downgrade() -> None:
    # Drop index first (depends on column)
    op.drop_index("ix_workspace_files_modules", table_name="workspace_files")

    # Drop content column
    op.drop_column("workspace_files", "content")
