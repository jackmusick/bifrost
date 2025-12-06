"""
Endpoints Router

Execute workflows via REST API using workflow API keys (x-bifrost-key header).
These endpoints are designed for external integrations that need to trigger
workflows without user authentication.

Authentication:
    - Uses X-Bifrost-Key header with workflow API key
    - Keys can be global (work for all workflows) or workflow-specific
    - Keys are created via /api/workflow-keys endpoint by platform admins

Architecture:
    - API never executes workflow code directly
    - Sync execution: Queue to RabbitMQ, wait on Redis BLPOP for result
    - Async execution: Queue to RabbitMQ, return immediately
"""

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from shared.context import ExecutionContext
from shared.discovery import get_workflow
from src.core.database import get_db_context
from src.core.redis_client import get_redis_client, DEFAULT_TIMEOUT_SECONDS
from src.routers.workflow_keys import validate_workflow_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/endpoints", tags=["Endpoints"])


# =============================================================================
# Request/Response Models
# =============================================================================


class EndpointExecuteRequest(BaseModel):
    """Request body for endpoint execution."""
    pass  # All fields are optional, passed through to workflow


class EndpointExecuteResponse(BaseModel):
    """Response for endpoint execution."""
    execution_id: str
    status: str
    message: str | None = None
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.api_route(
    "/{workflow_name}",
    methods=["GET", "POST", "PUT", "DELETE"],
    response_model=EndpointExecuteResponse,
    summary="Execute workflow via API key",
    description="Execute an endpoint-enabled workflow using an API key for authentication",
)
async def execute_endpoint(
    workflow_name: str,
    request: Request,
    x_bifrost_key: str = Header(..., alias="X-Bifrost-Key"),
) -> EndpointExecuteResponse:
    """
    Execute a workflow via REST endpoint using API key authentication.

    This is the main entry point for external integrations to trigger workflows.
    Uses X-Bifrost-Key header for authentication instead of user JWT.

    The workflow must have `endpoint_enabled=True` in its decorator.

    Args:
        workflow_name: Name of the workflow to execute
        request: FastAPI request (for body/query params)
        x_bifrost_key: API key from X-Bifrost-Key header

    Returns:
        Execution response with result or async execution ID
    """
    # Validate API key
    async with get_db_context() as db:
        is_valid, key_id = await validate_workflow_key(db, x_bifrost_key, workflow_name)

        if not is_valid:
            logger.warning(f"Invalid API key for workflow endpoint: {workflow_name}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )

        logger.info(f"API key validated for workflow: {workflow_name} (key_id: {key_id})")

    # Load workflow
    try:
        result = get_workflow(workflow_name)
        if not result:
            logger.warning(f"Workflow not found: {workflow_name}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_name}' not found",
            )
        workflow_func, workflow_metadata = result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load workflow {workflow_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load workflow '{workflow_name}': {str(e)}",
        )

    # Check if endpoint is enabled
    if not workflow_metadata.endpoint_enabled:
        logger.warning(f"Workflow endpoint not enabled: {workflow_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow endpoint '{workflow_name}' is not enabled",
        )

    # Check HTTP method
    http_method = request.method
    allowed_methods = workflow_metadata.allowed_methods or ["POST"]
    if http_method not in allowed_methods:
        logger.warning(f"Method {http_method} not allowed for {workflow_name}")
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Method {http_method} not allowed. Allowed: {', '.join(allowed_methods)}",
        )

    # Parse input data (query params + body)
    input_data = dict(request.query_params)
    try:
        body = await request.json()
        if isinstance(body, dict):
            input_data.update(body)
    except Exception:
        pass  # No JSON body or invalid JSON

    # Create execution context (no user, using API key)
    context = ExecutionContext(
        user_id=f"api-key:{key_id}",
        name="API Key",
        email="api-key@bifrost.local",
        scope="GLOBAL",
        organization=None,
        is_platform_admin=False,
        is_function_key=True,
        execution_id=str(uuid4()),
    )

    # Check execution mode
    if workflow_metadata.execution_mode == "async":
        return await _execute_async(
            context=context,
            workflow_name=workflow_name,
            input_data=input_data,
        )

    # Execute synchronously
    return await _execute_sync(
        context=context,
        workflow_name=workflow_name,
        input_data=input_data,
        workflow_func=workflow_func,
        workflow_metadata=workflow_metadata,
    )


async def _execute_async(
    context: ExecutionContext,
    workflow_name: str,
    input_data: dict[str, Any],
) -> EndpointExecuteResponse:
    """Execute workflow asynchronously via queue."""
    from shared.async_executor import enqueue_workflow_execution

    execution_id = await enqueue_workflow_execution(
        context=context,
        workflow_name=workflow_name,
        parameters=input_data,
        form_id=None,
    )

    return EndpointExecuteResponse(
        execution_id=execution_id,
        status="Pending",
        message="Workflow queued for async execution",
    )


async def _execute_sync(
    context: ExecutionContext,
    workflow_name: str,
    input_data: dict[str, Any],
    workflow_func: Any,
    workflow_metadata: Any,
) -> EndpointExecuteResponse:
    """
    Execute workflow synchronously via queue.

    Instead of executing workflow directly (which would block and require
    filesystem access), we:
    1. Store pending execution in Redis
    2. Queue to RabbitMQ with sync=True
    3. Wait for result via Redis BLPOP
    4. Return result to caller

    This allows the API to stay lightweight without filesystem access.
    Worker will write to PostgreSQL when it starts execution.
    """
    from shared.async_executor import enqueue_workflow_execution

    execution_id = str(uuid4())

    # Store pending execution in Redis
    redis_client = get_redis_client()
    await redis_client.set_pending_execution(
        execution_id=execution_id,
        workflow_name=workflow_name,
        parameters=input_data,
        org_id=context.org_id,
        user_id=context.user_id,
        user_name=context.name or "API Key",
        user_email=context.email or "",
        form_id=None,
    )

    # Get timeout from workflow metadata (default 5 minutes)
    timeout_seconds = getattr(workflow_metadata, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

    # Queue execution with sync=True
    await enqueue_workflow_execution(
        context=context,
        workflow_name=workflow_name,
        parameters=input_data,
        form_id=None,
        execution_id=execution_id,
        sync=True,
    )

    logger.info(f"Queued sync workflow execution: {workflow_name} ({execution_id})")

    # Wait for result from Redis
    result = await redis_client.wait_for_result(
        execution_id=execution_id,
        timeout_seconds=timeout_seconds,
    )

    if result is None:
        # Timeout waiting for result
        logger.error(f"Timeout waiting for workflow result: {workflow_name} ({execution_id})")
        return EndpointExecuteResponse(
            execution_id=execution_id,
            status="Timeout",
            error=f"Workflow execution timed out after {timeout_seconds} seconds",
        )

    # Return result from worker
    return EndpointExecuteResponse(
        execution_id=execution_id,
        status=result.get("status", "Unknown"),
        result=result.get("result"),
        error=result.get("error"),
        duration_ms=result.get("duration_ms"),
    )
