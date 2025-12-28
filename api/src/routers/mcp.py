"""
MCP (Model Context Protocol) Router

Provides external access to Bifrost's MCP server for LLM clients like Claude Desktop.
Uses FastMCP to expose tools via Streamable HTTP transport with Bearer token authentication.

Architecture:
    - FastMCP server is mounted as an ASGI sub-application at /mcp
    - JWT Bearer token authentication using Bifrost's existing auth system
    - Tools are dynamically loaded based on user's agent access permissions
    - Platform admins only (initially) - controlled by system config

Authentication:
    Users authenticate through Bifrost's normal login flow (UI or CLI) and use
    their access token as a Bearer token for MCP requests. The token is validated
    using Bifrost's existing JWT infrastructure (HS256 with shared secret).

Usage:
    # Get access token from Bifrost login
    curl -X POST https://your-bifrost.com/auth/login \
        -d '{"email":"admin@example.com","password":"..."}' \
        -H "Content-Type: application/json"

    # Use token for MCP access (example with test initialize)
    curl -X POST https://your-bifrost.com/api/mcp \
        -H "Authorization: Bearer <access_token>" \
        -H "Accept: application/json, text/event-stream" \
        -d '{"jsonrpc":"2.0","id":1,"method":"initialize",...}'
"""

import logging

from fastapi import APIRouter, HTTPException, status
from starlette.middleware.cors import CORSMiddleware

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession
from src.models.contracts.mcp import (
    MCPConfigRequest,
    MCPConfigResponse,
    MCPToolInfo,
    MCPToolsResponse,
)
from src.services.mcp.config_service import (
    MCPConfigService,
    invalidate_mcp_config_cache,
)

logger = logging.getLogger(__name__)

# Note: Router uses /api/mcp prefix for REST endpoints (status, config)
# The MCP protocol endpoint is also at /api/mcp (FastMCP handles it)
router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# =============================================================================
# MCP Status Endpoint (for debugging/info)
# =============================================================================


@router.get("/status")
async def mcp_status(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> dict:
    """
    Get MCP server status and available tools for the current user.

    This is a REST endpoint (not MCP protocol) for debugging and discovery.
    Returns information about which tools the user has access to.
    """
    from src.services.mcp.server import BifrostMCPServer, MCPContext

    # Check if user is platform admin (initial restriction)
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MCP access is currently restricted to platform administrators"
        )

    # Create context for this user
    context = MCPContext(
        user_id=current_user.user_id,
        org_id=current_user.organization_id,
        is_platform_admin=current_user.is_superuser,
        user_email=current_user.email,
        user_name=current_user.name or current_user.email,
    )

    # Get tool names
    server = BifrostMCPServer(context)
    tool_names = server.get_tool_names()

    return {
        "status": "available",
        "user_id": str(current_user.user_id),
        "is_platform_admin": current_user.is_superuser,
        "tools_count": len(tool_names),
        "tools": [name.replace("mcp__bifrost__", "") for name in tool_names],
        "mcp_endpoint": "/mcp",
        "transport": "streamable-http",
        "auth": "oauth2.1",
    }


# =============================================================================
# MCP ASGI App Mount (FastMCP)
# =============================================================================

# Note: The actual MCP protocol endpoint is mounted separately in main.py
# using FastMCP's http_app() method. This router just provides helper endpoints.

def get_mcp_asgi_app():
    """
    Create the FastMCP ASGI application for mounting.

    This creates a FastMCP server with all system tools and OAuth 2.1 authentication,
    then returns the ASGI app that can be mounted at /api (resulting in /api/mcp endpoint).

    Authentication:
        Uses BifrostAuthProvider which implements OAuth 2.1 with:
        - Discovery endpoints (/.well-known/oauth-*)
        - Authorization code flow with PKCE
        - Dynamic client registration
        - JWT token validation using Bifrost's existing tokens

        Users authenticate through Bifrost's normal login flow via OAuth redirect.
        Only platform admins can access MCP (by default, configurable).

    Returns:
        ASGI application from FastMCP
    """
    from src.services.mcp.server import HAS_FASTMCP

    if not HAS_FASTMCP:
        logger.warning("FastMCP not installed - MCP HTTP endpoint will not be available")
        return None

    # Import here to avoid circular imports and only when FastMCP is available
    from src.services.mcp.server import BifrostMCPServer, MCPContext

    # Create OAuth 2.1 auth provider for Bifrost
    try:
        from src.services.mcp.auth import create_bifrost_auth_provider
        auth_provider = create_bifrost_auth_provider()
        logger.info("Created Bifrost OAuth 2.1 auth provider for MCP")
    except ImportError as e:
        logger.warning(f"Could not create auth provider: {e}")
        auth_provider = None

    # Create a default context for tool schema generation
    # The actual user context is derived from the validated JWT token
    default_context = MCPContext(
        user_id="00000000-0000-0000-0000-000000000000",
        is_platform_admin=True,  # Shows all tools in schema
    )

    server = BifrostMCPServer(default_context)
    fastmcp_server = server.get_fastmcp_server(auth=auth_provider)

    # Create ASGI app with default path="/mcp" - we mount at root so FastMCP
    # handles /mcp directly without Starlette's trailing slash redirect
    mcp_app = fastmcp_server.http_app(json_response=True)

    # Store original lifespan before wrapping
    original_lifespan = getattr(mcp_app, 'lifespan', None)

    # Wrap with CORS middleware to expose Mcp-Session-Id header
    # Required for browser-based clients like MCP Inspector to read session ID
    # Without this, CORS policy prevents JavaScript from reading the header
    cors_app = CORSMiddleware(
        mcp_app,
        allow_origins=["*"],  # MCP clients can come from anywhere
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )

    # Preserve FastMCP lifespan on the wrapper for main.py to find
    if original_lifespan:
        cors_app.lifespan = original_lifespan  # type: ignore[attr-defined]

    logger.info("Created FastMCP ASGI application with OAuth 2.1 auth and CORS")

    return cors_app


