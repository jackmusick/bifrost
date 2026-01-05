"""
App Builder Component MCP Tools

Tools for managing components within App Builder pages.
"""

import json
import logging
from typing import Any
from uuid import UUID

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="list_components",
    name="List Components",
    description="List components in a page (summaries only - type, parent, order).",
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
                "description": "Page ID (slug, not UUID)",
            },
        },
        "required": ["app_id", "page_id"],
    },
)
async def list_components(
    context: Any,
    app_id: str,
    page_id: str,
) -> str:
    """List components in a page (summaries only - type, parent, order)."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP list_components called with app={app_id}, page={page_id}")

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
            if not (await db.execute(app_query)).scalar_one_or_none():
                return f"Application not found: {app_id}"

            # Get page
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.is_draft == True,  # noqa: E712
            )
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            service = AppComponentsService(db)
            components = await service.list_components(page.id, is_draft=True)

            if not components:
                return f"No components in page '{page_id}'."

            lines = [f"# Components in '{page.title}'\n"]
            lines.append("| Component ID | Type | Parent | Order |")
            lines.append("|--------------|------|--------|-------|")
            for comp in components:
                parent = str(comp.parent_id)[:8] + "..." if comp.parent_id else "root"
                lines.append(f"| {comp.component_id} | {comp.type} | {parent} | {comp.component_order} |")

            lines.append("")
            lines.append(f"*Total: {len(components)} components*")
            lines.append("*Use `get_component` to see full props for a specific component.*")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing components via MCP: {e}")
        return f"Error listing components: {str(e)}"


@system_tool(
    id="get_component",
    name="Get Component",
    description="Get a single component with full props.",
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
                "description": "Page ID (slug, not UUID)",
            },
            "component_id": {
                "type": "string",
                "description": "Component ID (human-readable ID, not UUID)",
            },
        },
        "required": ["app_id", "page_id", "component_id"],
    },
)
async def get_component(
    context: Any,
    app_id: str,
    page_id: str,
    component_id: str,
) -> str:
    """Get a single component with full props."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP get_component called: app={app_id}, page={page_id}, comp={component_id}")

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
            if not (await db.execute(app_query)).scalar_one_or_none():
                return f"Application not found: {app_id}"

            # Get page
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.is_draft == True,  # noqa: E712
            )
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id, is_draft=True)

            if not component:
                return f"Component not found: {component_id}"

            lines = [f"# Component: {component.component_id}\n"]
            lines.append(f"**Type:** {component.type}")
            lines.append(f"**ID (UUID):** {component.id}")
            lines.append(f"**Parent:** {component.parent_id or 'root'}")
            lines.append(f"**Order:** {component.component_order}")

            if component.visible:
                lines.append(f"**Visible:** {component.visible}")
            if component.width:
                lines.append(f"**Width:** {component.width}")
            if component.loading_workflows:
                lines.append(f"**Loading Workflows:** {component.loading_workflows}")

            lines.append("")
            lines.append("## Props")
            lines.append("```json")
            lines.append(json.dumps(component.props, indent=2))
            lines.append("```")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting component via MCP: {e}")
        return f"Error getting component: {str(e)}"


