"""Change form_fields.data_provider from String to UUID FK

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2025-12-22

This migration changes form_fields.data_provider from a string name
to a UUID foreign key referencing data_providers.id.

No data migration needed - this is a new feature with no existing data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old string column
    op.drop_column('form_fields', 'data_provider')

    # Add new UUID FK column
    op.add_column(
        'form_fields',
        sa.Column('data_provider_id', UUID(as_uuid=True), nullable=True)
    )

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_form_fields_data_provider_id',
        'form_fields',
        'data_providers',
        ['data_provider_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Drop FK constraint
    op.drop_constraint('fk_form_fields_data_provider_id', 'form_fields', type_='foreignkey')

    # Drop UUID column
    op.drop_column('form_fields', 'data_provider_id')

    # Restore old string column
    op.add_column(
        'form_fields',
        sa.Column('data_provider', sa.String(100), nullable=True)
    )
