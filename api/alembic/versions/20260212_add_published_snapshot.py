"""Add published_snapshot JSONB column to applications table.

Stores {path: content_hash} mapping for the published version of an app.
Replaces the app_versions-based publish model.

Revision ID: 20260212_pub_snap
Revises: 20260212_uq_webhook_es
Create Date: 2026-02-12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260212_pub_snap"
down_revision = "20260212_uq_webhook_es"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("published_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "published_snapshot")