@system_tool(
    id="create_component",
    name="Create Component",
    description="Create a new component in a page.",
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
                "description": "Page ID (slug, not UUID)",
            },
            "component_id": {
                "type": "string",
                "description": "Human-readable component ID (e.g., 'submit-button')",
            },
            "component_type": {
                "type": "string",
                "description": "Component type (e.g., 'Button', 'TextInput', 'DataTable')",
            },
            "props": {
                "type": "object",
                "description": "Component props (varies by type)",
            },
            "parent_id": {
                "type": "string",
                "description": "UUID of parent component (optional, omit for root level)",
            },
            "order": {
                "type": "integer",
                "description": "Order within parent (default: 0)",
            },
        },
        "required": ["app_id", "page_id", "component_id", "component_type"],
    },
)
async def create_component(
    context: Any,
    app_id: str,
    page_id: str,
    component_id: str,
    component_type: str,
    props: dict[str, Any] | None = None,
    parent_id: str | None = None,
    order: int = 0,
) -> str:
    """Create a new component in a page."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentCreate
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP create_component: app={app_id}, page={page_id}, comp={component_id}")

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
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            # Parse parent UUID if provided
            parent_uuid = None
            if parent_id:
                try:
                    parent_uuid = UUID(parent_id)
                except ValueError:
                    return f"Error: Invalid parent_id format: {parent_id}"

            service = AppComponentsService(db)

            # Check for duplicate
            existing = await service.get_component(page.id, component_id, is_draft=True)
            if existing:
                return f"Error: Component '{component_id}' already exists"

            try:
                data = AppComponentCreate(
                    component_id=component_id,
                    type=component_type,
                    props=props or {},
                    parent_id=parent_uuid,
                    component_order=order,
                )
                component = await service.create_component(page.id, is_draft=True, data=data)
            except ValueError as e:
                return f"Error: {str(e)}"

            page.version += 1
            app.draft_version += 1
            await db.commit()

            return (
                f"Component '{component_id}' created!\n\n"
                f"**Type:** {component_type}\n"
                f"**ID (UUID):** {component.id}\n"
                f"**Page Version:** {page.version}"
            )

    except Exception as e:
        logger.exception(f"Error creating component via MCP: {e}")
        return f"Error creating component: {str(e)}"


@system_tool(
    id="update_component",
    name="Update Component",
    description="Update a component's props or settings.",
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
                "description": "Page ID (slug, not UUID)",
            },
            "component_id": {
                "type": "string",
                "description": "Component ID (human-readable ID, not UUID)",
            },
            "props": {
                "type": "object",
                "description": "New props to set (replaces existing props)",
            },
            "component_type": {
                "type": "string",
                "description": "New component type (optional)",
            },
            "visible": {
                "type": "string",
                "description": "Visibility expression (e.g., '{{data.showField}}')",
            },
            "width": {
                "type": "string",
                "description": "Width setting (e.g., '50%', '200px')",
            },
        },
        "required": ["app_id", "page_id", "component_id"],
    },
)
async def update_component(
    context: Any,
    app_id: str,
    page_id: str,
    component_id: str,
    props: dict[str, Any] | None = None,
    component_type: str | None = None,
    visible: str | None = None,
    width: str | None = None,
) -> str:
    """Update a component's props or settings."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentUpdate
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP update_component: app={app_id}, page={page_id}, comp={component_id}")

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
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id, is_draft=True)

            if not component:
                return f"Component not found: {component_id}"

            updates_made = []

            data = AppComponentUpdate()
            if props is not None:
                data.props = props
                updates_made.append("props")
            if component_type is not None:
                data.type = component_type
                updates_made.append("type")
            if visible is not None:
                data.visible = visible
                updates_made.append("visible")
            if width is not None:
                data.width = width
                updates_made.append("width")

            if not updates_made:
                return "No updates specified"

            await service.update_component(component, data)

            page.version += 1
            app.draft_version += 1
            await db.commit()

            return (
                f"Component '{component_id}' updated!\n\n"
                f"**Updates:** {', '.join(updates_made)}\n"
                f"**Page Version:** {page.version}"
            )

    except Exception as e:
        logger.exception(f"Error updating component via MCP: {e}")
        return f"Error updating component: {str(e)}"


@system_tool(
    id="delete_component",
    name="Delete Component",
    description="Delete a component and all its children.",
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
                "description": "Page ID (slug, not UUID)",
            },
            "component_id": {
                "type": "string",
                "description": "Component ID (human-readable ID, not UUID)",
            },
        },
        "required": ["app_id", "page_id", "component_id"],
    },
)
async def delete_component(
    context: Any,
    app_id: str,
    page_id: str,
    component_id: str,
) -> str:
    """Delete a component and all its children."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP delete_component: app={app_id}, page={page_id}, comp={component_id}")

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
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id, is_draft=True)

            if not component:
                return f"Component not found: {component_id}"

            await service.delete_component(component)

            page.version += 1
            app.draft_version += 1
            await db.commit()

            return (
                f"Component '{component_id}' deleted!\n\n"
                f"**Page Version:** {page.version}"
            )

    except Exception as e:
        logger.exception(f"Error deleting component via MCP: {e}")
        return f"Error deleting component: {str(e)}"


@system_tool(
    id="move_component",
    name="Move Component",
    description="Move a component to a new parent and/or position.",
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
                "description": "Page ID (slug, not UUID)",
            },
            "component_id": {
                "type": "string",
                "description": "Component ID (human-readable ID, not UUID)",
            },
            "new_parent_id": {
                "type": "string",
                "description": "UUID of new parent component (null/empty for root level)",
            },
            "new_order": {
                "type": "integer",
                "description": "New order within parent",
            },
        },
        "required": ["app_id", "page_id", "component_id", "new_order"],
    },
)
async def move_component(
    context: Any,
    app_id: str,
    page_id: str,
    component_id: str,
    new_parent_id: str | None,
    new_order: int,
) -> str:
    """Move a component to a new parent and/or position."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentMove
    from src.models.orm.applications import AppPage, Application
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP move_component: app={app_id}, page={page_id}, comp={component_id}")

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
            page = (await db.execute(page_query)).scalar_one_or_none()
            if not page:
                return f"Page not found: {page_id}"

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id, is_draft=True)

            if not component:
                return f"Component not found: {component_id}"

            # Parse new parent UUID
            parent_uuid = None
            if new_parent_id:
                try:
                    parent_uuid = UUID(new_parent_id)
                except ValueError:
                    return f"Error: Invalid new_parent_id format: {new_parent_id}"

            try:
                data = AppComponentMove(new_parent_id=parent_uuid, new_order=new_order)
                await service.move_component(component, data)
            except ValueError as e:
                return f"Error: {str(e)}"

            page.version += 1
            app.draft_version += 1
            await db.commit()

            return (
                f"Component '{component_id}' moved!\n\n"
                f"**New Parent:** {new_parent_id or 'root'}\n"
                f"**New Order:** {new_order}\n"
                f"**Page Version:** {page.version}"
            )

    except Exception as e:
        logger.exception(f"Error moving component via MCP: {e}")
        return f"Error moving component: {str(e)}"
