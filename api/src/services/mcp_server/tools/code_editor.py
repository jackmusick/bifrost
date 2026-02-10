"""
Code Editor MCP Tools - Precision Editing

Tools for searching, reading, and editing code stored in the database:
- app_file (TSX/TypeScript for App Builder)
- workflow (Python workflow code)
- module (Python helper modules via file_index)
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

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastmcp.tools.tool import ToolResult
from sqlalchemy import select

from src.core.database import get_db_context
from src.models.orm.applications import AppFile, Application
from src.models.orm.file_index import FileIndex
from src.models.orm.organizations import Organization
from src.models.orm.workflows import Workflow
from src.services.file_storage import FileStorageService
from src.services.mcp_server.tool_result import (
    error_result,
    format_diff,
    format_file_content,
    format_grep_matches,
    success_result,
)


def _format_deactivation_result(
    path: str,
    pending_deactivations: list[dict[str, Any]],
    available_replacements: list[dict[str, Any]] | None,
) -> ToolResult:
    """
    Format a deactivation protection result for Claude to handle.

    Returns a ToolResult that tells Claude:
    1. Which workflows would be deactivated
    2. What entities (forms, agents) reference them
    3. Available replacement functions (for renames)
    4. How to proceed (apply replacements or force deactivation)
    """
    lines = [
        f"⚠️ Saving {path} would deactivate {len(pending_deactivations)} workflow(s):",
        "",
    ]

    for pd in pending_deactivations:
        lines.append(f"  • {pd['function_name']} ({pd['decorator_type']})")
        if pd["has_executions"]:
            lines.append(f"    - Has execution history (last: {pd['last_execution_at'] or 'unknown'})")
        if pd["endpoint_enabled"]:
            lines.append("    - Has API endpoint enabled")
        if pd["affected_entities"]:
            lines.append("    - Referenced by:")
            for ae in pd["affected_entities"][:5]:  # Limit to 5
                lines.append(f"      - {ae['entity_type']}: {ae['name']} ({ae['reference_type']})")
            if len(pd["affected_entities"]) > 5:
                lines.append(f"      - ... and {len(pd['affected_entities']) - 5} more")

    if available_replacements:
        lines.append("")
        lines.append("Possible renames detected:")
        for ar in available_replacements[:3]:  # Top 3 suggestions
            lines.append(f"  • {ar['function_name']} (similarity: {ar['similarity_score']:.0%})")

    lines.extend([
        "",
        "To proceed, you can:",
        "1. Apply replacements: Re-call with replacements={\"<old_workflow_id>\": \"<new_function_name>\"}",
        "2. Force deactivation: Re-call with force_deactivation=true",
        "3. Abort: Do not save this file",
    ])

    return ToolResult(
        content="\n".join(lines),
        structured_content={
            "status": "pending_deactivations",
            "path": path,
            "pending_deactivations": pending_deactivations,
            "available_replacements": available_replacements or [],
            "resolution_options": {
                "apply_replacements": "Re-call with replacements parameter mapping old workflow IDs to new function names",
                "force_deactivation": "Re-call with force_deactivation=true to proceed anyway",
                "abort": "Do not save the file",
            },
        },
    )

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


async def _try_file_index_fallback(path: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """
    Try reading content from file_index table (new workspace architecture).

    This is a fallback for when entity-specific lookups fail.
    Returns same format as _get_content_by_entity.
    """
    try:
        from src.models.orm.file_index import FileIndex
        async with get_db_context() as db:
            result = await db.execute(
                select(FileIndex.content, FileIndex.content_hash).where(
                    FileIndex.path == path
                )
            )
            row = result.one_or_none()
            if row and isinstance(row.content, str) and row.content:
                return (
                    row.content,
                    {"path": path, "source": "file_index"},
                    None,
                )
    except Exception:
        pass  # file_index table may not exist yet during migration
    return None, None, None


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
            workflow = result.scalars().first()

            if not workflow:
                # Try file_index fallback (workspace redesign migration)
                content, metadata, _ = await _try_file_index_fallback(path)
                if content is not None:
                    return content, metadata, None
                return None, None, f"Workflow not found: {path}"

            # Load code from file_index instead of workflows.code column
            code = None
            try:
                from src.models.orm.file_index import FileIndex
                fi_result = await db.execute(
                    select(FileIndex.content).where(FileIndex.path == path)
                )
                code = fi_result.scalar_one_or_none()
            except Exception:
                pass

            if not code:
                # Try file_index fallback (which opens its own session)
                content, metadata, _ = await _try_file_index_fallback(path)
                if content is not None:
                    return content, metadata, None
                return None, None, f"Workflow has no code: {path}"

            return (
                code,
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

        elif entity_type in ("module", "text"):
            # Query file_index for modules and text files
            fi_result = await db.execute(
                select(FileIndex.content).where(FileIndex.path == path)
            )
            fi_content = fi_result.scalar_one_or_none()

            if fi_content is None:
                return None, None, f"File not found: {path}"

            return (
                fi_content,
                {
                    "path": path,
                    "source": "file_index",
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
    from src.services.app_dependencies import sync_file_dependencies

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

        # Sync dependencies (parse source for workflow references)
        await sync_file_dependencies(db, file.id, content, app.organization_id)

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


@dataclass
class WorkspaceWriteResult:
    """Result of writing a workspace file."""

    created: bool
    pending_deactivations: list[dict[str, Any]] | None = None
    available_replacements: list[dict[str, Any]] | None = None


async def _replace_workspace_file(
    context: Any,
    entity_type: str,
    path: str,
    content: str,
    organization_id: str | None,
    force_deactivation: bool = False,
    replacements: dict[str, str] | None = None,
) -> WorkspaceWriteResult:
    """
    Replace or create a workflow/module file.

    Args:
        context: Request context
        entity_type: Type of entity ("workflow" or "module")
        path: File path
        content: File content
        organization_id: Optional organization ID
        force_deactivation: If True, bypass deactivation protection
        replacements: Mapping of old_workflow_id -> new_function_name for renames

    Returns:
        WorkspaceWriteResult with created status and any pending deactivations
    """
    async with get_db_context() as db:
        service = FileStorageService(db)

        # Check if file exists to determine created status
        try:
            await service.read_file(path)
            created = False
        except FileNotFoundError:
            created = True

        # Write through FileStorageService with deactivation protection
        write_result = await service.write_file(
            path=path,
            content=content.encode("utf-8"),
            updated_by=context.user_email or "mcp",
            force_deactivation=force_deactivation,
            replacements=replacements,
        )

        # Check for pending deactivations
        if write_result.pending_deactivations:
            pending = [
                {
                    "id": pd.id,
                    "name": pd.name,
                    "function_name": pd.function_name,
                    "path": pd.path,
                    "description": pd.description,
                    "decorator_type": pd.decorator_type,
                    "has_executions": pd.has_executions,
                    "last_execution_at": pd.last_execution_at,
                    "endpoint_enabled": pd.endpoint_enabled,
                    "affected_entities": pd.affected_entities,
                }
                for pd in write_result.pending_deactivations
            ]
            available = [
                {
                    "function_name": ar.function_name,
                    "name": ar.name,
                    "decorator_type": ar.decorator_type,
                    "similarity_score": ar.similarity_score,
                }
                for ar in (write_result.available_replacements or [])
            ]
            return WorkspaceWriteResult(
                created=created,
                pending_deactivations=pending,
                available_replacements=available,
            )

        return WorkspaceWriteResult(created=created)


async def _replace_text_file(
    context: Any, path: str, content: str
) -> bool:
    """Replace or create a text file (markdown, docs, config). Returns True if created."""
    async with get_db_context() as db:
        service = FileStorageService(db)

        # Check if file exists
        try:
            await service.read_file(path)
            created = False
        except FileNotFoundError:
            created = True

        # Write through FileStorageService
        await service.write_file(
            path=path,
            content=content.encode("utf-8"),
            updated_by=context.user_email or "mcp",
        )

        await db.commit()
        return created


async def _persist_content(
    entity_type: str,
    path: str,
    content: str,
    app_id: str | None,
    organization_id: str | None,
    context: Any,
    force_deactivation: bool = False,
    replacements: dict[str, str] | None = None,
) -> WorkspaceWriteResult | None:
    """
    Persist content changes to the database.

    Args:
        entity_type: Type of entity
        path: File path
        content: New content
        app_id: App ID for app_file entity type
        organization_id: Organization ID
        context: Request context
        force_deactivation: If True, bypass deactivation protection
        replacements: Mapping of old_workflow_id -> new_function_name for renames

    Returns:
        WorkspaceWriteResult if entity is workflow/module with pending deactivations,
        None otherwise
    """
    async with get_db_context() as db:
        if entity_type == "app_file":
            from src.core.pubsub import publish_app_code_file_update
            from src.services.app_dependencies import sync_file_dependencies

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

            # Sync dependencies (parse source for workflow references)
            await sync_file_dependencies(db, file.id, content, app.organization_id)

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
            return None

        elif entity_type in ("workflow", "module"):
            # Route through FileStorageService with deactivation protection
            service = FileStorageService(db)
            write_result = await service.write_file(
                path=path,
                content=content.encode("utf-8"),
                updated_by=context.user_email or "mcp",
                force_deactivation=force_deactivation,
                replacements=replacements,
            )

            # Check for pending deactivations
            if write_result.pending_deactivations:
                pending = [
                    {
                        "id": pd.id,
                        "name": pd.name,
                        "function_name": pd.function_name,
                        "path": pd.path,
                        "description": pd.description,
                        "decorator_type": pd.decorator_type,
                        "has_executions": pd.has_executions,
                        "last_execution_at": pd.last_execution_at,
                        "endpoint_enabled": pd.endpoint_enabled,
                        "affected_entities": pd.affected_entities,
                    }
                    for pd in write_result.pending_deactivations
                ]
                available = [
                    {
                        "function_name": ar.function_name,
                        "name": ar.name,
                        "decorator_type": ar.decorator_type,
                        "similarity_score": ar.similarity_score,
                    }
                    for ar in (write_result.available_replacements or [])
                ]
                return WorkspaceWriteResult(
                    created=False,
                    pending_deactivations=pending,
                    available_replacements=available,
                )

            return None

        return None


# =============================================================================
# list_content Tool
# =============================================================================


async def list_content(
    context: Any,
    entity_type: str | None = None,
    app_id: str | None = None,
    organization_id: str | None = None,
    path_prefix: str | None = None,
) -> ToolResult:
    """List files by entity type."""
    logger.info(f"MCP list_content: entity_type={entity_type}")

    # Validate entity_type if provided
    valid_types = ("app_file", "workflow", "module", "text")
    if entity_type is not None and entity_type not in valid_types:
        return error_result(
            f"Invalid entity_type: {entity_type}. Must be one of: app_file, workflow, module, text"
        )

    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

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

        # Format display
        if not all_files:
            display = "No files found"
        else:
            lines = [f"Found {len(all_files)} file(s):", ""]
            for f in all_files:
                lines.append(f"  {f['path']} ({f.get('entity_type', 'unknown')})")
            display = "\n".join(lines)

        result_data: dict[str, Any] = {
            "files": all_files,
            "count": len(all_files),
        }
        if entity_type:
            result_data["entity_type"] = entity_type

        return success_result(display, result_data)

    except Exception as e:
        logger.exception(f"Error in list_content: {e}")
        return error_result(f"List failed: {str(e)}")


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
    """List modules (Python files without workflow decorators)."""
    from src.services.file_storage.entity_detector import detect_platform_entity_type

    # Get all .py paths from file_index that are NOT workflows
    fi_query = select(FileIndex.path).where(
        FileIndex.path.endswith(".py"),
    )
    if path_prefix:
        fi_query = fi_query.where(FileIndex.path.startswith(path_prefix))

    fi_result = await db.execute(fi_query)
    all_py_paths = {row[0] for row in fi_result.fetchall()}

    # Get workflow paths to exclude
    wf_query = select(Workflow.path).where(
        Workflow.is_active == True,  # noqa: E712
    ).distinct()
    wf_result = await db.execute(wf_query)
    wf_paths = {row[0] for row in wf_result.fetchall()}

    # Modules = Python files that are not workflows
    module_paths = sorted(all_py_paths - wf_paths)
    return [{"path": p} for p in module_paths]


async def _list_text_files(
    db, context: Any, path_prefix: str | None
) -> list[dict[str, Any]]:
    """List text files (non-Python, non-entity files in file_index)."""
    query = select(FileIndex.path).where(
        ~FileIndex.path.endswith(".py"),
        ~FileIndex.path.endswith(".form.json"),
        ~FileIndex.path.endswith(".agent.json"),
        ~FileIndex.path.endswith("/"),
    )
    if path_prefix:
        query = query.where(FileIndex.path.startswith(path_prefix))

    result = await db.execute(query)
    return [{"path": row[0]} for row in result.fetchall()]


# =============================================================================
# search_content Tool
# =============================================================================


async def search_content(
    context: Any,
    pattern: str,
    entity_type: str | None = None,
    app_id: str | None = None,
    path: str | None = None,
    organization_id: str | None = None,
    context_lines: int = 3,
    max_results: int = 20,
) -> ToolResult:
    """Search for regex patterns in code content."""
    logger.info(f"MCP search_content: pattern={pattern}, entity_type={entity_type}")

    if not pattern:
        return error_result("pattern is required")

    # Validate entity_type if provided
    valid_types = ("app_file", "workflow", "module", "text")
    if entity_type is not None and entity_type not in valid_types:
        return error_result(
            f"Invalid entity_type: {entity_type}. Must be one of: app_file, workflow, module, text"
        )

    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return error_result(f"Invalid regex pattern: {e}")

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

        # Format grep-style display
        display = format_grep_matches(matches, pattern)

        return success_result(
            display,
            {
                "matches": matches,
                "total_matches": len(matches),
                "truncated": truncated,
            },
        )

    except Exception as e:
        logger.exception(f"Error in search_content: {e}")
        return error_result(f"Search failed: {str(e)}")


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
    all_workflows = result.scalars().all()

    # Deduplicate by path - multi-function files share identical code
    seen_paths: set[str] = set()
    workflows = []
    for wf in all_workflows:
        if wf.path not in seen_paths:
            seen_paths.add(wf.path)
            workflows.append(wf)

    # Load code from file_index for workflow paths
    from src.models.orm.file_index import FileIndex
    workflow_paths = [wf.path for wf in workflows]
    fi_result = await db.execute(
        select(FileIndex.path, FileIndex.content).where(
            FileIndex.path.in_(workflow_paths),
            FileIndex.content.isnot(None),
        )
    )
    fi_code_map = {row.path: row.content for row in fi_result.all()}

    matches = []
    for wf in workflows:
        code = fi_code_map.get(wf.path)
        if not code:
            continue

        content = _normalize_line_endings(code)
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
    """Search modules (non-workflow Python files) for regex matches."""
    # Get workflow paths to exclude
    wf_query = select(Workflow.path).where(
        Workflow.is_active == True,  # noqa: E712
    ).distinct()
    wf_result = await db.execute(wf_query)
    wf_paths = {row[0] for row in wf_result.fetchall()}

    query = select(FileIndex.path, FileIndex.content).where(
        FileIndex.path.endswith(".py"),
        FileIndex.content.isnot(None),
    )
    if path:
        query = query.where(FileIndex.path == path)

    result = await db.execute(query)
    all_files = result.all()

    matches = []
    for row in all_files:
        if row.path in wf_paths:
            continue  # Skip workflow files

        content = _normalize_line_endings(row.content)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": row.path,
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
    """Search text files (non-Python, non-entity) for regex matches."""
    query = select(FileIndex.path, FileIndex.content).where(
        ~FileIndex.path.endswith(".py"),
        ~FileIndex.path.endswith(".form.json"),
        ~FileIndex.path.endswith(".agent.json"),
        ~FileIndex.path.endswith("/"),
        FileIndex.content.isnot(None),
    )
    if path:
        query = query.where(FileIndex.path == path)

    result = await db.execute(query)
    all_files = result.all()

    matches = []
    for row in all_files:
        content = _normalize_line_endings(row.content)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if regex.search(line):
                before, after = _get_lines_with_context(content, i + 1, context_lines)
                matches.append(
                    {
                        "path": row.path,
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


async def read_content_lines(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
    start_line: int = 1,
    end_line: int | None = None,
) -> ToolResult:
    """Read a specific range of lines from a file."""
    logger.info(
        f"MCP read_content_lines: entity_type={entity_type}, path={path}, lines={start_line}-{end_line}"
    )

    if not path:
        return error_result("path is required")

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
    selected_lines_raw: list[str] = []
    selected_lines_numbered: list[str] = []
    for i in range(start_line - 1, end_line):
        if i < len(lines):
            selected_lines_raw.append(lines[i])
            selected_lines_numbered.append(f"{i + 1}: {lines[i]}")

    # Format display with line numbers
    display = format_file_content(
        metadata_result["path"],
        "\n".join(selected_lines_raw),
        start_line,
    )

    return success_result(
        display,
        {
            "path": metadata_result["path"],
            "organization_id": metadata_result.get("organization_id"),
            "app_id": metadata_result.get("app_id"),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "content": "\n".join(selected_lines_numbered),
        },
    )


# =============================================================================
# get_content Tool
# =============================================================================


async def get_content(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> ToolResult:
    """Get the entire content of a file."""
    logger.info(f"MCP get_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")

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

    # Format display with line numbers
    display = format_file_content(metadata_result["path"], content_str)
    if warning:
        display = f"{warning}\n\n{display}"

    result_data: dict[str, Any] = {
        "path": metadata_result["path"],
        "organization_id": metadata_result.get("organization_id"),
        "app_id": metadata_result.get("app_id"),
        "entity_id": metadata_result.get("entity_id"),
        "total_lines": total_lines,
        "content": content_str,
    }

    if truncated:
        result_data["truncated"] = True
        result_data["warning"] = warning

    return success_result(display, result_data)


# =============================================================================
# patch_content Tool
# =============================================================================


async def patch_content(
    context: Any,
    entity_type: str,
    path: str,
    old_string: str,
    new_string: str,
    app_id: str | None = None,
    organization_id: str | None = None,
    force_deactivation: bool = False,
    replacements: dict[str, str] | None = None,
) -> ToolResult:
    """
    Make a surgical edit by replacing a unique string.

    For workflow files, if the edit would deactivate existing workflows (e.g., function
    was renamed or removed), the tool returns information about affected workflows
    instead of proceeding. See replace_content for resolution options.

    Args:
        context: Request context
        entity_type: Type of entity (app_file, workflow, module, text)
        path: File path
        old_string: String to find and replace (must be unique in file)
        new_string: Replacement string
        app_id: App ID (required for app_file)
        organization_id: Organization ID
        force_deactivation: If True, proceed even if workflows would be deactivated
        replacements: Mapping of old_workflow_id -> new_function_name for renames
    """
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
        result = await _persist_content(
            entity_type,
            path,
            new_content,
            app_id,
            organization_id,
            context,
            force_deactivation=force_deactivation,
            replacements=replacements,
        )

        # Check for pending deactivations
        if result and result.pending_deactivations:
            return _format_deactivation_result(
                path,
                result.pending_deactivations,
                result.available_replacements,
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


async def replace_content(
    context: Any,
    entity_type: str,
    path: str,
    content: str,
    app_id: str | None = None,
    organization_id: str | None = None,
    force_deactivation: bool = False,
    replacements: dict[str, str] | None = None,
) -> ToolResult:
    """
    Replace entire file content or create a new file.

    For workflow files, if the save would deactivate existing workflows (e.g., function
    was renamed or removed), the tool returns information about affected workflows
    instead of proceeding. The caller can then:
    1. Apply replacements: Pass replacements={old_workflow_id: new_function_name}
    2. Force deactivation: Pass force_deactivation=True
    3. Abort: Don't save the file

    Args:
        context: Request context
        entity_type: Type of entity (app_file, workflow, module, text)
        path: File path
        content: New file content
        app_id: App ID (required for app_file)
        organization_id: Organization ID
        force_deactivation: If True, proceed even if workflows would be deactivated
        replacements: Mapping of old_workflow_id -> new_function_name for renames
    """
    logger.info(f"MCP replace_content: entity_type={entity_type}, path={path}")

    if not path:
        return error_result("path is required")
    if not content:
        return error_result("content is required")
    if entity_type not in ("app_file", "workflow", "module", "text"):
        return error_result(f"Invalid entity_type: {entity_type}")
    if entity_type == "app_file" and not app_id:
        return error_result("app_id is required for app_file entity type")

    content = _normalize_line_endings(content)

    try:
        if entity_type == "app_file":
            # app_id is validated above, assert for type narrowing
            assert app_id is not None
            created = await _replace_app_file(context, app_id, path, content)
        elif entity_type == "text":
            # Text files go through FileStorageService without validation
            created = await _replace_text_file(context, path, content)
        else:
            # Validate entity_type matches content before writing (workflow/module)
            validation_error = _validate_entity_type_match(entity_type, content)
            if validation_error:
                return error_result(validation_error)

            result = await _replace_workspace_file(
                context,
                entity_type,
                path,
                content,
                organization_id,
                force_deactivation=force_deactivation,
                replacements=replacements,
            )

            # Check for pending deactivations
            if result.pending_deactivations:
                return _format_deactivation_result(
                    path,
                    result.pending_deactivations,
                    result.available_replacements,
                )

            created = result.created

        action = "Created" if created else "Updated"
        return success_result(
            f"{action} {path}",
            {
                "success": True,
                "path": path,
                "entity_type": entity_type,
                "organization_id": organization_id,
                "app_id": app_id,
                "created": created,
            },
        )

    except Exception as e:
        logger.exception(f"Error in replace_content: {e}")
        return error_result(str(e))


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
    workflows = result.scalars().all()

    if not workflows:
        return False

    for workflow in workflows:
        workflow.is_active = False
    return True


async def _delete_module(db, context: Any, path: str) -> bool:
    """Delete a module file. Returns True if found and deleted."""
    from sqlalchemy import delete as sql_delete
    from src.core.module_cache import invalidate_module

    result = await db.execute(
        select(FileIndex.path).where(FileIndex.path == path)
    )
    if result.scalar_one_or_none() is None:
        return False

    await db.execute(sql_delete(FileIndex).where(FileIndex.path == path))
    await invalidate_module(path)
    return True


async def _delete_text_file(db, context: Any, path: str) -> bool:
    """Delete a text file. Returns True if found and deleted."""
    from sqlalchemy import delete as sql_delete

    result = await db.execute(
        select(FileIndex.path).where(FileIndex.path == path)
    )
    if result.scalar_one_or_none() is None:
        return False

    await db.execute(sql_delete(FileIndex).where(FileIndex.path == path))
    return True


# =============================================================================
# delete_content Tool
# =============================================================================


async def delete_content(
    context: Any,
    entity_type: str,
    path: str,
    app_id: str | None = None,
    organization_id: str | None = None,
) -> ToolResult:
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


# =============================================================================
# Tool Registration
# =============================================================================

# Tool metadata for registration
TOOLS = [
    ("list_content", "List Content", "List files by entity type. Returns paths without content."),
    ("search_content", "Search Content", "Search for patterns in code files. Returns matching lines with context."),
    ("read_content_lines", "Read Content Lines", "Read specific line range from a file."),
    ("get_content", "Get Content", "Get entire file content."),
    ("patch_content", "Patch Content", "Surgical edit: replace old_string with new_string."),
    ("replace_content", "Replace Content", "Replace entire file content or create new file."),
    ("delete_content", "Delete Content", "Delete a file."),
]


def register_tools(mcp: Any, get_context_fn: Any) -> None:
    """Register all code editor tools with FastMCP."""
    from src.services.mcp_server.generators.fastmcp_generator import register_tool_with_context

    tool_funcs = {
        "list_content": list_content,
        "search_content": search_content,
        "read_content_lines": read_content_lines,
        "get_content": get_content,
        "patch_content": patch_content,
        "replace_content": replace_content,
        "delete_content": delete_content,
    }

    for tool_id, name, description in TOOLS:
        register_tool_with_context(mcp, tool_funcs[tool_id], tool_id, description, get_context_fn)