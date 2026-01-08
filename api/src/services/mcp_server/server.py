"""
Bifrost MCP Server

MCP server for Bifrost platform capabilities with dual-mode support:
- Internal mode: Uses Claude Agent SDK's in-process MCP for Coding Agent
- External mode: Uses FastMCP for HTTP access (Claude Desktop, etc.)

Architecture:
    - MCPContext: Holds user/org context for permission-scoped tool execution
    - BifrostMCPServer: Creates MCP servers with registered tools
    - Supports both SDK in-process (internal) and FastMCP HTTP (external)

Usage:
    # For Coding Agent (SDK in-process)
    server = BifrostMCPServer(context)
    sdk_server = server.get_sdk_server()
    options = ClaudeAgentOptions(mcp_servers={"bifrost": sdk_server})

    # For external access (FastMCP HTTP)
    server = BifrostMCPServer(context)
    fastmcp_server = server.get_fastmcp_server()
    app = fastmcp_server.http_app()
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Import tools module to trigger registration via @system_tool decorators
import src.services.mcp_server.tools  # noqa: F401

from src.services.mcp_server.generators import create_sdk_tools, register_fastmcp_tools
from src.services.mcp_server.tool_registry import get_all_tool_ids

logger = logging.getLogger(__name__)

# Claude Agent SDK for internal MCP (Coding Agent)
try:
    from claude_agent_sdk import create_sdk_mcp_server

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    def create_sdk_mcp_server(*args: Any, **kwargs: Any) -> Any:
        """Stub when SDK not installed."""
        raise ImportError(
            "claude-agent-sdk is required for coding mode. "
            "Install it with: pip install claude-agent-sdk"
        )


# FastMCP for external HTTP access - runtime import check
HAS_FASTMCP = False
_FastMCP: type["FastMCP"] | None = None
_Icon: type | None = None

try:
    from fastmcp import FastMCP as _FastMCPClass
    from mcp.types import Icon as _IconClass

    _FastMCP = _FastMCPClass
    _Icon = _IconClass
    HAS_FASTMCP = True
except ImportError:
    pass

# Bifrost branding
BIFROST_ICON_URL = "https://bifrostintegrations.blob.core.windows.net/public/logo.svg"
BIFROST_WEBSITE_URL = "https://docs.gobifrost.com"


# =============================================================================
# Workflow Tool Name Mapping
# =============================================================================

# Workflow tools are registered with normalized names for MCP compatibility.
# These mappings track the relationship between tool names and workflow UUIDs.

# Forward mapping: normalized tool_name -> workflow_id
_TOOL_NAME_TO_WORKFLOW_ID: dict[str, str] = {}
# Reverse mapping: workflow_id -> tool_name
_WORKFLOW_ID_TO_TOOL_NAME: dict[str, str] = {}


def _normalize_tool_name(name: str) -> str:
    """
    Convert workflow name to valid MCP tool name (snake_case).

    Examples:
        "Review Tickets" -> "review_tickets"
        "get-user-data" -> "get_user_data"
        "ProcessOrder123" -> "processorder123"
    """
    import re

    name = name.lower().strip()
    # Replace spaces, hyphens, and multiple underscores with single underscore
    name = re.sub(r"[\s\-]+", "_", name)
    # Remove any non-alphanumeric characters except underscores
    name = re.sub(r"[^a-z0-9_]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Remove leading/trailing underscores
    name = name.strip("_")
    return name


def _generate_short_suffix(length: int = 3) -> str:
    """Generate a short random alphanumeric suffix for duplicate tool names."""
    import secrets
    import string

    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def get_workflow_id_for_tool(tool_name: str) -> str | None:
    """
    Get workflow UUID for a registered MCP tool name.

    Args:
        tool_name: The MCP tool name (e.g., "review_tickets")

    Returns:
        Workflow UUID string or None if not found
    """
    return _TOOL_NAME_TO_WORKFLOW_ID.get(tool_name)


def get_registered_tool_name(workflow_id: str) -> str | None:
    """
    Get the registered MCP tool name for a workflow ID.

    Args:
        workflow_id: The workflow UUID string

    Returns:
        Tool name string or None if not registered
    """
    return _WORKFLOW_ID_TO_TOOL_NAME.get(workflow_id)


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
    user_email: str = ""
    user_name: str = ""

    # System tools enabled for this context (from agent.system_tools)
    enabled_system_tools: list[str] = field(default_factory=list)

    # Knowledge namespaces accessible to this user (from agent.knowledge_sources)
    accessible_namespaces: list[str] = field(default_factory=list)


# =============================================================================
# Context Helper Functions (for FastMCP authentication)
# =============================================================================


def _get_context_from_token() -> MCPContext:
    """
    Get MCPContext from authenticated FastMCP token.

    This extracts user information from the validated JWT token set by
    FastMCP's authentication middleware. Used by tool execution to get
    the actual authenticated user instead of the default startup context.

    Returns:
        MCPContext populated with authenticated user's information

    Raises:
        ToolError: If no authenticated user (token missing or invalid)
    """
    from fastmcp.exceptions import ToolError
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()
    if token is None:
        raise ToolError("Authentication required")

    return MCPContext(
        user_id=token.claims.get("user_id", ""),
        org_id=token.claims.get("org_id"),
        is_platform_admin=token.claims.get("is_superuser", False),
        user_email=token.claims.get("email", ""),
        user_name=token.claims.get("name", ""),
    )


async def _get_context_with_namespaces() -> MCPContext:
    """
    Get MCPContext with accessible knowledge namespaces.

    This extends the basic token context with accessible namespaces
    queried from the database based on user's agent access.

    Returns:
        MCPContext with accessible_namespaces populated
    """
    from fastmcp.exceptions import ToolError
    from fastmcp.server.dependencies import get_access_token

    from src.core.database import get_db_context
    from src.services.mcp_server.tool_access import MCPToolAccessService

    token = get_access_token()
    if token is None:
        raise ToolError("Authentication required")

    user_roles = token.claims.get("roles", [])
    is_superuser = token.claims.get("is_superuser", False)

    # Query accessible namespaces from agents
    accessible_namespaces: list[str] = []
    try:
        async with get_db_context() as db:
            service = MCPToolAccessService(db)
            result = await service.get_accessible_tools(
                user_roles=user_roles,
                is_superuser=is_superuser,
            )
            accessible_namespaces = result.accessible_namespaces
    except Exception as e:
        logger.warning(f"Failed to get accessible namespaces: {e}")

    return MCPContext(
        user_id=token.claims.get("user_id", ""),
        org_id=token.claims.get("org_id"),
        is_platform_admin=is_superuser,
        user_email=token.claims.get("email", ""),
        user_name=token.claims.get("name", ""),
        accessible_namespaces=accessible_namespaces,
    )


# =============================================================================
# BifrostMCPServer
# =============================================================================


class BifrostMCPServer:
    """
    Bifrost MCP Server with dual-mode support.

    Creates MCP servers with tools registered based on user context and
    permissions. Supports both:
    - SDK mode: In-process MCP for Claude Agent SDK (Coding Agent)
    - FastMCP mode: HTTP server for external access (Claude Desktop)

    Usage:
        # Create server with context
        context = MCPContext(user_id=user.id, org_id=user.org_id)
        server = BifrostMCPServer(context)

        # For SDK in-process use (Coding Agent)
        sdk_server = server.get_sdk_server()
        options = ClaudeAgentOptions(mcp_servers={"bifrost": sdk_server})

        # For FastMCP HTTP use (external)
        fastmcp_server = server.get_fastmcp_server()
    """

    def __init__(
        self,
        context: MCPContext,
        *,
        name: str = "bifrost",
    ):
        """
        Initialize Bifrost MCP server.

        Args:
            context: MCP context with user/org information
            name: Server name (default: "bifrost")
        """
        self.context = context
        self._name = name

        # Determine enabled tools
        self._enabled_tools: set[str] | None = None
        if context.enabled_system_tools:
            self._enabled_tools = set(context.enabled_system_tools)

        # SDK server (lazy initialized)
        self._sdk_server: Any = None

        # FastMCP server (lazy initialized)
        self._fastmcp: Any = None

    def get_sdk_server(self) -> Any:
        """
        Get Claude Agent SDK compatible MCP server.

        The SDK server is cached for reuse across multiple calls.

        Returns:
            MCP server instance for ClaudeAgentOptions.mcp_servers
        """
        if self._sdk_server is None:
            tools = create_sdk_tools(self.context, self._enabled_tools)
            self._sdk_server = create_sdk_mcp_server(
                name=self._name,
                version="1.0.0",
                tools=tools,
            )
            logger.info(f"Created SDK MCP server with {len(tools)} tools")
        return self._sdk_server

    def get_fastmcp_server(self, auth: Any = None) -> "FastMCP":
        """
        Get FastMCP server for HTTP access.

        The server is cached for reuse. If auth is provided, a new server
        is created with authentication enabled.

        Args:
            auth: Optional authentication provider (e.g., token verifier).
                  If provided, creates a new server with auth.

        Returns:
            FastMCP server instance
        """
        if not HAS_FASTMCP:
            raise ImportError(
                "fastmcp is required for external MCP access. "
                "Install it with: pip install 'fastmcp>=2.0,<3'"
            )

        # Build icon list for branding
        icons = []
        if _Icon is not None:
            icons = [
                _Icon(
                    src=BIFROST_ICON_URL,
                    mimeType="image/svg+xml",
                    sizes=["any"],
                )
            ]

        # Create context getter that tries token auth first, falls back to default
        default_context = self.context

        def get_context_fn() -> MCPContext:
            try:
                return _get_context_from_token()
            except Exception:
                # Not in FastMCP request context, use provided context (SDK mode)
                return default_context

        # If auth is provided, always create a new server with auth
        if auth is not None:
            assert _FastMCP is not None
            mcp = _FastMCP(
                self._name,
                auth=auth,
                stateless_http=True,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            register_fastmcp_tools(mcp, self.context, self._enabled_tools, get_context_fn)
            tool_count = len(self._enabled_tools) if self._enabled_tools else len(get_all_tool_ids())
            logger.info(f"Created FastMCP server with {tool_count} tools and auth")
            return mcp

        # Otherwise use cached server
        if self._fastmcp is None:
            assert _FastMCP is not None
            self._fastmcp = _FastMCP(
                self._name,
                stateless_http=True,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            register_fastmcp_tools(self._fastmcp, self.context, self._enabled_tools, get_context_fn)
            tool_count = len(self._enabled_tools) if self._enabled_tools else len(get_all_tool_ids())
            logger.info(f"Created FastMCP server with {tool_count} tools")
        return self._fastmcp

    def get_tool_names(self) -> list[str]:
        """Get list of registered tool names (prefixed for SDK use)."""
        all_tools = get_all_tool_ids()
        if self._enabled_tools:
            tools = [t for t in all_tools if t in self._enabled_tools]
        else:
            tools = all_tools
        return [f"mcp__{self._name}__{t}" for t in tools]


# =============================================================================
# Factory Function
# =============================================================================


async def create_user_mcp_server(
    user_id: UUID | str,
    org_id: UUID | str | None = None,
    is_platform_admin: bool = False,
    enabled_tools: list[str] | None = None,
    user_email: str = "",
    user_name: str = "",
) -> BifrostMCPServer:
    """
    Create an MCP server scoped to a user's permissions.

    Args:
        user_id: User ID
        org_id: Organization ID (optional)
        is_platform_admin: Whether user is platform admin
        enabled_tools: List of enabled tool IDs (None = all)
        user_email: User email for context
        user_name: User name for context

    Returns:
        BifrostMCPServer configured for this user
    """
    context = MCPContext(
        user_id=user_id,
        org_id=org_id,
        is_platform_admin=is_platform_admin,
        enabled_system_tools=enabled_tools or [],
        user_email=user_email,
        user_name=user_name,
    )
    return BifrostMCPServer(context)


# =============================================================================
# Workflow Tools (Dynamic from Database)
# =============================================================================

# WorkflowTool class for FastMCP - wraps workflow execution
_WorkflowTool: type | None = None

if HAS_FASTMCP:
    from fastmcp.tools import Tool as _FastMCPTool  # type: ignore[import-not-found]
    from fastmcp.tools.tool import ToolResult as _ToolResult  # type: ignore[import-not-found]

    class WorkflowTool(_FastMCPTool):
        """
        MCP Tool that executes a Bifrost workflow.

        Subclasses FastMCP's Tool to:
        1. Accept JSON Schema directly via `parameters` field
        2. Override `run()` to delegate to workflow execution

        This bypasses FastMCP's function signature inspection, allowing
        dynamic parameter schemas from workflow `parameters_schema`.

        The execution context is retrieved dynamically from the authenticated
        token at runtime via _get_context_from_token().
        """

        workflow_id: str
        workflow_name: str

        model_config = {"arbitrary_types_allowed": True}

        async def run(self, arguments: dict[str, Any]) -> "_ToolResult":
            """Execute the workflow with the given arguments."""
            try:
                context = _get_context_from_token()
            except Exception as e:
                return _ToolResult(content=[{"type": "text", "text": f"Authentication error: {e}"}])

            result = await _execute_workflow_tool_impl(
                context,
                self.workflow_id,
                self.workflow_name,
                **arguments,
            )
            return _ToolResult(content=[{"type": "text", "text": result}])

    _WorkflowTool = WorkflowTool


def _map_type_to_json_schema(param_type: str) -> str:
    """Map workflow parameter type to JSON Schema type."""
    type_map = {
        "string": "string",
        "str": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "json": "object",
        "dict": "object",
        "object": "object",
        "list": "array",
        "array": "array",
    }
    return type_map.get(param_type.lower(), "string")


async def _execute_workflow_tool_impl(
    context: MCPContext,
    workflow_id: str,
    workflow_name: str,
    **inputs: Any,
) -> str:
    """Execute a specific workflow tool by ID."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflow = await repo.get_by_id(workflow_id)

            if not workflow:
                return f"Error: Workflow '{workflow_name}' not found"

            if not workflow.is_active:
                return f"Error: Workflow '{workflow_name}' is not active"

            # Execute the workflow
            result = await execute_tool(
                workflow=workflow,
                inputs=inputs,
                user_id=str(context.user_id),
                org_id=str(context.org_id) if context.org_id else None,
            )

            return result

    except Exception as e:
        logger.exception(f"Error executing workflow tool {workflow_name}: {e}")
        return f"Error executing workflow: {e}"


