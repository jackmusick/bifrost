"""merge solutions + branding migration heads

Both the Solutions chain (...add_solutions → add_app_model → app_identity →
solution_unique_scope) and main's branding/terminology migration (brand_terms)
fork from the same parent (20260601_promote_global_tok) and never rejoin, so a
merge of main into the Solutions branch leaves two alembic heads and
``alembic upgrade head`` fails. This is a no-op merge revision that unifies them.

Revision ID: 20260606_merge_sol_brand
Revises: 20260605_solution_unique_scope, 20260604_brand_terms
Create Date: 2026-06-06 00:00:00.000000
"""
from alembic import op  # noqa: F401

revision = "20260606_merge_sol_brand"
down_revision = ("20260605_solution_unique_scope", "20260604_brand_terms")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
