"""Add tables and documents for app builder data storage.

Revision ID: 20260101_000000
Revises: 20251230_035016
Create Date: 2026-01-01

Tables are a flexible document store similar to Dataverse.
- Global tables: organization_id = NULL
- Org-scoped tables: organization_id = UUID
- App-scoped tables: application_id = UUID (optional)

Documents are JSONB rows within tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260101_000000"
down_revision = "dc862360f7cb"  # 20251230_035016_remove_event_delivery_execution_fk
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tables table (metadata for document collections)
    op.create_table(
        "tables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("application_id", sa.UUID(), nullable=True),
        sa.Column("schema", postgresql.JSONB(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        # application_id FK will be added when applications table exists
        sa.PrimaryKeyConstraint("id"),
    )

    # Index for querying tables by org
    op.create_index("ix_tables_organization_id", "tables", ["organization_id"])

    # Unique constraint: table name unique within org (or globally if org is NULL)
    op.create_index(
        "ix_tables_org_name_unique",
        "tables",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tables_global_name_unique",
        "tables",
        ["name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )

    # Create documents table (rows within tables)
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("table_id", sa.UUID(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["table_id"], ["tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Index for querying documents by table
    op.create_index("ix_documents_table_id", "documents", ["table_id"])

    # GIN index for JSONB queries on document data
    op.create_index(
        "ix_documents_data_gin",
        "documents",
        ["data"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_documents_data_gin", table_name="documents")
    op.drop_index("ix_documents_table_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_tables_global_name_unique", table_name="tables")
    op.drop_index("ix_tables_org_name_unique", table_name="tables")
    op.drop_index("ix_tables_organization_id", table_name="tables")
    op.drop_table("tables")
