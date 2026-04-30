"""migrate table access role→roles list

Revision ID: 20260429b_table_access_roles
Revises: 20260429_table_access
Create Date: 2026-04-29 13:00:00.000000

Converts any existing table rows where access.role is a single object
into access.roles as a list with that object as the sole element.
Pre-launch only — rows in production will not exist yet.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260429b_table_access_roles"
down_revision = "20260429_table_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tables
            SET access = jsonb_set(
                access - 'role',
                '{roles}',
                CASE
                    WHEN access ? 'role' AND access->>'role' IS NOT NULL
                    THEN jsonb_build_array(access->'role')
                    ELSE '[]'::jsonb
                END
            )
            WHERE access IS NOT NULL
              AND (access ? 'role' OR NOT access ? 'roles')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tables
            SET access = jsonb_set(
                access - 'roles',
                '{role}',
                CASE
                    WHEN access ? 'roles'
                         AND jsonb_array_length(access->'roles') > 0
                    THEN access->'roles'->0
                    ELSE '{}'::jsonb
                END
            )
            WHERE access IS NOT NULL
              AND access ? 'roles'
            """
        )
    )
