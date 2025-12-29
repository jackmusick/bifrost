"""add_knowledge_storage_daily

Revision ID: caad9196f150
Revises: add_system_tools_to_agents
Create Date: 2025-12-29 00:26:18.267979+00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "caad9196f150"
down_revision: Union[str, None] = "add_system_tools_to_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_storage_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "organization_id",
            "namespace",
            name="uq_storage_daily_date_org_ns",
        ),
    )
    op.create_index(
        "ix_storage_daily_date", "knowledge_storage_daily", ["snapshot_date"]
    )
    op.create_index(
        "ix_storage_daily_org", "knowledge_storage_daily", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_storage_daily_org", table_name="knowledge_storage_daily")
    op.drop_index("ix_storage_daily_date", table_name="knowledge_storage_daily")
    op.drop_table("knowledge_storage_daily")
