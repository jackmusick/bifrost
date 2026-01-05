"""
FastMCP Tool Generator

Generates FastMCP compatible tools from the registry.
"""

import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable

from src.services.mcp.tool_registry import get_all_system_tools

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from src.services.mcp.server import MCPContext

logger = logging.getLogger(__name__)


def register_fastmcp_tools(
    mcp: "FastMCP",
    context: "MCPContext",
    enabled_tools: set[str] | None,
    get_context_fn: Callable[[], "MCPContext"],
) -> None:
    """
    Register all system tools from the registry with a FastMCP server.

    Args:
        mcp: FastMCP server instance
        context: Default MCP context (used for SDK mode fallback)
        enabled_tools: Set of tool IDs to enable (None = all)
        get_context_fn: Function to get current context (for HTTP mode auth)
    """
    registered_count = 0

    for metadata in get_all_system_tools():
        # Skip if no implementation
        if metadata.implementation is None:
            continue

        # Check if tool should be enabled
        if enabled_tools is not None and metadata.id not in enabled_tools:
            continue

        # Register with FastMCP
        _register_single_tool(mcp, metadata, get_context_fn)
        registered_count += 1
        logger.debug(f"Registered FastMCP tool: {metadata.id}")

    logger.info(f"Registered {registered_count} FastMCP tools from registry")


def _register_single_tool(
    mcp: "FastMCP",
    metadata: Any,
    get_context_fn: Callable[[], Any],
) -> None:
    """Register a single tool with FastMCP using its implementation signature."""
    if metadata.implementation is None:
        return

    impl = metadata.implementation

    # Get the implementation's signature (excluding 'context' parameter)
    sig = inspect.signature(impl)
    params = list(sig.parameters.items())

    # Skip the first parameter (context)
    impl_params = params[1:] if params else []

    # Create and register the wrapper
    wrapper = _create_sync_wrapper(impl, impl_params, sig, metadata, get_context_fn)

    # Register with FastMCP
    mcp.tool(name=metadata.id, description=metadata.description)(wrapper)


def _create_sync_wrapper(
    impl: Callable[..., Any],
    impl_params: list[tuple[str, Any]],
    sig: inspect.Signature,
    metadata: Any,
    get_context_fn: Callable[[], Any],
) -> Callable[..., Any]:
    """Create a wrapper function synchronously."""

    async def wrapper(**kwargs: Any) -> str:
        ctx = get_context_fn()
        return await impl(ctx, **kwargs)

    # Copy metadata
    wrapper.__name__ = metadata.id
    wrapper.__qualname__ = metadata.id
    wrapper.__doc__ = metadata.description

    # Build new signature without context parameter
    new_params = [param for _, param in impl_params]
    wrapper.__signature__ = sig.replace(parameters=new_params)  # type: ignore[attr-defined]

    # Build annotations for Pydantic type adapter (FastMCP uses this for introspection)
    annotations: dict[str, Any] = {}
    for param_name, param in impl_params:
        if param.annotation != inspect.Parameter.empty:
            annotations[param_name] = param.annotation
        else:
            annotations[param_name] = str  # Default to str if no annotation
    annotations["return"] = str
    wrapper.__annotations__ = annotations

    return wrapper
