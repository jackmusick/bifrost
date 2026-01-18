"""
Workflow Role Service

Manages workflow role assignments, including automatic sync from
forms/apps/agents to workflows.

This service implements Phase 3 of the workflow-role-access plan:
auto-assignment of roles to workflows when entities are saved.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agents import Agent, AgentRole
from src.models.orm.app_roles import AppRole
from src.models.orm.forms import Form, FormField, FormRole
from src.models.orm.workflow_roles import WorkflowRole


# =============================================================================
# Workflow ID Extraction Functions
# =============================================================================


def extract_form_workflow_ids(
    form: Form,
    fields: list[FormField] | None = None,
) -> list[UUID]:
    """
    Extract all workflow IDs referenced by a form.

    Extracts from:
    - form.workflow_id (main execution workflow)
    - form.launch_workflow_id (startup/pre-execution workflow)
    - form_fields.data_provider_id (dynamic field data providers)

    Args:
        form: The Form ORM object
        fields: Optional list of fields (uses form.fields if not provided)

    Returns:
        List of workflow UUIDs (deduplicated)
    """
    workflow_ids: set[UUID] = set()

    # Main workflow
    if form.workflow_id:
        try:
            workflow_ids.add(UUID(form.workflow_id))
        except ValueError:
            pass

    # Launch workflow
    if form.launch_workflow_id:
        try:
            workflow_ids.add(UUID(form.launch_workflow_id))
        except ValueError:
            pass

    # Data providers from fields
    form_fields = fields if fields is not None else form.fields
    for field in form_fields:
        if field.data_provider_id:
            workflow_ids.add(field.data_provider_id)

    return list(workflow_ids)


def extract_agent_workflow_ids(agent: Agent) -> list[UUID]:
    """
    Extract all workflow IDs (tools) referenced by an agent.

    Args:
        agent: The Agent ORM object with tools relationship loaded

    Returns:
        List of workflow UUIDs (tool IDs)
    """
    return [tool.id for tool in agent.tools]


def extract_app_workflow_ids() -> list[UUID]:
    """
    Extract all workflow IDs from app pages and components.

    Note: The component engine has been removed. Apps no longer reference
    workflows through pages/components. Code engine apps reference workflows
    through their code files, which is not tracked in the database.

    This function now always returns an empty list.

    Returns:
        Empty list (app workflow references are no longer tracked)
    """
    # Component engine removed - apps no longer have pages/components
    # that reference workflows in a trackable way
    return []


# =============================================================================
# WorkflowRoleService
# =============================================================================


class WorkflowRoleService:
    """Service for managing workflow role assignments."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_entity_roles_to_workflows(
        self,
        workflow_ids: list[UUID],
        role_ids: list[UUID],
        assigned_by: str,
    ) -> None:
        """
        Bulk assign roles to workflows (additive, upsert pattern).

        For each workflow in workflow_ids, ensure all role_ids are assigned.
        This is ADDITIVE - it never removes existing roles from workflows.
        Uses PostgreSQL ON CONFLICT DO NOTHING for efficiency.

        Args:
            workflow_ids: List of workflow UUIDs to assign roles to
            role_ids: List of role UUIDs to assign to the workflows
            assigned_by: Email of the user performing the assignment
        """
        if not workflow_ids or not role_ids:
            return

        now = datetime.utcnow()

        # Build list of all (workflow_id, role_id) combinations to insert
        values = [
            {
                "workflow_id": wf_id,
                "role_id": role_id,
                "assigned_by": assigned_by,
                "assigned_at": now,
            }
            for wf_id in workflow_ids
            for role_id in role_ids
        ]

        # Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING for efficiency
        stmt = insert(WorkflowRole).values(values)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["workflow_id", "role_id"]
        )

        await self.db.execute(stmt)

    async def get_form_role_ids(self, form_id: UUID) -> list[UUID]:
        """Get all role IDs assigned to a form."""
        result = await self.db.execute(
            select(FormRole.role_id).where(FormRole.form_id == form_id)
        )
        return list(result.scalars().all())

    async def get_agent_role_ids(self, agent_id: UUID) -> list[UUID]:
        """Get all role IDs assigned to an agent."""
        result = await self.db.execute(
            select(AgentRole.role_id).where(AgentRole.agent_id == agent_id)
        )
        return list(result.scalars().all())

    async def get_app_role_ids(self, app_id: UUID) -> list[UUID]:
        """Get all role IDs assigned to an application."""
        result = await self.db.execute(
            select(AppRole.role_id).where(AppRole.app_id == app_id)
        )
        return list(result.scalars().all())


# =============================================================================
# Convenience Functions
# =============================================================================


async def sync_form_roles_to_workflows(
    db: AsyncSession,
    form: Form,
    fields: list[FormField] | None = None,
    assigned_by: str = "system",
) -> None:
    """
    Sync form's roles to all workflows referenced by the form.

    This is a convenience wrapper that:
    1. Extracts workflow IDs from the form
    2. Gets the form's role IDs
    3. Assigns those roles to all workflows

    Args:
        db: Database session
        form: The Form ORM object
        fields: Optional list of fields (uses form.fields if not provided)
        assigned_by: Email of the user performing the assignment
    """
    service = WorkflowRoleService(db)

    # Extract workflow IDs from form
    workflow_ids = extract_form_workflow_ids(form, fields)
    if not workflow_ids:
        return

    # Get form's role IDs
    role_ids = await service.get_form_role_ids(form.id)
    if not role_ids:
        return

    # Sync roles to workflows
    await service.sync_entity_roles_to_workflows(
        workflow_ids=workflow_ids,
        role_ids=role_ids,
        assigned_by=assigned_by,
    )


async def sync_agent_roles_to_workflows(
    db: AsyncSession,
    agent: Agent,
    assigned_by: str = "system",
) -> None:
    """
    Sync agent's roles to all workflows (tools) used by the agent.

    This is a convenience wrapper that:
    1. Extracts workflow IDs (tools) from the agent
    2. Gets the agent's role IDs
    3. Assigns those roles to all workflows

    Args:
        db: Database session
        agent: The Agent ORM object with tools relationship loaded
        assigned_by: Email of the user performing the assignment
    """
    service = WorkflowRoleService(db)

    # Extract workflow IDs from agent tools
    workflow_ids = extract_agent_workflow_ids(agent)
    if not workflow_ids:
        return

    # Get agent's role IDs
    role_ids = await service.get_agent_role_ids(agent.id)
    if not role_ids:
        return

    # Sync roles to workflows
    await service.sync_entity_roles_to_workflows(
        workflow_ids=workflow_ids,
        role_ids=role_ids,
        assigned_by=assigned_by,
    )


async def sync_app_roles_to_workflows(
    db: AsyncSession,
    app_id: UUID,
    assigned_by: str = "system",
) -> None:
    """
    Sync app's roles to all workflows referenced by the app.

    Note: The component engine has been removed. Apps no longer reference
    workflows through pages/components. Code engine apps reference workflows
    through their code files, which is not tracked in the database.

    This function is now a no-op but kept for API compatibility.

    Args:
        db: Database session
        app_id: The Application UUID
        assigned_by: Email of the user performing the assignment
    """
    # Component engine removed - apps no longer have pages/components
    # that reference workflows in a trackable way. This is now a no-op.
    pass
