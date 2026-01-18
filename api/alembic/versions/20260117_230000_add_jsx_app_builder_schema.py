"""add_jsx_app_builder_schema

Add engine column to applications table and create app_jsx_files table
for the new JSX-based App Builder engine.

Revision ID: 3a8c291f0062
Revises: 2c9b170e7951
Create Date: 2026-01-17 23:00:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a8c291f0062"
down_revision: Union[str, None] = "2c9b170e7951"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add engine column to applications table
    # Values: 'components' = current JSON component tree (v1), 'jsx' = new JSX engine (v2)
    op.add_column(
        "applications",
        sa.Column(
            "engine",
            sa.String(20),
            nullable=False,
            server_default="components",
        ),
    )

    # Create app_jsx_files table for JSX engine apps
    op.create_table(
        "app_jsx_files",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "app_version_id",
            sa.UUID(),
            sa.ForeignKey("app_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Identity (path is the key)
        sa.Column("path", sa.String(500), nullable=False),
        # Content
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("compiled", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    )

    # Create indexes
    op.create_index("ix_jsx_files_version", "app_jsx_files", ["app_version_id"])
    op.create_index(
        "ix_jsx_files_path",
        "app_jsx_files",
        ["app_version_id", "path"],
        unique=True,
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_jsx_files_path", table_name="app_jsx_files")
    op.drop_index("ix_jsx_files_version", table_name="app_jsx_files")

    # Drop table
    op.drop_table("app_jsx_files")

    # Drop engine column
    op.drop_column("applications", "engine")
