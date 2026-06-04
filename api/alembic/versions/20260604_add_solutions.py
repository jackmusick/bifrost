"""add solutions table and nullable solution_id on managed entities

Creates the `solutions` install table and adds a nullable `solution_id` FK
(ON DELETE CASCADE) to the five portable entities — workflows, applications,
forms, agents, tables. A non-null `solution_id` marks an entity as
solution-managed (read-only on the platform; one writer per install). NULL
means an ad-hoc `_repo/` entity, i.e. existing behavior is unchanged.

See docs/plans/2026-06-04-solutions-success-criteria.md §3.2.

Revision ID: 20260604_add_solutions
Revises: 20260601_promote_global_tok
Create Date: 2026-06-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260604_add_solutions"
down_revision = "20260601_promote_global_tok"
branch_labels = None
depends_on = None

# Entities that gain solution_id. (table, index name)
_MANAGED = [
    ("workflows", "ix_workflows_solution_id"),
    ("applications", "ix_applications_solution_id"),
    ("forms", "ix_forms_solution_id"),
    ("agents", "ix_agents_solution_id"),
    ("tables", "ix_tables_solution_id"),
]


def upgrade() -> None:
    op.create_table(
        "solutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "global_repo_access",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "git_connected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("git_repo_url", sa.String(length=1024), nullable=True),
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
    op.create_index("ix_solutions_slug", "solutions", ["slug"])
    op.create_index("ix_solutions_organization_id", "solutions", ["organization_id"])

    for table, index_name in _MANAGED:
        op.add_column(
            table,
            sa.Column(
                "solution_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("solutions.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(index_name, table, ["solution_id"])


def downgrade() -> None:
    for table, index_name in _MANAGED:
        op.drop_index(index_name, table_name=table)
        op.drop_column(table, "solution_id")

    op.drop_index("ix_solutions_organization_id", table_name="solutions")
    op.drop_index("ix_solutions_slug", table_name="solutions")
    op.drop_table("solutions")
