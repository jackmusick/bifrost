"""
App Builder Page MCP Tools

Tools for managing pages in App Builder applications.
"""

import json
import logging
from typing import Any
from uuid import UUID

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="get_page",
    name="Get Page",
    description="Get a page with its full component tree. This is where the real token savings happen - only fetch the page you need.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "UUID of the application",
            },
            "page_id": {
                "type": "string",
                "description": "Page ID (e.g., 'home', 'settings')",
            },
            "is_draft": {
                "type": "boolean",
                "description": "Whether to get the draft version (default: True)",
            },
        },
        "required": ["app_id", "page_id"],
    },
)
async def get_page(
    context: Any,
    app_id: str,
    page_id: str,
    is_draft: bool = True,
) -> str:
    """
    Get a page with its full component tree.

    This is where the real token savings happen - only fetch the page you need.
    """
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.app_builder_service import AppBuilderService, tree_to_layout_json

    logger.info(f"MCP get_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(
                    (Application.organization_id == context.org_id) |
                    (Application.organization_id.is_(None))
                )
            app_result = await db.execute(app_query)
            if not app_result.scalar_one_or_none():
                return f"Application not found: {app_id}"

            # Get page with components
            service = AppBuilderService(db)
            page, tree = await service.get_page_with_components(app_uuid, page_id, is_draft)

            if not page:
                return f"Page not found: {page_id}"

            lines = [f"# Page: {page.title}\n"]
            lines.append(f"**Page ID:** {page.page_id}")
            lines.append(f"**Path:** {page.path}")
            lines.append(f"**Version:** {page.version}")
            lines.append(f"**Mode:** {'Draft' if is_draft else 'Live'}")
            lines.append("")

            if page.data_sources:
                lines.append("## Data Sources")
                lines.append("```json")
                lines.append(json.dumps(page.data_sources, indent=2))
                lines.append("```")
                lines.append("")

            if page.variables:
                lines.append("## Variables")
                lines.append("```json")
                lines.append(json.dumps(page.variables, indent=2))
                lines.append("```")
                lines.append("")

            if page.launch_workflow_id:
                lines.append(f"**Launch Workflow:** {page.launch_workflow_id}")
                if page.launch_workflow_params:
                    lines.append("**Launch Params:**")
                    lines.append("```json")
                    lines.append(json.dumps(page.launch_workflow_params, indent=2))
                    lines.append("```")
                lines.append("")

            # Show component tree as JSON layout
            if tree:
                layout = tree_to_layout_json(tree)
                lines.append("## Layout")
                lines.append("```json")
                lines.append(json.dumps(layout, indent=2))
                lines.append("```")
            else:
                lines.append("*No components defined yet.*")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting page via MCP: {e}")
        return f"Error getting page: {str(e)}"


