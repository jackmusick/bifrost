"""
Entity metadata extraction for GitHub sync UI.

Extracts display names and entity types from file paths and content
to provide human-readable labels in the sync preview UI.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Path patterns for entity detection
FORM_PATTERN = re.compile(r"^forms/.*\.form\.yaml$")
AGENT_PATTERN = re.compile(r"^agents/.*\.agent\.yaml$")
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
        content: Optional file content for YAML/JSON parsing

    Returns:
        EntityMetadata with type, display name, and parent slug
    """
    filename = Path(path).name

    # Form: forms/*.form.yaml
    if FORM_PATTERN.match(path):
        display_name = _extract_yaml_name(content, filename)
        return EntityMetadata(entity_type="form", display_name=display_name)

    # Agent: agents/*.agent.yaml
    if AGENT_PATTERN.match(path):
        display_name = _extract_yaml_name(content, filename)
        return EntityMetadata(entity_type="agent", display_name=display_name)

    # App file: apps/{slug}/**/*
    match = APP_FILE_PATTERN.match(path)
    if match:
        slug = match.group(1)
        relative_path = match.group(2)
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


def _extract_yaml_name(content: bytes | None, fallback: str) -> str:
    """Extract 'name' field from YAML content, with fallback."""
    if content is None:
        return fallback

    try:
        data = yaml.safe_load(content.decode("utf-8"))
        if isinstance(data, dict):
            return data.get("name", fallback)
        return fallback
    except (yaml.YAMLError, UnicodeDecodeError):
        logger.debug(f"Failed to parse YAML for name extraction, using fallback: {fallback}")
        return fallback
