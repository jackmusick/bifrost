"""Add allow_as_query_param boolean column to form_fields table.

Enables per-field control of whether a field's value can be populated
from URL query parameters.

Revision ID: 20260218_allow_qp
Revises: 20260218_oauth_audience
Create Date: 2026-02-18
"""

import sqlalchemy as sa
from alembic import op

revision = "20260218_allow_qp"
down_revision = "20260218_oauth_audience"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_fields",
        sa.Column("allow_as_query_param", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("form_fields", "allow_as_query_param")
