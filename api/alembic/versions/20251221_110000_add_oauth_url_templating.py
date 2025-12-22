"""add_oauth_url_templating

Adds support for OAuth URL templating with token_url_defaults field.

Revision ID: oauth_url_templating
Revises: 20251221_010000_add_config_integration_id
Create Date: 2025-12-21 11:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add token_url_defaults column to oauth_providers table
    # This allows for URL templates like: https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token
    # with defaults like: {"entity_id": "common"}
    op.add_column(
        'oauth_providers',
        sa.Column(
            'token_url_defaults',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='{}',
            comment='Default values for URL template placeholders (e.g., {"entity_id": "common"})'
        )
    )


def downgrade() -> None:
    op.drop_column('oauth_providers', 'token_url_defaults')
