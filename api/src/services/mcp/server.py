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
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

if TYPE_CHECKING:
    from fastmcp import FastMCP  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

# Claude Agent SDK for internal MCP (Coding Agent)
try:
    from claude_agent_sdk import create_sdk_mcp_server, tool as sdk_tool  # type: ignore

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    def create_sdk_mcp_server(*args: Any, **kwargs: Any) -> Any:
        """Stub when SDK not installed."""
        raise ImportError(
            "claude-agent-sdk is required for coding mode. "
            "Install it with: pip install claude-agent-sdk"
        )

    def sdk_tool(**kwargs: Any) -> Any:
        """Stub decorator when SDK not installed."""
        def decorator(func: Any) -> Any:
            return func
        return decorator

# FastMCP for external HTTP access - runtime import check
HAS_FASTMCP = False
_FastMCP: type["FastMCP"] | None = None  # Runtime class holder
_Icon: type | None = None  # MCP Icon type

try:
    from fastmcp import FastMCP as _FastMCPClass  # type: ignore[import-not-found]
    from mcp.types import Icon as _IconClass  # type: ignore[import-not-found]
    _FastMCP = _FastMCPClass
    _Icon = _IconClass
    HAS_FASTMCP = True
except ImportError:
    pass

# Bifrost branding
BIFROST_ICON_URL = "https://bifrostintegrations.blob.core.windows.net/public/logo.svg"
BIFROST_WEBSITE_URL = "https://docs.gobifrost.com"


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


# =============================================================================
# Tool Implementations (shared between SDK and FastMCP)
# =============================================================================

async def _execute_workflow_impl(
    context: MCPContext,
    workflow_name: str,
    inputs: dict[str, Any] | None = None,
) -> str:
    """Execute a workflow and return results."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    if not workflow_name:
        return "Error: workflow_name is required"

    inputs = inputs or {}
    logger.info(f"MCP execute_workflow: {workflow_name} with inputs: {inputs}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflow = await repo.get_by_name(workflow_name)

            if not workflow:
                return f"Error: Workflow '{workflow_name}' not found. Use list_workflows to see available workflows."

            result = await execute_tool(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                parameters=inputs,
                user_id=str(context.user_id),
                user_email=context.user_email or "mcp@bifrost.local",
                user_name=context.user_name or "MCP User",
                org_id=str(context.org_id) if context.org_id else None,
                is_platform_admin=context.is_platform_admin,
            )

            if result.status.value == "Success":
                import json
                result_str = json.dumps(result.result, indent=2, default=str) if result.result else "null"
                return (
                    f"✓ Workflow '{workflow_name}' executed successfully!\n\n"
                    f"**Duration:** {result.duration_ms}ms\n\n"
                    f"**Result:**\n```json\n{result_str}\n```"
                )
            else:
                return (
                    f"✗ Workflow '{workflow_name}' failed!\n\n"
                    f"**Status:** {result.status.value}\n"
                    f"**Error:** {result.error or 'Unknown error'}\n\n"
                    f"**Error Type:** {result.error_type or 'Unknown'}"
                )

    except Exception as e:
        logger.exception(f"Error executing workflow via MCP: {e}")
        return f"Error executing workflow: {str(e)}"


async def _list_workflows_impl(
    context: MCPContext,
    query: str | None = None,
    category: str | None = None,
) -> str:
    """List all registered workflows."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP list_workflows called with query={query}, category={category}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflows = await repo.search(query=query, category=category, limit=100)
            total_count = await repo.count_active()

            if not workflows:
                return (
                    "No workflows found.\n\n"
                    "If you've created a workflow file in `/tmp/bifrost/workspace`, "
                    "wait a moment for the file watcher to detect and register it.\n\n"
                    "Workflows are Python files with the `.workflow.py` extension that "
                    "use the `@workflow` decorator."
                )

            lines = ["# Registered Workflows\n"]
            lines.append(f"Showing {len(workflows)} of {total_count} total workflows\n")

            for workflow in workflows:
                lines.append(f"## {workflow.name}")
                if workflow.description:
                    lines.append(f"{workflow.description}")

                meta_parts = []
                if workflow.category:
                    meta_parts.append(f"Category: {workflow.category}")
                if workflow.is_tool:
                    meta_parts.append("Tool: Yes")
                if workflow.schedule:
                    meta_parts.append(f"Schedule: {workflow.schedule}")
                if workflow.endpoint_enabled:
                    meta_parts.append("Endpoint: Enabled")

                if meta_parts:
                    lines.append(f"- {' | '.join(meta_parts)}")
                if workflow.file_path:
                    lines.append(f"- File: `{workflow.file_path}`")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing workflows via MCP: {e}")
        return f"Error listing workflows: {str(e)}"


