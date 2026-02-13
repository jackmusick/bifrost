"""
Tools Router

Unified endpoint for listing all available tools (system + workflow).
System tools are auto-discovered from the tool registry.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession
from src.core.org_filter import resolve_org_filter
from src.models.contracts.agents import ToolInfo, ToolsResponse
from src.models.orm import Workflow

from src.services.mcp_server.server import get_system_tools as get_system_tools_from_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["Tools"])


# =============================================================================
# System Tools (Auto-generated from Registry)
# =============================================================================


def get_system_tools() -> list[ToolInfo]:
    """
    Get the list of system tools from the server module.

    Tools are defined in each tool module's TOOLS list.
    """
    return [
        ToolInfo(
            id=tool["id"],
            name=tool["name"],
            description=tool["description"],
            type="system",
        )
        for tool in get_system_tools_from_server()
    ]


def get_system_tool_ids() -> list[str]:
    """Get list of all system tool IDs."""
    return [tool["id"] for tool in get_system_tools_from_server()]


# =============================================================================
# Tools Endpoint
# =============================================================================


@router.get("")
async def list_tools(
    db: DbSession,
    user: CurrentActiveUser,
    type: Literal["system", "workflow"] | None = Query(
        default=None,
        description="Filter by tool type: 'system' for built-in tools, 'workflow' for user workflows",
    ),
    scope: str | None = Query(
        default=None,
        description="Filter scope for workflows: omit for all, 'global' for global only, or org UUID",
    ),
    include_inactive: bool = Query(
        default=False,
        description="Include deactivated workflows (for agent editor to show orphaned refs)",
    ),
) -> ToolsResponse:
    """
    List all available tools.

    Returns both system tools (built-in platform tools) and workflow tools
    (user workflows with is_tool=True). Use the `type` parameter to filter.

    System tools are always available. Workflow tools follow organization scoping.
    """
    tools: list[ToolInfo] = []

    # Add system tools (unless filtering to workflow only)
    if type is None or type == "system":
        tools.extend(get_system_tools())

    # Add workflow tools (unless filtering to system only)
    if type is None or type == "workflow":
        # Apply organization filter
        try:
            filter_type, filter_org_id = resolve_org_filter(user, scope)
        except ValueError:
            # Invalid scope - just return system tools
            return ToolsResponse(tools=tools)

        # Query workflows that are tools
        query = select(Workflow).where(Workflow.type == "tool")
        if not include_inactive:
            query = query.where(Workflow.is_active.is_(True))

        # Apply org filter
        if filter_type == "org" and filter_org_id:
            query = query.where(Workflow.organization_id == filter_org_id)
        elif filter_type == "global":
            query = query.where(Workflow.organization_id.is_(None))
        # "all" means no additional filter (superuser sees everything)

        result = await db.execute(query.order_by(Workflow.name))
        workflows = result.scalars().all()

        for workflow in workflows:
            tools.append(
                ToolInfo(
                    id=str(workflow.id),
                    name=workflow.name,
                    description=workflow.tool_description or workflow.description or "",
                    type="workflow",
                    category=workflow.category,
                    default_enabled_for_coding_agent=False,
                    is_active=workflow.is_active,
                )
            )

    return ToolsResponse(tools=tools)


@router.get("/system")
async def list_system_tools_endpoint(
    user: CurrentActiveUser,
) -> ToolsResponse:
    """
    List system tools only.

    Convenience endpoint that returns only built-in platform tools.
    Equivalent to GET /api/tools?type=system
    """
    return ToolsResponse(tools=get_system_tools())
