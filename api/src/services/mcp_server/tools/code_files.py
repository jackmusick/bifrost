"""
App Builder MCP Tools - Code Files

Tools for managing code files in code engine applications.
Supports listing, creating, reading, updating, and deleting TSX/module files.
"""

import json
import logging
from typing import Any
from uuid import UUID

from src.core.pubsub import publish_app_code_file_update
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


def _validate_file_path(path: str) -> str | None:
    """Validate file path against conventions. Returns error message or None."""
    import re

    ROOT_ALLOWED_FILES = {"_layout", "_providers"}
    VALID_TOP_DIRS = {"pages", "components", "modules"}
    DYNAMIC_SEGMENT_PATTERN = re.compile(r"^\[[\w-]+\]$")
    VALID_NAME_PATTERN = re.compile(r"^[\w-]+$")

    if not path:
        return "File path cannot be empty"

    path = path.strip("/")
    segments = path.split("/")

    if any(not seg for seg in segments):
        return "Path cannot contain empty segments (double slashes)"

    if len(segments) == 1:
        if segments[0] not in ROOT_ALLOWED_FILES:
            return f"Root-level file must be one of: {', '.join(sorted(ROOT_ALLOWED_FILES))}"
        return None

    top_dir = segments[0]
    if top_dir not in VALID_TOP_DIRS:
        return f"Files must be in one of: {', '.join(sorted(VALID_TOP_DIRS))}"

    for segment in segments[1:]:
        if DYNAMIC_SEGMENT_PATTERN.match(segment):
            if top_dir != "pages":
                return f"Dynamic segments like [{segment[1:-1]}] are only allowed in pages/"
            continue

        if not VALID_NAME_PATTERN.match(segment):
            return f"Invalid path segment '{segment}'. Use only alphanumeric characters, underscores, and hyphens."

        if segment == "_layout" and top_dir != "pages":
            return "_layout files are only allowed in pages/"

    return None


