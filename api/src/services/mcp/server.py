"""
Bifrost MCP Server

Extensible MCP server that exposes Bifrost platform capabilities to Claude Agent SDK.

Architecture:
    - MCPContext: Holds user/org context for permission-scoped tool execution
    - BifrostMCPServer: Manages tool registration and creates SDK-compatible servers

Future Vision:
    - User-facing MCP access via OAuth authentication
    - Dynamic tool registration based on agent permissions
    - Per-user tool scoping

Example:
    context = MCPContext(user_id="...", org_id="...")
    server = BifrostMCPServer(context)
    sdk_server = server.get_sdk_server()
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

# Claude Agent SDK is optional - will be installed when using coding mode
try:
    from claude_agent_sdk import create_sdk_mcp_server  # type: ignore

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    def create_sdk_mcp_server(*args: Any, **kwargs: Any) -> Any:
        """Stub when SDK not installed."""
        raise ImportError(
            "claude-agent-sdk is required for coding mode. "
            "Install it with: pip install claude-agent-sdk"
        )


@dataclass
class MCPContext:
    """
    Context for MCP tool execution.

    Provides user and organization scope for permission-aware tool execution.
    All MCP tools receive this context to enforce access control.
    """

    user_id: UUID | str
    org_id: UUID | str | None = None
    is_platform_admin: bool = False

    # Future: Add more context as needed
    # accessible_agents: list[UUID] = field(default_factory=list)
    # permissions: set[str] = field(default_factory=set)


class BifrostMCPServer:
    """
    Bifrost MCP Server for Claude Agent SDK integration.

    Manages tool registration and creates SDK-compatible MCP servers.
    Designed for extensibility - tools can be dynamically registered
    based on user permissions.

    Usage:
        context = MCPContext(user_id=user.id)
        server = BifrostMCPServer(context)

        # Tools are auto-registered on init
        sdk_server = server.get_sdk_server()

        # Use with Claude Agent SDK
        options = ClaudeAgentOptions(
            mcp_servers={"bifrost": sdk_server},
            allowed_tools=["mcp__bifrost__execute_workflow"]
        )
    """

    def __init__(self, context: MCPContext):
        self.context = context
        self._tools: list[Callable[..., Any]] = []
        self._sdk_server: Any = None  # Cache the SDK server to reuse transport
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of Bifrost MCP tools."""
        from src.services.mcp.tools import execute_workflow_tool, list_integrations_tool

        # Create tool instances bound to our context
        self._tools.append(execute_workflow_tool(self.context))
        self._tools.append(list_integrations_tool(self.context))

    def register_tool(self, tool: Callable[..., Any]) -> None:
        """
        Register an additional tool with this server.

        Args:
            tool: A decorated tool function created with @tool decorator
        """
        self._tools.append(tool)

    def get_sdk_server(self) -> Any:
        """
        Get or create a Claude Agent SDK compatible MCP server.

        The SDK server is cached to reuse the subprocess transport across
        multiple query() calls. Creating a new server for each message
        causes "ProcessTransport is not ready for writing" errors because
        the subprocess hasn't completed initialization.

        Returns:
            MCP server instance ready for use with ClaudeAgentOptions
        """
        if self._sdk_server is None:
            self._sdk_server = create_sdk_mcp_server(
                name="bifrost",
                version="1.0.0",
                tools=self._tools,
            )
        return self._sdk_server

    def get_tool_names(self) -> list[str]:
        """
        Get list of registered tool names (prefixed for SDK use).

        Returns:
            List of tool names in format "mcp__bifrost__tool_name"
        """
        return [f"mcp__bifrost__{t.name}" for t in self._tools if hasattr(t, "name")]


# Future: Factory for user-facing MCP servers
# def create_user_mcp_server(user: User, db: AsyncSession) -> BifrostMCPServer:
#     """
#     Create an MCP server scoped to a user's permissions.
#
#     This will be used when users connect to Bifrost via MCP from
#     Claude Desktop or other MCP clients.
#
#     Args:
#         user: Authenticated user
#         db: Database session for querying permissions
#
#     Returns:
#         BifrostMCPServer with tools scoped to user's accessible agents
#     """
#     context = MCPContext(
#         user_id=user.id,
#         org_id=user.organization_id,
#         is_platform_admin=user.is_platform_admin,
#     )
#     server = BifrostMCPServer(context)
#
#     # Query user's accessible agents and register their tools
#     # for agent in get_user_accessible_agents(user, db):
#     #     for workflow in agent.tools:
#     #         server.register_tool(create_workflow_tool(workflow, context))
#
#     return server
