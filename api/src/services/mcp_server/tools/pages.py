"""
App Builder Page MCP Tools

Tools for managing pages in App Builder applications.
"""

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from src.core.pubsub import publish_app_draft_update
from src.models.contracts.app_components import AppComponent as AppComponentModel
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="get_page",
    name="Get Page",
    description="Get a page with its full component tree. This is where the real token savings happen - only fetch the page you need.",
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
                "description": "Page ID (e.g., 'home', 'settings')",
            },
            "version_id": {
                "type": "string",
                "description": "Version UUID to get pages from. Defaults to draft version if not specified.",
            },
        },
        "required": ["app_id", "page_id"],
    },
)
async def get_page(
    context: Any,
    app_id: str,
    page_id: str,
    version_id: str | None = None,
) -> str:
    """
    Get a page with its full component tree.

    Uses version_id to fetch a specific version, or defaults to draft version.
    This is where the real token savings happen - only fetch the page you need.
    """
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP get_page called with app={app_id}, page={page_id}, version_id={version_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    # Parse version_id if provided
    version_uuid: UUID | None = None
    if version_id:
        try:
            version_uuid = UUID(version_id)
        except ValueError:
            return json.dumps({"error": f"Invalid version_id format: {version_id}"})

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
            app = app_result.scalar_one_or_none()
            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            # Use provided version_id or default to draft version
            effective_version_id = version_uuid or app.draft_version_id
            if not effective_version_id:
                return json.dumps({"error": "Application has no draft version"})

            # Get page
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.version_id == effective_version_id,
            )
            page_result = await db.execute(page_query)
            page = page_result.scalar_one_or_none()

            if not page:
                return json.dumps({"error": f"Page not found: {page_id}"})

            # Get components as unified AppComponent tree
            service = AppBuilderService(db)
            children = await service.get_page_children(page)

            # Serialize children to JSON-compatible dicts
            children_json = [
                child.model_dump(exclude_none=True, by_alias=True)
                for child in children
            ]

            # Build structured response
            result = {
                "page_id": page.page_id,
                "title": page.title,
                "path": page.path,
                "version_id": str(page.version_id) if page.version_id else None,
                "variables": page.variables or {},
                "launch_workflow_id": str(page.launch_workflow_id) if page.launch_workflow_id else None,
                "launch_workflow_params": page.launch_workflow_params,
                "launch_workflow_data_source_id": page.launch_workflow_data_source_id,
                "children": children_json,
            }

            return json.dumps(result)

    except Exception as e:
        logger.exception(f"Error getting page via MCP: {e}")
        return json.dumps({"error": f"Error getting page: {str(e)}"})


