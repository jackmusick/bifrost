"""add partial unique index for system_configs with null organization_id

Postgres treats NULL as distinct in unique constraints, so the table-level
``uq_system_config_category_key_org`` constraint does NOT enforce uniqueness
when ``organization_id IS NULL`` (platform-wide rows like the MCP master
config). A partial unique index closes that hole — at most one row per
``(category, key)`` is allowed when ``organization_id`` is NULL.

Revision ID: 20260426_part_uq_sysconfig
Revises: 20260420_hmac_scheme
Create Date: 2026-04-26 17:16:50.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260426_part_uq_sysconfig"
down_revision: Union[str, None] = "20260420_hmac_scheme"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_system_config_category_key_null_org",
        "system_configs",
        ["category", "key"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_system_config_category_key_null_org",
        table_name="system_configs",
        postgresql_where=sa.text("organization_id IS NULL"),
    )
