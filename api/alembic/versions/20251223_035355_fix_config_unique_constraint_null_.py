"""fix_config_unique_constraint_null_handling

Revision ID: 844ed1c74a82
Revises: f544b76ad25e
Create Date: 2025-12-23 03:53:55.936802+00:00

This migration fixes the unique constraint on configs table to properly handle
NULL values. PostgreSQL treats NULL != NULL, so the previous constraint allowed
duplicates when organization_id or integration_id was NULL.

Solution: Use a functional index with COALESCE to treat NULL as a sentinel value.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '844ed1c74a82'
down_revision: Union[str, None] = 'f544b76ad25e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel UUID for NULL replacement in unique constraint
NULL_SENTINEL = '00000000-0000-0000-0000-000000000000'


def upgrade() -> None:
    # First, clean up any existing duplicates by keeping only the most recent
    # This is necessary because the new constraint will reject duplicates
    op.execute("""
        DELETE FROM configs c1
        USING configs c2
        WHERE c1.id < c2.id
          AND COALESCE(c1.integration_id, '00000000-0000-0000-0000-000000000000'::uuid) =
              COALESCE(c2.integration_id, '00000000-0000-0000-0000-000000000000'::uuid)
          AND COALESCE(c1.organization_id, '00000000-0000-0000-0000-000000000000'::uuid) =
              COALESCE(c2.organization_id, '00000000-0000-0000-0000-000000000000'::uuid)
          AND c1.key = c2.key
    """)

    # Drop the old unique index that doesn't handle NULLs properly
    op.drop_index('ix_configs_integration_org_key', table_name='configs')

    # Create new functional unique index using COALESCE
    # This treats NULL as a specific value for uniqueness purposes
    op.execute(f"""
        CREATE UNIQUE INDEX ix_configs_integration_org_key
        ON configs (
            COALESCE(integration_id, '{NULL_SENTINEL}'::uuid),
            COALESCE(organization_id, '{NULL_SENTINEL}'::uuid),
            key
        )
    """)


def downgrade() -> None:
    # Drop the functional index
    op.drop_index('ix_configs_integration_org_key', table_name='configs')

    # Restore the simple column-based index (which has the NULL issue)
    op.create_index(
        'ix_configs_integration_org_key',
        'configs',
        ['integration_id', 'organization_id', 'key'],
        unique=True
    )
