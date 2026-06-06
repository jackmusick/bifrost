"""table name uniqueness: solution-scoped (mirror workflows)

A Solution OWNS the tables it deploys (criterion: a developer authoring a
Solution should never reason about the global table namespace — two solutions
may each ship a `users` table). Table NAME uniqueness must therefore be scoped
per source, exactly like workflow name uniqueness:

- _repo/ tables: unique by (org/global, name) WHERE solution_id IS NULL
  (restrict the EXISTING indexes — they currently fire for solution rows too,
  so a solution deploying a name that exists globally / in two installs in one
  org raises IntegrityError → an unhandled 500 on deploy).
- solution tables: unique by (solution_id, name) WHERE solution_id IS NOT NULL.

Revision ID: 20260606_table_name_sol_scope
Revises: 20260606_merge_sol_brand
Create Date: 2026-06-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "20260606_table_name_sol_scope"
down_revision = "20260606_merge_sol_brand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Restrict the existing _repo/ name indexes to non-solution rows.
    op.drop_index("ix_tables_org_name_unique", table_name="tables")
    op.drop_index("ix_tables_global_name_unique", table_name="tables")
    op.create_index(
        "ix_tables_org_name_unique",
        "tables",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL AND solution_id IS NULL"),
    )
    op.create_index(
        "ix_tables_global_name_unique",
        "tables",
        ["name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL AND solution_id IS NULL"),
    )
    # Solution-scoped: one name per install.
    op.create_index(
        "ix_tables_solution_name_unique",
        "tables",
        ["solution_id", "name"],
        unique=True,
        postgresql_where=sa.text("solution_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tables_solution_name_unique", table_name="tables")
    op.drop_index("ix_tables_global_name_unique", table_name="tables")
    op.drop_index("ix_tables_org_name_unique", table_name="tables")
    op.create_index(
        "ix_tables_org_name_unique",
        "tables",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tables_global_name_unique",
        "tables",
        ["name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
