# api/src/services/mcp_server/tool_result.py
"""
MCP Tool Result Helpers

Standard helpers for building CallToolResult objects with proper
content (human-readable) and structuredContent (machine-parseable).
"""

from typing import Any

from mcp.types import CallToolResult, TextContent


def success_result(display_text: str, data: dict[str, Any]) -> CallToolResult:
    """
    Create a successful tool result with display text and structured data.

    Args:
        display_text: Human-readable text for display in CLI/UI
        data: Structured data dict for LLM parsing

    Returns:
        CallToolResult with content and structuredContent
    """
    return CallToolResult(
        content=[TextContent(type="text", text=display_text)],
        structuredContent=data,
        isError=False,
    )


def error_result(error_message: str, extra_data: dict[str, Any] | None = None) -> CallToolResult:
    """
    Create an error tool result.

    Args:
        error_message: Human-readable error description
        extra_data: Optional additional data to include in structuredContent

    Returns:
        CallToolResult with isError=True
    """
    data = {"error": error_message}
    if extra_data:
        data.update(extra_data)

    return CallToolResult(
        content=[TextContent(type="text", text=f"Error: {error_message}")],
        structuredContent=data,
        isError=True,
    )
