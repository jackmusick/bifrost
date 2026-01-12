"""
Workflow reference translation utilities for git sync.

Handles translation between workflow UUIDs and portable path::function_name references.
This enables forms, agents, and apps to be exported/imported across environments.

Export (DB → Git): UUID → "workflows/my_module.py::my_function"
Import (Git → DB): "workflows/my_module.py::my_function" → UUID
"""

import json
import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Workflow

logger = logging.getLogger(__name__)


class UnresolvedRef(BaseModel):
    """A workflow reference that couldn't be resolved during import."""

    file: str
    field: str
    ref: str  # The path::function_name that couldn't be resolved


class TransformResult(BaseModel):
    """Result of transforming workflow references."""

    transformed_fields: list[str]
    unresolved_refs: list[UnresolvedRef]


# =============================================================================
# Map Building Functions
# =============================================================================


async def build_workflow_ref_map(db: AsyncSession) -> dict[str, str]:
    """
    Build mapping of workflow UUID -> path::function_name for export.

    Used when serializing entities to transform UUIDs to portable references.

    Args:
        db: Database session

    Returns:
        Dict mapping UUID string -> "path::function_name"
    """
    stmt = select(Workflow).where(Workflow.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    workflows = result.scalars().all()

    workflow_map = {
        str(wf.id): f"{wf.path}::{wf.function_name}"
        for wf in workflows
        if wf.path and wf.function_name
    }

    logger.debug(f"Built workflow ref map with {len(workflow_map)} entries")
    return workflow_map


async def build_ref_to_uuid_map(db: AsyncSession) -> dict[str, str]:
    """
    Build mapping of path::function_name -> UUID for import.

    Used when deserializing entities to resolve references back to UUIDs.

    Args:
        db: Database session

    Returns:
        Dict mapping "path::function_name" -> UUID string
    """
    stmt = select(Workflow).where(Workflow.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    workflows = result.scalars().all()

    ref_map = {
        f"{wf.path}::{wf.function_name}": str(wf.id)
        for wf in workflows
        if wf.path and wf.function_name
    }

    logger.debug(f"Built ref-to-UUID map with {len(ref_map)} entries")
    return ref_map


# =============================================================================
# Helper Functions
# =============================================================================


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

    for part in parts[:-1]:
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


# =============================================================================
# Transform Functions
# =============================================================================


def transform_workflow_refs(data: dict[str, Any], workflow_map: dict[str, str]) -> list[str]:
    """
    Transform workflow UUIDs to path refs in a data structure (for export).

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


def transform_path_refs_to_uuids(
    data: dict[str, Any],
    workflow_ref_fields: list[str],
    ref_to_uuid: dict[str, str],
    file_path: str = "",
) -> list[UnresolvedRef]:
    """
    Transform path refs back to UUIDs in a data structure (for import).

    Uses the workflow_refs metadata from _export to know which fields to transform.

    Args:
        data: The dictionary to transform (modified in place)
        workflow_ref_fields: List of field paths that contain workflow refs
        ref_to_uuid: Mapping of "path::function_name" -> UUID string
        file_path: File path for error reporting

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
                UnresolvedRef(file=file_path, field=field_path, ref=path_ref)
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


def add_export_metadata(data: dict[str, Any], transformed_fields: list[str]) -> None:
    """
    Add _export metadata to a serialized entity dict.

    The metadata tracks which fields were transformed so they can be
    resolved back during import.

    Args:
        data: The dictionary to add metadata to (modified in place)
        transformed_fields: List of field paths that were transformed
    """
    if transformed_fields:
        data["_export"] = {"workflow_refs": transformed_fields}


def extract_export_metadata(data: dict[str, Any]) -> list[str]:
    """
    Extract and remove _export metadata from a deserialized entity dict.

    Args:
        data: The dictionary to extract from (modified in place - _export is removed)

    Returns:
        List of field paths that contain workflow refs, or empty list if no metadata
    """
    export_meta = data.pop("_export", {})
    return export_meta.get("workflow_refs", [])