@system_tool(
    id="code_list_files",
    name="List Code Files",
    description="List all code files for a code engine application's draft version.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "Application UUID",
            },
        },
        "required": ["app_id"],
    },
)
async def code_list_files(context: Any, app_id: str) -> str:
    """List all code files for an app's draft version."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppCodeFile, Application

    logger.info(f"MCP code_list_files called for app {app_id}")

    try:
        async with get_db_context() as db:
            # Get app and verify access
            app = await db.get(Application, UUID(app_id))
            if not app:
                return json.dumps({"error": f"Application {app_id} not found"})

            # Check access
            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return json.dumps({"error": "Access denied"})

            if not app.draft_version_id:
                return json.dumps({"error": "No draft version found"})

            # List files
            query = (
                select(AppCodeFile)
                .where(AppCodeFile.app_version_id == app.draft_version_id)
                .order_by(AppCodeFile.path)
            )
            result = await db.execute(query)
            files = result.scalars().all()

            files_data = [
                {
                    "id": str(f.id),
                    "path": f.path,
                    "has_source": bool(f.source),
                    "has_compiled": bool(f.compiled),
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                }
                for f in files
            ]

            return json.dumps({
                "files": files_data,
                "count": len(files_data),
                "app_id": app_id,
                "version_id": str(app.draft_version_id),
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error listing code files via MCP: {e}")
        return json.dumps({"error": f"Error listing code files: {str(e)}"})


@system_tool(
    id="code_get_file",
    name="Get Code File",
    description="Get a specific code file's content by path from an app's draft version.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "Application UUID",
            },
            "path": {
                "type": "string",
                "description": "File path (e.g., 'pages/index', 'components/Button')",
            },
        },
        "required": ["app_id", "path"],
    },
)
async def code_get_file(context: Any, app_id: str, path: str) -> str:
    """Get a code file's content."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppCodeFile, Application

    logger.info(f"MCP code_get_file called for app {app_id}, path {path}")

    try:
        async with get_db_context() as db:
            # Get app and verify access
            app = await db.get(Application, UUID(app_id))
            if not app:
                return json.dumps({"error": f"Application {app_id} not found"})

            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return json.dumps({"error": "Access denied"})

            if not app.draft_version_id:
                return json.dumps({"error": "No draft version found"})

            # Get file
            query = select(AppCodeFile).where(
                AppCodeFile.app_version_id == app.draft_version_id,
                AppCodeFile.path == path.strip("/"),
            )
            result = await db.execute(query)
            file = result.scalar_one_or_none()

            if not file:
                return json.dumps({"error": f"File '{path}' not found"})

            return json.dumps({
                "id": str(file.id),
                "path": file.path,
                "source": file.source,
                "compiled": file.compiled,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "updated_at": file.updated_at.isoformat() if file.updated_at else None,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error getting code file via MCP: {e}")
        return json.dumps({"error": f"Error getting code file: {str(e)}"})


@system_tool(
    id="code_create_file",
    name="Create Code File",
    description="Create a new code file in an app's draft version. Path conventions: root allows only _layout/_providers; use pages/, components/, or modules/ for other files.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "Application UUID",
            },
            "path": {
                "type": "string",
                "description": "File path (e.g., 'pages/clients', 'components/Button')",
            },
            "source": {
                "type": "string",
                "description": "TSX/TypeScript source code",
            },
        },
        "required": ["app_id", "path", "source"],
    },
)
async def code_create_file(context: Any, app_id: str, path: str, source: str) -> str:
    """Create a new code file."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppCodeFile, Application

    logger.info(f"MCP code_create_file called for app {app_id}, path {path}")

    # Validate path
    path = path.strip("/")
    validation_error = _validate_file_path(path)
    if validation_error:
        return json.dumps({"error": validation_error})

    try:
        async with get_db_context() as db:
            # Get app and verify access
            app = await db.get(Application, UUID(app_id))
            if not app:
                return json.dumps({"error": f"Application {app_id} not found"})

            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return json.dumps({"error": "Access denied"})

            if not app.draft_version_id:
                return json.dumps({"error": "No draft version found"})

            # Check engine type
            if app.engine != "code":
                return json.dumps({"error": f"App engine is '{app.engine}', not 'code'. Code files only work with code engine apps."})

            # Check for duplicate
            existing_query = select(AppCodeFile).where(
                AppCodeFile.app_version_id == app.draft_version_id,
                AppCodeFile.path == path,
            )
            existing = await db.execute(existing_query)
            if existing.scalar_one_or_none():
                return json.dumps({"error": f"File with path '{path}' already exists"})

            # Create file
            file = AppCodeFile(
                app_version_id=app.draft_version_id,
                path=path,
                source=source,
            )
            db.add(file)
            await db.flush()
            await db.refresh(file)

            # Publish update with full content for real-time preview
            await publish_app_code_file_update(
                app_id=app_id,
                user_id=str(context.user_id) if context.user_id else "mcp",
                user_name=context.user_name or "MCP Tool",
                path=path,
                source=source,
                compiled=None,
                action="create",
            )

            await db.commit()

            logger.info(f"Created code file '{path}' in app {app_id}")
            return json.dumps({
                "success": True,
                "id": str(file.id),
                "path": file.path,
                "created_at": file.created_at.isoformat() if file.created_at else None,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error creating code file via MCP: {e}")
        return json.dumps({"error": f"Error creating code file: {str(e)}"})


@system_tool(
    id="code_update_file",
    name="Update Code File",
    description="Update a code file's source code in an app's draft version.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "Application UUID",
            },
            "path": {
                "type": "string",
                "description": "File path",
            },
            "source": {
                "type": "string",
                "description": "Updated TSX/TypeScript source code",
            },
        },
        "required": ["app_id", "path", "source"],
    },
)
async def code_update_file(context: Any, app_id: str, path: str, source: str) -> str:
    """Update a code file's content."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppCodeFile, Application

    logger.info(f"MCP code_update_file called for app {app_id}, path {path}")

    path = path.strip("/")

    try:
        async with get_db_context() as db:
            # Get app and verify access
            app = await db.get(Application, UUID(app_id))
            if not app:
                return json.dumps({"error": f"Application {app_id} not found"})

            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return json.dumps({"error": "Access denied"})

            if not app.draft_version_id:
                return json.dumps({"error": "No draft version found"})

            # Get file
            query = select(AppCodeFile).where(
                AppCodeFile.app_version_id == app.draft_version_id,
                AppCodeFile.path == path,
            )
            result = await db.execute(query)
            file = result.scalar_one_or_none()

            if not file:
                return json.dumps({"error": f"File '{path}' not found"})

            # Update
            file.source = source
            await db.flush()
            await db.refresh(file)

            # Publish update with full content for real-time preview
            await publish_app_code_file_update(
                app_id=app_id,
                user_id=str(context.user_id) if context.user_id else "mcp",
                user_name=context.user_name or "MCP Tool",
                path=path,
                source=source,
                compiled=file.compiled,
                action="update",
            )

            await db.commit()

            logger.info(f"Updated code file '{path}' in app {app_id}")
            return json.dumps({
                "success": True,
                "id": str(file.id),
                "path": file.path,
                "updated_at": file.updated_at.isoformat() if file.updated_at else None,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error updating code file via MCP: {e}")
        return json.dumps({"error": f"Error updating code file: {str(e)}"})


@system_tool(
    id="code_delete_file",
    name="Delete Code File",
    description="Delete a code file from an app's draft version.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {
                "type": "string",
                "description": "Application UUID",
            },
            "path": {
                "type": "string",
                "description": "File path to delete",
            },
        },
        "required": ["app_id", "path"],
    },
)
async def code_delete_file(context: Any, app_id: str, path: str) -> str:
    """Delete a code file."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppCodeFile, Application

    logger.info(f"MCP code_delete_file called for app {app_id}, path {path}")

    path = path.strip("/")

    try:
        async with get_db_context() as db:
            # Get app and verify access
            app = await db.get(Application, UUID(app_id))
            if not app:
                return json.dumps({"error": f"Application {app_id} not found"})

            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return json.dumps({"error": "Access denied"})

            if not app.draft_version_id:
                return json.dumps({"error": "No draft version found"})

            # Get file
            query = select(AppCodeFile).where(
                AppCodeFile.app_version_id == app.draft_version_id,
                AppCodeFile.path == path,
            )
            result = await db.execute(query)
            file = result.scalar_one_or_none()

            if not file:
                return json.dumps({"error": f"File '{path}' not found"})

            # Delete
            await db.delete(file)
            await db.flush()

            # Publish delete event
            await publish_app_code_file_update(
                app_id=app_id,
                user_id=str(context.user_id) if context.user_id else "mcp",
                user_name=context.user_name or "MCP Tool",
                path=path,
                source=None,
                compiled=None,
                action="delete",
            )

            await db.commit()

            logger.info(f"Deleted code file '{path}' from app {app_id}")
            return json.dumps({
                "success": True,
                "path": path,
                "deleted": True,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error deleting code file via MCP: {e}")
        return json.dumps({"error": f"Error deleting code file: {str(e)}"})