async def _list_integrations_impl(context: MCPContext) -> str:
    """List all available integrations."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.integrations import Integration, IntegrationMapping

    logger.info("MCP list_integrations called")

    try:
        async with get_db_context() as db:
            if context.is_platform_admin or not context.org_id:
                result = await db.execute(
                    select(Integration)
                    .where(Integration.is_deleted.is_(False))
                    .order_by(Integration.name)
                )
                integrations = result.scalars().all()
            else:
                result = await db.execute(
                    select(Integration)
                    .join(IntegrationMapping)
                    .where(IntegrationMapping.organization_id == context.org_id)
                    .where(Integration.is_deleted.is_(False))
                    .order_by(Integration.name)
                )
                integrations = result.scalars().all()

            if not integrations:
                return (
                    "No integrations are currently configured.\n\n"
                    "To use integrations in workflows, they must first be set up "
                    "in the Bifrost admin panel."
                )

            lines = ["# Available Integrations\n"]
            for integration in integrations:
                lines.append(f"## {integration.name}")
                if integration.has_oauth_config:
                    lines.append("- **Auth:** OAuth configured")
                if integration.entity_id_name:
                    lines.append(f"- **Entity:** {integration.entity_id_name}")
                lines.append("")

            lines.append("\n## Usage in Workflows\n")
            lines.append("```python")
            lines.append("from bifrost import integrations")
            lines.append("")
            lines.append('integration = await integrations.get("IntegrationName")')
            lines.append("if integration and integration.oauth:")
            lines.append("    access_token = integration.oauth.access_token")
            lines.append("```")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing integrations via MCP: {e}")
        return f"Error listing integrations: {str(e)}"


async def _list_forms_impl(context: MCPContext) -> str:
    """List all forms."""
    from src.core.database import get_db_context
    from src.repositories.forms import FormRepository

    logger.info("MCP list_forms called")

    try:
        async with get_db_context() as db:
            repo = FormRepository(db)

            # Get forms based on context
            if context.is_platform_admin:
                forms = await repo.list_all(limit=100)
            elif context.org_id:
                forms = await repo.list_by_organization(str(context.org_id), limit=100)
            else:
                forms = []

            if not forms:
                return "No forms found."

            lines = ["# Forms\n"]
            for form in forms:
                lines.append(f"## {form.name}")
                if form.description:
                    lines.append(f"{form.description}")
                lines.append(f"- URL: `/forms/{form.id}`")
                if form.workflow_id:
                    lines.append(f"- Linked workflow: {form.workflow_id}")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing forms via MCP: {e}")
        return f"Error listing forms: {str(e)}"


async def _get_form_schema_impl(context: MCPContext) -> str:
    """Get form schema documentation."""
    return """# Form Schema Documentation

Forms in Bifrost are defined using a JSON schema with the following structure:

## Form Definition

```json
{
  "name": "Example Form",
  "description": "Form description",
  "fields": [...],
  "workflow_id": "optional-workflow-uuid"
}
```

## Field Types

### Text Field
```json
{
  "name": "username",
  "type": "text",
  "label": "Username",
  "required": true,
  "placeholder": "Enter username"
}
```

### Select Field
```json
{
  "name": "country",
  "type": "select",
  "label": "Country",
  "options": [
    {"value": "us", "label": "United States"},
    {"value": "uk", "label": "United Kingdom"}
  ]
}
```

### Number Field
```json
{
  "name": "age",
  "type": "number",
  "label": "Age",
  "min": 0,
  "max": 150
}
```

### Boolean Field
```json
{
  "name": "subscribe",
  "type": "boolean",
  "label": "Subscribe to newsletter",
  "default": false
}
```

### Date Field
```json
{
  "name": "birthday",
  "type": "date",
  "label": "Birthday"
}
```

## Common Field Properties

