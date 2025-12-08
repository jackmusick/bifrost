"""Change unique constraints for workflows, data_providers, and forms

Revision ID: change_unique_constraints
Revises: add_developer_contexts_table
Create Date: 2025-12-08

Changes unique keys from name-based to (file_path, function_name) based:
- Workflows: unique(name) -> unique(file_path, function_name)
- DataProviders: unique(name) -> unique(file_path, function_name)
- Forms: add unique(file_path)

This allows duplicate display names across files while maintaining
proper indexing for ON CONFLICT upserts from file sync.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "change_unique_constraints"
down_revision = "add_developer_contexts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # Workflows: add function_name column, change unique constraint
    # =========================================================================

    # Add function_name column
    op.add_column(
        "workflows",
        sa.Column("function_name", sa.String(255), nullable=True)
    )

    # Populate function_name from name for existing rows
    # (In practice, function_name usually equals the decorator name)
    op.execute("UPDATE workflows SET function_name = name WHERE function_name IS NULL")

    # Make function_name NOT NULL after populating
    op.alter_column("workflows", "function_name", nullable=False)

    # Drop old unique constraint on name (constraint name from migration 005)
    op.drop_constraint("uq_workflows_name", "workflows", type_="unique")

    # Create new unique constraint on (file_path, function_name)
    op.create_unique_constraint(
        "workflows_file_function_key",
        "workflows",
        ["file_path", "function_name"]
    )

    # Keep index on name for searching (no longer unique)
    # The existing ix_workflows_name index should remain as a regular index

    # =========================================================================
    # DataProviders: add function_name column, change unique constraint
    # =========================================================================

    # Add function_name column
    op.add_column(
        "data_providers",
        sa.Column("function_name", sa.String(255), nullable=True)
    )

    # Populate function_name from name for existing rows
    op.execute("UPDATE data_providers SET function_name = name WHERE function_name IS NULL")

    # Make function_name NOT NULL after populating
    op.alter_column("data_providers", "function_name", nullable=False)

    # Drop old unique constraint on name (constraint name from migration 005)
    op.drop_constraint("uq_data_providers_name", "data_providers", type_="unique")

    # Create new unique constraint on (file_path, function_name)
    op.create_unique_constraint(
        "data_providers_file_function_key",
        "data_providers",
        ["file_path", "function_name"]
    )

    # =========================================================================
    # Forms: add unique constraint on file_path (for ON CONFLICT)
    # =========================================================================

    # Create unique constraint on file_path
    # Note: file_path can be NULL for forms not backed by files
    op.create_index(
        "ix_forms_file_path_unique",
        "forms",
        ["file_path"],
        unique=True,
        postgresql_where=sa.text("file_path IS NOT NULL")
    )


def downgrade() -> None:
    # Forms: remove file_path unique index
    op.drop_index("ix_forms_file_path_unique", "forms")

    # DataProviders: revert to unique(name)
    op.drop_constraint("data_providers_file_function_key", "data_providers", type_="unique")
    op.create_unique_constraint("uq_data_providers_name", "data_providers", ["name"])
    op.drop_column("data_providers", "function_name")

    # Workflows: revert to unique(name)
    op.drop_constraint("workflows_file_function_key", "workflows", type_="unique")
    op.create_unique_constraint("uq_workflows_name", "workflows", ["name"])
    op.drop_column("workflows", "function_name")
