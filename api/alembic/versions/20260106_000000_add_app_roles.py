"""Add app_roles junction table and access_level column to applications.

Revision ID: 20260106_000000
Revises: 20260105_000000
Create Date: 2026-01-06

This migration:
1. Adds access_level column to applications table (like forms)
2. Creates app_roles junction table for role-based access control
3. Migrates existing JSONB permissions data to new structure
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260106_000000"
down_revision = "20260105_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add access_level column to applications
    op.add_column(
        "applications",
        sa.Column(
            "access_level",
            sa.String(20),
            nullable=False,
            server_default="authenticated",
        ),
    )

    # 2. Create app_roles junction table
    op.create_table(
        "app_roles",
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["applications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("app_id", "role_id"),
    )

    # Create index for role lookups
    op.create_index("ix_app_roles_role_id", "app_roles", ["role_id"])

    # 3. Migrate existing JSONB permissions to new structure
    # Extract access_level from permissions JSONB if present
    op.execute("""
        UPDATE applications
        SET access_level = COALESCE(
            permissions->>'access_level',
            permissions->>'accessLevel',
            'authenticated'
        )
        WHERE permissions IS NOT NULL
          AND permissions != '{}'::jsonb
          AND (
            permissions->>'access_level' IS NOT NULL
            OR permissions->>'accessLevel' IS NOT NULL
          )
    """)

    # Insert existing allowed_roles into junction table
    # Handle both 'allowed_roles' and 'allowedRoles' key formats
    op.execute("""
        INSERT INTO app_roles (app_id, role_id, assigned_by, assigned_at)
        SELECT
            a.id,
            (role_elem::text)::uuid,
            'migration',
            NOW()
        FROM applications a,
             jsonb_array_elements_text(
                 COALESCE(
                     a.permissions->'allowed_roles',
                     a.permissions->'allowedRoles'
                 )
             ) AS role_elem
        WHERE (a.permissions->'allowed_roles' IS NOT NULL
               AND jsonb_array_length(a.permissions->'allowed_roles') > 0)
           OR (a.permissions->'allowedRoles' IS NOT NULL
               AND jsonb_array_length(a.permissions->'allowedRoles') > 0)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Restore permissions JSONB from access_level and app_roles
    op.execute("""
        UPDATE applications a
        SET permissions = jsonb_build_object(
            'access_level', a.access_level,
            'allowed_roles', COALESCE(
                (SELECT jsonb_agg(ar.role_id::text)
                 FROM app_roles ar
                 WHERE ar.app_id = a.id),
                '[]'::jsonb
            )
        )
    """)

    # Drop app_roles table
    op.drop_index("ix_app_roles_role_id", table_name="app_roles")
    op.drop_table("app_roles")

    # Drop access_level column
    op.drop_column("applications", "access_level")
