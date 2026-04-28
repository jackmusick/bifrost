"""add overlap_policy to schedule_sources

Revision ID: 20260428_add_overlap_policy
Revises: 20260426_part_uq_sysconfig
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_add_overlap_policy"
down_revision = "20260426_part_uq_sysconfig"
branch_labels = None
depends_on = None


def upgrade() -> None:
    overlap_policy_enum = sa.Enum("skip", "queue", "replace", name="schedule_overlap_policy")
    overlap_policy_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "schedule_sources",
        sa.Column(
            "overlap_policy",
            overlap_policy_enum,
            nullable=False,
            server_default="skip",
        ),
    )


def downgrade() -> None:
    op.drop_column("schedule_sources", "overlap_policy")
    sa.Enum(name="schedule_overlap_policy").drop(op.get_bind(), checkfirst=True)
