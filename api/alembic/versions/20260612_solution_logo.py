"""Solution-level icon: logo_data + logo_content_type on solutions.

Declared by ``logo:`` in bifrost.solution.yaml, validated and stamped by
deploy (present => set, absent => cleared), shown on the /solutions catalog.
Mirrors the application logo columns.

Revision ID: 20260612_solution_logo
Revises: 20260611_everyone_access
"""

import sqlalchemy as sa
from alembic import op

revision = "20260612_solution_logo"
down_revision = "20260611_everyone_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("solutions", sa.Column("logo_data", sa.LargeBinary(), nullable=True))
    op.add_column(
        "solutions",
        sa.Column("logo_content_type", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("solutions", "logo_content_type")
    op.drop_column("solutions", "logo_data")