@system_tool(
    id="create_page",
    name="Create Page",
    description="Create a new page in an application with optional children components.",
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
            "children": {
                "type": "array",
                "description": "List of child components for the page",
            },
            "variables": {
                "type": "object",
                "description": "Optional page variables",
            },
            "launch_workflow_id": {
                "type": "string",
                "description": "Workflow ID to run on page load. Data becomes available via {{ workflow.<data_source_id>.result }}",
            },
            "launch_workflow_data_source_id": {
                "type": "string",
                "description": "Key name for accessing launch workflow results (defaults to workflow function name). Access via {{ workflow.<this_value>.result }}",
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
    children: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    launch_workflow_id: str | None = None,
    launch_workflow_data_source_id: str | None = None,
) -> str:
    """Create a new page with optional children components."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP create_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            # Ensure app has a draft version
            if not app.draft_version_id:
                return json.dumps({"error": "Application has no draft version. Please recreate the app."})

            # Check for duplicate page in draft version
            existing_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.version_id == app.draft_version_id,
            )
            existing = await db.execute(existing_query)
            if existing.scalar_one_or_none():
                return json.dumps({"error": f"Page '{page_id}' already exists"})

            # Validate children through discriminated union
            validated_children: list[AppComponentModel] = []
            if children:
                try:
                    adapter = TypeAdapter(list[AppComponentModel])
                    validated_children = adapter.validate_python(children)
                except ValidationError as e:
                    return json.dumps({"error": f"Invalid children: {e}"})

            # Parse workflow ID
            wf_id = None
            if launch_workflow_id:
                try:
                    wf_id = UUID(launch_workflow_id)
                except ValueError:
                    return json.dumps({"error": f"Invalid launch_workflow_id format: {launch_workflow_id}"})

            service = AppBuilderService(db)
            new_page = await service.create_page_with_children(
                application_id=app_uuid,
                page_id=page_id,
                title=title,
                path=path,
                children=validated_children,
                version_id=app.draft_version_id,
                variables=variables or {},
                launch_workflow_id=wf_id,
                launch_workflow_data_source_id=launch_workflow_data_source_id,
            )

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="page",
                entity_id=page_id,
            )

            return json.dumps({
                "success": True,
                "page_id": new_page.page_id,
                "title": title,
                "path": new_page.path,
                "version_id": str(app.draft_version_id),
            })

    except Exception as e:
        logger.exception(f"Error creating page via MCP: {e}")
        return json.dumps({"error": f"Error creating page: {str(e)}"})


@system_tool(
    id="update_page",
    name="Update Page",
    description="Update a page's metadata or replace its children components.",
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
            "children": {
                "type": "array",
                "description": "New child components (replaces entire component tree)",
            },
            "variables": {
                "type": "object",
                "description": "New page variables",
            },
            "launch_workflow_id": {
                "type": "string",
                "description": "Workflow ID to run on page load (empty string to clear)",
            },
            "launch_workflow_data_source_id": {
                "type": "string",
                "description": "Key name for accessing launch workflow results. Access via {{ workflow.<this_value>.result }}",
            },
            "launch_workflow_params": {
                "type": "object",
                "description": "Parameters to pass to the launch workflow. Use {{ params.id }} for route parameters.",
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
    children: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    launch_workflow_id: str | None = None,
    launch_workflow_data_source_id: str | None = None,
    launch_workflow_params: dict[str, Any] | None = None,
) -> str:
    """Update a page's metadata or replace its children components."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP update_page called with app={app_id}, page={page_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            # Ensure app has a draft version
            if not app.draft_version_id:
                return json.dumps({"error": "Application has no draft version"})

            # Get page from draft version
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.version_id == app.draft_version_id,
            )
            page_result = await db.execute(page_query)
            page = page_result.scalar_one_or_none()
            if not page:
                return json.dumps({"error": f"Page not found: {page_id}"})

            updates_made = []

            if title is not None:
                page.title = title
                updates_made.append("title")

            if path is not None:
                page.path = path
                updates_made.append("path")

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
                        return json.dumps({"error": f"Invalid launch_workflow_id: {launch_workflow_id}"})
                updates_made.append("launch_workflow_id")

            if launch_workflow_data_source_id is not None:
                page.launch_workflow_data_source_id = launch_workflow_data_source_id if launch_workflow_data_source_id else None
                updates_made.append("launch_workflow_data_source_id")

            if launch_workflow_params is not None:
                page.launch_workflow_params = launch_workflow_params
                updates_made.append("launch_workflow_params")

            # Replace children if provided (this is the heavy operation)
            if children is not None:
                # Validate children through discriminated union
                try:
                    adapter = TypeAdapter(list[AppComponentModel])
                    validated_children = adapter.validate_python(children)
                except ValidationError as e:
                    return json.dumps({"error": f"Invalid children: {e}"})

                service = AppBuilderService(db)
                await service.update_page_children(page, validated_children)
                updates_made.append("children")

            if not updates_made:
                return json.dumps({"error": "No updates specified"})

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="page",
                entity_id=page_id,
            )

            return json.dumps({
                "success": True,
                "page_id": page.page_id,
                "title": page.title,
                "updates": updates_made,
                "version_id": str(app.draft_version_id),
            })

    except Exception as e:
        logger.exception(f"Error updating page via MCP: {e}")
        return json.dumps({"error": f"Error updating page: {str(e)}"})


@system_tool(
    id="delete_page",
    name="Delete Page",
    description="Delete a page and all its components from an application.",
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
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            # Verify app access
            app_query = select(Application).where(Application.id == app_uuid)
            if not context.is_platform_admin and context.org_id:
                app_query = app_query.where(Application.organization_id == context.org_id)
            app_result = await db.execute(app_query)
            app = app_result.scalar_one_or_none()
            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            # Ensure app has a draft version
            if not app.draft_version_id:
                return json.dumps({"error": "Application has no draft version"})

            # Get page from draft version
            page_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.page_id == page_id,
                AppPage.version_id == app.draft_version_id,
            )
            page_result = await db.execute(page_query)
            page = page_result.scalar_one_or_none()
            if not page:
                return json.dumps({"error": f"Page not found: {page_id}"})

            title = page.title
            await db.delete(page)
            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="page",
                entity_id=page_id,
            )

            return json.dumps({
                "success": True,
                "page_id": page_id,
                "title": title,
            })

    except Exception as e:
        logger.exception(f"Error deleting page via MCP: {e}")
        return json.dumps({"error": f"Error deleting page: {str(e)}"})
