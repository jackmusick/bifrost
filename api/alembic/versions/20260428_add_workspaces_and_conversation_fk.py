"""add workspaces table and conversation.workspace_id

Workspaces are first-class containers for chats. Conversations may belong to a
workspace OR live in the general pool (workspace_id IS NULL) — the unscoped
default chat list. There is no synthetic "Personal" workspace.

Revision ID: 20260428_add_workspaces
Revises: 20260428_webhook_rate_limit
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260428_add_workspaces"
down_revision = "20260428_webhook_rate_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. workspace_scope enum.
    workspace_scope = sa.Enum(
        "personal", "org", "role", name="workspace_scope"
    )
    workspace_scope.create(op.get_bind(), checkfirst=True)

    # 2. workspaces table.
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scope",
            postgresql.ENUM(
                "personal", "org", "role", name="workspace_scope", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "default_agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("enabled_tool_ids", postgresql.JSONB(), nullable=True),
        sa.Column("enabled_knowledge_source_ids", postgresql.JSONB(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_workspaces_organization_id", "workspaces", ["organization_id"]
    )
    op.create_index("ix_workspaces_role_id", "workspaces", ["role_id"])
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])
    op.create_index("ix_workspaces_is_active", "workspaces", ["is_active"])
    op.create_index("ix_workspaces_scope", "workspaces", ["scope"])

    # 3. conversations.workspace_id (nullable: NULL = general pool).
    op.add_column(
        "conversations",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_conversations_workspace_id", "conversations", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_workspace_id", table_name="conversations")
    op.drop_column("conversations", "workspace_id")
    op.drop_index("ix_workspaces_scope", table_name="workspaces")
    op.drop_index("ix_workspaces_is_active", table_name="workspaces")
    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_index("ix_workspaces_role_id", table_name="workspaces")
    op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
    op.drop_table("workspaces")
    sa.Enum(name="workspace_scope").drop(op.get_bind(), checkfirst=True)