- `name`: Field identifier (required)
- `type`: Field type (required)
- `label`: Display label
- `required`: Whether field is required
- `default`: Default value
- `placeholder`: Placeholder text
- `description`: Help text
"""


async def _validate_form_schema_impl(context: MCPContext, form_json: str) -> str:
    """Validate a form JSON structure."""
    import json

    try:
        form_data = json.loads(form_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {str(e)}"

    errors = []

    # Check required fields
    if "name" not in form_data:
        errors.append("Missing required field: 'name'")
    if "fields" not in form_data:
        errors.append("Missing required field: 'fields'")
    elif not isinstance(form_data.get("fields"), list):
        errors.append("'fields' must be an array")

    # Validate each field
    valid_types = {"text", "number", "select", "boolean", "date", "textarea", "email", "password"}
    if isinstance(form_data.get("fields"), list):
        for i, fld in enumerate(form_data["fields"]):
            if not isinstance(fld, dict):
                errors.append(f"Field {i}: must be an object")
                continue
            if "name" not in fld:
                errors.append(f"Field {i}: missing 'name'")
            if "type" not in fld:
                errors.append(f"Field {i}: missing 'type'")
            elif fld["type"] not in valid_types:
                errors.append(f"Field {i}: invalid type '{fld['type']}'. Valid types: {', '.join(valid_types)}")

    if errors:
        return "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)

    return "✓ Form schema is valid!"


async def _search_knowledge_impl(
    context: MCPContext,
    query: str,
    limit: int = 5,
) -> str:
    """Search the knowledge base."""
    from src.core.database import get_db_context
    from src.repositories.knowledge import KnowledgeRepository
    from src.services.embeddings import get_embedding_client

    logger.info(f"MCP search_knowledge called with query={query}")

    if not query:
        return "Error: query is required"

    try:
        async with get_db_context() as db:
            # Generate query embedding
            embedding_client = await get_embedding_client(db)
            query_embedding = await embedding_client.embed_single(query)

            # Search knowledge store
            repo = KnowledgeRepository(db)
            results = await repo.search(
                query_embedding=query_embedding,
                namespace=None,  # Search all namespaces
                organization_id=context.org_id if context.org_id else None,
                limit=limit,
                fallback=True,
            )

            if not results:
                return f"No results found for query: '{query}'"

            lines = [f"# Knowledge Search Results for '{query}'\n"]
            for i, doc in enumerate(results, 1):
                lines.append(f"## Result {i}")
                if doc.namespace:
                    lines.append(f"**Namespace:** {doc.namespace}")
                if doc.score:
                    lines.append(f"**Relevance:** {doc.score:.2%}")
                lines.append(f"\n{doc.content}\n")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error searching knowledge via MCP: {e}")
        return f"Error searching knowledge: {str(e)}"


# =============================================================================
# SDK Tool Wrappers (for Claude Agent SDK in-process MCP)
# =============================================================================

def _create_sdk_tools(context: MCPContext, enabled_tools: set[str] | None) -> list[Callable[..., Any]]:
    """Create SDK-compatible tools for the given context."""
    tools: list[Callable[..., Any]] = []

    # Tool definitions with SDK decorator
    if enabled_tools is None or "execute_workflow" in enabled_tools:
        @sdk_tool(
            name="execute_workflow",
            description="Execute a Bifrost workflow by name and return the results. Use this to test workflows you've written.",
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_name": {"type": "string", "description": "Name of the workflow to execute"},
                    "inputs": {"type": "object", "description": "Input parameters for the workflow"},
                },
                "required": ["workflow_name"],
            },
        )
        async def execute_workflow(args: dict[str, Any]) -> dict[str, Any]:
            result = await _execute_workflow_impl(context, args.get("workflow_name", ""), args.get("inputs"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(execute_workflow)

    if enabled_tools is None or "list_workflows" in enabled_tools:
        @sdk_tool(
            name="list_workflows",
            description="List workflows registered in Bifrost. Use this to verify a workflow you created was successfully discovered and registered.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search query to filter workflows"},
                    "category": {"type": "string", "description": "Optional category to filter workflows"},
                },
                "required": [],
            },
        )
        async def list_workflows(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_workflows_impl(context, args.get("query"), args.get("category"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_workflows)

    if enabled_tools is None or "list_integrations" in enabled_tools:
        @sdk_tool(
            name="list_integrations",
            description="List available integrations that can be used in workflows.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def list_integrations(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_integrations_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_integrations)

    if enabled_tools is None or "list_forms" in enabled_tools:
        @sdk_tool(
            name="list_forms",
            description="List all forms with their URLs for viewing in the platform.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def list_forms(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_forms_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_forms)

    if enabled_tools is None or "get_form_schema" in enabled_tools:
        @sdk_tool(
            name="get_form_schema",
            description="Get documentation about form structure, field types, and examples.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def get_form_schema(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_form_schema_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_form_schema)

    if enabled_tools is None or "validate_form_schema" in enabled_tools:
        @sdk_tool(
            name="validate_form_schema",
            description="Validate a form JSON structure before saving.",
            input_schema={
                "type": "object",
                "properties": {
                    "form_json": {"type": "string", "description": "JSON string of the form to validate"},
                },
                "required": ["form_json"],
            },
        )
        async def validate_form_schema(args: dict[str, Any]) -> dict[str, Any]:
            result = await _validate_form_schema_impl(context, args.get("form_json", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(validate_form_schema)

    if enabled_tools is None or "search_knowledge" in enabled_tools:
        @sdk_tool(
            name="search_knowledge",
            description="Search the Bifrost knowledge base for documentation and examples.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Maximum results to return (default: 5)"},
                },
                "required": ["query"],
            },
        )
        async def search_knowledge(args: dict[str, Any]) -> dict[str, Any]:
            result = await _search_knowledge_impl(context, args.get("query", ""), args.get("limit", 5))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(search_knowledge)

    return tools


# =============================================================================
# FastMCP Tool Registration (for external HTTP access)
# =============================================================================

def _register_fastmcp_tools(mcp: "FastMCP", context: MCPContext, enabled_tools: set[str] | None) -> None:
    """Register tools with a FastMCP server."""
    if enabled_tools is None or "execute_workflow" in enabled_tools:
        @mcp.tool(
            name="execute_workflow",
            description="Execute a Bifrost workflow by name and return the results.",
        )
        async def execute_workflow(workflow_name: str, inputs: dict[str, Any] | None = None) -> str:
            return await _execute_workflow_impl(context, workflow_name, inputs)

    if enabled_tools is None or "list_workflows" in enabled_tools:
        @mcp.tool(
            name="list_workflows",
            description="List workflows registered in Bifrost.",
        )
        async def list_workflows(query: str | None = None, category: str | None = None) -> str:
            return await _list_workflows_impl(context, query, category)

    if enabled_tools is None or "list_integrations" in enabled_tools:
        @mcp.tool(
            name="list_integrations",
            description="List available integrations that can be used in workflows.",
        )
        async def list_integrations() -> str:
            return await _list_integrations_impl(context)

    if enabled_tools is None or "list_forms" in enabled_tools:
        @mcp.tool(
            name="list_forms",
            description="List all forms with their URLs.",
        )
        async def list_forms() -> str:
            return await _list_forms_impl(context)

    if enabled_tools is None or "get_form_schema" in enabled_tools:
        @mcp.tool(
            name="get_form_schema",
            description="Get documentation about form structure and field types.",
        )
        async def get_form_schema() -> str:
            return await _get_form_schema_impl(context)

    if enabled_tools is None or "validate_form_schema" in enabled_tools:
        @mcp.tool(
            name="validate_form_schema",
            description="Validate a form JSON structure before saving.",
        )
        async def validate_form_schema(form_json: str) -> str:
            return await _validate_form_schema_impl(context, form_json)

    if enabled_tools is None or "search_knowledge" in enabled_tools:
        @mcp.tool(
            name="search_knowledge",
            description="Search the Bifrost knowledge base.",
        )
        async def search_knowledge(query: str, limit: int = 5) -> str:
            return await _search_knowledge_impl(context, query, limit)


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
            tools = _create_sdk_tools(self.context, self._enabled_tools)
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

        # If auth is provided, always create a new server with auth
        if auth is not None:
            assert _FastMCP is not None
            mcp = _FastMCP(
                self._name,
                auth=auth,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            _register_fastmcp_tools(mcp, self.context, self._enabled_tools)
            tool_count = len(self._enabled_tools) if self._enabled_tools else 7
            logger.info(f"Created FastMCP server with {tool_count} tools and auth")
            return mcp

        # Otherwise use cached server
        if self._fastmcp is None:
            assert _FastMCP is not None  # For type checker; HAS_FASTMCP check above ensures this
            self._fastmcp = _FastMCP(
                self._name,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            _register_fastmcp_tools(self._fastmcp, self.context, self._enabled_tools)
            tool_count = len(self._enabled_tools) if self._enabled_tools else 7
            logger.info(f"Created FastMCP server with {tool_count} tools")
        return self._fastmcp

    def get_tool_names(self) -> list[str]:
        """Get list of registered tool names (prefixed for SDK use)."""
        all_tools = ["execute_workflow", "list_workflows", "list_integrations",
                     "list_forms", "get_form_schema", "validate_form_schema", "search_knowledge"]
        if self._enabled_tools:
            tools = [t for t in all_tools if t in self._enabled_tools]
        else:
            tools = all_tools
        return [f"mcp__{self._name}__{t}" for t in tools]


# Factory function for creating user-scoped MCP servers
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
