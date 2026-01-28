"""
Code Editor MCP Tools - Precision Editing

Tools for searching, reading, and editing code stored in the database:
- app_file (TSX/TypeScript for App Builder)
- workflow (Python workflow code)
- module (Python helper modules via workspace_files)
- text (Markdown, README, documentation, config files)

These tools mirror Claude Code's precision editing workflow:
1. list_content - List files by entity type
2. search_content - Find code with regex
3. read_content_lines - Read specific line ranges
4. get_content - Full content read (fallback)
5. patch_content - Surgical old->new replacement
6. replace_content - Full content write (fallback)
7. delete_content - Delete a file
"""

import json
import logging
import re
from typing import Any
from uuid import UUID

from mcp.types import CallToolResult
from sqlalchemy import select

from src.core.database import get_db_context
from src.models.orm.applications import AppFile, Application
from src.models.orm.organizations import Organization
from src.models.orm.workflows import Workflow
from src.models.orm.workspace import WorkspaceFile
from src.services.file_storage import FileStorageService
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory
from src.services.mcp_server.tool_result import error_result, format_diff, success_result

logger = logging.getLogger(__name__)

# Maximum content size before truncation (characters)
MAX_CONTENT_CHARS = 100_000  # ~100KB, similar to Claude Code's Read tool


# =============================================================================
# Helper Functions
# =============================================================================


def _normalize_line_endings(content: str) -> str:
    """Normalize line endings to \\n for consistent matching."""
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _get_lines_with_context(
    content: str, line_number: int, context_lines: int = 3
) -> tuple[list[str], list[str]]:
    """Get context lines before and after a given line number (1-indexed)."""
    lines = content.split("\n")
    idx = line_number - 1  # Convert to 0-indexed

    start_before = max(0, idx - context_lines)
    end_after = min(len(lines), idx + context_lines + 1)

    before = [f"{i + 1}: {lines[i]}" for i in range(start_before, idx)]
    after = [f"{i + 1}: {lines[i]}" for i in range(idx + 1, end_after)]

    return before, after


def _find_match_locations(content: str, search_string: str) -> list[dict[str, Any]]:
    """Find all locations where search_string appears in content."""
    locations = []
    lines = content.split("\n")

    for i, line in enumerate(lines):
        if search_string in line:
            # Get a preview (truncated if too long)
            preview = line.strip()
            if len(preview) > 60:
                preview = preview[:57] + "..."
            locations.append({"line": i + 1, "preview": preview})

    return locations


async def _get_content_by_entity(
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
    context: Any = None,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """
    Get content for an entity by type and path.

    Returns:
        Tuple of (content, metadata_dict, error_message)
        - If successful: (content_str, {"path": ..., "entity_id": ...}, None)
        - If error: (None, None, "error message")
    """
    async with get_db_context() as db:
        if entity_type == "app_file":
            if not app_id:
                return None, None, "app_id is required for app_file entity type"

            try:
                app_uuid = UUID(app_id)
            except ValueError:
                return None, None, f"Invalid app_id format: {app_id}"

            # Get app and verify access
            app = await db.get(Application, app_uuid)
            if not app:
                return None, None, f"Application not found: {app_id}"

            if not context.is_platform_admin and context.org_id:
                if app.organization_id and app.organization_id != context.org_id:
                    return None, None, "Access denied"

            if not app.draft_version_id:
                return None, None, "No draft version found"

            # Get file
            query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path.strip("/"),
            )
            result = await db.execute(query)
            file = result.scalar_one_or_none()

            if not file:
                return None, None, f"File not found: {path}"

            return (
                file.source,
                {
                    "path": file.path,
                    "entity_id": str(file.id),
                    "app_id": app_id,
                },
                None,
            )

        elif entity_type == "workflow":
            # Query workflows table
            query = select(Workflow).where(
                Workflow.path == path,
                Workflow.is_active == True,  # noqa: E712
            )

            # Filter by organization if provided
            if organization_id:
                try:
                    org_uuid = UUID(organization_id)
                    query = query.where(Workflow.organization_id == org_uuid)
                except ValueError:
                    return (
                        None,
                        None,
                        f"Invalid organization_id format: {organization_id}",
                    )
            elif not context.is_platform_admin:
                # Non-admins can see their org's workflows + global
                if context.org_id:
                    query = query.where(
                        (Workflow.organization_id == context.org_id)
                        | (Workflow.organization_id.is_(None))
                    )

            result = await db.execute(query)
            workflow = result.scalar_one_or_none()

            if not workflow:
                return None, None, f"Workflow not found: {path}"

            if not workflow.code:
                return None, None, f"Workflow has no code: {path}"

            return (
                workflow.code,
                {
                    "path": workflow.path,
                    "entity_id": str(workflow.id),
                    "organization_id": (
                        str(workflow.organization_id)
                        if workflow.organization_id
                        else None
                    ),
                },
                None,
            )

        elif entity_type == "module":
            # Query workspace_files for modules
            query = select(WorkspaceFile).where(
                WorkspaceFile.path == path,
                WorkspaceFile.entity_type == "module",
                WorkspaceFile.is_deleted == False,  # noqa: E712
            )

            result = await db.execute(query)
            module = result.scalar_one_or_none()

            if not module:
                return None, None, f"Module not found: {path}"

            if not module.content:
                return None, None, f"Module has no content: {path}"

            return (
                module.content,
                {
                    "path": module.path,
                    "entity_id": str(module.id),
                },
                None,
            )

        elif entity_type == "text":
            # Query workspace_files for text files (markdown, docs, config)
            query = select(WorkspaceFile).where(
                WorkspaceFile.path == path,
                WorkspaceFile.entity_type == "text",
                WorkspaceFile.is_deleted == False,  # noqa: E712
            )

            result = await db.execute(query)
            text_file = result.scalar_one_or_none()

            if not text_file:
                return None, None, f"Text file not found: {path}"

            return (
                text_file.content or "",
                {
                    "path": text_file.path,
                    "entity_id": str(text_file.id),
                },
                None,
            )

        else:
            return None, None, f"Invalid entity_type: {entity_type}"


