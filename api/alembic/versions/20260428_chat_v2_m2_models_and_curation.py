"""chat v2 m2: platform model registry + cascading default-model fields

Adds:
- platform_models table (cache of the global model catalog, populated from models.json)
- org_model_aliases table (per-org logical aliases)
- model_deprecations table (platform-wide + org-level remap entries)
- orgs.allowed_chat_models (JSONB list, optional org-level allowlist narrowing)
- orgs.default_chat_model
- roles.default_chat_model
- users.default_chat_model
- workspaces.default_model
- conversations.current_model
- messages.cost_tier

Revision ID: 20260428_chat_v2_m2
Revises: 20260428_add_workspaces
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260428_chat_v2_m2"
down_revision = "20260428_add_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- platform_models -----------------------------------------------------
    op.create_table(
        "platform_models",
        sa.Column("model_id", sa.String(255), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cost_tier", sa.String(20), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("input_price_per_million", sa.Numeric(10, 4), nullable=True),
        sa.Column("output_price_per_million", sa.Numeric(10, 4), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
    op.create_index("ix_platform_models_provider", "platform_models", ["provider"])
    op.create_index("ix_platform_models_cost_tier", "platform_models", ["cost_tier"])
    op.create_index("ix_platform_models_is_active", "platform_models", ["is_active"])

    # --- org_model_aliases ---------------------------------------------------
    op.create_table(
        "org_model_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("target_model_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("cost_tier", sa.String(20), nullable=True),
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
        sa.UniqueConstraint("organization_id", "alias", name="uq_org_model_alias"),
    )
    op.create_index("ix_org_model_aliases_org", "org_model_aliases", ["organization_id"])

    # --- model_deprecations --------------------------------------------------
    op.create_table(
        "model_deprecations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("old_model_id", sa.String(255), nullable=False),
        sa.Column("new_model_id", sa.String(255), nullable=False),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "old_model_id",
            "organization_id",
            name="uq_model_deprecation_old_org",
        ),
    )
    op.create_index("ix_model_deprecations_org", "model_deprecations", ["organization_id"])

    # --- cascading default-model columns -------------------------------------
    op.add_column(
        "organizations",
        sa.Column(
            "allowed_chat_models",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("default_chat_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "roles",
        sa.Column("default_chat_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("default_chat_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "workspaces",
        sa.Column("default_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("current_model", sa.String(255), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("cost_tier", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "cost_tier")
    op.drop_column("conversations", "current_model")
    op.drop_column("workspaces", "default_model")
    op.drop_column("users", "default_chat_model")
    op.drop_column("roles", "default_chat_model")
    op.drop_column("organizations", "default_chat_model")
    op.drop_column("organizations", "allowed_chat_models")

    op.drop_index("ix_model_deprecations_org", table_name="model_deprecations")
    op.drop_table("model_deprecations")

    op.drop_index("ix_org_model_aliases_org", table_name="org_model_aliases")
    op.drop_table("org_model_aliases")

    op.drop_index("ix_platform_models_is_active", table_name="platform_models")
    op.drop_index("ix_platform_models_cost_tier", table_name="platform_models")
    op.drop_index("ix_platform_models_provider", table_name="platform_models")
    op.drop_table("platform_models")
