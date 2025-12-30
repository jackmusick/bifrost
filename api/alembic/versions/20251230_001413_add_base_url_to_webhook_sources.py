"""add_base_url_to_webhook_sources

Revision ID: cdbca2e76c2a
Revises: e1e2e3e4e5e6
Create Date: 2025-12-30 00:14:13.510184+00:00

Note: This migration is kept for history only. The base_url and callback_path
columns are removed in the next migration (0cde99f39214).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdbca2e76c2a'
down_revision: Union[str, None] = 'e1e2e3e4e5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add base_url column with a default for existing rows
    op.add_column(
        'webhook_sources',
        sa.Column('base_url', sa.String(500), nullable=True)
    )
    # Set default for existing rows (localhost for dev)
    op.execute("UPDATE webhook_sources SET base_url = 'http://localhost:8000' WHERE base_url IS NULL")
    # Make column non-nullable
    op.alter_column('webhook_sources', 'base_url', nullable=False)


def downgrade() -> None:
    op.drop_column('webhook_sources', 'base_url')
