"""Drop developer_contexts table.

Revision ID: 20260526_drop_developer_contexts
Revises: 20260522_merge_claims_knowledge
Create Date: 2026-05-26

The DeveloperContext model was a per-user override that let any
authenticated user set ``default_org_id`` to an arbitrary org via
``PUT /api/sdk/context`` with no platform-admin check. ``_get_cli_org_id``
then trusted that value as the caller's "own org", so the resolver's
rule "requested == caller_org_id is always allowed" served the other
org's data on every SDK call that omitted ``scope``.

The replacement model:
    - The caller's "own org" is ``User.organization_id`` (auth-verified).
    - Platform admins / provider-org members targeting another org pass
      ``scope`` explicitly per SDK call.

This migration drops the table outright. The rows had no value beyond
the org override + ``default_parameters`` / ``track_executions`` toggles,
neither of which are referenced after this change.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260526_drop_developer_contexts"
down_revision = "20260522_merge_claims_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_developer_contexts_user_id", table_name="developer_contexts")
    op.drop_table("developer_contexts")


def downgrade() -> None:
    op.create_table(
        "developer_contexts",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), nullable=False),
        sa.Column("default_org_id", UUID(), nullable=True),
        sa.Column("default_parameters", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("track_executions", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_developer_contexts_user_id", "developer_contexts", ["user_id"], unique=False
    )
