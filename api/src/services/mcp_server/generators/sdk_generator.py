"""
SDK Tool Generator

Generates Claude Agent SDK compatible tools from the registry.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable

from src.services.mcp_server.tool_registry import get_all_system_tools

if TYPE_CHECKING:
    from src.services.mcp_server.server import MCPContext

logger = logging.getLogger(__name__)

# Import SDK at runtime to avoid issues if not installed
_sdk_tool: Callable[..., Any] | None = None

try:
    from claude_agent_sdk import tool as sdk_tool_import  # type: ignore[import-not-found]

    _sdk_tool = sdk_tool_import
except ImportError:
    try:
        from anthropic.lib.bedrock._tools import tool as bedrock_tool  # type: ignore[import-not-found]

        _sdk_tool = bedrock_tool
    except ImportError:
        pass


def create_sdk_tools(
    context: "MCPContext", enabled_tools: set[str] | None
) -> list[Callable[..., Any]]:
    """
    Create SDK-compatible tools from the registry.

    Args:
        context: MCP context with user/org info
        enabled_tools: Set of tool IDs to enable (None = all default-enabled)

    Returns:
        List of SDK-decorated tool functions
    """
    if _sdk_tool is None:
        logger.debug("Claude SDK not available, skipping SDK tool generation")
        return []

    tools: list[Callable[..., Any]] = []

    for metadata in get_all_system_tools():
        # Skip if no implementation
        if metadata.implementation is None:
            continue

        # Check if tool should be enabled
        if enabled_tools is not None:
            if metadata.id not in enabled_tools:
                continue
        else:
            # No explicit list - use defaults
            if not metadata.default_enabled_for_coding_agent:
                continue

        # Create SDK wrapper
        tool_func = _create_sdk_wrapper(context, metadata)
        if tool_func:
            tools.append(tool_func)
            logger.debug(f"Created SDK tool: {metadata.id}")

    logger.info(f"Created {len(tools)} SDK tools from registry")
    return tools


def _create_sdk_wrapper(
    context: "MCPContext", metadata: Any
) -> Callable[..., Any] | None:
    """Create an SDK-compatible wrapper for a system tool."""
    if _sdk_tool is None or metadata.implementation is None:
        return None

    impl = metadata.implementation
    schema = metadata.input_schema
    properties = schema.get("properties", {})

    # Create the wrapper function
    @_sdk_tool(
        name=metadata.id,
        description=metadata.description,
        input_schema=schema,
    )
    async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
        # Extract arguments from args dict based on input_schema properties
        kwargs: dict[str, Any] = {}
        for key in properties:
            if key in args:
                kwargs[key] = args[key]

        # Call implementation with context + extracted kwargs
        result = await impl(context, **kwargs)
        return {"content": [{"type": "text", "text": result}]}

    # Give it a unique name to help with debugging
    wrapper.__name__ = f"sdk_{metadata.id}"
    wrapper.__qualname__ = f"sdk_{metadata.id}"

    return wrapper
