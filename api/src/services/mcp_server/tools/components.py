"""
App Builder Component MCP Tools

Tools for managing components within App Builder pages.
"""

import json
import logging
from typing import Any
from uuid import UUID

from src.core.pubsub import publish_app_draft_update
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


async def _get_draft_page(db: Any, context: Any, app_uuid: UUID, page_id: str) -> tuple[Any, Any, str | None]:
    """
    Helper to get app and draft page.

    Returns (app, page, error_message). If error_message is set, app/page may be None.
    """
    from sqlalchemy import select
    from src.models.orm.applications import AppPage, Application

    # Verify app access
    app_query = select(Application).where(Application.id == app_uuid)
    if not context.is_platform_admin and context.org_id:
        app_query = app_query.where(
            (Application.organization_id == context.org_id) |
            (Application.organization_id.is_(None))
        )
    app = (await db.execute(app_query)).scalar_one_or_none()
    if not app:
        return None, None, f"Application not found: {app_uuid}"

    # Ensure app has a draft version
    if not app.draft_version_id:
        return app, None, "Application has no draft version"

    # Get page from draft version
    page_query = select(AppPage).where(
        AppPage.application_id == app_uuid,
        AppPage.page_id == page_id,
        AppPage.version_id == app.draft_version_id,
    )
    page = (await db.execute(page_query)).scalar_one_or_none()
    if not page:
        return app, None, f"Page not found: {page_id}"

    return app, page, None


