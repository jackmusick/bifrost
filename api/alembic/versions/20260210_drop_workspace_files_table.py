"""Drop workspace_files table and workflows.portable_ref column.

The workspace_files table has been replaced by file_index and repo storage.
The portable_ref column is no longer needed with the new workspace architecture.

Revision ID: 20260210_drop_workspace
Revises: 20260210_drop_code
Create Date: 2026-02-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects import postgresql

revision = "20260210_drop_workspace"
down_revision = "20260210_drop_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop workspace_files table and workflows.portable_ref column."""
    # Drop the workspace_files table (includes all indexes and constraints)
    op.drop_table("workspace_files")

    # Drop workflows.portable_ref if it exists (it's a generated column)
    # Use raw SQL to handle the IF EXISTS clause
    op.execute("""
        ALTER TABLE workflows
        DROP COLUMN IF EXISTS portable_ref;
    """)

    # Drop the index if it exists
    op.execute("""
        DROP INDEX IF EXISTS ix_workflows_portable_ref;
    """)


def downgrade() -> None:
    """Recreate workspace_files table and workflows.portable_ref column (best effort)."""
    # Recreate git_status enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE git_status AS ENUM (
                'untracked',
                'synced',
                'modified',
                'deleted'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$
    """)

    # Recreate workspace_files table with minimal schema
    op.create_table(
        "workspace_files",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("github_sha", sa.String(40), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column(
            "git_status",
            postgresql.ENUM('untracked', 'synced', 'modified', 'deleted', name='git_status', create_type=False),
            nullable=False,
            server_default="untracked",
        ),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Recreate indexes
    op.create_unique_constraint(
        "uq_workspace_files_path",
        "workspace_files",
        ["path"],
    )

    op.create_index(
        "ix_workspace_files_path",
        "workspace_files",
        ["path"],
        postgresql_where=sa.text("NOT is_deleted"),
    )

    op.create_index(
        "ix_workspace_files_git_status",
        "workspace_files",
        ["git_status"],
        postgresql_where=sa.text("NOT is_deleted"),
    )

    # Recreate workflows.portable_ref as a generated column
    op.execute("""
        ALTER TABLE workflows
        ADD COLUMN portable_ref VARCHAR(512)
        GENERATED ALWAYS AS (path || '::' || function_name) STORED;
    """)

    # Recreate index on portable_ref
    op.create_index(
        "ix_workflows_portable_ref",
        "workflows",
        ["portable_ref"],
        unique=True,
    )
