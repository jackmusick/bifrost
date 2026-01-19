"""
Entity metadata extraction for GitHub sync UI.

Extracts display names and entity types from file paths and content
to provide human-readable labels in the sync preview UI.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Path patterns for entity detection
FORM_PATTERN = re.compile(r"^forms/.*\.form\.json$")
AGENT_PATTERN = re.compile(r"^agents/.*\.agent\.json$")
APP_JSON_PATTERN = re.compile(r"^apps/([^/]+)/app\.json$")
APP_FILE_PATTERN = re.compile(r"^apps/([^/]+)/(.+)$")
WORKFLOW_PATTERN = re.compile(r"^(workflows|data_providers)/.*\.py$")


@dataclass
class EntityMetadata:
    """Metadata extracted from a sync file for UI display."""
    entity_type: str | None
    display_name: str
    parent_slug: str | None = None


def extract_entity_metadata(path: str, content: bytes | None = None) -> EntityMetadata:
    """
    Extract entity metadata from a file path and optional content.

    Args:
        path: File path relative to workspace root
        content: Optional file content for JSON parsing

    Returns:
        EntityMetadata with type, display name, and parent slug
    """
    filename = Path(path).name

    # Form: forms/*.form.json
    if FORM_PATTERN.match(path):
        display_name = _extract_json_name(content, filename)
        return EntityMetadata(entity_type="form", display_name=display_name)

    # Agent: agents/*.agent.json
    if AGENT_PATTERN.match(path):
        display_name = _extract_json_name(content, filename)
        return EntityMetadata(entity_type="agent", display_name=display_name)

    # App metadata: apps/{slug}/app.json
    match = APP_JSON_PATTERN.match(path)
    if match:
        slug = match.group(1)
        display_name = _extract_json_name(content, slug)
        return EntityMetadata(entity_type="app", display_name=display_name, parent_slug=slug)

    # App file: apps/{slug}/**/*
    match = APP_FILE_PATTERN.match(path)
    if match:
        slug = match.group(1)
        relative_path = match.group(2)
        # Skip app.json (handled above)
        if relative_path != "app.json":
            return EntityMetadata(
                entity_type="app_file",
                display_name=relative_path,
                parent_slug=slug
            )

    # Workflow: workflows/*.py or data_providers/*.py
    if WORKFLOW_PATTERN.match(path):
        return EntityMetadata(entity_type="workflow", display_name=filename)

    # Unknown file type
    return EntityMetadata(entity_type=None, display_name=filename)


def _extract_json_name(content: bytes | None, fallback: str) -> str:
    """Extract 'name' field from JSON content, with fallback."""
    if content is None:
        return fallback

    try:
        data = json.loads(content.decode("utf-8"))
        return data.get("name", fallback)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.debug(f"Failed to parse JSON for name extraction, using fallback: {fallback}")
        return fallback
