"""Drop is_platform column from workflows

Revision ID: drop_is_platform
Revises: forms_use_workflow_id
Create Date: 2025-12-08

The is_platform concept (for distinguishing platform example workflows
from user workflows) is being removed as it adds unnecessary complexity.
All workflows are now treated the same regardless of source directory.

Changes:
- Drop ix_workflows_is_platform index
- Drop is_platform column
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "drop_is_platform"
down_revision = "forms_use_workflow_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop index first
    op.drop_index("ix_workflows_is_platform", table_name="workflows")

    # Drop column
    op.drop_column("workflows", "is_platform")


def downgrade() -> None:
    # Re-add column
    op.add_column(
        "workflows",
        sa.Column("is_platform", sa.Boolean(), nullable=False, server_default="false")
    )

    # Re-add index
    op.create_index("ix_workflows_is_platform", "workflows", ["is_platform"])
