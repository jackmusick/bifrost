"""
Workflows Router

Handles workflow discovery, execution, and validation.

Note: Workflows are discovered by the Discovery container and synced to the
database. This router queries the database for workflow metadata, providing
fast O(1) lookups instead of file system scanning.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

# Import existing Pydantic models for API compatibility
from src.models import (
    WorkflowExecutionRequest,
    WorkflowExecutionResponse,
    WorkflowMetadata,
    WorkflowParameter,
    WorkflowValidationRequest,
    WorkflowValidationResponse,
)
from src.models import Workflow as WorkflowORM
from src.services.workflow_validation import _extract_relative_path

from src.core.auth import Context, CurrentActiveUser, CurrentSuperuser
from src.core.database import DbSession
from src.core.pubsub import publish_execution_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


# =============================================================================
# Helper Functions
# =============================================================================


def _convert_workflow_orm_to_schema(workflow: WorkflowORM) -> WorkflowMetadata:
    """Convert ORM model to Pydantic schema for API response."""
    from typing import Literal

    # Convert parameters from JSONB to WorkflowParameter objects
    parameters = []
    for param in workflow.parameters_schema or []:
        if isinstance(param, dict):
            parameters.append(WorkflowParameter(**param))

    # Validate execution_mode - default to "sync" if invalid
    raw_mode = workflow.execution_mode or "sync"
    execution_mode: Literal["sync", "async"] = "async" if raw_mode == "async" else "sync"

    return WorkflowMetadata(
        id=str(workflow.id),
        name=workflow.name,
        description=workflow.description if workflow.description else None,
        category=workflow.category or "General",
        tags=workflow.tags or [],
        parameters=parameters,
        execution_mode=execution_mode,
        timeout_seconds=1800,  # Default timeout
        retry_policy=None,
        schedule=workflow.schedule,
        endpoint_enabled=workflow.endpoint_enabled or False,
        allowed_methods=workflow.allowed_methods or ["POST"],
        disable_global_key=False,
        public_endpoint=False,
        is_tool=workflow.is_tool or False,
        tool_description=workflow.tool_description,
        time_saved=workflow.time_saved or 0,
        value=float(workflow.value or 0.0),
        source_file_path=workflow.file_path,
        relative_file_path=_extract_relative_path(workflow.file_path),
    )


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
    is_tool: bool | None = None,
) -> list[WorkflowMetadata]:
    """List all registered workflows from the database.

    Workflows are discovered by the Discovery container and synced to the
    database. This endpoint queries the database for fast lookups.

    Args:
        is_tool: Filter by tool-enabled workflows. If True, only return workflows
                 that can be used as agent tools. If None, return all workflows.
    """
    try:
        # Query active workflows from database
        query = select(WorkflowORM).where(WorkflowORM.is_active.is_(True))

        # Optional filter for tool-enabled workflows
        if is_tool is not None:
            query = query.where(WorkflowORM.is_tool.is_(is_tool))

        result = await db.execute(query)
        workflows = result.scalars().all()

        # Convert ORM models to Pydantic schemas
        workflow_list = []
        for w in workflows:
            try:
                workflow_list.append(_convert_workflow_orm_to_schema(w))
            except Exception as e:
                logger.error(f"Failed to convert workflow '{w.name}': {e}")

        logger.info(f"Returning {len(workflow_list)} workflows")
        return workflow_list

    except Exception as e:
        logger.error(f"Error retrieving workflows: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve workflows",
        )


@router.post(
    "/execute",
    response_model=WorkflowExecutionResponse,
    summary="Execute a workflow or script",
    description="Execute a workflow by name or inline Python code (Platform admin only)",
)
async def execute_workflow(
    request: WorkflowExecutionRequest,
    ctx: Context,
    user: CurrentSuperuser,  # Platform admin only
) -> WorkflowExecutionResponse:
    """Execute a workflow or script with the provided parameters."""
    from uuid import uuid4
    from src.sdk.context import ExecutionContext as SharedContext, Organization
    from src.services.execution.service import (
        run_workflow,
        run_code,
        WorkflowNotFoundError,
        WorkflowLoadError,
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
        else:
            # Execute workflow by ID
            if not request.workflow_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either workflow_id or code must be provided",
                )

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

        return result

    except WorkflowNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except WorkflowLoadError as e:
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


