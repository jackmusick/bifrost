"""
Workflows Router

Handles workflow discovery, execution, and validation.

Note: Workflows are discovered by the Discovery container and synced to the
database. This router queries the database for workflow metadata, providing
fast O(1) lookups instead of file system scanning.

Organization Scoping:
- Workflows with organization_id = NULL are global (available to all orgs)
- Workflows with organization_id set are org-scoped
- Queries filter: global + user's org (unless platform admin requests all)
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import distinct, func, or_, select

# Import existing Pydantic models for API compatibility
from src.models import (
    EntityUsage,
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    WorkflowMetadata,
    WorkflowParameter,
    WorkflowUpdateRequest,
    WorkflowUsageStats,
    WorkflowValidationRequest,
    WorkflowValidationResponse,
)
from src.models import Workflow as WorkflowORM
from src.models.orm.workflow_access import WorkflowAccess
from src.models.orm.forms import Form, FormField
from src.models.orm.applications import Application, AppPage, AppComponent
from src.models.orm.agents import Agent, AgentTool
from src.services.workflow_validation import _extract_relative_path

from src.core.auth import Context, CurrentActiveUser, CurrentSuperuser
from src.core.database import DbSession
from src.core.pubsub import publish_execution_update, publish_history_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_workflow_orm_to_schema(workflow: WorkflowORM) -> WorkflowMetadata:
    """Convert ORM model to Pydantic schema for API response."""
    from typing import Literal
    from src.models.contracts.workflows import ExecutableType

    # Convert parameters from JSONB to WorkflowParameter objects
    parameters = []
    for param in workflow.parameters_schema or []:
        if isinstance(param, dict):
            parameters.append(WorkflowParameter(**param))

    # Validate execution_mode - default to "sync" if invalid
    raw_mode = workflow.execution_mode or "sync"
    execution_mode: Literal["sync", "async"] = "async" if raw_mode == "async" else "sync"

    # Convert string type to ExecutableType enum
    workflow_type = ExecutableType(workflow.type or "workflow")

    return WorkflowMetadata(
        id=str(workflow.id),
        name=workflow.name,
        description=workflow.description if workflow.description else None,
        category=workflow.category or "General",
        tags=workflow.tags or [],
        type=workflow_type,
        organization_id=str(workflow.organization_id) if workflow.organization_id else None,
        parameters=parameters,
        execution_mode=execution_mode,
        timeout_seconds=workflow.timeout_seconds or 1800,
        retry_policy=None,
        schedule=workflow.schedule,
        endpoint_enabled=workflow.endpoint_enabled or False,
        allowed_methods=workflow.allowed_methods or ["POST"],
        disable_global_key=False,
        public_endpoint=False,
        is_tool=workflow.type == "tool",  # Derive from type field
        tool_description=workflow.tool_description,
        cache_ttl_seconds=workflow.cache_ttl_seconds or 300,
        time_saved=workflow.time_saved or 0,
        value=float(workflow.value or 0.0),
        source_file_path=workflow.path,
        relative_file_path=_extract_relative_path(workflow.path),
    )


def _extract_workflows_from_props(obj: Any, workflow_ids: set[str]) -> None:
    """Recursively extract workflowId and dataProviderId values from JSONB props.

    Modifies workflow_ids in place to collect all workflow references found in:
    - props.workflowId
    - props.onClick.workflowId
    - props.rowActions[].onClick.workflowId
    - props.headerActions[].onClick.workflowId
    - props.footerActions[].workflowId
    - Any nested structure containing workflowId or dataProviderId
    """
    if obj is None:
        return

    if isinstance(obj, dict):
        # Check for workflowId key
        if wf_id := obj.get("workflowId"):
            if isinstance(wf_id, str):
                workflow_ids.add(wf_id)

        # Check for dataProviderId key
        if dp_id := obj.get("dataProviderId"):
            if isinstance(dp_id, str):
                workflow_ids.add(dp_id)

        # Recursively process all values
        for value in obj.values():
            _extract_workflows_from_props(value, workflow_ids)

    elif isinstance(obj, list):
        for item in obj:
            _extract_workflows_from_props(item, workflow_ids)


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "",
    response_model=list[WorkflowMetadata],
    summary="List all workflows",
    description="Returns metadata for all registered workflows in the system",
)
async def list_workflows(
    user: CurrentSuperuser,
    db: DbSession,
    type: str | None = None,
    is_tool: bool | None = None,  # Deprecated, use type="tool" instead
    scope: str | None = Query(
        None,
        description="Filter scope: omit for user's org + global, 'global' for global only, "
                    "'all' for all workflows (platform admins only), or org UUID for specific org."
    ),
    filter_by_form: UUID | None = Query(
        None,
        description="Filter to workflows used by a specific form"
    ),
    filter_by_app: UUID | None = Query(
        None,
        description="Filter to workflows used by a specific app"
    ),
    filter_by_agent: UUID | None = Query(
        None,
        description="Filter to workflows used by a specific agent"
    ),
) -> list[WorkflowMetadata]:
    """List all registered workflows from the database.

    Workflows are discovered by the Discovery container and synced to the
    database. This endpoint queries the database for fast lookups.

    Organization scoping (consistent with forms, agents):
    - scope omitted: All workflows (platform admins only)
    - scope='global': Only global workflows (organization_id IS NULL)
    - scope=<uuid>: Only that org's workflows (no global fallback)

    Entity filtering:
    - filter_by_form: Show only workflows used by the specified form
    - filter_by_app: Show only workflows used by the specified app
    - filter_by_agent: Show only workflows used by the specified agent

    Args:
        type: Filter by workflow type ('workflow', 'tool', 'data_provider').
        is_tool: [Deprecated] Use type="tool" instead. Filter by tool-enabled workflows.
        scope: Organization scope filter. Omit for all (platform admins only).
        filter_by_form: Form UUID to filter workflows by.
        filter_by_app: App UUID to filter workflows by.
        filter_by_agent: Agent UUID to filter workflows by.
    """
    from src.core.org_filter import resolve_org_filter, OrgFilterType

    try:
        # Resolve organization filter using shared helper (consistent with forms)
        try:
            filter_type, filter_org = resolve_org_filter(user, scope)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        # Query active workflows from database
        query = select(WorkflowORM).where(WorkflowORM.is_active.is_(True))

        # Apply organization scope filter
        if filter_type == OrgFilterType.ALL:
            # Platform admin sees all - no org filter
            pass
        elif filter_type == OrgFilterType.GLOBAL_ONLY:
            # Only global workflows (no organization)
            query = query.where(WorkflowORM.organization_id.is_(None))
        elif filter_type == OrgFilterType.ORG_ONLY:
            # Only that org's workflows (platform admin filtering)
            query = query.where(WorkflowORM.organization_id == filter_org)
        elif filter_type == OrgFilterType.ORG_PLUS_GLOBAL:
            # User's org + global (org users)
            query = query.where(
                or_(
                    WorkflowORM.organization_id == filter_org,
                    WorkflowORM.organization_id.is_(None),
                )
            )

        # Filter by type
        if type is not None:
            query = query.where(WorkflowORM.type == type)
        # Legacy support: is_tool=True maps to type="tool"
        elif is_tool is not None:
            if is_tool:
                query = query.where(WorkflowORM.type == "tool")
            else:
                query = query.where(WorkflowORM.type != "tool")

        # Apply entity filters via workflow_access table
        if filter_by_form:
            # Get workflow IDs used by this form
            workflow_ids_subquery = select(WorkflowAccess.workflow_id).where(
                WorkflowAccess.entity_type == "form",
                WorkflowAccess.entity_id == filter_by_form,
            )
            query = query.where(WorkflowORM.id.in_(workflow_ids_subquery))
        elif filter_by_app:
            # Get workflow IDs used by this app
            workflow_ids_subquery = select(WorkflowAccess.workflow_id).where(
                WorkflowAccess.entity_type == "app",
                WorkflowAccess.entity_id == filter_by_app,
            )
            query = query.where(WorkflowORM.id.in_(workflow_ids_subquery))
        elif filter_by_agent:
            # Get workflow IDs used by this agent
            workflow_ids_subquery = select(WorkflowAccess.workflow_id).where(
                WorkflowAccess.entity_type == "agent",
                WorkflowAccess.entity_id == filter_by_agent,
            )
            query = query.where(WorkflowORM.id.in_(workflow_ids_subquery))

        result = await db.execute(query)
        workflows = result.scalars().all()

        # Convert ORM models to Pydantic schemas
        workflow_list = []
        for w in workflows:
            try:
                workflow_list.append(_convert_workflow_orm_to_schema(w))
            except Exception as e:
                logger.error(f"Failed to convert workflow '{w.name}': {e}")

        logger.info(f"Returning {len(workflow_list)} workflows (scope={scope or 'default'})")
        return workflow_list

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving workflows: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflows",
        )


@router.get(
    "/usage-stats",
    response_model=WorkflowUsageStats,
    summary="Get workflow usage stats by entity",
    description="Returns counts of workflows used by each form, app, and agent",
)
async def get_workflow_usage_stats(
    user: CurrentSuperuser,
    db: DbSession,
    scope: str | None = Query(
        None,
        description="Filter scope: omit for all (superusers), 'global' for global only, "
                    "or org UUID for specific org only."
    ),
) -> WorkflowUsageStats:
    """Get workflow usage statistics grouped by entity type.

    Uses query-time aggregation for accurate counts (includes draft/unpublished).
    Returns counts of workflows used by each form, app, and agent.
    Useful for identifying which entities use workflows and filtering.

    Scope parameter (consistent with forms, agents):
    - Omitted: show all entities (superusers only)
    - "global": show only global entities (org_id IS NULL) - returns empty for usage stats
    - UUID string: show only that org's entities (no global fallback)
    """
    from src.core.org_filter import resolve_org_filter, OrgFilterType

    try:
        # Use shared org filter helper for consistency with forms, agents
        filter_type, filter_org = resolve_org_filter(user, scope)

        # Determine org_filter based on filter_type
        if filter_type == OrgFilterType.ALL:
            org_filter = None  # No filtering - show all
        elif filter_type == OrgFilterType.GLOBAL_ONLY:
            # Global entities only - doesn't make sense for usage stats, return empty
            return WorkflowUsageStats(forms=[], apps=[], agents=[])
        elif filter_type == OrgFilterType.ORG_ONLY:
            # Platform admin filtering by specific org - only that org (no global)
            org_filter = filter_org
        else:
            # ORG_PLUS_GLOBAL - shouldn't happen for superuser, but handle it
            org_filter = filter_org

        # =========================================================================
        # Forms: workflow_id, launch_workflow_id, and fields.data_provider_id
        # =========================================================================
        # Count distinct workflows per form from all three sources
        forms_query = (
            select(Form.id, Form.name)
            .where(Form.is_active.is_(True))
            .order_by(Form.name)
        )
        if org_filter:
            forms_query = forms_query.where(Form.organization_id == org_filter)

        forms_result = await db.execute(forms_query)
        forms_list = forms_result.all()

        forms: list[EntityUsage] = []
        for form_row in forms_list:
            # Get workflow_id and launch_workflow_id from form
            form_wf_query = select(Form.workflow_id, Form.launch_workflow_id).where(
                Form.id == form_row.id
            )
            form_wf_result = await db.execute(form_wf_query)
            form_wf = form_wf_result.first()

            workflow_ids: set[str] = set()
            if form_wf:
                if form_wf.workflow_id:
                    workflow_ids.add(form_wf.workflow_id)
                if form_wf.launch_workflow_id:
                    workflow_ids.add(form_wf.launch_workflow_id)

            # Get data_provider_id from fields
            fields_query = select(FormField.data_provider_id).where(
                FormField.form_id == form_row.id,
                FormField.data_provider_id.isnot(None),
            )
            fields_result = await db.execute(fields_query)
            for field_row in fields_result.all():
                workflow_ids.add(str(field_row.data_provider_id))

            forms.append(
                EntityUsage(
                    id=str(form_row.id),
                    name=form_row.name,
                    workflow_count=len(workflow_ids),
                )
            )

        # =========================================================================
        # Agents: via agent_tools junction table
        # =========================================================================
        agents_query = (
            select(
                Agent.id,
                Agent.name,
                func.count(distinct(AgentTool.workflow_id)).label("workflow_count"),
            )
            .outerjoin(AgentTool, AgentTool.agent_id == Agent.id)
            .where(Agent.is_active.is_(True))
            .group_by(Agent.id, Agent.name)
            .order_by(Agent.name)
        )
        if org_filter:
            agents_query = agents_query.where(Agent.organization_id == org_filter)

        agents_result = await db.execute(agents_query)
        agents = [
            EntityUsage(
                id=str(row.id), name=row.name, workflow_count=row.workflow_count or 0
            )
            for row in agents_result.all()
        ]

        # =========================================================================
        # Apps: global_data_sources + pages.launch_workflow_id + pages.data_sources + component props
        # Note: Pages belong to versions (draft/active). We check both to catch all usage.
        # =========================================================================
        apps_query = select(
            Application.id,
            Application.name,
            Application.global_data_sources,
            Application.draft_version_id,
            Application.active_version_id,
        ).order_by(Application.name)
        if org_filter:
            apps_query = apps_query.where(Application.organization_id == org_filter)

        apps_result = await db.execute(apps_query)
        apps_list = apps_result.all()

        apps: list[EntityUsage] = []
        for app_row in apps_list:
            workflow_ids: set[str] = set()

            # Extract workflows from app-level global_data_sources
            if app_row.global_data_sources:
                for ds in app_row.global_data_sources:
                    if isinstance(ds, dict):
                        if wf_id := ds.get("workflowId"):
                            workflow_ids.add(str(wf_id))
                        if dp_id := ds.get("dataProviderId"):
                            workflow_ids.add(str(dp_id))

            # Build list of version IDs to check (draft and/or active)
            version_ids: list[UUID] = []
            if app_row.draft_version_id:
                version_ids.append(app_row.draft_version_id)
            if app_row.active_version_id and app_row.active_version_id != app_row.draft_version_id:
                version_ids.append(app_row.active_version_id)

            # Get pages from relevant versions only
            if version_ids:
                pages_query = select(
                    AppPage.id,
                    AppPage.launch_workflow_id,
                    AppPage.data_sources,
                ).where(
                    AppPage.application_id == app_row.id,
                    AppPage.version_id.in_(version_ids),
                )
                pages_result = await db.execute(pages_query)
                page_ids: list[UUID] = []
                for page_row in pages_result.all():
                    page_ids.append(page_row.id)
                    if page_row.launch_workflow_id:
                        workflow_ids.add(str(page_row.launch_workflow_id))

                    # Extract workflows from page data_sources array
                    # Each data source can have workflowId or dataProviderId
                    if page_row.data_sources:
                        for ds in page_row.data_sources:
                            if isinstance(ds, dict):
                                if wf_id := ds.get("workflowId"):
                                    workflow_ids.add(str(wf_id))
                                if dp_id := ds.get("dataProviderId"):
                                    workflow_ids.add(str(dp_id))

                # Get workflow IDs from component props (JSONB extraction)
                if page_ids:
                    components_query = select(AppComponent.props).where(
                        AppComponent.page_id.in_(page_ids)
                    )
                    components_result = await db.execute(components_query)
                    for comp_row in components_result.all():
                        if comp_row.props:
                            _extract_workflows_from_props(comp_row.props, workflow_ids)

            apps.append(
                EntityUsage(
                    id=str(app_row.id),
                    name=app_row.name,
                    workflow_count=len(workflow_ids),
                )
            )

        return WorkflowUsageStats(forms=forms, apps=apps, agents=agents)

    except ValueError as e:
        # Invalid scope value from resolve_org_filter
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving workflow usage stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflow usage stats",
        )


@router.post(
    "/execute",
    response_model=WorkflowExecutionResponse,
    summary="Execute a workflow, data provider, or script",
    description="Execute a workflow or data provider by ID. For data providers, returns options list in result field. Requires platform admin, API key, or access via form/app/integration.",
)
async def execute_workflow(
    request: WorkflowExecutionRequest,
    ctx: Context,
    db: DbSession,
    user: CurrentActiveUser,  # Changed from CurrentSuperuser - auth check below
) -> WorkflowExecutionResponse:
    """Execute a workflow, data provider, or inline script.

    Authorization:
    - Inline code execution requires platform admin
    - Workflow/data provider execution requires one of:
      - Platform admin
      - User has access to a form using this workflow
      - User has access to an app using this workflow
      - Data provider is tied to an integration (any authenticated user)
    """
    from uuid import uuid4
    from src.sdk.context import ExecutionContext as SharedContext, Organization
    from src.services.execution.service import (
        run_workflow,
        run_code,
        run_data_provider,
        WorkflowNotFoundError,
        WorkflowLoadError,
        DataProviderNotFoundError,
        DataProviderLoadError,
    )
    from src.services.execution_auth import ExecutionAuthService
    from src.models.contracts.executions import ExecutionStatus

    # Look up workflow metadata for type checking (needed for data provider handling)
    workflow = None
    if request.workflow_id:
        result = await db.execute(
            select(WorkflowORM).where(
                WorkflowORM.id == request.workflow_id,
                WorkflowORM.is_active.is_(True),
            )
        )
        workflow = result.scalar_one_or_none()
        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{request.workflow_id}' not found",
            )

    # Authorization check
    if request.code:
        # Inline code execution requires platform admin
        if not ctx.user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inline code execution requires platform admin access",
            )
    elif request.workflow_id:
        # Workflow execution - check unified permissions
        auth_service = ExecutionAuthService(db)
        can_execute = await auth_service.can_execute_workflow(
            workflow_id=request.workflow_id,
            user_id=ctx.user.user_id,
            user_org_id=ctx.org_id,
            is_superuser=ctx.user.is_superuser,
            is_api_key=False,
        )
        if not can_execute:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to execute this workflow",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either workflow_id or code must be provided",
        )

    # Build shared context for execution
    org = None
    if ctx.org_id:
        org = Organization(id=str(ctx.org_id), name="", is_active=True)

    logger.info(
        f"Building execution context: org_id={ctx.org_id}, is_superuser={ctx.user.is_superuser}, scope={'GLOBAL' if not ctx.org_id else str(ctx.org_id)}"
    )

    shared_ctx = SharedContext(
        user_id=str(ctx.user.user_id),
        name=ctx.user.name,
        email=ctx.user.email,
        scope=str(ctx.org_id) if ctx.org_id else "GLOBAL",
        organization=org,
        is_platform_admin=ctx.user.is_superuser,
        is_function_key=False,
        execution_id=str(uuid4()),
    )

    try:
        if request.code:
            # Execute inline code
            result = await run_code(
                context=shared_ctx,
                code=request.code,
                script_name=request.script_name or "inline_script",
                input_data=request.input_data,
                transient=request.transient,
            )
        elif workflow and workflow.type == "data_provider":
            # Execute data provider - returns list of options directly
            options = await run_data_provider(
                context=shared_ctx,
                provider_name=workflow.name,
                params=request.input_data,
            )
            # Data providers are transient by default (no execution tracking)
            return WorkflowExecutionResponse(
                execution_id=str(uuid4()),
                workflow_id=request.workflow_id,
                workflow_name=workflow.name,
                status=ExecutionStatus.SUCCESS,
                result=options,  # list[dict] with value, label, description
                is_transient=True,
            )
        else:
            # Execute workflow by ID
            result = await run_workflow(
                context=shared_ctx,
                workflow_id=request.workflow_id,
                input_data=request.input_data,
                form_id=request.form_id,
                transient=request.transient,
            )

        # Publish execution update via WebSocket
        if not request.transient and result.execution_id:
            await publish_execution_update(
                execution_id=result.execution_id,
                status=result.status.value,
                data={
                    "result": result.result,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                },
            )
            await publish_history_update(
                execution_id=result.execution_id,
                status=result.status.value,
                executed_by=ctx.user.user_id,
                executed_by_name=ctx.user.name or ctx.user.email or "Unknown",
                workflow_name=result.workflow_name or request.script_name or "inline_script",
                org_id=ctx.org_id,
                started_at=result.started_at,
                completed_at=result.completed_at,
                duration_ms=result.duration_ms,
            )

        return result

    except (WorkflowNotFoundError, DataProviderNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except (WorkflowLoadError, DataProviderLoadError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error executing workflow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute workflow: {type(e).__name__}: {str(e)}",
        )


@router.post(
    "/validate",
    response_model=WorkflowValidationResponse,
    summary="Validate a workflow file",
    description="Validate a workflow file for syntax errors and decorator issues",
)
async def validate_workflow(
    request: WorkflowValidationRequest,
    user: CurrentActiveUser,
) -> WorkflowValidationResponse:
    """Validate a workflow file for errors."""
    from src.services.workflow_validation import validate_workflow_file

    try:
        result = await validate_workflow_file(
            path=request.path,
            content=request.content,
        )

        logger.info(f"Validation result for {request.path}: valid={result.valid}, issues={len(result.issues)}")
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error validating workflow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate workflow",
        )


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowMetadata,
    summary="Update a workflow",
    description="Update editable workflow properties like organization scope (Platform admin only)",
)
async def update_workflow(
    workflow_id: UUID,
    request: WorkflowUpdateRequest,
    user: CurrentSuperuser,
    db: DbSession,
) -> WorkflowMetadata:
    """Update a workflow's editable properties.

    Currently supports updating:
    - organization_id: Set to null for global scope, or an org UUID for org-scoped

    Requires platform admin access.
    """
    try:
        # Find the workflow
        result = await db.execute(
            select(WorkflowORM).where(WorkflowORM.id == workflow_id)
        )
        workflow = result.scalar_one_or_none()

        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow with ID '{workflow_id}' not found",
            )

        # Update organization_id
        # The request uses a special sentinel to distinguish between "set to null" and "not provided"
        # Since we're using Pydantic's default=None, we need to check if a value was actually provided
        # For now, we always update since organization_id is the only field
        if request.organization_id is not None:
            # Validate organization exists if not setting to global
            from src.models.orm.organizations import Organization
            org_result = await db.execute(
                select(Organization).where(Organization.id == UUID(request.organization_id))
            )
            if not org_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Organization with ID '{request.organization_id}' not found",
                )
            workflow.organization_id = UUID(request.organization_id)
        else:
            # Set to global scope
            workflow.organization_id = None

        await db.commit()
        await db.refresh(workflow)

        logger.info(f"Updated workflow '{workflow.name}' organization_id to {workflow.organization_id}")
        return _convert_workflow_orm_to_schema(workflow)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workflow: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update workflow",
        )


