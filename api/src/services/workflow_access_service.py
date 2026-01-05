"""
Workflow Access Service

Extracts workflow references from forms/apps and syncs to workflow_access table
for fast execution authorization lookups.

This service is called at mutation time (form create/update, app publish),
NOT at execution time. The precomputed table allows O(1) lookups.

Security boundary: Only API endpoints call this service.
File sync/import NEVER sets permissions.
"""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.forms import Form, FormField
from src.models.orm.workflow_access import WorkflowAccess


def extract_form_workflows(
    form: Form,
    fields: list[FormField] | None = None,
) -> set[UUID]:
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
        Set of workflow UUIDs
    """
    workflows: set[UUID] = set()

    # Main workflow
    if form.workflow_id:
        try:
            workflows.add(UUID(form.workflow_id))
        except ValueError:
            pass

    # Launch workflow
    if form.launch_workflow_id:
        try:
            workflows.add(UUID(form.launch_workflow_id))
        except ValueError:
            pass

    # Data providers from fields
    form_fields = fields if fields is not None else form.fields
    for field in form_fields:
        if field.data_provider_id:
            workflows.add(field.data_provider_id)

    return workflows


def _extract_workflows_from_props(obj: Any) -> set[UUID]:
    """
    Recursively find all workflowId and dataProviderId values in a nested dict/list.

    Handles all nested patterns including:
    - props.workflowId
    - props.onClick.workflowId
    - props.rowActions[].onClick.workflowId
    - props.headerActions[].onClick.workflowId
    - props.footerActions[].workflowId
    - Any other nested structure

    Args:
        obj: Nested dict, list, or primitive

    Returns:
        Set of workflow UUIDs found
    """
    workflows: set[UUID] = set()

    if isinstance(obj, dict):
        # Check for workflowId key
        if wf_id := obj.get("workflowId"):
            if isinstance(wf_id, str):
                try:
                    workflows.add(UUID(wf_id))
                except ValueError:
                    pass

        # Check for dataProviderId key
        if dp_id := obj.get("dataProviderId"):
            if isinstance(dp_id, str):
                try:
                    workflows.add(UUID(dp_id))
                except ValueError:
                    pass

        # Recurse into all values
        for value in obj.values():
            workflows.update(_extract_workflows_from_props(value))

    elif isinstance(obj, list):
        for item in obj:
            workflows.update(_extract_workflows_from_props(item))

    return workflows


def extract_app_workflows(
    pages: list[Any],
    components: list[Any],
    live_only: bool = True,
) -> set[UUID]:
    """
    Extract all workflow IDs from app pages and components.

    Extracts from:
    - page.launch_workflow_id
    - page.data_sources[].workflowId
    - page.data_sources[].dataProviderId
    - component.loading_workflows[]
    - component.props (recursively - all workflowId/dataProviderId values)

    Args:
        pages: List of AppPage ORM objects (or dicts with same structure)
        components: List of AppComponent ORM objects (or dicts with same structure)
        live_only: Only extract from published (is_draft=False) pages/components

    Returns:
        Set of workflow UUIDs
    """
    workflows: set[UUID] = set()

    for page in pages:
        # Filter to live pages if requested
        is_draft = getattr(page, "is_draft", page.get("is_draft", True) if isinstance(page, dict) else True)
        if live_only and is_draft:
            continue

        # Page launch workflow
        launch_wf_id = (
            getattr(page, "launch_workflow_id", None)
            if hasattr(page, "launch_workflow_id")
            else page.get("launch_workflow_id") if isinstance(page, dict) else None
        )
        if launch_wf_id:
            if isinstance(launch_wf_id, UUID):
                workflows.add(launch_wf_id)
            else:
                try:
                    workflows.add(UUID(launch_wf_id))
                except (ValueError, TypeError):
                    pass

        # Page data sources
        data_sources = (
            getattr(page, "data_sources", None)
            if hasattr(page, "data_sources")
            else page.get("data_sources") if isinstance(page, dict) else None
        ) or []
        for ds in data_sources:
            if wf_id := ds.get("workflowId"):
                try:
                    workflows.add(UUID(wf_id))
                except (ValueError, TypeError):
                    pass
            if dp_id := ds.get("dataProviderId"):
                try:
                    workflows.add(UUID(dp_id))
                except (ValueError, TypeError):
                    pass

    for comp in components:
        # Filter to live components if requested
        is_draft = getattr(comp, "is_draft", comp.get("is_draft", True) if isinstance(comp, dict) else True)
        if live_only and is_draft:
            continue

        # Component loading_workflows
        loading_wfs = (
            getattr(comp, "loading_workflows", None)
            if hasattr(comp, "loading_workflows")
            else comp.get("loading_workflows") if isinstance(comp, dict) else None
        ) or []
        for wf_id in loading_wfs:
            try:
                workflows.add(UUID(wf_id))
            except (ValueError, TypeError):
                pass

        # Component props (recursive extraction)
        props = (
            getattr(comp, "props", None)
            if hasattr(comp, "props")
            else comp.get("props") if isinstance(comp, dict) else None
        ) or {}
        workflows.update(_extract_workflows_from_props(props))

    return workflows


async def sync_workflow_access(
    db: AsyncSession,
    entity_type: Literal["form", "app"],
    entity_id: UUID,
    workflow_ids: set[UUID],
    access_level: str,
    organization_id: UUID | None,
) -> None:
    """
    Sync workflow_access table for an entity.

    Deletes existing entries for this entity and inserts new ones.
    This is an atomic operation within the caller's transaction.

    Args:
        db: Database session
        entity_type: "form" or "app"
        entity_id: UUID of the form or app
        workflow_ids: Set of workflow UUIDs to grant access to
        access_level: Access level ("authenticated" or "role_based")
        organization_id: Organization UUID or None for global
    """
    # Delete existing entries for this entity
    await db.execute(
        delete(WorkflowAccess).where(
            WorkflowAccess.entity_type == entity_type,
            WorkflowAccess.entity_id == entity_id,
        )
    )

    # Insert new entries
    for wf_id in workflow_ids:
        db.add(
            WorkflowAccess(
                workflow_id=wf_id,
                entity_type=entity_type,
                entity_id=entity_id,
                access_level=access_level,
                organization_id=organization_id,
            )
        )


async def sync_form_workflow_access(
    db: AsyncSession,
    form: Form,
    fields: list[FormField] | None = None,
) -> None:
    """
    Convenience function to extract and sync workflow access for a form.

    Args:
        db: Database session
        form: The Form ORM object
        fields: Optional list of fields (uses form.fields if not provided)
    """
    workflow_ids = extract_form_workflows(form, fields)
    await sync_workflow_access(
        db=db,
        entity_type="form",
        entity_id=form.id,
        workflow_ids=workflow_ids,
        access_level=form.access_level.value if hasattr(form.access_level, "value") else str(form.access_level),
        organization_id=form.organization_id,
    )


async def sync_app_workflow_access(
    db: AsyncSession,
    app_id: UUID,
    access_level: str,
    organization_id: UUID | None,
    pages: list[Any],
    components: list[Any],
) -> None:
    """
    Convenience function to extract and sync workflow access for an app.

    Only considers live (is_draft=False) pages and components.

    Args:
        db: Database session
        app_id: The Application UUID
        access_level: Access level string
        organization_id: Organization UUID or None
        pages: List of AppPage ORM objects
        components: List of AppComponent ORM objects
    """
    workflow_ids = extract_app_workflows(pages, components, live_only=True)
    await sync_workflow_access(
        db=db,
        entity_type="app",
        entity_id=app_id,
        workflow_ids=workflow_ids,
        access_level=access_level,
        organization_id=organization_id,
    )


async def delete_entity_workflow_access(
    db: AsyncSession,
    entity_type: Literal["form", "app"],
    entity_id: UUID,
) -> None:
    """
    Delete all workflow access entries for an entity.

    This is typically called when a form or app is deleted.
    Note: Cascade delete on the table should handle this automatically,
    but this function is available for explicit cleanup.

    Args:
        db: Database session
        entity_type: "form" or "app"
        entity_id: UUID of the form or app
    """
    await db.execute(
        delete(WorkflowAccess).where(
            WorkflowAccess.entity_type == entity_type,
            WorkflowAccess.entity_id == entity_id,
        )
    )
