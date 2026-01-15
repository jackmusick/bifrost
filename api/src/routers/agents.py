"""
Agents Router

CRUD operations for AI agents.
Role-based access control following the forms pattern.

Agents are persisted to BOTH database AND file system (S3):
- Database: Fast queries, access control, relationships
- S3/File system: Source control, deployment portability, workspace sync
"""

import json
import logging
import re
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.core.auth import CurrentActiveUser, CurrentSuperuser
from src.core.database import DbSession
from src.core.org_filter import resolve_org_filter
from src.models.contracts.agents import (
    AgentCreate,
    AgentPublic,
    AgentSummary,
    AgentUpdate,
    AssignDelegationsToAgentRequest,
    AssignToolsToAgentRequest,
)
from src.models.orm import Agent, AgentDelegation, AgentRole, AgentTool, Role, Workflow
from src.repositories.agents import AgentRepository
from src.services.workflow_role_service import sync_agent_roles_to_workflows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agents"])


async def _validate_agent_references(
    db: DbSession,
    tool_ids: list[str] | None,
    delegated_agent_ids: list[str] | None,
    agent_id: UUID | None = None,  # For self-delegation check
) -> None:
    """
    Validate that all referenced tools and agents exist and are valid.

    Args:
        db: Database session
        tool_ids: List of tool IDs to validate (must be type='tool')
        delegated_agent_ids: List of agent IDs to delegate to
        agent_id: The agent being created/updated (for self-delegation check)

    Raises:
        HTTPException: 422 if any reference is invalid
    """
    errors: list[str] = []

    # Validate tool_ids
    if tool_ids:
        for tool_id in tool_ids:
            try:
                workflow_uuid = UUID(tool_id)
                result = await db.execute(
                    select(Workflow).where(Workflow.id == workflow_uuid)
                )
                workflow = result.scalar_one_or_none()
                if workflow is None:
                    errors.append(f"tool_id '{tool_id}' does not reference an existing workflow")
                elif not workflow.is_active:
                    errors.append(f"tool_id '{tool_id}' references an inactive workflow")
                elif workflow.type != "tool":
                    errors.append(
                        f"tool_id '{tool_id}' references a {workflow.type}, not a tool"
                    )
            except ValueError:
                errors.append(f"tool_id '{tool_id}' is not a valid UUID")

    # Validate delegated_agent_ids
    if delegated_agent_ids:
        for delegate_id in delegated_agent_ids:
            try:
                delegate_uuid = UUID(delegate_id)

                # Check for self-delegation
                if agent_id and delegate_uuid == agent_id:
                    errors.append(f"Agent cannot delegate to itself ('{delegate_id}')")
                    continue

                result = await db.execute(
                    select(Agent).where(Agent.id == delegate_uuid)
                )
                delegate = result.scalar_one_or_none()
                if delegate is None:
                    errors.append(f"delegated_agent_id '{delegate_id}' does not reference an existing agent")
                elif not delegate.is_active:
                    errors.append(f"delegated_agent_id '{delegate_id}' references an inactive agent")
            except ValueError:
                errors.append(f"delegated_agent_id '{delegate_id}' is not a valid UUID")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors, "message": "Invalid agent references"},
        )


def _generate_agent_filename(agent_name: str, agent_id: str) -> str:
    """
    Generate filesystem-safe filename from agent name.

    Format: {slugified-name}-{first-8-chars-of-uuid}.agent.json
    Example: customer-support-a1b2c3d4.agent.json
    """
    slug = re.sub(r'[^a-z0-9]+', '-', agent_name.lower()).strip('-')
    short_id = str(agent_id)[:8]
    return f"{slug[:50]}-{short_id}.agent.json"


def _agent_to_public(agent: Agent) -> AgentPublic:
    """Convert Agent ORM to AgentPublic with relationships."""
    return AgentPublic(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        system_prompt=agent.system_prompt,
        channels=agent.channels,
        access_level=agent.access_level,
        organization_id=agent.organization_id,
        is_active=agent.is_active,
        is_coding_mode=agent.is_coding_mode,
        is_system=agent.is_system,
        file_path=agent.file_path,
        created_by=agent.created_by,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        tool_ids=[str(t.id) for t in agent.tools],
        delegated_agent_ids=[str(a.id) for a in agent.delegated_agents],
        role_ids=[str(r.id) for r in agent.roles],
        knowledge_sources=agent.knowledge_sources or [],
        system_tools=agent.system_tools or [],
    )


