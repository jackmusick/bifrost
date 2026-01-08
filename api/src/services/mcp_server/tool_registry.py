"""
System Tool Registry

Single source of truth for system tool definitions.
All tool metadata is defined here via the @system_tool decorator.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class ToolCategory(str, Enum):
    """Categories for grouping system tools."""

    WORKFLOW = "workflow"
    FILE = "file"
    FORM = "form"
    APP_BUILDER = "app_builder"
    DATA_PROVIDER = "data_provider"
    KNOWLEDGE = "knowledge"
    INTEGRATION = "integration"
    ORGANIZATION = "organization"


@dataclass
class SystemToolMetadata:
    """
    Complete metadata for a system tool.

    This is the SINGLE SOURCE OF TRUTH for tool registration.
    All other registration points derive from this.
    """

    # Identity
    id: str  # e.g., "execute_workflow"
    name: str  # e.g., "Execute Workflow"
    description: str  # Tool description for LLM

    # Categorization
    category: ToolCategory = ToolCategory.WORKFLOW

    # Configuration
    default_enabled_for_coding_agent: bool = True

    # Access control
    is_restricted: bool = False  # Platform-admin only regardless of agent assignment

    # Schema for tool parameters
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    # Implementation reference (set by decorator)
    implementation: Callable[..., Coroutine[Any, Any, str]] | None = None


# Global registry - populated by @system_tool decorator
_SYSTEM_TOOL_REGISTRY: dict[str, SystemToolMetadata] = {}


def register_tool(metadata: SystemToolMetadata) -> None:
    """Register a tool in the global registry."""
    if metadata.id in _SYSTEM_TOOL_REGISTRY:
        raise ValueError(f"Tool '{metadata.id}' is already registered")
    _SYSTEM_TOOL_REGISTRY[metadata.id] = metadata


def get_all_system_tools() -> list[SystemToolMetadata]:
    """Get all registered system tools."""
    return list(_SYSTEM_TOOL_REGISTRY.values())


def get_system_tool(tool_id: str) -> SystemToolMetadata | None:
    """Get a specific system tool by ID."""
    return _SYSTEM_TOOL_REGISTRY.get(tool_id)


def get_all_tool_ids() -> list[str]:
    """Get all registered tool IDs."""
    return list(_SYSTEM_TOOL_REGISTRY.keys())


def clear_registry() -> None:
    """Clear the registry. Only for testing."""
    _SYSTEM_TOOL_REGISTRY.clear()