def _validate_entity_type_match(entity_type: str, content: str) -> str | None:
    """
    Validate that declared entity_type matches the content.

    Returns error message if mismatch, None if valid.
    """
    # No validation needed for text files
    if entity_type == "text":
        return None

    has_workflow_decorator = (
        "@workflow" in content or "@tool" in content or "@data_provider" in content
    )

    if entity_type == "workflow" and not has_workflow_decorator:
        return "entity_type mismatch: declared 'workflow' but no @workflow, @tool, or @data_provider decorator found"

    if entity_type == "module" and has_workflow_decorator:
        return "entity_type mismatch: declared 'module' but content contains @workflow/@tool/@data_provider decorator. Use entity_type='workflow' instead."

    return None


async def _replace_app_file(
    context: Any, app_id: str, path: str, content: str
) -> bool:
    """Replace or create an app file. Returns True if created, False if updated."""
    from src.core.pubsub import publish_app_code_file_update

    async with get_db_context() as db:
        app_uuid = UUID(app_id)
        app = await db.get(Application, app_uuid)

        if not app:
            raise ValueError(f"Application not found: {app_id}")

        if not context.is_platform_admin and context.org_id:
            if app.organization_id and app.organization_id != context.org_id:
                raise PermissionError("Access denied")

        if not app.draft_version_id:
            raise ValueError("No draft version found")

        # Check if file exists
        query = select(AppFile).where(
            AppFile.app_version_id == app.draft_version_id,
            AppFile.path == path.strip("/"),
        )
        result = await db.execute(query)
        file = result.scalar_one_or_none()

        created = False
        if file:
            # Update existing
            file.source = content
            action = "update"
        else:
            # Create new
            file = AppFile(
                app_version_id=app.draft_version_id,
                path=path.strip("/"),
                source=content,
            )
            db.add(file)
            created = True
            action = "create"

        await db.flush()

        # Publish update for real-time preview
        await publish_app_code_file_update(
            app_id=app_id,
            user_id=str(context.user_id) if context.user_id else "mcp",
            user_name=context.user_name or "MCP Tool",
            path=path,
            source=content,
            compiled=file.compiled if hasattr(file, "compiled") else None,
            action=action,
        )

        await db.commit()
        return created


async def _replace_workspace_file(
    context: Any, entity_type: str, path: str, content: str, organization_id: str | None
) -> bool:
    """Replace or create a workflow/module file. Returns True if created, False if updated."""
    async with get_db_context() as db:
        service = FileStorageService(db)

        # Check if file exists to determine created status
        try:
            await service.read_file(path)
            created = False
        except FileNotFoundError:
            created = True

        # Write through FileStorageService for validation
        await service.write_file(
            path=path,
            content=content.encode("utf-8"),
            updated_by=context.user_email or "mcp",
            force_deactivation=True,
        )

        return created


