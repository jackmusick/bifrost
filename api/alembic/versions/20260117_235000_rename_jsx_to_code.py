"""rename_jsx_to_code

Rename JSX app builder schema to use 'code' terminology:
- Rename table app_jsx_files -> app_code_files
- Rename indexes accordingly
- Update 'jsx' engine values to 'code' in applications table

This migration is reversible.

Revision ID: 4b9d382g1173
Revises: 3a8c291f0062
Create Date: 2026-01-17 23:50:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4b9d382g1173"
down_revision: Union[str, None] = "3a8c291f0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Drop old indexes (must drop before renaming table)
    op.drop_index("ix_jsx_files_path", table_name="app_jsx_files")
    op.drop_index("ix_jsx_files_version", table_name="app_jsx_files")

    # Step 2: Rename table app_jsx_files -> app_code_files
    op.rename_table("app_jsx_files", "app_code_files")

    # Step 3: Create new indexes with updated names
    op.create_index("ix_code_files_version", "app_code_files", ["app_version_id"])
    op.create_index(
        "ix_code_files_path",
        "app_code_files",
        ["app_version_id", "path"],
        unique=True,
    )

    # Step 4: Update engine values from 'jsx' to 'code' in applications table
    # Note: 'components' remains as the default for the JSON component tree engine
    op.execute("UPDATE applications SET engine = 'code' WHERE engine = 'jsx'")


def downgrade() -> None:
    # Step 1: Update engine values from 'code' back to 'jsx'
    op.execute("UPDATE applications SET engine = 'jsx' WHERE engine = 'code'")

    # Step 2: Drop new indexes
    op.drop_index("ix_code_files_path", table_name="app_code_files")
    op.drop_index("ix_code_files_version", table_name="app_code_files")

    # Step 3: Rename table back to app_jsx_files
    op.rename_table("app_code_files", "app_jsx_files")

    # Step 4: Recreate original indexes
    op.create_index("ix_jsx_files_version", "app_jsx_files", ["app_version_id"])
    op.create_index(
        "ix_jsx_files_path",
        "app_jsx_files",
        ["app_version_id", "path"],
        unique=True,
    )