@system_tool(
    id="list_components",
    name="List Components",
    description="List components in a page (summaries only - type, parent, order).",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    from src.core.database import get_db_context
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP list_components called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            service = AppComponentsService(db)
            components = await service.list_components(page.id)

            component_list = [
                {
                    "component_id": comp.component_id,
                    "type": comp.type,
                    "parent_id": str(comp.parent_id) if comp.parent_id else None,
                    "order": comp.component_order,
                }
                for comp in components
            ]

            return json.dumps({
                "components": component_list,
                "count": len(component_list),
                "page_title": page.title,
            })

    except Exception as e:
        logger.exception(f"Error listing components via MCP: {e}")
        return json.dumps({"error": f"Error listing components: {str(e)}"})


@system_tool(
    id="get_component",
    name="Get Component",
    description="Get a single component with full props.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    from src.core.database import get_db_context
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP get_component called: app={app_id}, page={page_id}, comp={component_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id)

            if not component:
                return json.dumps({"error": f"Component not found: {component_id}"})

            result = {
                "component_id": component.component_id,
                "type": component.type,
                "id": str(component.id),
                "parent_id": str(component.parent_id) if component.parent_id else None,
                "order": component.component_order,
                "props": component.props,
            }

            if component.visible:
                result["visible"] = component.visible
            if component.width:
                result["width"] = component.width
            if component.loading_workflows:
                result["loading_workflows"] = component.loading_workflows

            return json.dumps(result)

    except Exception as e:
        logger.exception(f"Error getting component via MCP: {e}")
        return json.dumps({"error": f"Error getting component: {str(e)}"})


@system_tool(
    id="create_component",
    name="Create Component",
    description="Create a new component in a page.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
                "description": "UUID of parent component from create_component response (NOT the component_id you provided). Omit for root level.",
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
    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentCreate
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP create_component: app={app_id}, page={page_id}, comp={component_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            # Parse parent UUID if provided
            parent_uuid = None
            if parent_id:
                try:
                    parent_uuid = UUID(parent_id)
                except ValueError:
                    return json.dumps({"error": f"Invalid parent_id format: {parent_id}"})

            service = AppComponentsService(db)

            # Check for duplicate
            existing = await service.get_component(page.id, component_id)
            if existing:
                return json.dumps({"error": f"Component '{component_id}' already exists"})

            try:
                # Validate props through the discriminated union (AppComponent)
                # This routes to the correct component model based on 'type' field
                from pydantic import ValidationError
                from src.models.contracts.app_components import AppComponent

                component_data = {
                    "id": component_id,
                    "type": component_type,
                    "props": props or {},
                }
                try:
                    validated_component = AppComponent.model_validate(component_data)
                    validated_props = validated_component.props.model_dump(exclude_none=True)
                except ValidationError as e:
                    return json.dumps({
                        "error": f"Invalid component props for type '{component_type}': {e}"
                    })

                data = AppComponentCreate(
                    component_id=component_id,
                    type=component_type,
                    props=validated_props,
                    parent_id=parent_uuid,
                    component_order=order,
                )
                component = await service.create_component(page.id, data)
            except ValueError as e:
                return json.dumps({"error": str(e)})

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="component",
                entity_id=component_id,
                page_id=page_id,
            )

            return json.dumps({
                "success": True,
                "component_id": component_id,
                "type": component_type,
                "id": str(component.id),
            })

    except Exception as e:
        logger.exception(f"Error creating component via MCP: {e}")
        return json.dumps({"error": f"Error creating component: {str(e)}"})


@system_tool(
    id="update_component",
    name="Update Component",
    description="Update a component's props or settings.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentUpdate
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP update_component: app={app_id}, page={page_id}, comp={component_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id)

            if not component:
                return json.dumps({"error": f"Component not found: {component_id}"})

            updates_made = []

            data = AppComponentUpdate()

            # If props are being updated, validate through the component model
            if props is not None:
                from pydantic import ValidationError
                from src.models.contracts.app_components import AppComponent

                # Use new type if provided, otherwise use existing component type
                effective_type = component_type if component_type is not None else component.type

                component_data = {
                    "id": component_id,
                    "type": effective_type,
                    "props": props,
                }
                try:
                    validated_component = AppComponent.model_validate(component_data)
                    data.props = validated_component.props.model_dump(exclude_none=True)
                    updates_made.append("props")
                except ValidationError as e:
                    return json.dumps({
                        "error": f"Invalid component props for type '{effective_type}': {e}"
                    })

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
                return json.dumps({"error": "No updates specified"})

            await service.update_component(component, data)
            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="component",
                entity_id=component_id,
                page_id=page_id,
            )

            return json.dumps({
                "success": True,
                "component_id": component_id,
                "updates": updates_made,
            })

    except Exception as e:
        logger.exception(f"Error updating component via MCP: {e}")
        return json.dumps({"error": f"Error updating component: {str(e)}"})


@system_tool(
    id="delete_component",
    name="Delete Component",
    description="Delete a component and all its children.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    from src.core.database import get_db_context
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP delete_component: app={app_id}, page={page_id}, comp={component_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id)

            if not component:
                return json.dumps({"error": f"Component not found: {component_id}"})

            await service.delete_component(component)
            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="component",
                entity_id=component_id,
                page_id=page_id,
            )

            return json.dumps({
                "success": True,
                "component_id": component_id,
            })

    except Exception as e:
        logger.exception(f"Error deleting component via MCP: {e}")
        return json.dumps({"error": f"Error deleting component: {str(e)}"})


@system_tool(
    id="move_component",
    name="Move Component",
    description="Move a component to a new parent and/or position.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
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
    from src.core.database import get_db_context
    from src.models.contracts.applications import AppComponentMove
    from src.services.app_components_service import AppComponentsService

    logger.info(f"MCP move_component: app={app_id}, page={page_id}, comp={component_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            app, page, error = await _get_draft_page(db, context, app_uuid, page_id)
            if error:
                return json.dumps({"error": error})

            service = AppComponentsService(db)
            component = await service.get_component(page.id, component_id)

            if not component:
                return json.dumps({"error": f"Component not found: {component_id}"})

            # Parse new parent UUID
            parent_uuid = None
            if new_parent_id:
                try:
                    parent_uuid = UUID(new_parent_id)
                except ValueError:
                    return json.dumps({"error": f"Invalid new_parent_id format: {new_parent_id}"})

            try:
                data = AppComponentMove(new_parent_id=parent_uuid, new_order=new_order)
                await service.move_component(component, data)
            except ValueError as e:
                return json.dumps({"error": str(e)})

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="component",
                entity_id=component_id,
                page_id=page_id,
            )

            return json.dumps({
                "success": True,
                "component_id": component_id,
                "new_parent_id": new_parent_id,
                "new_order": new_order,
            })

    except Exception as e:
        logger.exception(f"Error moving component via MCP: {e}")
        return json.dumps({"error": f"Error moving component: {str(e)}"})
