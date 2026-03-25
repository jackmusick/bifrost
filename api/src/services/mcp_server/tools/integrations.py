"""
Integration MCP Tools

Tools for listing available integrations.
"""

import logging
from typing import Any

from fastmcp.tools.tool import ToolResult

from src.services.mcp_server.tool_result import error_result, success_result
from src.services.mcp_server.tools.db import get_tool_db

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


async def list_integrations(context: Any) -> ToolResult:
    """List all available integrations."""
    from sqlalchemy import select

    from src.models.orm.integrations import Integration, IntegrationMapping

    logger.info("MCP list_integrations called")

    try:
        async with get_tool_db(context) as db:
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

            integration_list = [
                {
                    "name": integration.name,
                    "has_oauth": integration.has_oauth_config,
                    "entity_id_name": integration.entity_id_name,
                }
                for integration in integrations
            ]

            display_text = f"Found {len(integration_list)} integration(s)"
            return success_result(
                display_text, {"integrations": integration_list, "count": len(integration_list)}
            )

    except Exception as e:
        logger.exception(f"Error listing integrations via MCP: {e}")
        return error_result(f"Error listing integrations: {str(e)}")


# Tool metadata for registration
TOOLS = [
    ("list_integrations", "List Integrations", "List available integrations that can be used in workflows."),
]


def register_tools(mcp: Any, get_context_fn: Any) -> None:
    """Register all integrations tools with FastMCP."""
    from src.services.mcp_server.generators.fastmcp_generator import register_tool_with_context

    tool_funcs = {
        "list_integrations": list_integrations,
    }

    for tool_id, name, description in TOOLS:
        register_tool_with_context(mcp, tool_funcs[tool_id], tool_id, description, get_context_fn)
