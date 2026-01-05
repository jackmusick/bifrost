"""
Integration MCP Tools

Tools for listing available integrations.
"""

import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="list_integrations",
    name="List Integrations",
    description="List available integrations that can be used in workflows.",
    category=ToolCategory.INTEGRATION,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_integrations(context: Any) -> str:
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