@system_tool(
    id="create_page",
    name="Create Page",
    description="Create a new page in an application with optional layout.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "UUID of the application",
            },
            "page_id": {
                "type": "string",
                "description": "Unique page identifier (e.g., 'settings', 'dashboard')",
            },
            "title": {
                "type": "string",
                "description": "Display title for the page",
            },
            "path": {
                "type": "string",
                "description": "URL path for the page (e.g., '/settings')",
            },
            "layout": {
                "type": "object",
                "description": "Optional layout structure with components",
            },
            "data_sources": {
                "type": "array",
                "description": "Optional data sources for the page",
            },
            "variables": {
                "type": "object",
                "description": "Optional page variables",
            },
            "launch_workflow_id": {
                "type": "string",
                "description": "Optional workflow ID to run on page load",
            },
        },
        "required": ["app_id", "page_id", "title", "path"],
    },
)
async def create_page(
    context: Any,
    app_id: str,
    page_id: str,
    title: str,
    path: str,
    layout: dict[str, Any] | None = None,
    data_sources: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    launch_workflow_id: str | None = None,
) -> str:
    """Create a new page with optional layout."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP create_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return f"Application not found: {app_id}"

            # Check for duplicate
            existing_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.is_draft == True,  # noqa: E712
            )
            existing = await db.execute(existing_query)
            if existing.scalar_one_or_none():
                return f"Error: Page '{page_id}' already exists"

            # Build layout
            if layout is None:
                layout = {"type": "column", "children": []}

            # Parse workflow ID
            wf_id = None
            if launch_workflow_id:
                try:
                    wf_id = UUID(launch_workflow_id)
                except ValueError:
                    return f"Error: Invalid launch_workflow_id format: {launch_workflow_id}"

            service = AppBuilderService(db)
            new_page = await service.create_page_with_layout(
                application_id=app_uuid,
                page_id=page_id,
                title=title,
                path=path,
                layout=layout,
                is_draft=True,
                data_sources=data_sources or [],
                variables=variables or {},
                launch_workflow_id=wf_id,
            )

            app.draft_version += 1
            await db.commit()

            return (
                f"Page '{title}' created!\n\n"
                f"**Page ID:** {new_page.page_id}\n"
                f"**Path:** {new_page.path}\n"
                f"**App Draft Version:** v{app.draft_version}"
            )

    except Exception as e:
        logger.exception(f"Error creating page via MCP: {e}")
        return f"Error creating page: {str(e)}"


@system_tool(
    id="update_page",
    name="Update Page",
    description="Update a page's metadata or replace its layout.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "UUID of the application",
            },
            "page_id": {
                "type": "string",
                "description": "Page ID to update",
            },
            "title": {
                "type": "string",
                "description": "New title for the page",
            },
            "path": {
                "type": "string",
                "description": "New URL path for the page",
            },
            "layout": {
                "type": "object",
                "description": "New layout structure (replaces entire layout)",
            },
            "data_sources": {
                "type": "array",
                "description": "New data sources for the page",
            },
            "variables": {
                "type": "object",
                "description": "New page variables",
            },
            "launch_workflow_id": {
                "type": "string",
                "description": "Workflow ID to run on page load (empty string to clear)",
            },
        },
        "required": ["app_id", "page_id"],
    },
)
async def update_page(
    context: Any,
    app_id: str,
    page_id: str,
    title: str | None = None,
    path: str | None = None,
    layout: dict[str, Any] | None = None,
    data_sources: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    launch_workflow_id: str | None = None,
) -> str:
    """Update a page's metadata or replace its layout."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP update_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return f"Application not found: {app_id}"

            # Get page
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.is_draft == True,  # noqa: E712
            )
            page_result = await db.execute(page_query)
            page = page_result.scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            updates_made = []

            if title is not None:
                page.title = title
                updates_made.append("title")

            if path is not None:
                page.path = path
                updates_made.append("path")

            if data_sources is not None:
                page.data_sources = data_sources
                updates_made.append("data_sources")

            if variables is not None:
                page.variables = variables
                updates_made.append("variables")

            if launch_workflow_id is not None:
                if launch_workflow_id == "":
                    page.launch_workflow_id = None
                else:
                    try:
                        page.launch_workflow_id = UUID(launch_workflow_id)
                    except ValueError:
                        return f"Error: Invalid launch_workflow_id: {launch_workflow_id}"
                updates_made.append("launch_workflow_id")

            # Replace layout if provided (this is the heavy operation)
            if layout is not None:
                service = AppBuilderService(db)
                await service.update_page_layout(page, layout)
                updates_made.append("layout")

            if not updates_made:
                return "No updates specified"

            page.version += 1
            app.draft_version += 1
            await db.commit()

            return (
                f"Page '{page.title}' updated!\n\n"
                f"**Updates:** {', '.join(updates_made)}\n"
                f"**Page Version:** {page.version}\n"
                f"**App Draft Version:** v{app.draft_version}"
            )

    except Exception as e:
        logger.exception(f"Error updating page via MCP: {e}")
        return f"Error updating page: {str(e)}"


@system_tool(
    id="delete_page",
    name="Delete Page",
    description="Delete a page and all its components from an application.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "UUID of the application",
            },
            "page_id": {
                "type": "string",
                "description": "Page ID to delete",
            },
        },
        "required": ["app_id", "page_id"],
    },
)
async def delete_page(context: Any, app_id: str, page_id: str) -> str:
    """Delete a page and all its components."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application

    logger.info(f"MCP delete_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return f"Application not found: {app_id}"

            # Get page
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.is_draft == True,  # noqa: E712
            )
            page_result = await db.execute(page_query)
            page = page_result.scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            title = page.title
            await db.delete(page)
            app.draft_version += 1
            await db.commit()

            return f"Page '{title}' deleted!\n\n**App Draft Version:** v{app.draft_version}"

    except Exception as e:
        logger.exception(f"Error deleting page via MCP: {e}")
        return f"Error deleting page: {str(e)}"