async def _replace_text_file(
    context: Any, path: str, content: str
) -> bool:
    """Replace or create a text file (markdown, docs, config). Returns True if created."""
    import hashlib

    # Compute content hash and size
    content_bytes = content.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()
    size_bytes = len(content_bytes)

    async with get_db_context() as db:
        # Check if file exists (including deleted ones to handle re-creation)
        query = select(WorkspaceFile).where(WorkspaceFile.path == path)
        result = await db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing (or resurrect if deleted)
            existing.content = content
            existing.content_hash = content_hash
            existing.size_bytes = size_bytes
            existing.entity_type = "text"
            existing.is_deleted = False
            created = existing.is_deleted  # Was deleted, now resurrected
        else:
            # Create new
            new_file = WorkspaceFile(
                path=path,
                entity_type="text",
                content=content,
                content_hash=content_hash,
                size_bytes=size_bytes,
                is_deleted=False,
            )
            db.add(new_file)
            created = True

        await db.commit()
        return created


async def _persist_content(
    entity_type: str,
    path: str,
    content: str,
    app_id: str | None,
    organization_id: str | None,
    context: Any,
) -> None:
    """Persist content changes to the database."""
    async with get_db_context() as db:
        if entity_type == "app_file":
            from src.core.pubsub import publish_app_code_file_update

            if not app_id:
                raise ValueError("app_id is required for app_file entity type")

            app_uuid = UUID(app_id)
            app = await db.get(Application, app_uuid)
            if not app or not app.draft_version_id:
                raise ValueError(f"Application or draft not found: {app_id}")

            query = select(AppFile).where(
                AppFile.app_version_id == app.draft_version_id,
                AppFile.path == path.strip("/"),
            )
            result = await db.execute(query)
            file = result.scalar_one_or_none()
            if not file:
                raise ValueError(f"File not found: {path}")

            file.source = content
            await db.flush()

            # Publish update for real-time preview
            await publish_app_code_file_update(
                app_id=app_id,
                user_id=str(context.user_id) if context.user_id else "mcp",
                user_name=context.user_name or "MCP Tool",
                path=path,
                source=content,
                compiled=file.compiled,
                action="update",
            )

            await db.commit()

        elif entity_type in ("workflow", "module"):
            # Route through FileStorageService for validation
            service = FileStorageService(db)
            await service.write_file(
                path=path,
                content=content.encode("utf-8"),
                updated_by=context.user_email or "mcp",
                force_deactivation=True,  # Allow changes
            )


# =============================================================================
# list_content Tool
# =============================================================================


@system_tool(
    id="list_content",
    name="List Content",
    description="List files by entity type. Returns paths without content. Use to discover what files exist before searching or reading.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity to list. Optional - omit to search all types (except app_file which requires app_id)",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required for app_file, optional for others)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: limit to this organization (optional). Not applicable to modules or text.",
            },
            "path_prefix": {
                "type": "string",
                "description": "Filter to paths starting with this prefix (optional)",
            },
        },
        "required": [],
    },
)
async def list_content(
    context: Any,
    entity_type: str | None = None,
    app_id: str | None = None,
    organization_id: str | None = None,
    path_prefix: str | None = None,
) -> str:
    """List files by entity type."""
    logger.info(f"MCP list_content: entity_type={entity_type}")

    # Validate entity_type if provided
    valid_types = ("app_file", "workflow", "module", "text")
    if entity_type is not None and entity_type not in valid_types:
        return json.dumps(
            {
                "error": f"Invalid entity_type: {entity_type}. Must be one of: app_file, workflow, module, text"
            }
        )

    if entity_type == "app_file" and not app_id:
        return json.dumps({"error": "app_id is required for app_file entity type"})

    try:
        async with get_db_context() as db:
            all_files: list[dict[str, Any]] = []

            # Determine which types to query
            if entity_type:
                types_to_query = [entity_type]
            else:
                # Query all types (app_file only if app_id provided)
                types_to_query = ["workflow", "module", "text"]
                if app_id:
                    types_to_query.append("app_file")

            for etype in types_to_query:
                if etype == "app_file" and app_id:
                    files = await _list_app_files(db, context, app_id, path_prefix)
                    for f in files:
                        f["entity_type"] = "app_file"
                    all_files.extend(files)
                elif etype == "workflow":
                    files = await _list_workflows_deduped(
                        db, context, organization_id, path_prefix
                    )
                    for f in files:
                        f["entity_type"] = "workflow"
                    all_files.extend(files)
                elif etype == "module":
                    files = await _list_modules(db, context, path_prefix)
                    for f in files:
                        f["entity_type"] = "module"
                    all_files.extend(files)
                elif etype == "text":
                    files = await _list_text_files(db, context, path_prefix)
                    for f in files:
                        f["entity_type"] = "text"
                    all_files.extend(files)

        result: dict[str, Any] = {
            "files": all_files,
            "count": len(all_files),
        }
        if entity_type:
            result["entity_type"] = entity_type

        return json.dumps(result)

    except Exception as e:
        logger.exception(f"Error in list_content: {e}")
        return json.dumps({"error": f"List failed: {str(e)}"})


