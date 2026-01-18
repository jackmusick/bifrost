"""
App Builder MCP Tools - App Files

Tools for managing files in applications.
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
    # Dynamic segments with optional extension for filenames
    DYNAMIC_SEGMENT_PATTERN = re.compile(r"^\[[\w-]+\](\.tsx?)?$")
    VALID_NAME_PATTERN = re.compile(r"^[\w-]+$")
    # Require .ts or .tsx extension on filenames
    VALID_FILENAME_PATTERN = re.compile(r"^[\w-]+\.tsx?$")

    if not path:
        return "File path cannot be empty"

    path = path.strip("/")
    segments = path.split("/")

    if any(not seg for seg in segments):
        return "Path cannot contain empty segments (double slashes)"

    if len(segments) == 1:
        filename = segments[0]

        # Must have .ts or .tsx extension
        if not re.search(r"\.tsx?$", filename):
            return "Files must have a .ts or .tsx extension"

        # Check root name without extension
        root_name = re.sub(r"\.tsx?$", "", filename)
        if root_name not in ROOT_ALLOWED_FILES:
            allowed = ", ".join(sorted(f"{f}.tsx" for f in ROOT_ALLOWED_FILES))
            return f"Root-level file must be one of: {allowed}. Use pages/, components/, or modules/ directories for other files."
        return None

    top_dir = segments[0]
    if top_dir not in VALID_TOP_DIRS:
        return f"Files must be in one of: {', '.join(sorted(VALID_TOP_DIRS))}"

    for i, segment in enumerate(segments[1:], start=1):
        is_last_segment = i == len(segments) - 1

        if DYNAMIC_SEGMENT_PATTERN.match(segment):
            if top_dir != "pages":
                return f"Dynamic segments like [{segment[1:-1]}] are only allowed in pages/"
            # For last segment, require extension
            if is_last_segment and not segment.endswith((".ts", ".tsx")):
                return f"Files must have a .ts or .tsx extension. Got: '{segment}'"
            continue

        # Use filename pattern (requires .ts/.tsx) for last segment, name pattern for directories
        pattern = VALID_FILENAME_PATTERN if is_last_segment else VALID_NAME_PATTERN
        if not pattern.match(segment):
            if is_last_segment:
                # Check if missing extension
                if VALID_NAME_PATTERN.match(segment):
                    return f"Files must have a .ts or .tsx extension. Got: '{segment}'"
                return f"Invalid filename '{segment}'. Use alphanumeric characters, underscores, hyphens, with .ts or .tsx extension."
            else:
                return f"Invalid path segment '{segment}'. Use only alphanumeric characters, underscores, and hyphens."

        # Check _layout restriction (strip extension for comparison)
        segment_name = re.sub(r"\.tsx?$", "", segment)
        if segment_name == "_layout" and top_dir != "pages":
            return "_layout files are only allowed in pages/"

    return None


@system_tool(
    id="list_app_files",
    name="List App Files",
    description="List all files for an application's draft version.",
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
async def list_app_files(context: Any, app_id: str) -> str:
    """List all files for an app's draft version."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP list_app_files called for app {app_id}")

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
                select(AppFile)
                .where(AppFile.app_version_id == app.draft_version_id)
                .order_by(AppFile.path)
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
        logger.exception(f"Error listing app files via MCP: {e}")
        return json.dumps({"error": f"Error listing app files: {str(e)}"})


@system_tool(
    id="get_app_file",
    name="Get App File",
    description="Get a specific file's content by path from an app's draft version.",
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
                "description": "File path with extension (e.g., 'pages/index.tsx', 'components/Button.tsx')",
            },
        },
        "required": ["app_id", "path"],
    },
)
async def get_app_file(context: Any, app_id: str, path: str) -> str:
    """Get an app file's content."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP get_app_file called for app {app_id}, path {path}")

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
            query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path.strip("/"),
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
        logger.exception(f"Error getting app file via MCP: {e}")
        return json.dumps({"error": f"Error getting app file: {str(e)}"})


@system_tool(
    id="create_app_file",
    name="Create App File",
    description="Create a new file in an app's draft version. Path conventions: root allows only _layout/_providers; use pages/, components/, or modules/ for other files.",
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
                "description": "File path with extension (e.g., 'pages/clients.tsx', 'components/Button.tsx')",
            },
            "source": {
                "type": "string",
                "description": "TSX/TypeScript source code",
            },
        },
        "required": ["app_id", "path", "source"],
    },
)
async def create_app_file(context: Any, app_id: str, path: str, source: str) -> str:
    """Create a new app file."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP create_app_file called for app {app_id}, path {path}")

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

            # Check for duplicate
            existing_query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path,
            )
            existing = await db.execute(existing_query)
            if existing.scalar_one_or_none():
                return json.dumps({"error": f"File with path '{path}' already exists"})

            # Create file
            file = AppFile(
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

            logger.info(f"Created app file '{path}' in app {app_id}")
            return json.dumps({
                "success": True,
                "id": str(file.id),
                "path": file.path,
                "created_at": file.created_at.isoformat() if file.created_at else None,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error creating app file via MCP: {e}")
        return json.dumps({"error": f"Error creating app file: {str(e)}"})


@system_tool(
    id="update_app_file",
    name="Update App File",
    description="Update a file's source code in an app's draft version.",
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
async def update_app_file(context: Any, app_id: str, path: str, source: str) -> str:
    """Update an app file's content."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP update_app_file called for app {app_id}, path {path}")

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
            query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path,
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

            logger.info(f"Updated app file '{path}' in app {app_id}")
            return json.dumps({
                "success": True,
                "id": str(file.id),
                "path": file.path,
                "updated_at": file.updated_at.isoformat() if file.updated_at else None,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error updating app file via MCP: {e}")
        return json.dumps({"error": f"Error updating app file: {str(e)}"})


@system_tool(
    id="delete_app_file",
    name="Delete App File",
    description="Delete a file from an app's draft version.",
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
async def delete_app_file(context: Any, app_id: str, path: str) -> str:
    """Delete an app file."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP delete_app_file called for app {app_id}, path {path}")

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
            query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path,
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

            logger.info(f"Deleted app file '{path}' from app {app_id}")
            return json.dumps({
                "success": True,
                "path": path,
                "deleted": True,
            })

    except ValueError as e:
        return json.dumps({"error": f"Invalid UUID: {str(e)}"})
    except Exception as e:
        logger.exception(f"Error deleting app file via MCP: {e}")
        return json.dumps({"error": f"Error deleting app file: {str(e)}"})
