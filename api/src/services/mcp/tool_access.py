"""
MCP Tool Access Service

Computes which MCP tools a user can access based on their agent access permissions.
Tools are sourced from agents the user has access to via role assignments.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.contracts.agents import ToolInfo
from src.models.enums import AgentAccessLevel
from src.models.orm.agents import Agent
from src.routers.tools import SYSTEM_TOOLS
from src.services.mcp.config_service import MCPConfig, MCPConfigService

logger = logging.getLogger(__name__)


@dataclass
class MCPToolAccessResult:
    """Result of computing accessible MCP tools."""

    tools: list[ToolInfo]
    accessible_agent_ids: list[UUID]
    accessible_namespaces: list[str]  # Knowledge namespaces from accessible agents


class MCPToolAccessService:
    """
    Service for computing which MCP tools a user can access.

    Access flow:
    1. Determine which agents the user can access via their roles
    2. Collect system_tools and workflow tools from accessible agents
    3. Apply global MCP config allowlist/blocklist
    4. Return the final tool list

    Tool sources per agent:
    - System tools: agent.system_tools array (e.g., ["execute_workflow", "list_workflows"])
    - Workflow tools: agent.tools relationship (workflows assigned via agent_tools table)
    """

    # Map system tool IDs to their metadata from SYSTEM_TOOLS
    _SYSTEM_TOOL_MAP: dict[str, ToolInfo] = {tool.id: tool for tool in SYSTEM_TOOLS}

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_accessible_tools(
        self,
        user_roles: list[str],
        is_superuser: bool,
    ) -> MCPToolAccessResult:
        """
        Get all MCP tools accessible to the user.

        Args:
            user_roles: List of role names the user has (from JWT claims)
            is_superuser: Whether user is platform admin

        Returns:
            MCPToolAccessResult with tools and accessible agent IDs
        """
        # Step 1: Get accessible agents
        accessible_agents = await self._get_accessible_agents(
            user_roles=user_roles,
            is_superuser=is_superuser,
        )

        # Step 2: Collect tools from accessible agents
        tools: list[ToolInfo] = []
        seen_tool_ids: set[str] = set()  # Deduplicate across agents

        for agent in accessible_agents:
            # Add system tools from agent.system_tools
            for system_tool_id in agent.system_tools or []:
                if system_tool_id in seen_tool_ids:
                    continue
                seen_tool_ids.add(system_tool_id)

                # Get metadata from SYSTEM_TOOLS registry
                if system_tool_id in self._SYSTEM_TOOL_MAP:
                    tools.append(self._SYSTEM_TOOL_MAP[system_tool_id])
                else:
                    # Unknown system tool - create basic info
                    logger.warning(f"Unknown system tool '{system_tool_id}' in agent '{agent.name}'")
                    tools.append(
                        ToolInfo(
                            id=system_tool_id,
                            name=system_tool_id.replace("_", " ").title(),
                            description=f"System tool: {system_tool_id}",
                            type="system",
                        )
                    )

            # Add workflow tools from agent.tools relationship
            for workflow in agent.tools or []:
                workflow_id = str(workflow.id)
                if workflow_id in seen_tool_ids:
                    continue
                seen_tool_ids.add(workflow_id)

                # Get the registered MCP tool name (human-readable)
                # Falls back to workflow ID if not yet registered
                from src.services.mcp.server import get_registered_tool_name

                registered_name = get_registered_tool_name(workflow_id)
                tool_id = registered_name if registered_name else workflow_id

                tools.append(
                    ToolInfo(
                        id=tool_id,  # Use registered MCP tool name for middleware matching
                        name=workflow.name,
                        description=workflow.tool_description or workflow.description or "",
                        type="workflow",
                        category=workflow.category,
                        default_enabled_for_coding_agent=False,
                    )
                )

        # Step 3: Apply global MCP config allowlist/blocklist
        config_service = MCPConfigService(self.session)
        config = await config_service.get_config()
        tools = self._apply_config_filters(tools, config)

        # Collect knowledge namespaces from accessible agents
        seen_namespaces: set[str] = set()
        for agent in accessible_agents:
            for ns in agent.knowledge_sources or []:
                seen_namespaces.add(ns)

        return MCPToolAccessResult(
            tools=tools,
            accessible_agent_ids=[agent.id for agent in accessible_agents],
            accessible_namespaces=list(seen_namespaces),
        )

    async def _get_accessible_agents(
        self,
        user_roles: list[str],
        is_superuser: bool,
    ) -> list[Agent]:
        """
        Get agents accessible to the user based on access_level and roles.

        Rules:
        - AUTHENTICATED: Any authenticated user can access
        - ROLE_BASED with roles: User must share at least one role with the agent
        - ROLE_BASED with no roles: Only superusers can access
        - Platform admins (superusers) are ALSO filtered by agent access (no bypass)
        """
        # Query all active agents with their tools and roles eagerly loaded
        query = (
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.roles),
            )
            .where(Agent.is_active.is_(True))
        )

        result = await self.session.execute(query)
        all_agents = result.scalars().unique().all()

        # Filter by access level
        accessible_agents: list[Agent] = []
        user_role_set = set(user_roles)

        for agent in all_agents:
            if agent.access_level == AgentAccessLevel.AUTHENTICATED:
                # Any authenticated user can access
                accessible_agents.append(agent)

            elif agent.access_level == AgentAccessLevel.ROLE_BASED:
                # Get role names from agent's roles
                agent_role_names = {role.name for role in agent.roles}

                if not agent_role_names:
                    # ROLE_BASED with no roles = only superusers can access
                    if is_superuser:
                        accessible_agents.append(agent)
                elif user_role_set & agent_role_names:
                    # User has at least one matching role
                    accessible_agents.append(agent)

            # Note: PUBLIC agents are not included for MCP access
            # as MCP requires authentication

        return accessible_agents

    def _apply_config_filters(
        self,
        tools: list[ToolInfo],
        config: MCPConfig,
    ) -> list[ToolInfo]:
        """Apply global allowlist/blocklist from MCP config."""
        # Apply allowlist (if set, only show tools in the list)
        if config.allowed_tool_ids:
            allowed_set = set(config.allowed_tool_ids)
            tools = [t for t in tools if t.id in allowed_set]

        # Apply blocklist (remove any blocked tools)
        if config.blocked_tool_ids:
            blocked_set = set(config.blocked_tool_ids)
            tools = [t for t in tools if t.id not in blocked_set]

        return tools