async def _list_app_files(
    db, context: Any, app_id: str | None, path_prefix: str | None
) -> list[dict[str, Any]]:
    """List app files for an application."""
    if not app_id:
        return []

    app_uuid = UUID(app_id)
    app = await db.get(Application, app_uuid)
    if not app:
        return []

    if not context.is_platform_admin and context.org_id:
        if app.organization_id and app.organization_id != context.org_id:
            return []

    if not app.draft_version_id:
        return []

    query = select(AppFile).where(AppFile.app_version_id == app.draft_version_id)
    if path_prefix:
        query = query.where(AppFile.path.startswith(path_prefix.strip("/")))

    result = await db.execute(query)
    files = result.scalars().all()

    return [{"path": f.path, "app_id": app_id} for f in files]


async def _list_workflows(
    db, context: Any, organization_id: str | None, path_prefix: str | None
) -> list[dict[str, Any]]:
    """List workflows."""
    query = select(Workflow).where(Workflow.is_active == True)  # noqa: E712

    if path_prefix:
        query = query.where(Workflow.path.startswith(path_prefix))

    if organization_id:
        org_uuid = UUID(organization_id)
        query = query.where(Workflow.organization_id == org_uuid)
    elif not context.is_platform_admin and context.org_id:
        query = query.where(
            (Workflow.organization_id == context.org_id)
            | (Workflow.organization_id.is_(None))
        )

    result = await db.execute(query)
    workflows = result.scalars().all()

    return [
        {
            "path": wf.path,
            "organization_id": str(wf.organization_id) if wf.organization_id else None,
        }
        for wf in workflows
    ]


async def _list_workflows_deduped(
    db, context: Any, organization_id: str | None, path_prefix: str | None
) -> list[dict[str, Any]]:
    """
    List workflows with deduplication by path.

    Returns unique paths with human-readable scopes array (e.g., ["global", "Acme Corp"]).
    """
    query = select(Workflow).where(Workflow.is_active == True)  # noqa: E712

    if path_prefix:
        query = query.where(Workflow.path.startswith(path_prefix))

    if organization_id:
        org_uuid = UUID(organization_id)
        query = query.where(Workflow.organization_id == org_uuid)
    elif not context.is_platform_admin and context.org_id:
        query = query.where(
            (Workflow.organization_id == context.org_id)
            | (Workflow.organization_id.is_(None))
        )

    result = await db.execute(query)
    workflows = result.scalars().all()

    # Collect unique org_ids to fetch names
    org_ids = {wf.organization_id for wf in workflows if wf.organization_id}

    # Fetch organization names in one query
    org_names: dict[UUID, str] = {}
    if org_ids:
        org_query = select(Organization).where(Organization.id.in_(org_ids))
        org_result = await db.execute(org_query)
        orgs = org_result.scalars().all()
        org_names = {org.id: org.name for org in orgs}

    # Group by path, collecting scopes
    path_scopes: dict[str, list[str]] = {}
    for wf in workflows:
        path = wf.path
        if wf.organization_id:
            scope = org_names.get(wf.organization_id, str(wf.organization_id))
        else:
            scope = "global"

        if path not in path_scopes:
            path_scopes[path] = []
        if scope not in path_scopes[path]:
            path_scopes[path].append(scope)

    # Sort scopes: "global" first, then alphabetically
    def sort_scopes(scopes: list[str]) -> list[str]:
        result = []
        if "global" in scopes:
            result.append("global")
        result.extend(sorted(s for s in scopes if s != "global"))
        return result

    return [
        {
            "path": path,
            "scopes": sort_scopes(scopes),
        }
        for path, scopes in sorted(path_scopes.items())
    ]


async def _list_modules(
    db, context: Any, path_prefix: str | None
) -> list[dict[str, Any]]:
    """List modules."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    if path_prefix:
        query = query.where(WorkspaceFile.path.startswith(path_prefix))

    result = await db.execute(query)
    modules = result.scalars().all()

    return [{"path": m.path} for m in modules]


async def _list_text_files(
    db, context: Any, path_prefix: str | None
) -> list[dict[str, Any]]:
    """List text files (markdown, docs, config)."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "text",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    if path_prefix:
        query = query.where(WorkspaceFile.path.startswith(path_prefix))

    result = await db.execute(query)
    text_files = result.scalars().all()

    return [{"path": t.path} for t in text_files]


# =============================================================================
# search_content Tool
# =============================================================================


