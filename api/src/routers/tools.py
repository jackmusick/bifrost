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

# Import tools package to trigger registration of all @system_tool decorated functions
import src.services.mcp.tools  # noqa: F401
from src.services.mcp.tool_registry import get_all_system_tools, get_all_tool_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["Tools"])


# =============================================================================
# System Tools (Auto-generated from Registry)
# =============================================================================


def get_system_tools() -> list[ToolInfo]:
    """
    Get the list of system tools from the registry.

    Tools are automatically registered via @system_tool decorator.
    """
    return [
        ToolInfo(
            id=meta.id,
            name=meta.name,
            description=meta.description,
            type="system",
            category=meta.category.value if meta.category else None,
            default_enabled_for_coding_agent=meta.default_enabled_for_coding_agent,
        )
        for meta in get_all_system_tools()
    ]


def get_system_tool_ids() -> list[str]:
    """Get list of all system tool IDs."""
    return get_all_tool_ids()


# Backwards compatibility - some code imports SYSTEM_TOOLS directly
# This is now a computed property from the registry
def _get_system_tools_list() -> list[ToolInfo]:
    return get_system_tools()


# For backwards compatibility with imports like: from src.routers.tools import SYSTEM_TOOLS
# We create a lazy-loading wrapper
class _SystemToolsList(list):  # type: ignore[type-arg]
    """Lazy-loading list that populates from registry on first access."""

    _populated = False

    def _populate(self) -> None:
        if not self._populated:
            self.clear()
            self.extend(get_system_tools())
            self._populated = True

    def __iter__(self):  # type: ignore[override]
        self._populate()
        return super().__iter__()

    def __len__(self) -> int:
        self._populate()
        return super().__len__()

    def __getitem__(self, key):  # type: ignore[override]
        self._populate()
        return super().__getitem__(key)

    def copy(self) -> list[ToolInfo]:
        self._populate()
        return list(self)


SYSTEM_TOOLS: list[ToolInfo] = _SystemToolsList()  # type: ignore[assignment]


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
        query = (
            select(Workflow).where(Workflow.type == "tool").where(Workflow.is_active.is_(True))
        )

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