async def _write_agent_to_file(
    db: DbSession,
    agent: Agent,
    tools: list[Workflow] | None = None,
    delegated_agents: list[Agent] | None = None,
) -> str:
    """
    Write agent to S3 file system.

    Returns the file path.
    """
    from src.services.file_storage import FileStorageService

    filename = _generate_agent_filename(agent.name, str(agent.id))
    file_path = f"workspace/agents/{filename}"

    # Use explicit None check - empty list [] is falsy but should still be used
    tool_list = tools if tools is not None else agent.tools
    delegate_list = delegated_agents if delegated_agents is not None else agent.delegated_agents

    # Note: access_level and organization_id are NOT written to JSON
    # These are environment-specific and should only be set in the database
    agent_data = {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "channels": agent.channels,
        "is_active": agent.is_active,
        "tool_ids": [str(t.id) for t in tool_list],
        "delegated_agent_ids": [str(a.id) for a in delegate_list],
        "knowledge_sources": agent.knowledge_sources or [],
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }

    storage = FileStorageService(db)
    await storage.write_file(
        path=file_path,
        content=json.dumps(agent_data, indent=2).encode("utf-8"),
    )
    # Result not used - agent JSON files don't need ID injection

    return file_path


# =============================================================================
# Agent CRUD Endpoints
# =============================================================================


