"""Make IntegrationMapping.organization_id nullable for global mappings.

Revision ID: 20260115_int_mapping_nullable
Revises: 20260113_drop_app_global_fields
Create Date: 2026-01-15

Allows integration_mappings.organization_id to be NULL for global/default
mappings that apply when no org-specific mapping exists (cascade fallback
pattern).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260115_int_mapping_nullable"
down_revision = "20260113_drop_app_global_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make organization_id nullable on integration_mappings table
    op.alter_column(
        "integration_mappings",
        "organization_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # Add partial unique index to enforce only ONE global mapping per integration
    # The existing unique index on (integration_id, organization_id) allows multiple
    # NULL organization_id rows because NULL != NULL in SQL. This partial index
    # ensures only one global mapping can exist per integration.
    op.create_index(
        "ix_integration_mappings_unique_global",
        "integration_mappings",
        ["integration_id"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )


def downgrade() -> None:
    # Drop the partial unique index for global mappings
    op.drop_index(
        "ix_integration_mappings_unique_global",
        table_name="integration_mappings",
    )

    # Make organization_id required again
    # Note: This will fail if there are any rows with NULL organization_id
    op.alter_column(
        "integration_mappings",
        "organization_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
