"""add ondelete SET NULL to executions.api_key_id FK

Revision ID: 20260302_api_key_ondelete
Revises: 20260227_ondelete_fks
Create Date: 2026-03-02

The executions.api_key_id FK to workflows.id had ON UPDATE CASCADE but
no ON DELETE action, causing IntegrityError when git-sync deletes
workflows that have execution history.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260302_api_key_ondelete"
down_revision = "20260227_ondelete_fks"
branch_labels = None
depends_on = None

_FIND_FK_SQL = sa.text("""
    SELECT tc.constraint_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
        AND tc.table_schema = ccu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_name = :table
        AND kcu.column_name = :column
        AND ccu.table_name = :ref_table
        AND ccu.column_name = :ref_column
    LIMIT 1
""")


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        _FIND_FK_SQL,
        {"table": "executions", "column": "api_key_id",
         "ref_table": "workflows", "ref_column": "id"},
    ).fetchone()
    if row is None:
        raise RuntimeError("FK not found: executions.api_key_id -> workflows.id")
    fk_name = row[0]

    op.drop_constraint(fk_name, "executions", type_="foreignkey")
    op.create_foreign_key(
        fk_name, "executions", "workflows",
        ["api_key_id"], ["id"],
        ondelete="SET NULL", onupdate="CASCADE",
    )


def downgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        _FIND_FK_SQL,
        {"table": "executions", "column": "api_key_id",
         "ref_table": "workflows", "ref_column": "id"},
    ).fetchone()
    if row is None:
        raise RuntimeError("FK not found: executions.api_key_id -> workflows.id")
    fk_name = row[0]

    op.drop_constraint(fk_name, "executions", type_="foreignkey")
    op.create_foreign_key(
        fk_name, "executions", "workflows",
        ["api_key_id"], ["id"],
        onupdate="CASCADE",
    )