@system_tool(
    id="search_content",
    name="Search Content",
    description="Search for patterns in code files. Returns matching lines with context. Use to find functions, imports, or usages before making edits.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for (e.g., 'def get_.*agent', 'useWorkflow')",
            },
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity to search. Optional - omit to search all types (except app_file which requires app_id)",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required for app_file, optional for others)",
            },
            "path": {
                "type": "string",
                "description": "Filter to a specific file path (optional - searches all if omitted)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: limit to this organization (optional). Not applicable to modules or text.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of lines to show before and after each match (default: 3)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 20)",
            },
        },
        "required": ["pattern"],
    },
)
async def search_content(
    context: Any,
    pattern: str,
    entity_type: str | None = None,
    app_id: str | None = None,
    path: str | None = None,
    organization_id: str | None = None,
    context_lines: int = 3,
    max_results: int = 20,
) -> str:
    """Search for regex patterns in code content."""
    logger.info(f"MCP search_content: pattern={pattern}, entity_type={entity_type}")

    if not pattern:
        return json.dumps({"error": "pattern is required"})

    # Validate entity_type if provided
    valid_types = ("app_file", "workflow", "module", "text")
    if entity_type is not None and entity_type not in valid_types:
        return json.dumps(
            {
                "error": f"Invalid entity_type: {entity_type}. Must be one of: app_file, workflow, module, text"
            }
        )

    if entity_type == "app_file" and not app_id:
        return json.dumps({"error": "app_id is required for app_file entity type"})

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return json.dumps({"error": f"Invalid regex pattern: {e}"})

    matches: list[dict[str, Any]] = []
    truncated = False

    try:
        async with get_db_context() as db:
            # Determine which types to search
            if entity_type:
                types_to_search = [entity_type]
            else:
                # Search all types (app_file only if app_id provided)
                types_to_search = ["workflow", "module", "text"]
                if app_id:
                    types_to_search.append("app_file")

            remaining = max_results
            for etype in types_to_search:
                if remaining <= 0:
                    break

                if etype == "app_file" and app_id:
                    type_matches = await _search_app_files(
                        db, context, app_id, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "app_file"
                    matches.extend(type_matches)
                elif etype == "workflow":
                    type_matches = await _search_workflows(
                        db, context, path, organization_id, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "workflow"
                    matches.extend(type_matches)
                elif etype == "module":
                    type_matches = await _search_modules(
                        db, context, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "module"
                    matches.extend(type_matches)
                elif etype == "text":
                    type_matches = await _search_text_files(
                        db, context, path, regex, context_lines, remaining
                    )
                    for m in type_matches:
                        m["entity_type"] = "text"
                    matches.extend(type_matches)

                remaining = max_results - len(matches)

            if len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True

        return json.dumps(
            {
                "matches": matches,
                "total_matches": len(matches),
                "truncated": truncated,
            }
        )

    except Exception as e:
        logger.exception(f"Error in search_content: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"})


async def _search_app_files(
    db,
    context: Any,
    app_id: str | None,
    path: str | None,
    regex: re.Pattern,
    context_lines: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search app files for regex matches."""
    if not app_id:
        return []

    app_uuid = UUID(app_id)
    app = await db.get(Application, app_uuid)
    if not app:
        return []

    if not context.is_platform_admin and context.org_id:
        if app.organization_id and app.organization_id != context.org_id:
            return []

    if not app.draft_version_id:
        return []

    query = select(AppFile).where(AppFile.app_version_id == app.draft_version_id)
    if path:
        query = query.where(AppFile.path == path.strip("/"))

    result = await db.execute(query)
    files = result.scalars().all()

    matches = []
    for file in files:
        content = _normalize_line_endings(file.source or "")
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": file.path,
                        "app_id": app_id,
                        "line_number": i + 1,
                        "match": line,
                        "context_before": before,
                        "context_after": after,
                    }
                )
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return matches


async def _search_workflows(
    db,
    context: Any,
    path: str | None,
    organization_id: str | None,
    regex: re.Pattern,
    context_lines: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search workflows for regex matches."""
    query = select(Workflow).where(Workflow.is_active == True)  # noqa: E712

    if path:
        query = query.where(Workflow.path == path)

    if organization_id:
        org_uuid = UUID(organization_id)
        query = query.where(Workflow.organization_id == org_uuid)
    elif not context.is_platform_admin and context.org_id:
        query = query.where(
            (Workflow.organization_id == context.org_id)
            | (Workflow.organization_id.is_(None))
        )

    result = await db.execute(query)
    workflows = result.scalars().all()

    matches = []
    for wf in workflows:
        if not wf.code:
            continue

        content = _normalize_line_endings(wf.code)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": wf.path,
                        "organization_id": (
                            str(wf.organization_id) if wf.organization_id else None
                        ),
                        "line_number": i + 1,
                        "match": line,
                        "context_before": before,
                        "context_after": after,
                    }
                )
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return matches


async def _search_modules(
    db,
    context: Any,
    path: str | None,
    regex: re.Pattern,
    context_lines: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search modules for regex matches."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    if path:
        query = query.where(WorkspaceFile.path == path)

    result = await db.execute(query)
    modules = result.scalars().all()

    matches = []
    for mod in modules:
        if not mod.content:
            continue

        content = _normalize_line_endings(mod.content)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": mod.path,
                        "line_number": i + 1,
                        "match": line,
                        "context_before": before,
                        "context_after": after,
                    }
                )
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return matches


