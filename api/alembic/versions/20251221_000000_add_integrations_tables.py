"""Add integrations and integration_mappings tables

Revision ID: b2c3d4e5f6g7
Revises: 60f0741b55d9
Create Date: 2025-12-21

This migration creates:
- integrations table: Platform-level integration definitions
- integration_mappings table: Organization-specific integration mappings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = '60f0741b55d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create integrations table
    op.create_table(
        'integrations',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('oauth_provider_id', UUID(as_uuid=True), nullable=True),
        sa.Column('list_entities_data_provider_id', UUID(as_uuid=True), nullable=True),
        sa.Column('config_schema', JSONB(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['oauth_provider_id'], ['oauth_providers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes on integrations table
    op.create_index('ix_integrations_name', 'integrations', ['name'])
    op.create_index('ix_integrations_oauth_provider_id', 'integrations', ['oauth_provider_id'])
    op.create_index('ix_integrations_is_deleted', 'integrations', ['is_deleted'])

    # Create integration_mappings table
    op.create_table(
        'integration_mappings',
        sa.Column('id', UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('integration_id', UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', UUID(as_uuid=True), nullable=False),
        sa.Column('entity_id', sa.String(255), nullable=False),
        sa.Column('entity_name', sa.String(255), nullable=True),
        sa.Column('oauth_token_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['oauth_token_id'], ['oauth_tokens.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('integration_id', 'organization_id', name='uq_integration_org_mapping')
    )

    # Create indexes on integration_mappings table
    op.create_index('ix_integration_mappings_integration_id', 'integration_mappings', ['integration_id'])
    op.create_index('ix_integration_mappings_organization_id', 'integration_mappings', ['organization_id'])
    op.create_index('ix_integration_mappings_oauth_token_id', 'integration_mappings', ['oauth_token_id'])
    op.create_index(
        'ix_integration_mappings_entity',
        'integration_mappings',
        ['integration_id', 'entity_id']
    )


def downgrade() -> None:
    # Drop integration_mappings table and indexes
    op.drop_index('ix_integration_mappings_entity', table_name='integration_mappings')
    op.drop_index('ix_integration_mappings_oauth_token_id', table_name='integration_mappings')
    op.drop_index('ix_integration_mappings_organization_id', table_name='integration_mappings')
    op.drop_index('ix_integration_mappings_integration_id', table_name='integration_mappings')
    op.drop_table('integration_mappings')

    # Drop integrations table and indexes
    op.drop_index('ix_integrations_is_deleted', table_name='integrations')
    op.drop_index('ix_integrations_oauth_provider_id', table_name='integrations')
    op.drop_index('ix_integrations_name', table_name='integrations')
    op.drop_table('integrations')
