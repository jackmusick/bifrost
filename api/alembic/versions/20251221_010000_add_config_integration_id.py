"""Add integration_id column to configs table

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2025-12-21

This migration adds:
- integration_id column to configs table for integration-scoped configuration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add integration_id column to configs table
    op.add_column(
        'configs',
        sa.Column('integration_id', UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_configs_integration_id',
        'configs',
        'integrations',
        ['integration_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Add index for efficient queries
    op.create_index('ix_configs_integration_id', 'configs', ['integration_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_configs_integration_id', table_name='configs')

    # Drop foreign key constraint
    op.drop_constraint('fk_configs_integration_id', 'configs', type_='foreignkey')

    # Drop column
    op.drop_column('configs', 'integration_id')