async def _search_text_files(
    db,
    context: Any,
    path: str | None,
    regex: re.Pattern,
    context_lines: int,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search text files for regex matches."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "text",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    if path:
        query = query.where(WorkspaceFile.path == path)

    result = await db.execute(query)
    text_files = result.scalars().all()

    matches = []
    for tf in text_files:
        if not tf.content:
            continue

        content = _normalize_line_endings(tf.content)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": tf.path,
                        "line_number": i + 1,
                        "match": line,
                        "context_before": before,
                        "context_after": after,
                    }
                )
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

    return matches


# =============================================================================
# read_content_lines Tool
# =============================================================================


@system_tool(
    id="read_content_lines",
    name="Read Content Lines",
    description="Read specific line range from a file. Use to get context around a search match without loading entire file.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional for global). Not applicable to modules.",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to read (1-indexed, default: 1)",
            },
            "end_line": {
                "type": "integer",
                "description": "Last line to read (defaults to start_line + 100)",
            },
        },
        "required": ["entity_type", "path"],
    },
)
async def read_content_lines(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
    start_line: int = 1,
    end_line: int | None = None,
) -> str:
    """Read a specific range of lines from a file."""
    logger.info(
        f"MCP read_content_lines: entity_type={entity_type}, path={path}, lines={start_line}-{end_line}"
    )

    if not path:
        return json.dumps({"error": "path is required"})

    if entity_type not in ("app_file", "workflow", "module", "text"):
        return json.dumps({"error": f"Invalid entity_type: {entity_type}"})

    if entity_type == "app_file" and not app_id:
        return json.dumps({"error": "app_id is required for app_file entity type"})

    content_result, metadata_result, error = await _get_content_by_entity(
        entity_type, path, app_id, organization_id, context
    )

    if error:
        return json.dumps({"error": error})
    if content_result is None or metadata_result is None:
        return json.dumps({"error": "Failed to retrieve content"})

    # Now we know these are not None
    content_str = _normalize_line_endings(content_result)
    lines = content_str.split("\n")
    total_lines = len(lines)

    # Apply defaults
    if start_line < 1:
        start_line = 1
    if end_line is None:
        end_line = min(start_line + 100, total_lines)
    if end_line > total_lines:
        end_line = total_lines

    # Extract requested lines (1-indexed)
    selected_lines = []
    for i in range(start_line - 1, end_line):
        if i < len(lines):
            selected_lines.append(f"{i + 1}: {lines[i]}")

    return json.dumps(
        {
            "path": metadata_result["path"],
            "organization_id": metadata_result.get("organization_id"),
            "app_id": metadata_result.get("app_id"),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "content": "\n".join(selected_lines),
        }
    )


# =============================================================================
# get_content Tool
# =============================================================================


