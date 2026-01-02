"""Change document ID from UUID to string for user-defined keys.

Revision ID: 20260102_010000
Revises: 20260102_000000
Create Date: 2026-01-02

This enables DynamoDB-style document IDs where users can provide their own
keys (like email or employee_id) instead of auto-generated UUIDs.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260102_010000"
down_revision = "20260102_000000"  # add_applications
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change document id from UUID to VARCHAR(255)
    # This allows user-defined string IDs (like email, employee_id, etc.)
    # while still supporting auto-generated UUID strings for backward compat
    op.alter_column(
        "documents",
        "id",
        existing_type=sa.UUID(),
        type_=sa.String(255),
        existing_nullable=False,
        postgresql_using="id::text",
    )

    # Add unique constraint on (table_id, id) to ensure IDs are unique within a table
    op.create_index(
        "ix_documents_table_id_id_unique",
        "documents",
        ["table_id", "id"],
        unique=True,
    )


def downgrade() -> None:
    # Remove the unique index
    op.drop_index("ix_documents_table_id_id_unique", table_name="documents")

    # Change back to UUID (will fail if non-UUID strings exist)
    op.alter_column(
        "documents",
        "id",
        existing_type=sa.String(255),
        type_=sa.UUID(),
        existing_nullable=False,
        postgresql_using="id::uuid",
    )
