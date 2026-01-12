"""
Agent MCP Tools

Tools for listing, creating, updating, and managing AI agents.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from uuid import uuid4

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


# ==================== SCHEMA TOOL ====================


@system_tool(
    id="get_agent_schema",
    name="Get Agent Schema",
    description="Get documentation for AI agent structure, channels, and configuration.",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_agent_schema(context: Any) -> str:  # noqa: ARG001
    """Get agent schema documentation generated from Pydantic models."""
    from src.models.contracts.agents import AgentCreate, AgentUpdate
    from src.services.mcp_server.schema_utils import models_to_markdown

    # Generate markdown from Pydantic models
    model_docs = models_to_markdown([
        (AgentCreate, "AgentCreate (for creating agents)"),
        (AgentUpdate, "AgentUpdate (for updating agents)"),
    ], "Agent Schema Documentation")

    # Add channel enum documentation
    channels_doc = """
## Available Channels

| Channel | Description |
|---------|-------------|
| chat | Web chat interface |
| voice | Voice/phone integration |
| teams | Microsoft Teams bot |
| slack | Slack bot integration |

## Usage Notes

- **tool_ids**: UUIDs of workflows to assign as callable tools. Use `list_workflows` to find available tools.
- **delegated_agent_ids**: UUIDs of agents this agent can delegate to for specialized tasks.
- **knowledge_sources**: Knowledge namespaces for RAG search.
- **system_tools**: Built-in MCP tool names to enable (e.g., "list_tables", "query_table").
- **scope**: Use "global" for visibility to all orgs, or "organization" (default).

## MCP Tools for Agents

