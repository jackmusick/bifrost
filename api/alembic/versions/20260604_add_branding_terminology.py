"""add branding terminology

Revision ID: 20260604_brand_terms
Revises: 20260601_promote_global_tok
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260604_brand_terms"
down_revision: Union[str, Sequence[str]] = "20260601_promote_global_tok"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "branding",
        sa.Column("terminology", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("branding", "terminology")
