"""
System Tool Decorator

Provides @system_tool decorator for registering MCP tools.
This is the single point where tool metadata is defined.
"""

from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

from src.services.mcp_server.tool_registry import (
    SystemToolMetadata,
    ToolCategory,
    ToolReturnType,
    register_tool,
)

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, ToolReturnType]])


def system_tool(
    id: str,
    name: str,
    description: str,
    *,
    category: ToolCategory = ToolCategory.WORKFLOW,
    default_enabled_for_coding_agent: bool = True,
    is_restricted: bool = False,
    input_schema: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    Decorator that registers a function as a system tool.

    This is the SINGLE SOURCE OF TRUTH for tool registration.
    Adding this decorator automatically:
    - Registers the tool in SYSTEM_TOOLS for /api/tools endpoint
    - Makes it available for SDK tool generation (Coding Agent)
    - Makes it available for FastMCP registration (Claude Desktop)
    - Includes it in get_tool_names() for middleware

    Usage:
        @system_tool(
            id="execute_workflow",
            name="Execute Workflow",
            description="Execute a Bifrost workflow by ID",
            category=ToolCategory.WORKFLOW,
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "UUID of workflow"},
                    "params": {"type": "object", "description": "Input parameters"},
                },
                "required": ["workflow_id"]
            }
        )
        async def execute_workflow_impl(context: MCPContext, workflow_id: str, params: dict | None = None) -> str:
            ...

    Args:
        id: Unique tool identifier (e.g., "execute_workflow")
        name: Human-readable name (e.g., "Execute Workflow")
        description: Description shown to LLM
        category: Tool category for grouping
        default_enabled_for_coding_agent: Whether enabled by default for coding agents
        is_restricted: If True, tool is only available to platform admins regardless of agent assignment
        input_schema: JSON Schema for tool parameters
    """

    def decorator(func: F) -> F:
        # Create metadata
        metadata = SystemToolMetadata(
            id=id,
            name=name,
            description=description,
            category=category,
            default_enabled_for_coding_agent=default_enabled_for_coding_agent,
            is_restricted=is_restricted,
            input_schema=input_schema
            or {"type": "object", "properties": {}, "required": []},
            implementation=func,
        )

        # Register in global registry
        register_tool(metadata)

        # Preserve the original function with metadata attached
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> ToolReturnType:
            return await func(*args, **kwargs)

        # Attach metadata to function for introspection
        wrapper._tool_metadata = metadata  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