- `list_agents` - List all accessible agents
- `get_agent` - Get agent details by ID or name
- `create_agent` - Create a new agent
- `update_agent` - Update agent properties
- `delete_agent` - Soft-delete an agent (deactivate)
"""

    return model_docs + channels_doc


# ==================== LIST/GET TOOLS ====================


@system_tool(
    id="list_agents",
    name="List Agents",
    description="List all AI agents accessible to the current user.",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_agents(context: Any) -> str:
    """List all agents."""
    from src.core.database import get_db_context
    from src.core.org_filter import OrgFilterType
    from src.repositories.agents import AgentRepository

    logger.info("MCP list_agents called")

    try:
        async with get_db_context() as db:
            # Determine filter type and org_id based on context
            if context.is_platform_admin:
                # Platform admins see all agents
                filter_type = OrgFilterType.ALL
                org_id = None
            elif context.org_id:
                # Org users see their org's agents + global agents
                filter_type = OrgFilterType.ORG_PLUS_GLOBAL
                org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
            else:
                # No org context - only global agents
                filter_type = OrgFilterType.GLOBAL_ONLY
                org_id = None

            repo = AgentRepository(db, org_id)
            agents = await repo.list_agents(filter_type, active_only=True)

            return json.dumps({
                "agents": [
                    {
                        "id": str(agent.id),
                        "name": agent.name,
                        "description": agent.description,
                        "channels": agent.channels,
                        "is_coding_mode": agent.is_coding_mode,
                        "is_active": agent.is_active,
                    }
                    for agent in agents
                ],
                "count": len(agents),
            })

    except Exception as e:
        logger.exception(f"Error listing agents via MCP: {e}")
        return json.dumps({"error": f"Error listing agents: {str(e)}"})


@system_tool(
    id="get_agent",
    name="Get Agent",
    description="Get detailed information about a specific agent including assigned tools and delegation targets.",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent UUID"},
            "agent_name": {"type": "string", "description": "Agent name (alternative to ID)"},
        },
        "required": [],
    },
)
async def get_agent(
    context: Any,
    agent_id: str | None = None,
    agent_name: str | None = None,
) -> str:
    """Get detailed information about a specific agent.

    Args:
        context: MCP context with user permissions
        agent_id: Agent UUID (preferred)
        agent_name: Agent name (alternative to ID)

    Returns:
        JSON with agent details
    """
    from sqlalchemy import or_, select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models.orm import Agent

    logger.info(f"MCP get_agent called: agent_id={agent_id}, agent_name={agent_name}")

    if not agent_id and not agent_name:
        return json.dumps({"error": "Either agent_id or agent_name is required"})

    try:
        async with get_db_context() as db:
            # Build query
            query = select(Agent).options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )

            if agent_id:
                try:
                    uuid_id = UUID(agent_id)
                except ValueError:
                    return json.dumps({"error": f"'{agent_id}' is not a valid UUID"})
                query = query.where(Agent.id == uuid_id)
            else:
                query = query.where(Agent.name == agent_name)

            # Apply org scoping for non-admins
            if not context.is_platform_admin and context.org_id:
                org_uuid = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
                query = query.where(
                    or_(
                        Agent.organization_id == org_uuid,
                        Agent.organization_id.is_(None)  # Global agents
                    )
                )

            result = await db.execute(query)
            agent = result.scalar_one_or_none()

            if not agent:
                identifier = agent_id or agent_name
                return json.dumps({"error": f"Agent '{identifier}' not found. Use list_agents to see available agents."})

            return json.dumps({
                "id": str(agent.id),
                "name": agent.name,
                "description": agent.description,
                "system_prompt": agent.system_prompt,
                "channels": agent.channels,
                "access_level": agent.access_level.value if agent.access_level else "role_based",
                "organization_id": str(agent.organization_id) if agent.organization_id else None,
                "is_active": agent.is_active,
                "is_coding_mode": agent.is_coding_mode,
                "is_system": agent.is_system,
                "file_path": agent.file_path,
                "created_by": agent.created_by,
                "created_at": agent.created_at.isoformat() if agent.created_at else None,
                "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
                "tool_ids": [str(t.id) for t in agent.tools] if agent.tools else [],
                "delegated_agent_ids": [str(a.id) for a in agent.delegated_agents] if agent.delegated_agents else [],
                "role_ids": [str(r.id) for r in agent.roles] if agent.roles else [],
                "knowledge_sources": agent.knowledge_sources or [],
                "system_tools": agent.system_tools or [],
            })

    except Exception as e:
        logger.exception(f"Error getting agent via MCP: {e}")
        return json.dumps({"error": f"Error getting agent: {str(e)}"})


@system_tool(
    id="create_agent",
    name="Create Agent",
    description="Create a new AI agent with system prompt and configuration.",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Agent name (1-255 chars)"},
            "system_prompt": {"type": "string", "description": "System prompt that defines the agent's behavior"},
            "description": {"type": "string", "description": "Optional description of what the agent does"},
            "channels": {
                "type": "array",
                "items": {"type": "string", "enum": ["chat", "voice", "teams", "slack"]},
                "description": "Communication channels (default: ['chat'])",
            },
            "is_coding_mode": {"type": "boolean", "description": "Enable coding mode with Claude Agent SDK"},
            "tool_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of workflow IDs to assign as tools",
            },
            "delegated_agent_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of agent IDs this agent can delegate to",
            },
            "knowledge_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of knowledge namespaces this agent can search",
            },
            "system_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of system tool names enabled for this agent",
            },
            "scope": {
                "type": "string",
                "enum": ["global", "organization"],
                "description": "Resource scope: 'global' (visible to all orgs) or 'organization' (default)",
            },
            "organization_id": {
                "type": "string",
                "description": "Organization UUID (overrides context.org_id when scope='organization')",
            },
        },
        "required": ["name", "system_prompt"],
    },
)
async def create_agent(
    context: Any,
    name: str,
    system_prompt: str,
    description: str | None = None,
    channels: list[str] | None = None,
    is_coding_mode: bool = False,
    tool_ids: list[str] | None = None,
    delegated_agent_ids: list[str] | None = None,
    knowledge_sources: list[str] | None = None,
    system_tools: list[str] | None = None,
    scope: str = "organization",
    organization_id: str | None = None,
) -> str:
    """Create a new agent.

    Args:
        context: MCP context with user permissions
        name: Agent name (1-255 chars)
        system_prompt: System prompt that defines the agent's behavior
        description: Optional description of what the agent does
        channels: Communication channels (default: ['chat'])
        is_coding_mode: Enable coding mode with Claude Agent SDK
        tool_ids: List of workflow IDs to assign as tools
        delegated_agent_ids: List of agent IDs this agent can delegate to
        knowledge_sources: List of knowledge namespaces this agent can search
        system_tools: List of system tool names enabled for this agent
        scope: 'global' (visible to all orgs) or 'organization' (default)
        organization_id: Override context.org_id when scope='organization'

    Returns:
        JSON with created agent details
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models.enums import AgentAccessLevel
    from src.models.orm import Agent, AgentDelegation, AgentTool, Workflow

    logger.info(f"MCP create_agent called: name={name}, scope={scope}")

    # Validate inputs
    if not name:
        return json.dumps({"error": "name is required"})
    if not system_prompt:
        return json.dumps({"error": "system_prompt is required"})
    if len(name) > 255:
        return json.dumps({"error": "name must be 255 characters or less"})
    if len(system_prompt) > 50000:
        return json.dumps({"error": "system_prompt must be 50000 characters or less"})

    # Validate scope parameter
    if scope not in ("global", "organization"):
        return json.dumps({"error": "scope must be 'global' or 'organization'"})

    # Validate channels if provided
    valid_channels = {"chat", "voice", "teams", "slack"}
    if channels:
        invalid_channels = set(channels) - valid_channels
        if invalid_channels:
            return json.dumps({"error": f"Invalid channels: {list(invalid_channels)}. Valid options: {list(valid_channels)}"})
    else:
        channels = ["chat"]

    # Determine effective organization_id based on scope
    effective_org_id: UUID | None = None
    if scope == "global":
        # Global resources have no organization_id
        effective_org_id = None
    else:
        # Organization scope: use provided organization_id or fall back to context.org_id
        if organization_id:
            try:
                effective_org_id = UUID(organization_id)
            except ValueError:
                return json.dumps({"error": f"organization_id '{organization_id}' is not a valid UUID"})
        elif context.org_id:
            effective_org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
        else:
            return json.dumps({"error": "organization_id is required when scope='organization' and no context org_id is set"})

    try:
        async with get_db_context() as db:
            agent_id = uuid4()
            now = datetime.now(tz=timezone.utc)

            # Create the agent
            agent = Agent(
                id=agent_id,
                name=name,
                description=description,
                system_prompt=system_prompt,
                channels=channels,
                access_level=AgentAccessLevel.ROLE_BASED,
                organization_id=effective_org_id,
                is_active=True,
                is_coding_mode=is_coding_mode,
                knowledge_sources=knowledge_sources or [],
                system_tools=system_tools or [],
                created_by=context.user_email or "mcp@bifrost.local",
                created_at=now,
                updated_at=now,
            )
            db.add(agent)

            # Add tool relationships
            tools: list[Workflow] = []
            if tool_ids:
                for tool_id in tool_ids:
                    try:
                        workflow_uuid = UUID(tool_id)
                        result = await db.execute(
                            select(Workflow)
                            .where(Workflow.id == workflow_uuid)
                            .where(Workflow.type == "tool")
                            .where(Workflow.is_active.is_(True))
                        )
                        workflow = result.scalar_one_or_none()
                        if workflow:
                            tools.append(workflow)
                            db.add(AgentTool(agent_id=agent_id, workflow_id=workflow.id))
                        else:
                            logger.warning(f"Tool workflow not found or inactive: {tool_id}")
                    except ValueError:
                        logger.warning(f"Invalid tool ID: {tool_id}")

            # Add delegation relationships
            delegated_agents: list[Agent] = []
            if delegated_agent_ids:
                for delegate_id in delegated_agent_ids:
                    try:
                        delegate_uuid = UUID(delegate_id)
                        if delegate_uuid == agent_id:
                            logger.warning("Agent cannot delegate to itself, skipping")
                            continue
                        result = await db.execute(
                            select(Agent)
                            .where(Agent.id == delegate_uuid)
                            .where(Agent.is_active.is_(True))
                        )
                        delegate = result.scalar_one_or_none()
                        if delegate:
                            delegated_agents.append(delegate)
                            db.add(AgentDelegation(
                                parent_agent_id=agent_id,
                                child_agent_id=delegate.id,
                            ))
                        else:
                            logger.warning(f"Delegate agent not found or inactive: {delegate_id}")
                    except ValueError:
                        logger.warning(f"Invalid delegate agent ID: {delegate_id}")

            await db.flush()

            # Write to file system (dual-write pattern)
            try:
                from src.routers.agents import _write_agent_to_file
                file_path = await _write_agent_to_file(db, agent, tools, delegated_agents)
                agent.file_path = file_path
                await db.flush()
            except Exception as e:
                logger.error(f"Failed to write agent file for {agent.id}: {e}", exc_info=True)
                # Continue - database write succeeded

            # Reload with relationships
            result = await db.execute(
                select(Agent)
                .options(
                    selectinload(Agent.tools),
                    selectinload(Agent.delegated_agents),
                    selectinload(Agent.roles),
                )
                .where(Agent.id == agent_id)
            )
            agent = result.scalar_one()

            logger.info(f"Created agent {agent.id}: {agent.name}")

            return json.dumps({
                "success": True,
                "id": str(agent.id),
                "name": agent.name,
                "description": agent.description,
                "channels": agent.channels,
                "is_coding_mode": agent.is_coding_mode,
                "tool_count": len(tools),
                "delegated_agent_count": len(delegated_agents),
                "file_path": agent.file_path,
            })

    except Exception as e:
        logger.exception(f"Error creating agent via MCP: {e}")
        return json.dumps({"error": f"Error creating agent: {str(e)}"})


