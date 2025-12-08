"""Add workspace_files table for S3-based storage

Revision ID: add_workspace_files_table
Revises: fix_global_metrics_duplicates
Create Date: 2025-12-07

This table indexes workspace files stored in S3, enabling:
- Fast file listing and search without S3 List operations
- Git status tracking for each file
- Content hash for change detection
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "add_workspace_files_table"
down_revision = "fix_global_metrics_duplicates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create git_status enum type if it doesn't exist
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

    op.create_table(
        "workspace_files",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True, server_default="text/plain"),

        # Git sync status
        sa.Column(
            "git_status",
            postgresql.ENUM('untracked', 'synced', 'modified', 'deleted', name='git_status', create_type=False),
            nullable=False,
            server_default="untracked",
        ),
        sa.Column("last_git_commit_hash", sa.String(40), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),

        # Soft delete
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        # Primary key
        sa.PrimaryKeyConstraint("id"),
    )

    # Unique constraint on path - allows ON CONFLICT upsert
    op.create_unique_constraint(
        "uq_workspace_files_path",
        "workspace_files",
        ["path"],
    )

    # Index for path lookups (non-unique, filtered for active files)
    op.create_index(
        "ix_workspace_files_path",
        "workspace_files",
        ["path"],
        postgresql_where=sa.text("NOT is_deleted"),
    )

    # Index for querying by git status
    op.create_index(
        "ix_workspace_files_git_status",
        "workspace_files",
        ["git_status"],
        postgresql_where=sa.text("NOT is_deleted"),
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_files_git_status", table_name="workspace_files")
    op.drop_index("ix_workspace_files_path", table_name="workspace_files")
    op.drop_constraint("uq_workspace_files_path", table_name="workspace_files")
    op.drop_table("workspace_files")
    op.execute("DROP TYPE git_status")
