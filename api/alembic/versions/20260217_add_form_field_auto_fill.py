"""Add auto_fill JSONB column to form_fields table.

Stores a mapping of sibling field names to data provider metadata paths,
enabling auto-population of form fields when a data provider returns results.

Revision ID: 20260217_auto_fill
Revises: 20260212_drop_old_app_tables
Create Date: 2026-02-17
"""

import sqlalchemy as sa
from alembic import op

revision = "20260217_auto_fill"
down_revision = "20260212_drop_old_app_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_fields",
        sa.Column("auto_fill", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("form_fields", "auto_fill")
