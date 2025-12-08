"""Forms: Replace linked_workflow (name) with workflow_id (UUID)

Revision ID: forms_use_workflow_id
Revises: change_unique_constraints
Create Date: 2025-12-08

This migration removes the legacy name-based workflow reference and
uses ID-based references exclusively. Forms now use workflow_id (UUID)
to reference the workflow to execute.

Changes:
- Rename launch_workflow_id to workflow_id
- Drop linked_workflow column (name-based, legacy)
- Drop ix_forms_linked_workflow index
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "forms_use_workflow_id"
down_revision = "change_unique_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the index on linked_workflow first
    op.drop_index("ix_forms_linked_workflow", "forms")

    # Drop the linked_workflow column (name-based, no longer used)
    op.drop_column("forms", "linked_workflow")

    # Rename launch_workflow_id to workflow_id
    # This becomes the primary workflow reference for form execution
    op.alter_column(
        "forms",
        "launch_workflow_id",
        new_column_name="workflow_id",
    )

    # Add index on workflow_id for lookups
    op.create_index("ix_forms_workflow_id", "forms", ["workflow_id"])


def downgrade() -> None:
    # Drop the new index
    op.drop_index("ix_forms_workflow_id", "forms")

    # Rename workflow_id back to launch_workflow_id
    op.alter_column(
        "forms",
        "workflow_id",
        new_column_name="launch_workflow_id",
    )

    # Re-add linked_workflow column
    op.add_column(
        "forms",
        sa.Column("linked_workflow", sa.String(255), nullable=True)
    )

    # Re-add the index
    op.create_index("ix_forms_linked_workflow", "forms", ["linked_workflow"])
