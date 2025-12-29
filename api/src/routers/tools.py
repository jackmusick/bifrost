"""
Tools Router

Unified endpoint for listing all available tools (system + workflow).
Provides a single source of truth for tool discovery.
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["Tools"])


# =============================================================================
# System Tools Registry
# =============================================================================

# These are the built-in MCP tools available to agents.
# For coding agents, all system tools are enabled by default.
SYSTEM_TOOLS: list[ToolInfo] = [
    ToolInfo(
        id="execute_workflow",
        name="Execute Workflow",
        description="Execute a Bifrost workflow by name and get results",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="list_workflows",
        name="List Workflows",
        description="List all registered workflows to verify file watcher discovery",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="list_integrations",
        name="List Integrations",
        description="List available integrations and their OAuth/config status",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="list_forms",
        name="List Forms",
        description="List all forms with their URLs for viewing in the platform",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="get_form_schema",
        name="Get Form Schema",
        description="Get documentation about form structure, field types, and examples",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="validate_form_schema",
        name="Validate Form Schema",
        description="Validate a form JSON structure before saving",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="create_form",
        name="Create Form",
        description="Create a new form with fields linked to a workflow",
        type="system",
        default_enabled_for_coding_agent=False,  # File ops for coding agent
    ),
    ToolInfo(
        id="get_form",
        name="Get Form",
        description="Get detailed information about a specific form including all fields",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="update_form",
        name="Update Form",
        description="Update an existing form's properties or fields",
        type="system",
        default_enabled_for_coding_agent=False,  # File ops for coding agent
    ),
    ToolInfo(
        id="search_knowledge",
        name="Search Knowledge",
        description="Search the Bifrost knowledge base for documentation and examples",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    # File Operations (disabled for coding agent - it has local file access)
    ToolInfo(
        id="read_file",
        name="Read File",
        description="Read a file from the workspace",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    ToolInfo(
        id="write_file",
        name="Write File",
        description="Write content to a file in the workspace (creates or overwrites)",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    ToolInfo(
        id="list_files",
        name="List Files",
        description="List files and directories in the workspace",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    ToolInfo(
        id="delete_file",
        name="Delete File",
        description="Delete a file or directory from the workspace",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    ToolInfo(
        id="search_files",
        name="Search Files",
        description="Search for text patterns across files in the workspace",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    ToolInfo(
        id="create_folder",
        name="Create Folder",
        description="Create a new folder in the workspace",
        type="system",
        default_enabled_for_coding_agent=False,
    ),
    # Workflow and Execution Tools
    ToolInfo(
        id="validate_workflow",
        name="Validate Workflow",
        description="Validate a workflow Python file for syntax and decorator issues",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="get_workflow_schema",
        name="Get Workflow Schema",
        description="Get documentation about workflow structure, decorators, and SDK features",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="get_workflow",
        name="Get Workflow",
        description="Get detailed metadata for a specific workflow by ID or name",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="list_executions",
        name="List Executions",
        description="List recent workflow executions with optional filtering",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
    ToolInfo(
        id="get_execution",
        name="Get Execution",
        description="Get details and logs for a specific workflow execution",
        type="system",
        default_enabled_for_coding_agent=True,
    ),
]


def get_system_tools() -> list[ToolInfo]:
    """Get the list of system tools."""
    return SYSTEM_TOOLS.copy()


def get_system_tool_ids() -> list[str]:
    """Get list of all system tool IDs (single source of truth)."""
    return [tool.id for tool in SYSTEM_TOOLS]


# =============================================================================
# Tools Endpoint
# =============================================================================


@router.get("")
async def list_tools(
    db: DbSession,
    user: CurrentActiveUser,
    type: Literal["system", "workflow"] | None = Query(
        default=None,
        description="Filter by tool type: 'system' for built-in tools, 'workflow' for user workflows"
    ),
    scope: str | None = Query(
        default=None,
        description="Filter scope for workflows: omit for all, 'global' for global only, or org UUID"
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
            select(Workflow)
            .where(Workflow.is_tool.is_(True))
            .where(Workflow.is_active.is_(True))
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
            tools.append(ToolInfo(
                id=str(workflow.id),
                name=workflow.name,
                description=workflow.tool_description or workflow.description or "",
                type="workflow",
                category=workflow.category,
                default_enabled_for_coding_agent=False,
            ))

    return ToolsResponse(tools=tools)


@router.get("/system")
async def list_system_tools(
    user: CurrentActiveUser,
) -> ToolsResponse:
    """
    List system tools only.

    Convenience endpoint that returns only built-in platform tools.
    Equivalent to GET /api/tools?type=system
    """
    return ToolsResponse(tools=get_system_tools())