# =============================================================================
# MCP Configuration Endpoints (Platform Admin Only)
# =============================================================================


@router.get("/config")
async def get_mcp_config(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> MCPConfigResponse:
    """
    Get MCP external access configuration.

    Returns the current configuration for external MCP access,
    including whether it's enabled and what restrictions apply.
    """
    # Only platform admins can view MCP config
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform administrators can view MCP configuration"
        )

    service = MCPConfigService(db)
    config = await service.get_config()

    return MCPConfigResponse(
        enabled=config.enabled,
        require_platform_admin=config.require_platform_admin,
        allowed_tool_ids=config.allowed_tool_ids,
        blocked_tool_ids=config.blocked_tool_ids or [],
        is_configured=config.is_configured,
        configured_at=config.configured_at,
        configured_by=config.configured_by,
    )


@router.put("/config")
async def update_mcp_config(
    current_user: CurrentActiveUser,
    db: DbSession,
    request: MCPConfigRequest,
) -> MCPConfigResponse:
    """
    Update MCP external access configuration.

    Allows platform admins to configure:
    - Whether MCP is enabled
    - Whether platform admin is required
    - Which tools are allowed/blocked
    """
    # Only platform admins can update MCP config
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform administrators can update MCP configuration"
        )

    service = MCPConfigService(db)
    config = await service.save_config(
        enabled=request.enabled,
        require_platform_admin=request.require_platform_admin,
        allowed_tool_ids=request.allowed_tool_ids,
        blocked_tool_ids=request.blocked_tool_ids,
        updated_by=current_user.email,
    )

    # Invalidate cache so auth middleware picks up changes
    invalidate_mcp_config_cache()

    return MCPConfigResponse(
        enabled=config.enabled,
        require_platform_admin=config.require_platform_admin,
        allowed_tool_ids=config.allowed_tool_ids,
        blocked_tool_ids=config.blocked_tool_ids or [],
        is_configured=config.is_configured,
        configured_at=config.configured_at,
        configured_by=config.configured_by,
    )


@router.delete("/config")
async def delete_mcp_config(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> dict:
    """
    Delete MCP configuration and revert to defaults.

    This removes any custom configuration and reverts to:
    - enabled: True
    - require_platform_admin: True
    - all tools allowed
    """
    # Only platform admins can delete MCP config
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform administrators can delete MCP configuration"
        )

    service = MCPConfigService(db)
    deleted = await service.delete_config()

    # Invalidate cache
    invalidate_mcp_config_cache()

    if deleted:
        return {"message": "MCP configuration deleted, reverted to defaults"}
    else:
        return {"message": "No custom MCP configuration existed"}


@router.get("/tools")
async def list_mcp_tools(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> MCPToolsResponse:
    """
    List all available MCP tools.

    Returns information about each tool that can be exposed via MCP,
    useful for configuring allowed/blocked tool lists.
    """
    from src.services.mcp.server import BifrostMCPServer, MCPContext

    # Only platform admins can view tools
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform administrators can view MCP tools"
        )

    # Create context showing all tools
    context = MCPContext(
        user_id=current_user.user_id,
        org_id=current_user.organization_id,
        is_platform_admin=True,  # Show all tools
        user_email=current_user.email,
        user_name=current_user.name or current_user.email,
    )

    server = BifrostMCPServer(context)
    tool_names = server.get_tool_names()

    # Build tool info list
    tools = []
    for name in tool_names:
        # Remove prefix for display
        display_name = name.replace("mcp__bifrost__", "")
        tools.append(MCPToolInfo(
            id=display_name,
            name=display_name.replace("_", " ").title(),
            description=f"MCP tool: {display_name}",
            is_system=True,
        ))

    return MCPToolsResponse(tools=tools)
