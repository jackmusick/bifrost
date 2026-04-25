"""add hmac_scheme to embed secrets

Revision ID: 20260420_hmac_scheme
Revises: 20260424c_answered
Create Date: 2026-04-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260420_hmac_scheme"
down_revision = "20260424c_answered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default backfills existing rows; column stays NOT NULL with default
    # for forward compatibility (CLI/MCP secret creation paths can omit the field).
    op.add_column(
        "app_embed_secrets",
        sa.Column(
            "hmac_scheme",
            sa.String(length=32),
            nullable=False,
            server_default="shopify",
        ),
    )
    op.add_column(
        "form_embed_secrets",
        sa.Column(
            "hmac_scheme",
            sa.String(length=32),
            nullable=False,
            server_default="shopify",
        ),
    )


def downgrade() -> None:
    op.drop_column("form_embed_secrets", "hmac_scheme")
    op.drop_column("app_embed_secrets", "hmac_scheme")
