"""Split App Builder schema into app_pages and app_components tables.

Revision ID: 20260105_000000
Revises: 20260104_000000
Create Date: 2026-01-05

Splits the monolithic application definition JSONB into separate tables:
- applications: metadata, navigation, permissions (no definition blob)
- app_pages: one row per page (draft and live as separate rows)
- app_components: one row per component with parent_id for tree structure

This enables:
- Granular MCP operations (99% token savings on component edits)
- Lazy loading of pages in the frontend
- Backend-enforced page permissions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260105_000000"
down_revision = "20260104_000000"  # workflow_identity_schema
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Modify applications table - add new columns, drop definition blobs
    # =========================================================================

    # Add new app-level JSONB columns (small, not the full definition)
    op.add_column(
        "applications",
        sa.Column("navigation", postgresql.JSONB(), server_default="{}", nullable=False),
    )
    op.add_column(
        "applications",
        sa.Column("global_data_sources", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "applications",
        sa.Column("global_variables", postgresql.JSONB(), server_default="{}", nullable=False),
    )
    op.add_column(
        "applications",
        sa.Column("permissions", postgresql.JSONB(), server_default="{}", nullable=False),
    )

    # Drop the old definition columns (not live yet, so no data migration needed)
    op.drop_column("applications", "live_definition")
    op.drop_column("applications", "draft_definition")
    op.drop_column("applications", "version_history")

    # =========================================================================
    # 2. Create app_pages table
    # =========================================================================
    op.create_table(
        "app_pages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.String(255), nullable=False),  # e.g., "dashboard"
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),  # e.g., "/"
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Page-level config (small JSONB)
        sa.Column("data_sources", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("variables", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("launch_workflow_id", sa.UUID(), nullable=True),
        sa.Column("launch_workflow_params", postgresql.JSONB(), server_default="{}", nullable=True),
        sa.Column("permission", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("page_order", sa.Integer(), nullable=False, server_default="0"),
        # Root layout config (the page's top-level container)
        sa.Column("root_layout_type", sa.String(20), nullable=False, server_default="'column'"),
        sa.Column("root_layout_config", postgresql.JSONB(), server_default="{}", nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        # Constraints
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["launch_workflow_id"], ["workflows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Index for listing pages by app
    op.create_index("ix_app_pages_application_id", "app_pages", ["application_id"])
    op.create_index("ix_app_pages_application_draft", "app_pages", ["application_id", "is_draft"])

    # Unique constraint: page_id unique within app + draft/live
    op.create_index(
        "ix_app_pages_unique",
        "app_pages",
        ["application_id", "page_id", "is_draft"],
        unique=True,
    )

    # =========================================================================
    # 3. Create app_components table
    # =========================================================================
    op.create_table(
        "app_components",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.String(255), nullable=False),  # e.g., "btn_submit"
        sa.Column("parent_id", sa.UUID(), nullable=True),  # NULL for root-level
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("type", sa.String(50), nullable=False),  # "button", "row", "data-table", etc.
        sa.Column("props", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("component_order", sa.Integer(), nullable=False, server_default="0"),
        # Common component fields promoted to columns for querying
        sa.Column("visible", sa.Text(), nullable=True),  # Visibility expression
        sa.Column("width", sa.String(20), nullable=True),  # Component width
        sa.Column("loading_workflows", postgresql.JSONB(), server_default="[]", nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        # Constraints
        sa.ForeignKeyConstraint(["page_id"], ["app_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["app_components.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Index for listing components by page
    op.create_index("ix_app_components_page_id", "app_components", ["page_id"])
    op.create_index("ix_app_components_page_draft", "app_components", ["page_id", "is_draft"])

    # Index for tree traversal (finding children)
    op.create_index("ix_app_components_parent_order", "app_components", ["parent_id", "component_order"])

    # Unique constraint: component_id unique within page + draft/live
    op.create_index(
        "ix_app_components_unique",
        "app_components",
        ["page_id", "component_id", "is_draft"],
        unique=True,
    )


def downgrade() -> None:
    # Drop app_components table
    op.drop_index("ix_app_components_unique", table_name="app_components")
    op.drop_index("ix_app_components_parent_order", table_name="app_components")
    op.drop_index("ix_app_components_page_draft", table_name="app_components")
    op.drop_index("ix_app_components_page_id", table_name="app_components")
    op.drop_table("app_components")

    # Drop app_pages table
    op.drop_index("ix_app_pages_unique", table_name="app_pages")
    op.drop_index("ix_app_pages_application_draft", table_name="app_pages")
    op.drop_index("ix_app_pages_application_id", table_name="app_pages")
    op.drop_table("app_pages")

    # Restore applications columns
    op.add_column(
        "applications",
        sa.Column("version_history", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "applications",
        sa.Column("draft_definition", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("live_definition", postgresql.JSONB(), nullable=True),
    )

    # Drop new columns
    op.drop_column("applications", "permissions")
    op.drop_column("applications", "global_variables")
    op.drop_column("applications", "global_data_sources")
    op.drop_column("applications", "navigation")
