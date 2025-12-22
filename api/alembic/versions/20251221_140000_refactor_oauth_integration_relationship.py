"""Refactor OAuth-Integration relationship (OAuth owns Integration)

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2025-12-21

This migration inverts the OAuth-Integration relationship:
- OLD: Integration.oauth_provider_id -> OAuthProvider
- NEW: OAuthProvider.integration_id -> Integration (one-to-one)

This makes sense because:
1. An integration always belongs to exactly one OAuth provider (or none)
2. An OAuth provider may be used by multiple integrations (future flexibility)
3. Data is already structured this way in code after previous migrations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, None] = 'f6g7h8i9j0k1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add integration_id column to oauth_providers
    op.add_column(
        'oauth_providers',
        sa.Column('integration_id', UUID(as_uuid=True), nullable=True)
    )

    # Step 2: Create foreign key and index
    op.create_foreign_key(
        'oauth_providers_integration_id_fkey',
        'oauth_providers',
        'integrations',
        ['integration_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_oauth_providers_integration_id', 'oauth_providers', ['integration_id'])

    # Step 3: Migrate data from integrations.oauth_provider_id to oauth_providers.integration_id
    # This update statement copies the reference from integrations to oauth_providers
    op.execute("""
        UPDATE oauth_providers
        SET integration_id = integrations.id
        FROM integrations
        WHERE integrations.oauth_provider_id = oauth_providers.id
        AND oauth_providers.integration_id IS NULL
    """)

    # Step 4: Drop the old foreign key constraint and index on integrations table
    op.drop_constraint('integrations_oauth_provider_id_fkey', 'integrations', type_='foreignkey')
    op.drop_index('ix_integrations_oauth_provider_id', table_name='integrations')

    # Step 5: Drop the oauth_provider_id column from integrations
    op.drop_column('integrations', 'oauth_provider_id')

    # Step 6: Add unique constraint on integration_id in oauth_providers
    # This ensures one OAuth provider per integration
    op.create_unique_constraint(
        'uq_oauth_providers_integration_id',
        'oauth_providers',
        ['integration_id']
    )


def downgrade() -> None:
    # Step 1: Drop the unique constraint on integration_id
    op.drop_constraint('uq_oauth_providers_integration_id', 'oauth_providers', type_='unique')

    # Step 2: Add back oauth_provider_id column to integrations
    op.add_column(
        'integrations',
        sa.Column('oauth_provider_id', UUID(as_uuid=True), nullable=True)
    )

    # Step 3: Migrate data back from oauth_providers.integration_id to integrations.oauth_provider_id
    op.execute("""
        UPDATE integrations
        SET oauth_provider_id = oauth_providers.id
        FROM oauth_providers
        WHERE oauth_providers.integration_id = integrations.id
        AND integrations.oauth_provider_id IS NULL
    """)

    # Step 4: Re-add the foreign key constraint and index on integrations
    op.create_foreign_key(
        'integrations_oauth_provider_id_fkey',
        'integrations',
        'oauth_providers',
        ['oauth_provider_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_integrations_oauth_provider_id', 'integrations', ['oauth_provider_id'])

    # Step 5: Drop the integration_id column from oauth_providers
    op.drop_index('ix_oauth_providers_integration_id', table_name='oauth_providers')
    op.drop_constraint('oauth_providers_integration_id_fkey', 'oauth_providers', type_='foreignkey')
    op.drop_column('oauth_providers', 'integration_id')
