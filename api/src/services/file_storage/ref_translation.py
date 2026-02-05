"""
Workflow reference translation utilities for git sync.

Handles translation between workflow UUIDs and portable references.
This enables forms, agents, and apps to be exported/imported across environments.

Portable Ref Format: "workflow::path::function_name"
Example: "workflow::workflows/my_module.py::my_function"

The `portable_ref` column is a Postgres generated column that automatically
computes this value from path and function_name. Direct lookups via this
column eliminate O(n) map building on every sync.

Export (DB → Git): UUID → portable_ref (via column lookup)
Import (Git → DB): portable_ref → UUID (via column lookup)
"""

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Workflow

logger = logging.getLogger(__name__)


# =============================================================================
# Direct Lookup Functions (New - Use portable_ref Column)
# =============================================================================


async def get_portable_ref_for_workflow(db: AsyncSession, workflow_id: UUID | str) -> str | None:
    """
    Get the portable reference for a workflow by ID.

    Uses the portable_ref generated column for O(1) lookup.

    Args:
        db: Database session
        workflow_id: Workflow UUID

    Returns:
        Portable ref string (e.g., "workflow::path::function") or None if not found
    """
    if isinstance(workflow_id, str):
        workflow_id = UUID(workflow_id)

    stmt = select(Workflow.portable_ref).where(
        Workflow.id == workflow_id,
        Workflow.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_workflow_id_for_ref(db: AsyncSession, portable_ref: str) -> str | None:
    """
    Get workflow UUID for a portable reference.

    Uses the portable_ref column index for O(1) lookup.

    Supports both formats for backward compatibility:
    - New format: "workflow::path::function_name"
    - Legacy format: "path::function_name" (auto-prefixed with "workflow::")

    Args:
        db: Database session
        portable_ref: Portable reference string

    Returns:
        UUID string or None if not found
    """
    # Normalize to new format if needed
    normalized_ref = normalize_portable_ref(portable_ref)

    stmt = select(Workflow.id).where(
        Workflow.portable_ref == normalized_ref,
        Workflow.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    workflow_id = result.scalar_one_or_none()
    return str(workflow_id) if workflow_id else None


def normalize_portable_ref(ref: str) -> str:
    """
    Normalize a portable ref to the canonical format.

    Converts legacy "path::function" format to "workflow::path::function".

    Args:
        ref: Portable reference (may be legacy or new format)

    Returns:
        Normalized portable ref with "workflow::" prefix
    """
    if ref.startswith("workflow::"):
        return ref
    # Legacy format - add prefix
    return f"workflow::{ref}"


def strip_portable_ref_prefix(ref: str) -> str:
    """
    Strip the "workflow::" prefix from a portable ref.

    Used when displaying refs to users or in exported files
    where the prefix may be redundant.

    Args:
        ref: Portable reference with or without prefix

    Returns:
        Reference without "workflow::" prefix
    """
    if ref.startswith("workflow::"):
        return ref[10:]  # len("workflow::") == 10
    return ref


# =============================================================================
# Map Building Functions (Legacy - Still Used During Transition)
# =============================================================================


async def build_workflow_ref_map(db: AsyncSession) -> dict[str, str]:
    """
    Build mapping of workflow UUID -> portable_ref for export.

    INCLUDES INACTIVE WORKFLOWS for serialization consistency.
    This prevents false conflicts when agents/forms reference
    workflows that were deactivated after the last sync.

    Note: Import operations should use build_ref_to_uuid_map() which
    filters to active workflows only (don't resolve to deactivated).

    Args:
        db: Database session

    Returns:
        Dict mapping UUID string -> portable_ref (without "workflow::" prefix for compatibility)
    """
    stmt = select(Workflow.id, Workflow.portable_ref).where(
        Workflow.portable_ref.isnot(None),
        # No is_active filter - include all for consistent serialization
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Strip "workflow::" prefix for backward compatibility with existing code
    workflow_map = {
        str(row.id): strip_portable_ref_prefix(row.portable_ref)
        for row in rows
        if row.portable_ref
    }

    logger.debug(f"Built workflow ref map with {len(workflow_map)} entries (includes inactive)")
    return workflow_map


async def build_ref_to_uuid_map(db: AsyncSession) -> dict[str, str]:
    """
    Build mapping of portable_ref -> UUID for import.

    Now uses the portable_ref column directly instead of computing refs.

    Note: This function is kept for backward compatibility during the transition
    to direct lookups. New code should use get_workflow_id_for_ref().

    The map includes both formats (with and without prefix) for compatibility:
    - "workflow::path::function" -> UUID
    - "path::function" -> UUID (legacy format still supported in imports)

    Args:
        db: Database session

    Returns:
        Dict mapping portable_ref -> UUID string
    """
    stmt = select(Workflow.id, Workflow.portable_ref).where(
        Workflow.is_active == True,  # noqa: E712
        Workflow.portable_ref.isnot(None),
    )
    result = await db.execute(stmt)
    rows = result.all()

    ref_map: dict[str, str] = {}
    for row in rows:
        if row.portable_ref:
            uuid_str = str(row.id)
            # Add both formats for backward compatibility
            ref_map[row.portable_ref] = uuid_str
            # Also add without prefix (legacy format)
            stripped = strip_portable_ref_prefix(row.portable_ref)
            if stripped != row.portable_ref:
                ref_map[stripped] = uuid_str

    logger.debug(f"Built ref-to-UUID map with {len(ref_map)} entries")
    return ref_map


# =============================================================================
# Helper Functions
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


# =============================================================================
# App Source Transformation Functions
# =============================================================================

# Pattern to match useWorkflow('...') or useWorkflow("...")
# Captures the quote style and the argument
USE_WORKFLOW_PATTERN = re.compile(r"useWorkflow\((['\"])([^'\"]+)\1\)")


def transform_app_source_uuids_to_refs(
    source: str,
    workflow_map: dict[str, str],
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{uuid}') to useWorkflow('{ref}') in TSX source.

    Scans source code for useWorkflow() calls and replaces UUIDs with
    portable workflow references (path::function_name format).

    Args:
        source: TSX/TypeScript source code
        workflow_map: Mapping of UUID string -> "path::function_name"

    Returns:
        Tuple of (transformed_source, list_of_transformed_uuids)
    """
    if not source or not workflow_map:
        return source, []

    transformed_uuids: list[str] = []

    def replace_uuid(match: re.Match[str]) -> str:
        quote = match.group(1)
        arg = match.group(2)

        if arg in workflow_map:
            transformed_uuids.append(arg)
            return f"useWorkflow({quote}{workflow_map[arg]}{quote})"
        return match.group(0)

    result = USE_WORKFLOW_PATTERN.sub(replace_uuid, source)
    return result, transformed_uuids


def transform_app_source_refs_to_uuids(
    source: str,
    ref_to_uuid: dict[str, str],
) -> tuple[str, list[str]]:
    """
    Transform useWorkflow('{ref}') to useWorkflow('{uuid}') in TSX source.

    Scans source code for useWorkflow() calls and resolves portable
    workflow references back to UUIDs.

    Args:
        source: TSX/TypeScript source code
        ref_to_uuid: Mapping of "path::function_name" -> UUID string

    Returns:
        Tuple of (transformed_source, list_of_unresolved_refs)
    """
    if not source:
        return source, []

    unresolved_refs: list[str] = []

    def replace_ref(match: re.Match[str]) -> str:
        quote = match.group(1)
        arg = match.group(2)

        # Check if already a UUID (skip transformation)
        if _looks_like_uuid(arg):
            return match.group(0)

        # Check if it's a portable ref we can resolve (try both formats)
        if arg in ref_to_uuid:
            return f"useWorkflow({quote}{ref_to_uuid[arg]}{quote})"

        # Try with workflow:: prefix if not present
        normalized = normalize_portable_ref(arg)
        if normalized in ref_to_uuid:
            return f"useWorkflow({quote}{ref_to_uuid[normalized]}{quote})"

        # Unresolved ref - keep as-is but track it
        if "::" in arg:  # Looks like a portable ref
            unresolved_refs.append(arg)

        return match.group(0)

    result = USE_WORKFLOW_PATTERN.sub(replace_ref, source)
    return result, unresolved_refs


def _looks_like_uuid(value: str) -> bool:
    """
    Check if a string looks like a UUID.

    Simple heuristic: 36 chars with hyphens in the right places.
    """
    if len(value) != 36:
        return False
    if value[8] != "-" or value[13] != "-" or value[18] != "-" or value[23] != "-":
        return False
    return True
