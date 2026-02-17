"""add app_embed_secrets table

Revision ID: 20260216_embed_secrets
Revises: 20260216_app_repo_path
Create Date: 2026-02-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260216_embed_secrets"
down_revision = "20260216_app_repo_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_embed_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_app_embed_secrets_application_id",
        "app_embed_secrets",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_app_embed_secrets_application_id")
    op.drop_table("app_embed_secrets")