@system_tool(
    id="update_agent",
    name="Update Agent",
    description="Update an existing agent's properties.",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent UUID (required)"},
            "name": {"type": "string", "description": "New agent name"},
            "description": {"type": "string", "description": "New description"},
            "system_prompt": {"type": "string", "description": "New system prompt"},
            "channels": {
                "type": "array",
                "items": {"type": "string", "enum": ["chat", "voice", "teams", "slack"]},
                "description": "New communication channels",
            },
            "is_active": {"type": "boolean", "description": "Enable/disable the agent"},
            "is_coding_mode": {"type": "boolean", "description": "Enable/disable coding mode"},
            "tool_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New list of workflow IDs (replaces existing)",
            },
            "delegated_agent_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New list of delegated agent IDs (replaces existing)",
            },
            "knowledge_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New list of knowledge namespaces",
            },
            "system_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New list of system tool names",
            },
        },
        "required": ["agent_id"],
    },
)
async def update_agent(
    context: Any,
    agent_id: str,
    name: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    channels: list[str] | None = None,
    is_active: bool | None = None,
    is_coding_mode: bool | None = None,
    tool_ids: list[str] | None = None,
    delegated_agent_ids: list[str] | None = None,
    knowledge_sources: list[str] | None = None,
    system_tools: list[str] | None = None,
) -> str:
    """Update an existing agent.

    Args:
        context: MCP context with user permissions
        agent_id: Agent UUID (required)
        name: New agent name
        description: New description
        system_prompt: New system prompt
        channels: New communication channels
        is_active: Enable/disable the agent
        is_coding_mode: Enable/disable coding mode
        tool_ids: New list of workflow IDs (replaces existing)
        delegated_agent_ids: New list of delegated agent IDs (replaces existing)
        knowledge_sources: New list of knowledge namespaces
        system_tools: New list of system tool names

    Returns:
        JSON with update confirmation
    """
    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models.orm import Agent, AgentDelegation, AgentTool, Workflow

    logger.info(f"MCP update_agent called: agent_id={agent_id}")

    if not agent_id:
        return json.dumps({"error": "agent_id is required"})

    # Validate agent_id is a valid UUID
    try:
        uuid_id = UUID(agent_id)
    except ValueError:
        return json.dumps({"error": f"'{agent_id}' is not a valid UUID"})

    # Validate channels if provided
    valid_channels = {"chat", "voice", "teams", "slack"}
    if channels:
        invalid_channels = set(channels) - valid_channels
        if invalid_channels:
            return json.dumps({"error": f"Invalid channels: {list(invalid_channels)}. Valid options: {list(valid_channels)}"})

    try:
        async with get_db_context() as db:
            # Get existing agent
            result = await db.execute(
                select(Agent)
                .options(
                    selectinload(Agent.tools),
                    selectinload(Agent.delegated_agents),
                    selectinload(Agent.roles),
                )
                .where(Agent.id == uuid_id)
            )
            agent = result.scalar_one_or_none()

            if not agent:
                return json.dumps({"error": f"Agent '{agent_id}' not found. Use list_agents to see available agents."})

            # Check access for non-admins
            if not context.is_platform_admin:
                if agent.organization_id:
                    if context.org_id and str(agent.organization_id) != str(context.org_id):
                        return json.dumps({"error": "You don't have permission to update this agent."})
                # Global agents can only be updated by admins
                if agent.organization_id is None:
                    return json.dumps({"error": "Only platform admins can update global agents."})

            # Check if system agent
            if agent.is_system:
                return json.dumps({"error": "System agents cannot be updated."})

            updates_made = []

            # Apply updates
            if name is not None:
                if len(name) > 255:
                    return json.dumps({"error": "name must be 255 characters or less"})
                agent.name = name
                updates_made.append("name")

            if description is not None:
                agent.description = description
                updates_made.append("description")

            if system_prompt is not None:
                if len(system_prompt) > 50000:
                    return json.dumps({"error": "system_prompt must be 50000 characters or less"})
                agent.system_prompt = system_prompt
                updates_made.append("system_prompt")

            if channels is not None:
                agent.channels = channels
                updates_made.append("channels")

            if is_active is not None:
                agent.is_active = is_active
                updates_made.append("is_active")

            if is_coding_mode is not None:
                agent.is_coding_mode = is_coding_mode
                updates_made.append("is_coding_mode")

            if knowledge_sources is not None:
                agent.knowledge_sources = knowledge_sources
                updates_made.append("knowledge_sources")

            if system_tools is not None:
                agent.system_tools = system_tools
                updates_made.append("system_tools")

            agent.updated_at = datetime.now(tz=timezone.utc)

            # Update tool relationships if provided
            tools: list[Workflow] = []
            if tool_ids is not None:
                await db.execute(
                    delete(AgentTool).where(AgentTool.agent_id == uuid_id)
                )
                for tool_id in tool_ids:
                    try:
                        workflow_uuid = UUID(tool_id)
                        result = await db.execute(
                            select(Workflow)
                            .where(Workflow.id == workflow_uuid)
                            .where(Workflow.type == "tool")
                            .where(Workflow.is_active.is_(True))
                        )
                        workflow = result.scalar_one_or_none()
                        if workflow:
                            tools.append(workflow)
                            db.add(AgentTool(agent_id=uuid_id, workflow_id=workflow.id))
                    except ValueError:
                        logger.warning(f"Invalid tool ID: {tool_id}")
                updates_made.append("tool_ids")

            # Update delegation relationships if provided
            delegated_agents: list[Agent] = []
            if delegated_agent_ids is not None:
                await db.execute(
                    delete(AgentDelegation).where(AgentDelegation.parent_agent_id == uuid_id)
                )
                for delegate_id in delegated_agent_ids:
                    try:
                        delegate_uuid = UUID(delegate_id)
                        if delegate_uuid == uuid_id:
                            logger.warning("Agent cannot delegate to itself, skipping")
                            continue
                        result = await db.execute(
                            select(Agent)
                            .where(Agent.id == delegate_uuid)
                            .where(Agent.is_active.is_(True))
                        )
                        delegate = result.scalar_one_or_none()
                        if delegate:
                            delegated_agents.append(delegate)
                            db.add(AgentDelegation(
                                parent_agent_id=uuid_id,
                                child_agent_id=delegate.id,
                            ))
                    except ValueError:
                        logger.warning(f"Invalid delegate agent ID: {delegate_id}")
                updates_made.append("delegated_agent_ids")

            if not updates_made:
                return json.dumps({"error": "No updates provided. Specify at least one field to update."})

            await db.flush()

            # Update file
            try:
                from src.routers.agents import _write_agent_to_file
                await _write_agent_to_file(
                    db, agent,
                    tools if tool_ids is not None else None,
                    delegated_agents if delegated_agent_ids is not None else None,
                )
            except Exception as e:
                logger.error(f"Failed to update agent file for {agent.id}: {e}", exc_info=True)

            # Reload with relationships
            result = await db.execute(
                select(Agent)
                .options(
                    selectinload(Agent.tools),
                    selectinload(Agent.delegated_agents),
                    selectinload(Agent.roles),
                )
                .where(Agent.id == uuid_id)
            )
            agent = result.scalar_one()

            logger.info(f"Updated agent {agent.id}: {', '.join(updates_made)}")

            return json.dumps({
                "success": True,
                "id": str(agent.id),
                "name": agent.name,
                "updates": updates_made,
                "file_path": agent.file_path,
            })

    except Exception as e:
        logger.exception(f"Error updating agent via MCP: {e}")
        return json.dumps({"error": f"Error updating agent: {str(e)}"})


