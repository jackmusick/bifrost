"""
Git Serialization Service

DEPRECATED: This module is deprecated and will be removed in a future version.
Use github_sync.py instead, which handles all serialization/deserialization
via the GitHub REST API without requiring a local git folder.

The new API-only approach:
- Reads/writes files directly via GitHub API (no local filesystem)
- Tracks changes via github_sha per file in workspace_files table
- Eliminates the need for local git folder staging

Legacy description:
Handles serialization and deserialization of workspace content to/from git folder.
This is used for git operations (push/pull) where:
- DB is the source of truth
- Git folder is a staging area for git operations

Serialization (Phase 3 - DB -> Git):
- Serialize workflows, modules from DB to .py files
- Serialize forms, apps, agents from DB to .json files
- Transform workflow UUIDs to path refs for portable JSON exports
- Lazy file updates (skip unchanged files via hash comparison)

Deserialization (Phase 4 - Git -> DB):
- Import .py files first (creates/updates workflows and modules with UUIDs)
- Import .json files second (forms/apps/agents) with path ref -> UUID resolution
- Import other files to S3

Workflow references in JSON files (forms, apps, agents) are transformed:
- Export (DB -> Git): UUID -> path::function_name
- Import (Git -> DB): path::function_name -> UUID

The _export metadata in JSON files tracks which fields contain workflow refs.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.auth import ExecutionContext
from src.models import (
    Agent,
    Form,
    Workflow,
    WorkspaceFile,
)
from src.models.orm.applications import Application, AppPage, AppComponent, AppVersion

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


def compute_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def hash_file(path: Path) -> str | None:
    """Compute SHA-256 hash of a local file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return compute_file_hash(path.read_bytes())


def find_fields_with_value(data: Any, value: str, prefix: str = "") -> list[str]:
    """
    Find all field paths in a nested dict/list structure that contain a specific value.

    Args:
        data: The data structure to search (dict, list, or primitive)
        value: The string value to search for
        prefix: Current path prefix for recursive calls

    Returns:
        List of field paths (e.g., ["workflow_id", "form_schema.fields.0.data_provider_id"])
    """
    found_fields: list[str] = []

    if isinstance(data, dict):
        for key, val in data.items():
            current_path = f"{prefix}.{key}" if prefix else key
            if val == value:
                found_fields.append(current_path)
            elif isinstance(val, (dict, list)):
                found_fields.extend(find_fields_with_value(val, value, current_path))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current_path = f"{prefix}.{idx}"
            if item == value:
                found_fields.append(current_path)
            elif isinstance(item, (dict, list)):
                found_fields.extend(find_fields_with_value(item, value, current_path))

    return found_fields


# =============================================================================
# Data Retrieval Functions
# =============================================================================


