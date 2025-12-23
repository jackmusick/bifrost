"""Add unique constraint for integration config

Revision ID: f544b76ad25e
Revises: h8i9j0k1l2m3
Create Date: 2025-12-23 02:02:55.696316+00:00

This migration:
- Drops the old (organization_id, key) unique constraint
- Adds new (integration_id, organization_id, key) unique constraint for proper upserts
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f544b76ad25e'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old unique constraint (organization_id, key)
    op.drop_index('ix_configs_org_key', table_name='configs')

    # Create new unique constraint including integration_id
    # This allows same key for different integrations, and supports upserts
    op.create_index(
        'ix_configs_integration_org_key',
        'configs',
        ['integration_id', 'organization_id', 'key'],
        unique=True
    )


def downgrade() -> None:
    # Drop new constraint
    op.drop_index('ix_configs_integration_org_key', table_name='configs')

    # Restore old constraint
    op.create_index('ix_configs_org_key', 'configs', ['organization_id', 'key'], unique=True)
