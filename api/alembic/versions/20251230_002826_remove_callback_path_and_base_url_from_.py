"""remove_callback_path_and_base_url_from_webhook_sources

Revision ID: 0cde99f39214
Revises: cdbca2e76c2a
Create Date: 2025-12-30 00:28:26.650037+00:00

This migration removes the callback_path and base_url columns from webhook_sources.
Webhook URLs now use the event_source_id directly: /api/hooks/{event_source_id}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cde99f39214'
down_revision: Union[str, None] = 'cdbca2e76c2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique index on callback_path if it exists
    # (may not exist if callback_path was never added to this database)
    op.execute("""
        DROP INDEX IF EXISTS ix_webhook_sources_callback_path
    """)

    # Drop the columns if they exist
    # callback_path: may not exist in some databases
    # base_url: added in migration cdbca2e76c2a
    op.execute("""
        ALTER TABLE webhook_sources
        DROP COLUMN IF EXISTS callback_path
    """)
    op.execute("""
        ALTER TABLE webhook_sources
        DROP COLUMN IF EXISTS base_url
    """)


def downgrade() -> None:
    # Re-add the columns
    op.add_column(
        'webhook_sources',
        sa.Column('callback_path', sa.String(255), nullable=True)
    )
    op.add_column(
        'webhook_sources',
        sa.Column('base_url', sa.String(500), nullable=True)
    )

    # Set defaults for existing rows
    op.execute("UPDATE webhook_sources SET callback_path = id::text WHERE callback_path IS NULL")
    op.execute("UPDATE webhook_sources SET base_url = 'http://localhost:8000' WHERE base_url IS NULL")

    # Make columns non-nullable
    op.alter_column('webhook_sources', 'callback_path', nullable=False)
    op.alter_column('webhook_sources', 'base_url', nullable=False)

    # Re-create the unique index
    op.create_index(
        'ix_webhook_sources_callback_path',
        'webhook_sources',
        ['callback_path'],
        unique=True
    )
