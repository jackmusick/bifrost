"""
MCP Tool Filter Middleware

Filters the tools/list response based on the authenticated user's
agent access permissions. This ensures users only see tools from
agents they have access to via their roles.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext

logger = logging.getLogger(__name__)

# Check if FastMCP is available
try:
    from fastmcp.exceptions import ToolError
    from fastmcp.server.dependencies import get_access_token
    from fastmcp.server.middleware import Middleware

    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False

    # Stub classes for when FastMCP is not installed
    class Middleware:  # type: ignore[no-redef]
        """Stub middleware class."""

        pass

    class ToolError(Exception):  # type: ignore[no-redef]
        """Stub error class."""

        pass

    def get_access_token():  # type: ignore[no-redef]
        """Stub function."""
        return None


class ToolFilterMiddleware(Middleware):
    """
    FastMCP middleware that filters tools based on user's agent access.

    This middleware intercepts the tools/list MCP method and filters
    the response to only include tools the authenticated user has
    access to based on their role assignments to agents.

    It also blocks execution of tools the user doesn't have access to
    as a second layer of protection.
    """

    async def on_list_tools(
        self, context: "MiddlewareContext", call_next
    ) -> list:
        """
        Filter tools/list response based on user permissions.

        Args:
            context: FastMCP middleware context
            call_next: Next handler in the chain

        Returns:
            Filtered list of tools the user can access
        """
        # Get all tools first
        all_tools = await call_next(context)

        # Get authenticated user from token
        token = get_access_token()
        if token is None:
            logger.warning("MCP tools/list: No authenticated user, returning empty list")
            return []

        user_roles = token.claims.get("roles", [])
        is_superuser = token.claims.get("is_superuser", False)
        user_email = token.claims.get("email", "unknown")

        logger.info(
            f"MCP tools/list: Filtering for user {user_email}, "
            f"roles={user_roles}, is_superuser={is_superuser}"
        )

        # Get accessible tool IDs from service
        try:
            from src.core.database import get_db_context
            from src.services.mcp.tool_access import MCPToolAccessService

            async with get_db_context() as db:
                service = MCPToolAccessService(db)
                result = await service.get_accessible_tools(
                    user_roles=user_roles,
                    is_superuser=is_superuser,
                )
                accessible_ids = {t.id for t in result.tools}

            # Filter to only accessible tools
            filtered_tools = [
                tool for tool in all_tools
                if tool.name in accessible_ids
            ]

            logger.info(
                f"MCP tools/list: Filtered {len(all_tools)} -> {len(filtered_tools)} tools "
                f"for user {user_email}"
            )

            return filtered_tools

        except Exception as e:
            logger.exception(f"MCP tools/list: Error filtering tools: {e}")
            # On error, return empty list for security
            return []

    async def on_call_tool(
        self, context: "MiddlewareContext", call_next
    ):
        """
        Block execution of tools user doesn't have access to.

        This is a second layer of protection in case someone tries to
        call a tool directly without going through tools/list.

        Args:
            context: FastMCP middleware context
            call_next: Next handler in the chain

        Returns:
            Tool execution result if authorized

        Raises:
            ToolError: If user doesn't have access to the tool
        """
        tool_name = context.message.name

        # Get authenticated user from token
        token = get_access_token()
        if token is None:
            raise ToolError("Authentication required to call tools")

        user_roles = token.claims.get("roles", [])
        is_superuser = token.claims.get("is_superuser", False)
        user_email = token.claims.get("email", "unknown")

        # Check if user has access to this tool
        try:
            from src.core.database import get_db_context
            from src.services.mcp.tool_access import MCPToolAccessService

            async with get_db_context() as db:
                service = MCPToolAccessService(db)
                result = await service.get_accessible_tools(
                    user_roles=user_roles,
                    is_superuser=is_superuser,
                )
                accessible_ids = {t.id for t in result.tools}

            if tool_name not in accessible_ids:
                logger.warning(
                    f"MCP tools/call: Access denied for user {user_email} "
                    f"to tool '{tool_name}'"
                )
                raise ToolError(
                    f"Access denied: You don't have permission to use '{tool_name}'"
                )

            logger.info(
                f"MCP tools/call: User {user_email} authorized to call '{tool_name}'"
            )

        except ToolError:
            raise
        except Exception as e:
            logger.exception(f"MCP tools/call: Error checking access: {e}")
            raise ToolError(f"Authorization check failed: {e}")

        # User is authorized, proceed with tool call
        return await call_next(context)
