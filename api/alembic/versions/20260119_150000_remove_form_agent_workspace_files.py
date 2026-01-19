"""Remove form and agent entries from workspace_files.

Revision ID: 6b9fd30e4d68
Revises: 5a8fc29d3c57
Create Date: 2026-01-19

These entities are now fully virtual - they exist only in their
entity tables and are serialized on-the-fly for git sync.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "6b9fd30e4d68"
down_revision = "5a8fc29d3c57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Delete form and agent entries from workspace_files."""
    op.execute("""
        DELETE FROM workspace_files
        WHERE entity_type IN ('form', 'agent')
    """)


def downgrade() -> None:
    """No downgrade - entries were virtual anyway."""
    pass
