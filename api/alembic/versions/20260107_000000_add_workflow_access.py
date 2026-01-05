"""Add workflow_access table for precomputed execution permissions.

Revision ID: 20260107_000000
Revises: 20260106_000000
Create Date: 2026-01-07

This migration:
1. Creates workflow_access table for fast execution authorization lookups
2. Backfills from existing forms (workflow_id, launch_workflow_id, data_provider_id)
3. App backfill requires Python code (run separately after migration)
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260107_000000"
down_revision = "20260106_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow_access table
    op.create_table(
        "workflow_access",
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("access_level", sa.String(20), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("workflow_id", "entity_type", "entity_id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
    )

    # Create index for fast execution lookups
    op.create_index(
        "ix_workflow_access_lookup",
        "workflow_access",
        ["workflow_id", "organization_id"],
    )

    # Create index for entity cleanup
    op.create_index(
        "ix_workflow_access_entity",
        "workflow_access",
        ["entity_type", "entity_id"],
    )

    # Backfill from existing forms - workflow_id
    op.execute("""
        INSERT INTO workflow_access (workflow_id, entity_type, entity_id, access_level, organization_id)
        SELECT DISTINCT
            workflow_id::uuid,
            'form',
            id,
            access_level,
            organization_id
        FROM forms
        WHERE is_active = true
          AND workflow_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # Backfill from existing forms - launch_workflow_id
    op.execute("""
        INSERT INTO workflow_access (workflow_id, entity_type, entity_id, access_level, organization_id)
        SELECT DISTINCT
            launch_workflow_id::uuid,
            'form',
            id,
            access_level,
            organization_id
        FROM forms
        WHERE is_active = true
          AND launch_workflow_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # Backfill from existing forms - data_provider_id in form_fields
    op.execute("""
        INSERT INTO workflow_access (workflow_id, entity_type, entity_id, access_level, organization_id)
        SELECT DISTINCT
            ff.data_provider_id,
            'form',
            f.id,
            f.access_level,
            f.organization_id
        FROM forms f
        JOIN form_fields ff ON ff.form_id = f.id
        WHERE f.is_active = true
          AND ff.data_provider_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # Note: App backfill requires Python code to recursively extract from JSONB props.
    # Run the backfill script after migration: python -m scripts.backfill_workflow_access


def downgrade() -> None:
    op.drop_index("ix_workflow_access_entity", table_name="workflow_access")
    op.drop_index("ix_workflow_access_lookup", table_name="workflow_access")
    op.drop_table("workflow_access")
