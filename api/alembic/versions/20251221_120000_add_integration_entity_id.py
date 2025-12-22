"""Add entity_id and entity_id_name to integrations table

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2025-12-21

This migration adds:
- entity_id: Global entity ID for token URL templating (optional)
- entity_id_name: Display name for the global entity ID (optional)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entity_id column to integrations table
    op.add_column(
        'integrations',
        sa.Column('entity_id', sa.String(255), nullable=True)
    )

    # Add entity_id_name column to integrations table
    op.add_column(
        'integrations',
        sa.Column('entity_id_name', sa.String(255), nullable=True)
    )


def downgrade() -> None:
    # Remove entity_id_name column
    op.drop_column('integrations', 'entity_id_name')

    # Remove entity_id column
    op.drop_column('integrations', 'entity_id')
