"""solutions version bookkeeping

Task 20 (upgrade scope change): the install record carries the deployed
bundle's ``version`` (from bifrost.solution.yaml) and, after an upgrade, the
``upgraded_from_version`` it replaced. Both are free-form strings — ordering is
attempted as PEP 440 only for the downgrade gate, never enforced here.

Revision ID: 20260610_solution_version
Revises: 20260609_drop_dup_slug_idx
Create Date: 2026-06-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "20260610_solution_version"
down_revision = "20260609_drop_dup_slug_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("solutions", sa.Column("version", sa.String(64), nullable=True))
    op.add_column(
        "solutions", sa.Column("upgraded_from_version", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("solutions", "upgraded_from_version")
    op.drop_column("solutions", "version")
