"""Add developer_contexts and developer_api_keys tables

Revision ID: add_developer_contexts_table
Revises: add_workspace_files_table
Create Date: 2025-12-07

These tables support the Bifrost SDK for local development:
- developer_contexts: Per-user development context settings
- developer_api_keys: API keys for SDK authentication
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "add_developer_contexts_table"
down_revision = "add_workspace_files_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create developer_contexts table
    op.create_table(
        "developer_contexts",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), nullable=False),

        # Context configuration
        sa.Column("default_org_id", UUID(), nullable=True),
        sa.Column("default_parameters", JSONB(), nullable=False, server_default="{}"),
        sa.Column("track_executions", sa.Boolean(), nullable=False, server_default=sa.text("true")),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_org_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", name="uq_developer_contexts_user_id"),
    )

    op.create_index("ix_developer_contexts_user_id", "developer_contexts", ["user_id"])

    # Create developer_api_keys table
    op.create_table(
        "developer_api_keys",
        sa.Column("id", UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(), nullable=False),

        # Key identification
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),  # First 8 chars for display: bfsk_xxxx
        sa.Column("key_hash", sa.String(64), nullable=False),  # SHA-256 hash

        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),

        # Usage tracking
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("last_used_ip", sa.String(45), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),

        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_developer_api_keys_user_id", "developer_api_keys", ["user_id"])
    op.create_index("ix_developer_api_keys_key_hash", "developer_api_keys", ["key_hash"], unique=True)
    op.create_index(
        "ix_developer_api_keys_active",
        "developer_api_keys",
        ["user_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_developer_api_keys_active", table_name="developer_api_keys")
    op.drop_index("ix_developer_api_keys_key_hash", table_name="developer_api_keys")
    op.drop_index("ix_developer_api_keys_user_id", table_name="developer_api_keys")
    op.drop_table("developer_api_keys")

    op.drop_index("ix_developer_contexts_user_id", table_name="developer_contexts")
    op.drop_table("developer_contexts")