async def _notify_duplicate_workflow_names(duplicates: dict[str, list]) -> None:
    """Log warning about duplicate workflow names."""
    for name, workflows in duplicates.items():
        workflow_names = [w.name for w in workflows]
        logger.warning(
            f"Multiple workflows normalize to '{name}': {workflow_names}. "
            "Consider renaming to avoid confusion."
        )


async def _register_workflow_tools(mcp: "FastMCP", context: MCPContext) -> int:
    """
    Register workflow tools with FastMCP server using human-readable names.

    Creates WorkflowTool instances for each workflow with is_tool=True,
    passing the parameters_schema directly as JSON Schema. This bypasses
    FastMCP's function signature inspection.

    Tool names are normalized from workflow names (e.g., "Review Tickets" -> "review_tickets").
    Duplicate names get a short random suffix (e.g., "review_tickets_x7k").

    Returns:
        Number of workflow tools registered
    """
    global _TOOL_NAME_TO_WORKFLOW_ID, _WORKFLOW_ID_TO_TOOL_NAME

    if not HAS_FASTMCP or _WorkflowTool is None:
        logger.warning("FastMCP not available, skipping workflow tool registration")
        return 0

    from src.core.database import get_db_context
    from src.services.tool_registry import ToolRegistry

    try:
        async with get_db_context() as db:
            registry = ToolRegistry(db)
            tools = await registry.get_all_tools()

            # Clear previous mappings (in case of re-registration)
            _TOOL_NAME_TO_WORKFLOW_ID = {}
            _WORKFLOW_ID_TO_TOOL_NAME = {}

            # Group workflows by normalized name to detect duplicates
            name_groups: dict[str, list] = {}
            for tool in tools:
                normalized = _normalize_tool_name(tool.name)
                # Handle edge case: empty normalized name falls back to workflow ID
                if not normalized:
                    normalized = str(tool.id)
                name_groups.setdefault(normalized, []).append(tool)

            # Detect duplicates and notify admins
            duplicates = {name: wfs for name, wfs in name_groups.items() if len(wfs) > 1}
            if duplicates:
                await _notify_duplicate_workflow_names(duplicates)
                logger.warning(
                    f"Found {len(duplicates)} duplicate workflow names: "
                    f"{list(duplicates.keys())}"
                )

            # Assign unique tool names and register
            count = 0
            for base_name, workflows in name_groups.items():
                for i, tool in enumerate(workflows):
                    workflow_id = str(tool.id)
                    workflow_name = tool.name
                    description = tool.description or f"Execute the {workflow_name} workflow"

                    # First workflow gets clean name, duplicates get suffix
                    if i == 0:
                        tool_name = base_name
                    else:
                        tool_name = f"{base_name}_{_generate_short_suffix()}"

                    # Store mapping for middleware lookups
                    _TOOL_NAME_TO_WORKFLOW_ID[tool_name] = workflow_id
                    _WORKFLOW_ID_TO_TOOL_NAME[workflow_id] = tool_name

                    # Build JSON Schema from parameters_schema
                    properties: dict[str, Any] = {}
                    required: list[str] = []
                    for param in tool.parameters_schema:
                        param_name = param.get("name")
                        if not param_name:
                            continue

                        param_type = param.get("type", "string")
                        json_type = _map_type_to_json_schema(param_type)

                        properties[param_name] = {
                            "type": json_type,
                            "description": param.get("label") or param.get("description") or param_name,
                        }

                        if param.get("required", False):
                            required.append(param_name)

                    # Create WorkflowTool with human-readable name
                    # Context is retrieved dynamically from authenticated token at runtime
                    workflow_tool = _WorkflowTool(
                        name=tool_name,  # Human-readable name instead of UUID
                        description=description,
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        parameters={
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    )

                    # Add to FastMCP server
                    try:
                        mcp.add_tool(workflow_tool)
                        count += 1
                        logger.debug(
                            f"Registered workflow tool: {tool_name} "
                            f"(workflow: {workflow_name}, id: {workflow_id})"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to register workflow tool {workflow_name}: {e}")

            logger.info(f"Registered {count} workflow tools with FastMCP")
            return count

    except Exception as e:
        logger.exception(f"Error registering workflow tools: {e}")
        return 0
