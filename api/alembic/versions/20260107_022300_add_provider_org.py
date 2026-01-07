"""add_provider_org

Revision ID: b4ad64a97000
Revises: bb2e39289168
Create Date: 2026-01-07 02:23:00.354670+00:00

This migration:
1. Adds is_provider column to organizations table
2. Creates the provider organization (immutable, cannot be deleted)
3. Migrates existing superusers (PLATFORM type) to belong to provider org
4. Makes user.organization_id non-nullable (no more global users)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4ad64a97000'
down_revision: Union[str, None] = 'bb2e39289168'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Provider organization UUID - well-known constant (like SYSTEM_USER_ID)
PROVIDER_ORG_ID = '00000000-0000-0000-0000-000000000002'


def upgrade() -> None:
    # 1. Add is_provider column to organizations
    op.add_column(
        'organizations',
        sa.Column('is_provider', sa.Boolean(), nullable=False, server_default='false')
    )

    # 2. Create the provider organization
    op.execute(f"""
        INSERT INTO organizations (id, name, domain, is_active, is_provider, settings, created_by, created_at, updated_at)
        VALUES (
            '{PROVIDER_ORG_ID}',
            'Provider',
            NULL,
            true,
            true,
            '{{}}'::jsonb,
            'system',
            NOW(),
            NOW()
        )
        ON CONFLICT (id) DO UPDATE SET is_provider = true
    """)

    # 3. Migrate existing PLATFORM users to provider org
    op.execute(f"""
        UPDATE users
        SET organization_id = '{PROVIDER_ORG_ID}'
        WHERE user_type = 'PLATFORM' AND organization_id IS NULL
    """)

    # 4. Assign system user to provider org as well
    op.execute(f"""
        UPDATE users
        SET organization_id = '{PROVIDER_ORG_ID}'
        WHERE user_type = 'SYSTEM' AND organization_id IS NULL
    """)

    # 5. Make organization_id non-nullable
    # First ensure no NULL values remain (catch any edge cases)
    op.execute(f"""
        UPDATE users
        SET organization_id = '{PROVIDER_ORG_ID}'
        WHERE organization_id IS NULL
    """)

    # Now alter the column to be non-nullable
    op.alter_column(
        'users',
        'organization_id',
        existing_type=sa.UUID(),
        nullable=False
    )


def downgrade() -> None:
    # Make organization_id nullable again
    op.alter_column(
        'users',
        'organization_id',
        existing_type=sa.UUID(),
        nullable=True
    )

    # Set PLATFORM and SYSTEM users back to NULL org
    op.execute("""
        UPDATE users
        SET organization_id = NULL
        WHERE user_type IN ('PLATFORM', 'SYSTEM')
    """)

    # Delete provider organization
    op.execute(f"DELETE FROM organizations WHERE id = '{PROVIDER_ORG_ID}'")

    # Drop is_provider column
    op.drop_column('organizations', 'is_provider')
