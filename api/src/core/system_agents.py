"""Security policy helpers for built-in MCP agent tools."""

from __future__ import annotations


# Agent-management MCP tools can create, modify, or remove agents and their
# tool grants. They are safe for direct admin-controlled MCP use, but not as
# chat-agent callable tools.
PRIVILEGED_AGENT_MANAGEMENT_TOOLS: frozenset[str] = frozenset({
    "create_agent",
    "update_agent",
    "delete_agent",
})


def is_privileged_agent_management_tool(tool_name: str) -> bool:
    """Return True when a built-in MCP tool manages agent privileges."""
    return tool_name in PRIVILEGED_AGENT_MANAGEMENT_TOOLS
