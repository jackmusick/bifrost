"""
Bifrost MCP Server Module

Provides Model Context Protocol (MCP) server capabilities for Claude Agent SDK integration.
Designed for extensibility - initially supports coding mode, but architected for future
user-facing MCP access via OAuth.

Usage:
    from src.services.mcp_server import BifrostMCPServer, MCPContext

    # Create server with context
    context = MCPContext(user_id=user.id, org_id=org.id)
    server = BifrostMCPServer(context)

    # Get SDK-compatible server for Claude Agent SDK
    sdk_server = server.get_sdk_server()
"""

from src.services.mcp_server.server import BifrostMCPServer, MCPContext

__all__ = ["BifrostMCPServer", "MCPContext"]
