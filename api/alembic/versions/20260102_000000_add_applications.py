"""Add applications table for App Builder.

Revision ID: 20260102_000000
Revises: 20260101_000000
Create Date: 2026-01-02

Applications are app definitions with draft/live versioning.
- organization_id = NULL: Global application (platform-wide)
- organization_id = UUID: Organization-scoped application
- Supports draft/live versioning with version history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260102_000000"
down_revision = "20260101_000000"  # add_tables_and_documents
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create applications table
    op.create_table(
        "applications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        # Versioning
        sa.Column("live_definition", postgresql.JSONB(), nullable=True),
        sa.Column("draft_definition", postgresql.JSONB(), nullable=True),
        sa.Column("live_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("draft_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("version_history", postgresql.JSONB(), server_default="[]", nullable=False),
        # Metadata
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        # Constraints
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Index for querying applications by org
    op.create_index("ix_applications_organization_id", "applications", ["organization_id"])

    # Unique constraint: slug unique within org (or globally if org is NULL)
    op.create_index(
        "ix_applications_org_slug_unique",
        "applications",
        ["organization_id", "slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "ix_applications_global_slug_unique",
        "applications",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )

    # Add foreign key from tables.application_id to applications.id
    op.create_foreign_key(
        "fk_tables_application_id",
        "tables",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Index for querying tables by application
    op.create_index("ix_tables_application_id", "tables", ["application_id"])


def downgrade() -> None:
    # Remove FK and index from tables
    op.drop_index("ix_tables_application_id", table_name="tables")
    op.drop_constraint("fk_tables_application_id", "tables", type_="foreignkey")

    # Remove applications table
    op.drop_index("ix_applications_global_slug_unique", table_name="applications")
    op.drop_index("ix_applications_org_slug_unique", table_name="applications")
    op.drop_index("ix_applications_organization_id", table_name="applications")
    op.drop_table("applications")