@system_tool(
    id="get_content",
    name="Get Content",
    description="Get entire file content. Prefer search_content + read_content_lines for large files. Use this for small files or when you need the complete picture.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional for global). Not applicable to modules.",
            },
        },
        "required": ["entity_type", "path"],
    },
)
async def get_content(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> str:
    """Get the entire content of a file."""
    logger.info(f"MCP get_content: entity_type={entity_type}, path={path}")

    if not path:
        return json.dumps({"error": "path is required"})

    if entity_type not in ("app_file", "workflow", "module", "text"):
        return json.dumps({"error": f"Invalid entity_type: {entity_type}"})

    if entity_type == "app_file" and not app_id:
        return json.dumps({"error": "app_id is required for app_file entity type"})

    content_result, metadata_result, error = await _get_content_by_entity(
        entity_type, path, app_id, organization_id, context
    )

    if error:
        return json.dumps({"error": error})
    if content_result is None or metadata_result is None:
        return json.dumps({"error": "Failed to retrieve content"})

    content_str = _normalize_line_endings(content_result)
    lines = content_str.split("\n")
    total_lines = len(lines)
    total_chars = len(content_str)
    truncated = False
    warning = None

    # Truncate if content exceeds limit
    if total_chars > MAX_CONTENT_CHARS:
        truncated = True
        # Find last complete line within limit
        truncated_content = content_str[:MAX_CONTENT_CHARS]
        last_newline = truncated_content.rfind("\n")
        if last_newline > 0:
            content_str = truncated_content[:last_newline]
        else:
            content_str = truncated_content
        lines_shown = content_str.count("\n") + 1
        warning = (
            f"Content truncated: {total_chars:,} chars exceeds {MAX_CONTENT_CHARS:,} limit. "
            f"Showing {lines_shown:,} of {total_lines:,} lines. "
            f"Use read_content_lines with start_line/end_line for specific sections."
        )

    result: dict[str, Any] = {
        "path": metadata_result["path"],
        "organization_id": metadata_result.get("organization_id"),
        "app_id": metadata_result.get("app_id"),
        "entity_id": metadata_result.get("entity_id"),
        "total_lines": total_lines,
        "content": content_str,
    }

    if truncated:
        result["truncated"] = True
        result["warning"] = warning

    return json.dumps(result)


# =============================================================================
# patch_content Tool
# =============================================================================


@system_tool(
    id="patch_content",
    name="Patch Content",
    description="Surgical edit: replace old_string with new_string. The old_string must be unique in the file. Include enough context to ensure uniqueness. Use replace_content if patch fails due to syntax issues.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional for global). Not applicable to modules.",
            },
            "old_string": {
                "type": "string",
                "description": "Exact string to find and replace (must be unique in file)",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement string",
            },
        },
        "required": ["entity_type", "path", "old_string", "new_string"],
    },
)
async def patch_content(
    context: Any,
    entity_type: str,
    path: str,
    old_string: str,
    new_string: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> CallToolResult:
    """Make a surgical edit by replacing a unique string."""
    logger.info(f"MCP patch_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")
    if not old_string:
        return error_result("old_string is required")
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return error_result(f"Invalid entity_type: {entity_type}")
    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    content_result, metadata_result, error = await _get_content_by_entity(
        entity_type, path, app_id, organization_id, context
    )

    if error:
        return error_result(error)
    if content_result is None or metadata_result is None:
        return error_result("Failed to retrieve content")

    content_str = _normalize_line_endings(content_result)
    old_string = _normalize_line_endings(old_string)
    new_string = _normalize_line_endings(new_string)

    # Check uniqueness
    match_count = content_str.count(old_string)

    if match_count == 0:
        return error_result("old_string not found in file")

    if match_count > 1:
        locations = _find_match_locations(content_str, old_string)
        return error_result(
            f"old_string matches {match_count} locations. Include more context to make it unique.",
            {"match_locations": locations},
        )

    # Perform replacement
    new_content = content_str.replace(old_string, new_string, 1)

    # Count lines changed
    old_lines = old_string.count("\n") + 1
    new_lines = new_string.count("\n") + 1
    lines_changed = max(old_lines, new_lines)

    # Persist the change
    try:
        await _persist_content(
            entity_type, path, new_content, app_id, organization_id, context
        )

        # Format diff-style display
        display = format_diff(
            metadata_result["path"],
            old_string.split("\n"),
            new_string.split("\n"),
        )

        return success_result(
            display,
            {
                "success": True,
                "path": metadata_result["path"],
                "lines_changed": lines_changed,
            },
        )

    except Exception as e:
        logger.exception(f"Error persisting patch: {e}")
        return error_result(f"Failed to save changes: {str(e)}")


# =============================================================================
# replace_content Tool
# =============================================================================


@system_tool(
    id="replace_content",
    name="Replace Content",
    description="Replace entire file content or create new file. For workflows/modules: validates syntax and confirms entity_type matches content (e.g., workflow must have @workflow decorator). Use when: (1) creating new files, (2) patch_content fails due to syntax issues, (3) file is small and full replacement is simpler. Prefer patch_content for targeted edits.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity. Must match content (e.g., workflow code must have @workflow decorator)",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID. Omit for global scope. Not applicable to modules.",
            },
            "content": {
                "type": "string",
                "description": "New file content",
            },
        },
        "required": ["entity_type", "path", "content"],
    },
)
async def replace_content(
    context: Any,
    entity_type: str,
    path: str,
    content: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> str:
    """Replace entire file content or create a new file."""
    logger.info(f"MCP replace_content: entity_type={entity_type}, path={path}")

    if not path:
        return json.dumps({"error": "path is required"})
    if not content:
        return json.dumps({"error": "content is required"})
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return json.dumps({"error": f"Invalid entity_type: {entity_type}"})
    if entity_type == "app_file" and not app_id:
        return json.dumps({"error": "app_id is required for app_file entity type"})

    content = _normalize_line_endings(content)

    try:
        if entity_type == "app_file":
            # app_id is validated above, assert for type narrowing
            assert app_id is not None
            created = await _replace_app_file(context, app_id, path, content)
        elif entity_type == "text":
            # Text files go directly to workspace_files without validation
            created = await _replace_text_file(context, path, content)
        else:
            # Validate entity_type matches content before writing (workflow/module)
            validation_error = _validate_entity_type_match(entity_type, content)
            if validation_error:
                return json.dumps({
                    "success": False,
                    "error": validation_error,
                })

            created = await _replace_workspace_file(
                context, entity_type, path, content, organization_id
            )

        return json.dumps({
            "success": True,
            "path": path,
            "entity_type": entity_type,
            "organization_id": organization_id,
            "app_id": app_id,
            "created": created,
        })

    except Exception as e:
        logger.exception(f"Error in replace_content: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
        })


