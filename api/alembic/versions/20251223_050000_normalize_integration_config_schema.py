"""normalize_integration_config_schema

Revision ID: 5bcfc05cfeda
Revises: 844ed1c74a82
Create Date: 2025-12-23 05:00:00.000000+00:00

Normalizes integration config_schema from JSONB column to a proper table.

Benefits:
- Referential integrity with cascade delete
- Deleting a schema key automatically deletes related configs
- Proper unique constraints on (integration_id, key)
- Cleaner updates (add/update/remove schema items)

Changes:
1. Create integration_config_schema table
2. Add config_schema_id FK to configs table
3. Drop config_schema JSONB column from integrations

Note: This migration does NOT migrate existing data. All integrations
will need their config_schema re-created after this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5bcfc05cfeda'
down_revision: Union[str, None] = '844ed1c74a82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sentinel UUID for NULL replacement in unique constraint
NULL_SENTINEL = '00000000-0000-0000-0000-000000000000'


def upgrade() -> None:
    # 1. Create the new integration_config_schema table
    op.create_table(
        'integration_config_schema',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('integration_id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('options', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['integration_id'],
            ['integrations.id'],
            ondelete='CASCADE'
        ),
    )

    # Create indexes for integration_config_schema
    op.create_index(
        'ix_integration_config_schema_integration_id',
        'integration_config_schema',
        ['integration_id']
    )
    op.create_index(
        'ix_integration_config_schema_unique_key',
        'integration_config_schema',
        ['integration_id', 'key'],
        unique=True
    )

    # 2. Add config_schema_id to configs table with FK
    op.add_column(
        'configs',
        sa.Column('config_schema_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_configs_config_schema_id',
        'configs',
        'integration_config_schema',
        ['config_schema_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index(
        'ix_configs_schema_id',
        'configs',
        ['config_schema_id']
    )

    # 3. Drop the old config_schema JSONB column from integrations
    # First, clear any existing integration configs since we're not migrating data
    op.execute("DELETE FROM configs WHERE integration_id IS NOT NULL")

    # Now drop the column
    op.drop_column('integrations', 'config_schema')


def downgrade() -> None:
    # 1. Add back the JSONB column
    op.add_column(
        'integrations',
        sa.Column('config_schema', postgresql.JSONB(), nullable=True)
    )

    # 2. Remove config_schema_id from configs
    op.drop_index('ix_configs_schema_id', table_name='configs')
    op.drop_constraint('fk_configs_config_schema_id', 'configs', type_='foreignkey')
    op.drop_column('configs', 'config_schema_id')

    # 3. Drop the integration_config_schema table
    op.drop_index('ix_integration_config_schema_unique_key', table_name='integration_config_schema')
    op.drop_index('ix_integration_config_schema_integration_id', table_name='integration_config_schema')
    op.drop_table('integration_config_schema')