@system_tool(
    id="delete_agent",
    name="Delete Agent",
    description="Delete an agent (soft delete - sets is_active to false).",
    category=ToolCategory.AGENT,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "description": "Agent UUID"},
        },
        "required": ["agent_id"],
    },
)
async def delete_agent(
    context: Any,
    agent_id: str,
) -> str:
    """Delete an agent (soft delete).

    Args:
        context: MCP context with user permissions
        agent_id: Agent UUID

    Returns:
        JSON with deletion confirmation
    """
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm import Agent

    logger.info(f"MCP delete_agent called: agent_id={agent_id}")

    if not agent_id:
        return json.dumps({"error": "agent_id is required"})

    # Validate agent_id is a valid UUID
    try:
        uuid_id = UUID(agent_id)
    except ValueError:
        return json.dumps({"error": f"'{agent_id}' is not a valid UUID"})

    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Agent).where(Agent.id == uuid_id)
            )
            agent = result.scalar_one_or_none()

            if not agent:
                return json.dumps({"error": f"Agent '{agent_id}' not found. Use list_agents to see available agents."})

            # Check access for non-admins
            if not context.is_platform_admin:
                if agent.organization_id:
                    if context.org_id and str(agent.organization_id) != str(context.org_id):
                        return json.dumps({"error": "You don't have permission to delete this agent."})
                # Global agents can only be deleted by admins
                if agent.organization_id is None:
                    return json.dumps({"error": "Only platform admins can delete global agents."})

            # Prevent deletion of system agents
            if agent.is_system:
                return json.dumps({"error": "System agents cannot be deleted."})

            # Soft delete
            agent.is_active = False
            agent.updated_at = datetime.now(tz=timezone.utc)
            await db.flush()

            logger.info(f"Deleted (soft) agent {agent.id}: {agent.name}")

            return json.dumps({
                "success": True,
                "id": str(agent.id),
                "name": agent.name,
                "message": f"Agent '{agent.name}' has been deactivated.",
            })

    except Exception as e:
        logger.exception(f"Error deleting agent via MCP: {e}")
        return json.dumps({"error": f"Error deleting agent: {str(e)}"})
