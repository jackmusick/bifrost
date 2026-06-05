"""add app_model to applications (v2 standalone app model)

Adds the render-model discriminator: 'inline_v1' (default, legacy inline render)
vs 'standalone_v2' (own createRoot + router + real SDK). All existing apps stay
inline_v1. See docs/superpowers/specs/2026-06-04-solutions-v2-app-model-design.md.

Revision ID: 20260604_add_app_model
Revises: 20260604_add_solutions
Create Date: 2026-06-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260604_add_app_model"
down_revision = "20260604_add_solutions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("app_model", sa.String(length=20), nullable=False, server_default="inline_v1"),
    )


def downgrade() -> None:
    op.drop_column("applications", "app_model")
