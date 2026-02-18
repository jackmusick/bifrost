"""add_oauth_audience

Revision ID: 20260218_oauth_audience
Revises: 20260218_is_system_users
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260218_oauth_audience"
down_revision = "20260218_is_system_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oauth_providers", sa.Column("audience", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("oauth_providers", "audience")