@router.get("")
async def list_agents(
    db: DbSession,
    user: CurrentActiveUser,
    scope: str | None = Query(
        default=None,
        description="Filter scope: omit for all (superusers), 'global' for global only, "
        "or org UUID for specific org."
    ),
    category: str | None = None,
    active_only: bool = True,
) -> list[AgentSummary]:
    """
    List agents the user has access to.

    Organization filtering:
    - Superusers with scope omitted: show all agents
    - Superusers with scope='global': show only global agents
    - Superusers with scope={uuid}: show that org's agents only
    - Org users: always show their org's agents + global agents (scope ignored)

    Access level filtering (applied after org filter):
    - Platform admins see all agents
    - Users see AUTHENTICATED agents + ROLE_BASED agents assigned to their roles
    """
    # Apply organization filter using repository
    try:
        filter_type, filter_org_id = resolve_org_filter(user, scope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Check if user is platform admin
    is_admin = user.is_superuser or any(
        role in ["Platform Admin", "Platform Owner"]
        for role in user.roles
    )

    # Create repository with appropriate access context
    repo = AgentRepository(
        session=db,
        org_id=filter_org_id,
        user_id=user.user_id,
        is_superuser=is_admin,
    )

    if is_admin:
        # Admins use list_all_in_scope with filter_type for flexibility
        agents = await repo.list_all_in_scope(filter_type, active_only=active_only)
    else:
        # Regular users use list_agents with built-in cascade + role-based access
        agents = await repo.list_agents(active_only=active_only)

    return [
        AgentSummary(
            id=a.id,
            name=a.name,
            description=a.description,
            channels=a.channels,
            is_active=a.is_active,
            is_coding_mode=a.is_coding_mode,
        )
        for a in agents
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    db: DbSession,
    user: CurrentSuperuser,
) -> AgentPublic:
    """
    Create a new agent (platform admin only).

    Creates both database record and S3 file.
    """
    # Validate references before creating the agent
    await _validate_agent_references(
        db=db,
        tool_ids=agent_data.tool_ids,
        delegated_agent_ids=agent_data.delegated_agent_ids,
        agent_id=None,  # No self-delegation check for new agents
    )

    agent_id = uuid4()
    now = datetime.utcnow()

    # Create the agent
    agent = Agent(
        id=agent_id,
        name=agent_data.name,
        description=agent_data.description,
        system_prompt=agent_data.system_prompt,
        channels=[c.value for c in agent_data.channels],
        access_level=agent_data.access_level,
        organization_id=agent_data.organization_id,
        is_active=True,
        is_coding_mode=agent_data.is_coding_mode,
        knowledge_sources=agent_data.knowledge_sources or [],
        system_tools=agent_data.system_tools or [],
        created_by=user.email,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)

    # Add tool relationships
    tools: list[Workflow] = []
    if agent_data.tool_ids:
        for tool_id in agent_data.tool_ids:
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
            except ValueError:
                logger.warning(f"Invalid tool ID: {tool_id}")

    # Add delegation relationships
    delegated_agents: list[Agent] = []
    if agent_data.delegated_agent_ids:
        for delegate_id in agent_data.delegated_agent_ids:
            try:
                delegate_uuid = UUID(delegate_id)
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
            except ValueError:
                logger.warning(f"Invalid delegate agent ID: {delegate_id}")

    # Add role relationships
    if agent_data.role_ids:
        for role_id in agent_data.role_ids:
            try:
                role_uuid = UUID(role_id)
                result = await db.execute(
                    select(Role)
                    .where(Role.id == role_uuid)
                    .where(Role.is_active.is_(True))
                )
                role = result.scalar_one_or_none()
                if role:
                    db.add(AgentRole(
                        agent_id=agent_id,
                        role_id=role.id,
                        assigned_by=user.email,
                    ))
            except ValueError:
                logger.warning(f"Invalid role ID: {role_id}")

    await db.flush()

    # Write to file system
    file_path = await _write_agent_to_file(db, agent, tools, delegated_agents)
    agent.file_path = file_path
    await db.flush()

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

    # Sync agent roles to referenced workflows (tools) - additive
    await sync_agent_roles_to_workflows(db, agent, assigned_by=user.email)

    return _agent_to_public(agent)


@router.get("/{agent_id}")
async def get_agent(
    agent_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentPublic:
    """Get agent by ID."""
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.tools),
            selectinload(Agent.delegated_agents),
            selectinload(Agent.roles),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # TODO: Add access control check based on user roles

    return _agent_to_public(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    db: DbSession,
    user: CurrentSuperuser,
) -> AgentPublic:
    """Update an agent (platform admin only)."""
    result = await db.execute(
        select(Agent)
        .options(
            selectinload(Agent.tools),
            selectinload(Agent.delegated_agents),
            selectinload(Agent.roles),
        )
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # Validate references being updated
    await _validate_agent_references(
        db=db,
        tool_ids=agent_data.tool_ids,
        delegated_agent_ids=agent_data.delegated_agent_ids,
        agent_id=agent_id,  # For self-delegation check
    )

    # Update fields
    if agent_data.name is not None:
        agent.name = agent_data.name
    if agent_data.description is not None:
        agent.description = agent_data.description
    if agent_data.system_prompt is not None:
        agent.system_prompt = agent_data.system_prompt
    if agent_data.channels is not None:
        agent.channels = [c.value for c in agent_data.channels]
    if agent_data.access_level is not None:
        agent.access_level = agent_data.access_level
    if agent_data.organization_id is not None:
        agent.organization_id = agent_data.organization_id
    if agent_data.is_active is not None:
        agent.is_active = agent_data.is_active
    if agent_data.is_coding_mode is not None:
        agent.is_coding_mode = agent_data.is_coding_mode
    if agent_data.knowledge_sources is not None:
        agent.knowledge_sources = agent_data.knowledge_sources
    if agent_data.system_tools is not None:
        agent.system_tools = agent_data.system_tools

    agent.updated_at = datetime.utcnow()

    # Update tool relationships if provided
    tools: list[Workflow] = []
    if agent_data.tool_ids is not None:
        await db.execute(
            delete(AgentTool).where(AgentTool.agent_id == agent_id)
        )
        for tool_id in agent_data.tool_ids:
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
            except ValueError:
                logger.warning(f"Invalid tool ID: {tool_id}")

    # Update delegation relationships if provided
    delegated_agents: list[Agent] = []
    if agent_data.delegated_agent_ids is not None:
        await db.execute(
            delete(AgentDelegation).where(AgentDelegation.parent_agent_id == agent_id)
        )
        for delegate_id in agent_data.delegated_agent_ids:
            try:
                delegate_uuid = UUID(delegate_id)
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
            except ValueError:
                logger.warning(f"Invalid delegate agent ID: {delegate_id}")

    # Update role relationships if provided
    if agent_data.role_ids is not None:
        await db.execute(
            delete(AgentRole).where(AgentRole.agent_id == agent_id)
        )
        for role_id in agent_data.role_ids:
            try:
                role_uuid = UUID(role_id)
                result = await db.execute(
                    select(Role)
                    .where(Role.id == role_uuid)
                    .where(Role.is_active.is_(True))
                )
                role = result.scalar_one_or_none()
                if role:
                    db.add(AgentRole(
                        agent_id=agent_id,
                        role_id=role.id,
                        assigned_by=user.email,
                    ))
            except ValueError:
                logger.warning(f"Invalid role ID: {role_id}")

    await db.flush()

    # Update file
    await _write_agent_to_file(
        db, agent,
        tools if agent_data.tool_ids is not None else None,
        delegated_agents if agent_data.delegated_agent_ids is not None else None,
    )

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

    # Sync agent roles to referenced workflows (tools) - additive
    await sync_agent_roles_to_workflows(db, agent, assigned_by=user.email)

    return _agent_to_public(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    db: DbSession,
    user: CurrentSuperuser,
) -> None:
    """Soft delete an agent (platform admin only)."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # Prevent deletion of system agents
    if agent.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System agents cannot be deleted",
        )

    # Soft delete
    agent.is_active = False
    agent.updated_at = datetime.utcnow()
    await db.flush()


# =============================================================================
# Tool Assignment Endpoints
# =============================================================================


@router.get("/{agent_id}/tools")
async def get_agent_tools(
    agent_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> list[dict]:
    """Get tools assigned to an agent."""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.tools))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "description": t.tool_description or t.description,
            "category": t.category,
        }
        for t in agent.tools
    ]


@router.post("/{agent_id}/tools", status_code=status.HTTP_201_CREATED)
async def assign_tools_to_agent(
    agent_id: UUID,
    request: AssignToolsToAgentRequest,
    db: DbSession,
    user: CurrentSuperuser,
) -> list[dict]:
    """Assign tools to an agent (platform admin only)."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # Validate all tool references before proceeding
    await _validate_agent_references(
        db=db,
        tool_ids=request.workflow_ids,
        delegated_agent_ids=None,
    )

    added_tools = []
    for workflow_id in request.workflow_ids:
        try:
            workflow_uuid = UUID(workflow_id)
            result = await db.execute(
                select(Workflow)
                .where(Workflow.id == workflow_uuid)
                .where(Workflow.type == "tool")
                .where(Workflow.is_active.is_(True))
            )
            workflow = result.scalar_one_or_none()
            if workflow:
                # Check if already assigned
                existing = await db.execute(
                    select(AgentTool)
                    .where(AgentTool.agent_id == agent_id)
                    .where(AgentTool.workflow_id == workflow.id)
                )
                if not existing.scalar_one_or_none():
                    db.add(AgentTool(agent_id=agent_id, workflow_id=workflow.id))
                    added_tools.append({
                        "id": str(workflow.id),
                        "name": workflow.name,
                    })
        except ValueError:
            logger.warning(f"Invalid workflow ID: {workflow_id}")

    await db.flush()

    return added_tools


@router.delete("/{agent_id}/tools/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tool_from_agent(
    agent_id: UUID,
    workflow_id: UUID,
    db: DbSession,
    user: CurrentSuperuser,
) -> None:
    """Remove a tool from an agent (platform admin only)."""
    await db.execute(
        delete(AgentTool)
        .where(AgentTool.agent_id == agent_id)
        .where(AgentTool.workflow_id == workflow_id)
    )
    await db.flush()


# =============================================================================
# Delegation Assignment Endpoints
# =============================================================================


@router.get("/{agent_id}/delegations")
async def get_agent_delegations(
    agent_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> list[AgentSummary]:
    """Get agents this agent can delegate to."""
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.delegated_agents))
        .where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    return [
        AgentSummary(
            id=a.id,
            name=a.name,
            description=a.description,
            channels=a.channels,
            is_active=a.is_active,
        )
        for a in agent.delegated_agents
    ]


@router.post("/{agent_id}/delegations", status_code=status.HTTP_201_CREATED)
async def assign_delegations_to_agent(
    agent_id: UUID,
    request: AssignDelegationsToAgentRequest,
    db: DbSession,
    user: CurrentSuperuser,
) -> list[AgentSummary]:
    """Assign delegation targets to an agent (platform admin only)."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    # Validate all delegation references before proceeding
    await _validate_agent_references(
        db=db,
        tool_ids=None,
        delegated_agent_ids=request.agent_ids,
        agent_id=agent_id,  # For self-delegation check
    )

    added_delegations = []
    for delegate_id in request.agent_ids:
        try:
            delegate_uuid = UUID(delegate_id)
            if delegate_uuid == agent_id:
                continue  # Can't delegate to self

            result = await db.execute(
                select(Agent)
                .where(Agent.id == delegate_uuid)
                .where(Agent.is_active.is_(True))
            )
            delegate = result.scalar_one_or_none()
            if delegate:
                # Check if already assigned
                existing = await db.execute(
                    select(AgentDelegation)
                    .where(AgentDelegation.parent_agent_id == agent_id)
                    .where(AgentDelegation.child_agent_id == delegate.id)
                )
                if not existing.scalar_one_or_none():
                    db.add(AgentDelegation(
                        parent_agent_id=agent_id,
                        child_agent_id=delegate.id,
                    ))
                    added_delegations.append(AgentSummary(
                        id=delegate.id,
                        name=delegate.name,
                        description=delegate.description,
                        channels=delegate.channels,
                        is_active=delegate.is_active,
                    ))
        except ValueError:
            logger.warning(f"Invalid delegate agent ID: {delegate_id}")

    await db.flush()

    return added_delegations


@router.delete("/{agent_id}/delegations/{delegate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_delegation_from_agent(
    agent_id: UUID,
    delegate_id: UUID,
    db: DbSession,
    user: CurrentSuperuser,
) -> None:
    """Remove a delegation from an agent (platform admin only)."""
    await db.execute(
        delete(AgentDelegation)
        .where(AgentDelegation.parent_agent_id == agent_id)
        .where(AgentDelegation.child_agent_id == delegate_id)
    )
    await db.flush()