# =============================================================================
# delete_content Tool - Helper Functions
# =============================================================================


async def _delete_app_file(db, context: Any, app_id: str, path: str) -> bool:
    """Delete an app file. Returns True if deleted."""
    from src.core.pubsub import publish_app_code_file_update

    app_uuid = UUID(app_id)
    app = await db.get(Application, app_uuid)

    if not app or not app.draft_version_id:
        return False

    if not context.is_platform_admin and context.org_id:
        if app.organization_id and app.organization_id != context.org_id:
            return False

    query = select(AppFile).where(
        AppFile.app_version_id == app.draft_version_id,
        AppFile.path == path.strip("/"),
    )
    result = await db.execute(query)
    file = result.scalar_one_or_none()

    if not file:
        return False

    await db.delete(file)

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

    return True


async def _delete_workflow(
    db, context: Any, path: str, organization_id: str | None
) -> bool:
    """Deactivate a workflow. Returns True if found and deactivated."""
    query = select(Workflow).where(
        Workflow.path == path,
        Workflow.is_active == True,  # noqa: E712
    )

    if organization_id:
        org_uuid = UUID(organization_id)
        query = query.where(Workflow.organization_id == org_uuid)
    elif not context.is_platform_admin and context.org_id:
        query = query.where(
            (Workflow.organization_id == context.org_id)
            | (Workflow.organization_id.is_(None))
        )

    result = await db.execute(query)
    workflow = result.scalar_one_or_none()

    if not workflow:
        return False

    workflow.is_active = False
    return True


async def _delete_module(db, context: Any, path: str) -> bool:
    """Mark a module as deleted. Returns True if found and marked."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.path == path,
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    result = await db.execute(query)
    module = result.scalar_one_or_none()

    if not module:
        return False

    module.is_deleted = True
    return True


async def _delete_text_file(db, context: Any, path: str) -> bool:
    """Mark a text file as deleted. Returns True if found and marked."""
    query = select(WorkspaceFile).where(
        WorkspaceFile.path == path,
        WorkspaceFile.entity_type == "text",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )

    result = await db.execute(query)
    text_file = result.scalar_one_or_none()

    if not text_file:
        return False

    text_file.is_deleted = True
    return True


# =============================================================================
# delete_content Tool
# =============================================================================


@system_tool(
    id="delete_content",
    name="Delete Content",
    description="Delete a file. For workflows, this deactivates the workflow. For modules, marks as deleted. For app files, removes from the draft version.",
    category=ToolCategory.CODE_EDITOR,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "enum": ["app_file", "workflow", "module", "text"],
                "description": "Type of entity to delete",
            },
            "app_id": {
                "type": "string",
                "description": "For app_file: the app UUID (required)",
            },
            "path": {
                "type": "string",
                "description": "File path to delete (required)",
            },
            "organization_id": {
                "type": "string",
                "description": "For workflow: the organization UUID (optional). Not applicable to modules.",
            },
        },
        "required": ["entity_type", "path"],
    },
)
async def delete_content(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> CallToolResult:
    """Delete a file."""
    logger.info(f"MCP delete_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return error_result(f"Invalid entity_type: {entity_type}")
    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    try:
        async with get_db_context() as db:
            if entity_type == "app_file":
                # app_id is validated above, assert for type narrowing
                assert app_id is not None
                deleted = await _delete_app_file(db, context, app_id, path)
            elif entity_type == "workflow":
                deleted = await _delete_workflow(db, context, path, organization_id)
            elif entity_type == "module":
                deleted = await _delete_module(db, context, path)
            elif entity_type == "text":
                deleted = await _delete_text_file(db, context, path)
            else:
                deleted = False

            if not deleted:
                return error_result(f"File not found: {path}")

            await db.commit()

        return success_result(
            f"Deleted {path}",
            {
                "success": True,
                "path": path,
                "entity_type": entity_type,
            },
        )

    except Exception as e:
        logger.exception(f"Error in delete_content: {e}")
        return error_result(str(e))