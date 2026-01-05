"""
MCP Tool Generators

Generate SDK and FastMCP tool wrappers from the central registry.
"""

from src.services.mcp.generators.fastmcp_generator import register_fastmcp_tools
from src.services.mcp.generators.sdk_generator import create_sdk_tools

__all__ = ["create_sdk_tools", "register_fastmcp_tools"]