async def get_all_workflows(db: AsyncSession) -> list[Workflow]:
    """Get all active workflows from the database."""
    stmt = select(Workflow).where(Workflow.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_modules(db: AsyncSession) -> list[WorkspaceFile]:
    """
    Get all module files from the database.

    Modules are Python files without workflow/data_provider decorators,
    stored in workspace_files with entity_type='module'.
    """
    stmt = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_forms(db: AsyncSession) -> list[Form]:
    """Get all active forms with their fields."""
    stmt = (
        select(Form)
        .options(selectinload(Form.fields))
        .where(Form.is_active == True)  # noqa: E712
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_agents(db: AsyncSession) -> list[Agent]:
    """Get all active agents with their tools and delegations."""
    stmt = (
        select(Agent)
        .options(
            selectinload(Agent.tools),
            selectinload(Agent.delegated_agents),
        )
        .where(Agent.is_active == True)  # noqa: E712
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_apps(db: AsyncSession) -> list[Application]:
    """Get all applications with their draft version pages and components."""
    stmt = (
        select(Application)
        .options(
            selectinload(Application.draft_version_ref).selectinload(AppVersion.pages).selectinload(AppPage.components),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_non_entity_workspace_files(db: AsyncSession) -> list[WorkspaceFile]:
    """
    Get workspace files that are not platform entities.

    These are files stored in S3 that need to be downloaded to the git folder
    (e.g., configuration files, assets, non-Python files).
    """
    stmt = select(WorkspaceFile).where(
        WorkspaceFile.is_deleted == False,  # noqa: E712
        # Exclude platform entity types (their content comes from DB tables)
        ~WorkspaceFile.entity_type.in_(["workflow", "form", "app", "agent", "module"]),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# =============================================================================
# Serialization Functions
# =============================================================================


def serialize_form_to_dict(form: Form, workflow_map: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """
    Serialize a Form to a dictionary, transforming workflow UUIDs to path refs.

    Args:
        form: Form ORM instance with fields loaded
        workflow_map: Mapping of workflow UUID string -> "path::function_name"

    Returns:
        Tuple of (serialized dict, list of transformed field names)
    """
    # Convert fields to form_schema format
    fields_data = []
    for field in sorted(form.fields, key=lambda f: f.position):
        field_data: dict[str, Any] = {
            "name": field.name,
            "type": field.type,
            "required": field.required,
        }

        if field.label:
            field_data["label"] = field.label
        if field.placeholder:
            field_data["placeholder"] = field.placeholder
        if field.help_text:
            field_data["help_text"] = field.help_text
        if field.default_value is not None:
            field_data["default_value"] = field.default_value
        if field.options:
            field_data["options"] = field.options
        if field.data_provider_id:
            field_data["data_provider_id"] = str(field.data_provider_id)
        if field.data_provider_inputs:
            field_data["data_provider_inputs"] = field.data_provider_inputs
        if field.visibility_expression:
            field_data["visibility_expression"] = field.visibility_expression
        if field.validation:
            field_data["validation"] = field.validation
        if field.allowed_types:
            field_data["allowed_types"] = field.allowed_types
        if field.multiple is not None:
            field_data["multiple"] = field.multiple
        if field.max_size_mb:
            field_data["max_size_mb"] = field.max_size_mb
        if field.content:
            field_data["content"] = field.content

        fields_data.append(field_data)

    form_schema = {"fields": fields_data}

    # Build form JSON
    form_data: dict[str, Any] = {
        "id": str(form.id),
        "name": form.name,
        "description": form.description,
        "workflow_id": form.workflow_id,
        "launch_workflow_id": form.launch_workflow_id,
        "form_schema": form_schema,
        "is_active": form.is_active,
        "created_by": form.created_by,
        "created_at": form.created_at.isoformat() + "Z" if form.created_at else None,
        "updated_at": form.updated_at.isoformat() + "Z" if form.updated_at else None,
        "allowed_query_params": form.allowed_query_params,
        "default_launch_params": form.default_launch_params,
    }

    # Transform workflow UUIDs to path refs
    transformed_fields = transform_workflow_refs(form_data, workflow_map)

    return form_data, transformed_fields


def serialize_agent_to_dict(agent: Agent, workflow_map: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """
    Serialize an Agent to a dictionary, transforming workflow UUIDs to path refs.

    Args:
        agent: Agent ORM instance with tools and delegations loaded
        workflow_map: Mapping of workflow UUID string -> "path::function_name"

    Returns:
        Tuple of (serialized dict, list of transformed field names)
    """
    # Get tool IDs (workflow UUIDs)
    tool_ids = [str(tool.id) for tool in agent.tools]

    # Get delegated agent IDs
    delegated_agent_ids = [str(da.id) for da in agent.delegated_agents]

    agent_data: dict[str, Any] = {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "channels": agent.channels,
        "access_level": agent.access_level.value if agent.access_level else None,
        "is_active": agent.is_active,
        "is_coding_mode": agent.is_coding_mode,
        "is_system": agent.is_system,
        "knowledge_sources": agent.knowledge_sources,
        "system_tools": agent.system_tools,
        "tool_ids": tool_ids,
        "delegated_agent_ids": delegated_agent_ids,
        "created_by": agent.created_by,
        "created_at": agent.created_at.isoformat() + "Z" if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() + "Z" if agent.updated_at else None,
    }

    # Transform workflow UUIDs in tool_ids to path refs
    transformed_fields = transform_workflow_refs(agent_data, workflow_map)

    return agent_data, transformed_fields


def serialize_app_to_dict(app: Application, workflow_map: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """
    Serialize an Application to a dictionary, transforming workflow UUIDs to path refs.

    Args:
        app: Application ORM instance with draft version, pages, and components loaded
        workflow_map: Mapping of workflow UUID string -> "path::function_name"

    Returns:
        Tuple of (serialized dict, list of transformed field names)
    """
    # Build pages data from draft version
    pages_data = []
    if app.draft_version_ref and app.draft_version_ref.pages:
        for page in sorted(app.draft_version_ref.pages, key=lambda p: p.page_order):
            page_data: dict[str, Any] = {
                "page_id": page.page_id,
                "title": page.title,
                "path": page.path,
                "data_sources": page.data_sources,
                "variables": page.variables,
                "permission": page.permission,
                "page_order": page.page_order,
            }

            if page.launch_workflow_id:
                page_data["launch_workflow_id"] = str(page.launch_workflow_id)
            if page.launch_workflow_params:
                page_data["launch_workflow_params"] = page.launch_workflow_params
            if page.launch_workflow_data_source_id:
                page_data["launch_workflow_data_source_id"] = page.launch_workflow_data_source_id

            # Serialize components as a tree structure
            components_data = serialize_components_tree(page.components)
            page_data["components"] = components_data

            pages_data.append(page_data)

    app_data: dict[str, Any] = {
        "id": str(app.id),
        "name": app.name,
        "slug": app.slug,
        "description": app.description,
        "icon": app.icon,
        "navigation": app.navigation,
        "permissions": app.permissions,
        "access_level": app.access_level,
        "pages": pages_data,
        "created_by": app.created_by,
        "created_at": app.created_at.isoformat() + "Z" if app.created_at else None,
        "updated_at": app.updated_at.isoformat() + "Z" if app.updated_at else None,
    }

    # Transform workflow UUIDs to path refs
    transformed_fields = transform_workflow_refs(app_data, workflow_map)

    return app_data, transformed_fields


def serialize_components_tree(components: list[AppComponent]) -> list[dict[str, Any]]:
    """
    Serialize app components into a tree structure.

    Components have parent_id references that form a tree.
    This builds the tree and returns it as nested dicts.
    """
    # Find root components (parent_id is None)
    roots = [c for c in components if c.parent_id is None]

    def serialize_component(comp: AppComponent) -> dict[str, Any]:
        data: dict[str, Any] = {
            "component_id": comp.component_id,
            "type": comp.type,
            "props": comp.props,
            "component_order": comp.component_order,
        }

        if comp.visible:
            data["visible"] = comp.visible
        if comp.width:
            data["width"] = comp.width
        if comp.loading_workflows:
            data["loading_workflows"] = comp.loading_workflows

        # Find children
        children = [c for c in components if c.parent_id == comp.id]
        if children:
            children_sorted = sorted(children, key=lambda c: c.component_order)
            data["children"] = [serialize_component(child) for child in children_sorted]

        return data

    roots_sorted = sorted(roots, key=lambda c: c.component_order)
    return [serialize_component(root) for root in roots_sorted]


def transform_workflow_refs(data: dict[str, Any], workflow_map: dict[str, str]) -> list[str]:
    """
    Transform workflow UUIDs to path refs in a data structure.

    Does string replacement in the JSON representation to handle all
    locations where UUIDs might appear.

    Args:
        data: The dictionary to transform (modified in place)
        workflow_map: Mapping of workflow UUID string -> "path::function_name"

    Returns:
        List of field paths that were transformed
    """
    transformed_fields: list[str] = []

    # Convert to JSON string for replacement
    json_str = json.dumps(data)

    for uuid_str, path_ref in workflow_map.items():
        # Find fields containing this UUID before replacement
        fields = find_fields_with_value(data, uuid_str)
        if fields:
            transformed_fields.extend(fields)
            # Replace in JSON string
            json_str = json_str.replace(f'"{uuid_str}"', f'"{path_ref}"')

    # Parse back and update data in place
    if transformed_fields:
        updated = json.loads(json_str)
        data.clear()
        data.update(updated)

    return list(set(transformed_fields))  # Remove duplicates


# =============================================================================
# Main Serialization Functions
# =============================================================================


async def serialize_platform_entities(
    db: AsyncSession,
    git_path: Path,
    workflow_map: dict[str, str],
) -> dict[str, int]:
    """
    Serialize forms, apps, and agents to JSON files with workflow ref transformation.

    Args:
        db: Database session
        git_path: Path to git folder
        workflow_map: Mapping of workflow UUID -> "path::function_name"

    Returns:
        Dict with counts: {"forms": N, "apps": N, "agents": N}
    """
    counts = {"forms": 0, "apps": 0, "agents": 0}

    # Serialize forms
    forms = await get_all_forms(db)
    for form in forms:
        if not form.file_path:
            # Generate path for forms without file_path
            form_path = f"forms/{form.name.lower().replace(' ', '_')}.form.json"
        else:
            form_path = form.file_path

        form_data, transformed_fields = serialize_form_to_dict(form, workflow_map)

        # Add export metadata if any fields were transformed
        if transformed_fields:
            form_data["_export"] = {"workflow_refs": transformed_fields}

        file_path = git_path / form_path
        content = json.dumps(form_data, indent=2).encode("utf-8")

        # Lazy update - skip if unchanged
        if not file_path.exists() or compute_file_hash(content) != hash_file(file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            counts["forms"] += 1
            logger.debug(f"Serialized form: {form.name} to {form_path}")

    # Serialize agents
    agents = await get_all_agents(db)
    for agent in agents:
        if not agent.file_path:
            agent_path = f"agents/{agent.name.lower().replace(' ', '_')}.agent.json"
        else:
            agent_path = agent.file_path

        agent_data, transformed_fields = serialize_agent_to_dict(agent, workflow_map)

        if transformed_fields:
            agent_data["_export"] = {"workflow_refs": transformed_fields}

        file_path = git_path / agent_path
        content = json.dumps(agent_data, indent=2).encode("utf-8")

        if not file_path.exists() or compute_file_hash(content) != hash_file(file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            counts["agents"] += 1
            logger.debug(f"Serialized agent: {agent.name} to {agent_path}")

    # Serialize apps
    apps = await get_all_apps(db)
    for app in apps:
        app_path = f"apps/{app.slug}.app.json"

        app_data, transformed_fields = serialize_app_to_dict(app, workflow_map)

        if transformed_fields:
            app_data["_export"] = {"workflow_refs": transformed_fields}

        file_path = git_path / app_path
        content = json.dumps(app_data, indent=2).encode("utf-8")

        if not file_path.exists() or compute_file_hash(content) != hash_file(file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            counts["apps"] += 1
            logger.debug(f"Serialized app: {app.name} to {app_path}")

    return counts


async def download_s3_files_to_git(
    ctx: ExecutionContext,
    git_path: Path,
) -> int:
    """
    Download non-entity files from S3 to the git folder.

    Lazy: skips files that already exist with the same content hash.

    Args:
        ctx: Execution context with db session
        git_path: Path to git folder

    Returns:
        Number of files downloaded
    """
    from src.config import get_settings
    from src.services.file_storage.s3_client import S3StorageClient

    settings = get_settings()
    s3_client = S3StorageClient(settings)

    workspace_files = await get_non_entity_workspace_files(ctx.db)
    downloaded = 0

    for wf in workspace_files:
        local_path = git_path / wf.path

        # Skip .git folder
        if wf.path.startswith(".git/") or wf.path == ".git":
            continue

        # Skip if local file exists with same hash
        if local_path.exists():
            local_hash = hash_file(local_path)
            if local_hash == wf.content_hash:
                continue

        # Download from S3
        try:
            if not settings.s3_bucket:
                logger.warning(f"S3 bucket not configured, skipping {wf.path}")
                continue

            async with s3_client.get_client() as s3:
                response = await s3.get_object(
                    Bucket=settings.s3_bucket,
                    Key=wf.path,
                )
                content = await response["Body"].read()

            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)
            downloaded += 1
            logger.debug(f"Downloaded S3 file: {wf.path}")
        except Exception as e:
            logger.warning(f"Failed to download S3 file {wf.path}: {e}")

    return downloaded


async def serialize_workspace_to_git(
    ctx: ExecutionContext,
    git_path: Path,
) -> dict[str, Any]:
    """
    Serialize all workspace content from database to git folder.

    This is the main entry point for DB -> git serialization.

    - Platform entities from DB -> files
    - Non-entity files from S3 -> files

    Lazy: skips files that haven't changed (compare hashes).

    Args:
        ctx: Execution context containing db session
        git_path: Path to git folder

    Returns:
        Summary dict with counts of serialized items
    """
    db = ctx.db

    # Build workflow UUID -> path ref map
    workflows = await get_all_workflows(db)
    workflow_map: dict[str, str] = {
        str(wf.id): f"{wf.path}::{wf.function_name}"
        for wf in workflows
    }

    logger.info(f"Serializing workspace to {git_path}")
    logger.debug(f"Built workflow map with {len(workflow_map)} entries")

    # 1. Serialize workflows -> .py files
    workflows_count = 0
    for wf in workflows:
        if not wf.code:
            continue

        file_path = git_path / wf.path
        content = wf.code.encode("utf-8")

        # Lazy update
        if not file_path.exists() or compute_file_hash(content) != hash_file(file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            workflows_count += 1
            logger.debug(f"Serialized workflow: {wf.name} to {wf.path}")

    # 2. Serialize modules -> .py files
    modules = await get_all_modules(db)
    modules_count = 0
    for mod in modules:
        if not mod.content:
            continue

        file_path = git_path / mod.path
        content = mod.content.encode("utf-8")

        if not file_path.exists() or compute_file_hash(content) != hash_file(file_path):
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            modules_count += 1
            logger.debug(f"Serialized module: {mod.path}")

    # 3. Serialize forms/apps/agents -> .json files (with workflow ref transformation)
    entity_counts = await serialize_platform_entities(db, git_path, workflow_map)

    # 4. Download S3 files (lazy - skip if already exists with same hash)
    s3_files_count = await download_s3_files_to_git(ctx, git_path)

    summary = {
        "workflows": workflows_count,
        "modules": modules_count,
        "forms": entity_counts["forms"],
        "apps": entity_counts["apps"],
        "agents": entity_counts["agents"],
        "s3_files": s3_files_count,
        "total": (
            workflows_count + modules_count +
            entity_counts["forms"] + entity_counts["apps"] +
            entity_counts["agents"] + s3_files_count
        ),
    }

    logger.info(f"Serialization complete: {summary}")

    return summary


# =============================================================================
# Deserialization Result Models
# =============================================================================


class UnresolvedRef(BaseModel):
    """A workflow reference that couldn't be resolved during import."""

    file: str
    field: str
    ref: str  # The path::function_name that couldn't be resolved


class DeserializationResult(BaseModel):
    """Result of deserializing git files back to the database."""

    success: bool
    files_processed: int = 0
    unresolved_refs: list[UnresolvedRef] = []
    errors: list[str] = []


# =============================================================================
# Deserialization Helper Functions
# =============================================================================


def get_nested_value(data: dict, field_path: str) -> str | None:
    """
    Get a value from a nested dict using dot notation with array indices.

    Args:
        data: Dictionary to search
        field_path: Dot-separated path like "form_schema.fields.0.workflow_id"

    Returns:
        The value at the path, or None if not found
    """
    parts = field_path.split(".")
    current: Any = data

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            except (ValueError, TypeError):
                current = None
        else:
            return None

        if current is None:
            return None

    return current if isinstance(current, str) else None


def set_nested_value(data: dict, field_path: str, new_value: str) -> None:
    """
    Set a value in a nested dict using dot notation with array indices.

    Args:
        data: Dictionary to modify
        field_path: Dot-separated path like "form_schema.fields.0.workflow_id"
        new_value: New value to set
    """
    parts = field_path.split(".")
    current: Any = data

    for i, part in enumerate(parts[:-1]):
        if isinstance(current, dict):
            if part not in current:
                return  # Path doesn't exist
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return
            except (ValueError, TypeError):
                return
        else:
            return

    # Set the final value
    final_part = parts[-1]
    if isinstance(current, dict):
        current[final_part] = new_value
    elif isinstance(current, list):
        try:
            idx = int(final_part)
            if 0 <= idx < len(current):
                current[idx] = new_value
        except (ValueError, TypeError):
            pass


def transform_path_refs_to_uuids(
    data: dict[str, Any],
    workflow_ref_fields: list[str],
    ref_to_uuid: dict[str, str],
) -> list[UnresolvedRef]:
    """
    Transform path refs back to UUIDs in a data structure.

    Uses the workflow_refs metadata from _export to know which fields to transform.

    Args:
        data: The dictionary to transform (modified in place)
        workflow_ref_fields: List of field paths that contain workflow refs
        ref_to_uuid: Mapping of "path::function_name" -> UUID string

    Returns:
        List of UnresolvedRef for any refs that couldn't be resolved
    """
    unresolved: list[UnresolvedRef] = []

    # Build a reverse map for JSON string replacement
    replacements: dict[str, str] = {}

    for field_path in workflow_ref_fields:
        path_ref = get_nested_value(data, field_path)
        if not path_ref:
            continue

        if path_ref in ref_to_uuid:
            # Found the UUID - add to replacements
            replacements[path_ref] = ref_to_uuid[path_ref]
        else:
            # Couldn't resolve this ref
            unresolved.append(
                UnresolvedRef(file="", field=field_path, ref=path_ref)  # file set by caller
            )

    # Do all replacements via JSON string manipulation
    if replacements:
        json_str = json.dumps(data)
        for path_ref, uuid_str in replacements.items():
            json_str = json_str.replace(f'"{path_ref}"', f'"{uuid_str}"')
        updated = json.loads(json_str)
        data.clear()
        data.update(updated)

    return unresolved


# =============================================================================
# Main Deserialization Functions
# =============================================================================


async def deserialize_git_to_workspace(
    db: AsyncSession,
    git_path: Path,
    files: list[str],
) -> DeserializationResult:
    """
    Import files from git folder back to DB.

    Processing order matters:
    1. .py files first (creates/updates workflows and modules with UUIDs)
    2. .json files second (forms/apps/agents) with path ref -> UUID resolution
    3. Other files -> upload to S3

    Args:
        db: Database session
        git_path: Path to git workspace (e.g., /tmp/bifrost/git)
        files: List of relative file paths to import

    Returns:
        DeserializationResult with success status and any unresolved refs
    """
    from src.services.file_storage import FileStorageService

    result = DeserializationResult(success=True, files_processed=0)
    storage = FileStorageService(db)

    # Separate files by type for ordered processing
    py_files = [f for f in files if f.endswith(".py")]
    json_files = [f for f in files if f.endswith(".json")]
    other_files = [f for f in files if not f.endswith(".py") and not f.endswith(".json")]

    # 1. Process .py files first (workflows and modules)
    for file_path in py_files:
        full_path = git_path / file_path
        if not full_path.exists():
            result.errors.append(f"File not found: {file_path}")
            continue

        try:
            content = full_path.read_bytes()
            await storage.write_file(
                path=file_path,
                content=content,
                updated_by="git_sync",
                force_deactivation=True,  # Skip deactivation protection for git imports
            )
            result.files_processed += 1
            logger.info(f"Imported Python file: {file_path}")
        except Exception as e:
            result.errors.append(f"Failed to import {file_path}: {str(e)}")
            logger.error(f"Failed to import {file_path}: {e}", exc_info=True)

    # Flush to ensure workflows are committed before building ref map
    await db.flush()

    # 2. Build fresh workflow path::function_name -> UUID map
    workflows = await get_all_workflows(db)
    ref_to_uuid: dict[str, str] = {
        f"{wf.path}::{wf.function_name}": str(wf.id) for wf in workflows
    }
    logger.debug(f"Built workflow ref map with {len(ref_to_uuid)} entries")

    # 3. Process .json files (forms, apps, agents)
    for file_path in json_files:
        full_path = git_path / file_path
        if not full_path.exists():
            result.errors.append(f"File not found: {file_path}")
            continue

        try:
            content_str = full_path.read_text(encoding="utf-8")
            data = json.loads(content_str)

            # Get export metadata and remove it before saving
            export_meta = data.pop("_export", {})
            workflow_ref_fields = export_meta.get("workflow_refs", [])

            # Resolve path refs -> UUIDs
            file_unresolved = transform_path_refs_to_uuids(
                data, workflow_ref_fields, ref_to_uuid
            )

            # Update file path in unresolved refs
            for ref in file_unresolved:
                ref.file = file_path

            if file_unresolved:
                result.unresolved_refs.extend(file_unresolved)
                result.success = False
                logger.warning(
                    f"Skipping {file_path} due to {len(file_unresolved)} unresolved refs"
                )
                # Don't import files with unresolved refs
                continue

            # Write the resolved JSON back through FileStorageService
            final_content = json.dumps(data, indent=2).encode("utf-8")
            await storage.write_file(
                path=file_path,
                content=final_content,
                updated_by="git_sync",
            )
            result.files_processed += 1
            logger.info(f"Imported JSON file: {file_path}")

        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON in {file_path}: {str(e)}")
            logger.error(f"Invalid JSON in {file_path}: {e}")
        except Exception as e:
            result.errors.append(f"Failed to import {file_path}: {str(e)}")
            logger.error(f"Failed to import {file_path}: {e}", exc_info=True)

    # 4. Process other files -> S3
    for file_path in other_files:
        full_path = git_path / file_path
        if not full_path.exists():
            result.errors.append(f"File not found: {file_path}")
            continue

        try:
            content = full_path.read_bytes()
            await storage.write_file(
                path=file_path,
                content=content,
                updated_by="git_sync",
            )
            result.files_processed += 1
            logger.info(f"Imported file to S3: {file_path}")
        except Exception as e:
            result.errors.append(f"Failed to import {file_path}: {str(e)}")
            logger.error(f"Failed to import {file_path}: {e}", exc_info=True)

    if result.errors:
        result.success = False

    logger.info(
        f"Deserialization complete: {result.files_processed} files processed, "
        f"{len(result.unresolved_refs)} unresolved refs, "
        f"{len(result.errors)} errors"
    )

    return result


async def deserialize_all_from_git(
    db: AsyncSession,
    git_path: Path,
) -> DeserializationResult:
    """
    Import all files from git folder to DB.

    Scans the git folder for all files and imports them.

    Args:
        db: Database session
        git_path: Path to git workspace

    Returns:
        DeserializationResult with success status and any unresolved refs
    """
    # Collect all files (excluding .git folder)
    all_files: list[str] = []

    for path in git_path.rglob("*"):
        if path.is_file():
            rel_path = str(path.relative_to(git_path))
            # Skip .git folder
            if rel_path.startswith(".git/") or rel_path == ".git":
                continue
            all_files.append(rel_path)

    logger.info(f"Found {len(all_files)} files to import from {git_path}")

    return await deserialize_git_to_workspace(db, git_path, all_files)


# =============================================================================
# Reference Resolution
# =============================================================================


class RefResolutionResult(BaseModel):
    """Result of applying reference resolutions."""

    success: bool
    files_updated: int = 0
    errors: list[str] = []


async def apply_ref_resolutions(
    ctx: ExecutionContext,
    git_path: Path,
    resolutions: list[Any],  # List of RefResolution from contracts
) -> RefResolutionResult:
    """
    Apply manual workflow reference resolutions.

    When automatic resolution fails during import, the user can manually map
    unresolved path refs to workflow IDs. This function applies those mappings
    and completes the import.

    Args:
        ctx: Execution context with db session
        git_path: Path to git workspace
        resolutions: List of RefResolution objects with file, field, ref, resolved_workflow_id

    Returns:
        RefResolutionResult with success status and errors
    """
    from src.services.file_storage.service import FileStorageService

    errors: list[str] = []
    files_updated = 0

    # Group resolutions by file
    by_file: dict[str, list[Any]] = {}
    for res in resolutions:
        if res.file not in by_file:
            by_file[res.file] = []
        by_file[res.file].append(res)

    storage = FileStorageService(ctx.db)

    for file_path, file_resolutions in by_file.items():
        try:
            full_path = git_path / file_path

            if not full_path.exists():
                errors.append(f"File not found: {file_path}")
                continue

            # Read the JSON file
            content = full_path.read_text(encoding="utf-8")
            data = json.loads(content)

            # Apply each resolution
            for res in file_resolutions:
                # Get current value to verify it matches the expected ref
                current_value = get_nested_value(data, res.field)
                if current_value != res.ref:
                    errors.append(
                        f"{file_path}: Field {res.field} has value '{current_value}', "
                        f"expected '{res.ref}'"
                    )
                    continue

                # Replace with resolved workflow ID
                set_nested_value(data, res.field, res.resolved_workflow_id)

            # Remove _export metadata since we're resolving everything
            if "_export" in data:
                del data["_export"]

            # Write back and import to DB
            full_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

            # Import the file to DB
            content_bytes = full_path.read_bytes()
            await storage.write_file(file_path, content_bytes, "system")
            files_updated += 1

        except Exception as e:
            errors.append(f"{file_path}: {str(e)}")

    return RefResolutionResult(
        success=len(errors) == 0,
        files_updated=files_updated,
        errors=errors
    )
