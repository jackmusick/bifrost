"""
Drop knowledge_sources and knowledge_source_roles tables.
Create knowledge_namespace_roles junction table for namespace-based RBAC.

Revision ID: 25549bb29ea6
Revises: 0fd35b896176
Create Date: 2026-02-09
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = '25549bb29ea6'
down_revision: Union[str, None] = '0fd35b896176'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop junction table first (has FK to knowledge_sources)
    op.drop_table("knowledge_source_roles")
    # Drop the main entity table
    op.drop_table("knowledge_sources")
    # Drop the enum type
    op.execute("DROP TYPE IF EXISTS knowledge_source_access_level")

    # Create new namespace-based roles table
    op.create_table(
        "knowledge_namespace_roles",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint(
            "namespace", "organization_id", "role_id",
            name="uq_knowledge_ns_role_org",
            postgresql_nulls_not_distinct=True,
        ),
        sa.Index("ix_knowledge_namespace_roles_role_id", "role_id"),
        sa.Index("ix_knowledge_namespace_roles_namespace", "namespace"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_namespace_roles")

    # Recreate enum
    knowledge_source_access_level = sa.Enum("authenticated", "role_based", name="knowledge_source_access_level")
    knowledge_source_access_level.create(op.get_bind())

    # Recreate knowledge_sources
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("namespace", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("access_level", knowledge_source_access_level, server_default="role_based", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    )

    # Recreate knowledge_source_roles
    op.create_table(
        "knowledge_source_roles",
        sa.Column("knowledge_source_id", sa.Uuid(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
    )
