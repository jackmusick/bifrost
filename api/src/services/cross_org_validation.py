"""
Cross-Organization Validation Service

Validates that org-scoped entities only reference workflows from:
1. The same organization
2. Global workflows (organization_id = NULL)

This prevents org A from using workflows belonging to org B.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import Workflow


class CrossOrgValidationError(ValueError):
    """Raised when a cross-org reference is detected."""
    pass


async def validate_workflow_reference(
    db: AsyncSession,
    workflow_id: UUID,
    entity_org_id: UUID | None,
    entity_type: str = "entity",
) -> None:
    """
    Validate that an entity can reference a workflow.

    Rules:
    - Global entities (org_id = None) can reference any workflow
    - Org-scoped entities can reference:
      - Global workflows (organization_id = None)
      - Workflows from the same organization

    Args:
        db: Database session
        workflow_id: The workflow being referenced
        entity_org_id: The organization of the referencing entity (None = global)
        entity_type: Description for error messages (e.g., "form", "agent", "app")

    Raises:
        CrossOrgValidationError: If the reference crosses organization boundaries
    """
    # Global entities can reference any workflow
    if entity_org_id is None:
        return

    # Get workflow's organization
    result = await db.execute(
        select(Workflow.organization_id).where(Workflow.id == workflow_id)
    )
    workflow_org_id = result.scalar_one_or_none()

    # Workflow not found - let the caller handle 404
    if workflow_org_id is None:
        # Check if workflow exists at all
        exists_result = await db.execute(
            select(Workflow.id).where(Workflow.id == workflow_id)
        )
        if exists_result.scalar_one_or_none() is None:
            # Workflow doesn't exist - not our problem
            return
        # Workflow exists and is global - allowed
        return

    # Check if same organization
    if workflow_org_id != entity_org_id:
        raise CrossOrgValidationError(
            f"Cannot reference workflow from a different organization. "
            f"The {entity_type} belongs to organization {entity_org_id}, "
            f"but the workflow belongs to organization {workflow_org_id}. "
            f"Only global workflows or workflows from the same organization can be referenced."
        )


async def validate_workflow_references(
    db: AsyncSession,
    workflow_ids: list[UUID],
    entity_org_id: UUID | None,
    entity_type: str = "entity",
) -> None:
    """
    Validate multiple workflow references at once.

    Args:
        db: Database session
        workflow_ids: List of workflow IDs being referenced
        entity_org_id: The organization of the referencing entity (None = global)
        entity_type: Description for error messages

    Raises:
        CrossOrgValidationError: If any reference crosses organization boundaries
    """
    for workflow_id in workflow_ids:
        await validate_workflow_reference(db, workflow_id, entity_org_id, entity_type)
