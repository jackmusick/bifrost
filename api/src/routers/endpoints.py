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
from typing import Any, get_type_hints
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from src.core.constants import SYSTEM_USER_ID, SYSTEM_USER_EMAIL
from src.sdk.context import ExecutionContext
from src.core.database import get_db_context
from src.core.redis_client import get_redis_client
from src.routers.workflow_keys import validate_workflow_key
from src.repositories.workflows import WorkflowRepository

# Dataclass-like holder for cached workflow metadata (avoids module loading)
from dataclasses import dataclass


@dataclass
class CachedWorkflowMetadata:
    """Minimal workflow metadata for endpoint execution (cached in Redis)."""
    workflow_id: str
    file_path: str
    execution_mode: str
    timeout_seconds: int
    allowed_methods: list[str]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/endpoints", tags=["Endpoints"])


def _coerce_query_params(query_params: dict[str, str], workflow_func: Any) -> dict[str, Any]:
    """
    Coerce query parameter strings to the types expected by the workflow function.

    GET query parameters are always strings, but workflow functions may expect
    int, float, bool, etc. This function inspects the function signature and
    converts parameters accordingly.

    Args:
        query_params: Dictionary of string query parameters
        workflow_func: The workflow function to get type hints from

    Returns:
        Dictionary with parameters coerced to the correct types
    """
    if not query_params:
        return {}

    result: dict[str, Any] = {}

    # Get type hints from the workflow function
    try:
        hints = get_type_hints(workflow_func)
    except Exception:
        # If we can't get type hints, return params as-is
        return dict(query_params)

    for key, value in query_params.items():
        if key not in hints:
            # No type hint, keep as string
            result[key] = value
            continue

        expected_type = hints[key]

        # Handle Optional types (Union[X, None])
        origin = getattr(expected_type, "__origin__", None)
        if origin is type(None):  # noqa: E721
            result[key] = value
            continue

        # Extract the actual type from Optional/Union
        if hasattr(expected_type, "__args__"):
            # Filter out NoneType from Union args
            non_none_types = [t for t in expected_type.__args__ if t is not type(None)]
            if non_none_types:
                expected_type = non_none_types[0]

        # Coerce based on expected type
        try:
            if expected_type is int:
                result[key] = int(value)
            elif expected_type is float:
                result[key] = float(value)
            elif expected_type is bool:
                result[key] = value.lower() in ("true", "1", "yes", "on")
            else:
                result[key] = value
        except (ValueError, TypeError):
            # Coercion failed, keep as string (will fail validation later)
            result[key] = value

    return result


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
    redis_client = get_redis_client()

    # Try to get workflow metadata from cache (FAST path - skips module loading)
    cached = await redis_client.get_endpoint_workflow_cache(workflow_name)
    workflow_metadata: CachedWorkflowMetadata | None = None

    if cached:
        logger.debug(f"Cache hit for endpoint workflow: {workflow_name}")
        workflow_metadata = CachedWorkflowMetadata(
            workflow_id=cached["workflow_id"],
            file_path=cached["file_path"],
            execution_mode=cached["execution_mode"],
            timeout_seconds=cached["timeout_seconds"],
            allowed_methods=cached["allowed_methods"],
        )

    async with get_db_context() as db:
        # Validate API key
        is_valid, key_id = await validate_workflow_key(db, x_bifrost_key, workflow_name)

        if not is_valid:
            logger.warning(f"Invalid API key for workflow endpoint: {workflow_name}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )

        logger.debug(f"API key validated for workflow: {workflow_name} (key_id: {key_id})")

        # If no cache hit, load from DB and module
        if workflow_metadata is None:
            logger.debug(f"Cache miss for endpoint workflow: {workflow_name}")

            # Get workflow from database (need the UUID for execution)
            workflow_repo = WorkflowRepository(db)
            try:
                workflow = await workflow_repo.get_endpoint_workflow_by_name(workflow_name)
            except ValueError as e:
                # Multiple workflows with same name and endpoint_enabled
                logger.error(f"Duplicate endpoint workflows: {e}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(e),
                )

            if not workflow:
                logger.warning(f"Endpoint workflow not found: {workflow_name}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Endpoint workflow '{workflow_name}' not found or not enabled",
                )

            # Build cached metadata from DB workflow record
            # All metadata (execution_mode, timeout, allowed_methods) is stored in the workflows table
            workflow_metadata = CachedWorkflowMetadata(
                workflow_id=str(workflow.id),
                file_path=workflow.path,
                execution_mode=workflow.execution_mode or "async",
                timeout_seconds=workflow.timeout_seconds or 1800,
                allowed_methods=workflow.allowed_methods or ["POST"],
            )

            # Cache for future requests
            await redis_client.set_endpoint_workflow_cache(
                workflow_name=workflow_name,
                workflow_id=workflow_metadata.workflow_id,
                file_path=workflow_metadata.file_path,
                execution_mode=workflow_metadata.execution_mode,
                timeout_seconds=workflow_metadata.timeout_seconds,
                allowed_methods=workflow_metadata.allowed_methods,
            )

    # Check HTTP method
    http_method = request.method
    if http_method not in workflow_metadata.allowed_methods:
        logger.warning(f"Method {http_method} not allowed for {workflow_name}")
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail=f"Method {http_method} not allowed. Allowed: {', '.join(workflow_metadata.allowed_methods)}",
        )

    # Parse input data (query params + body)
    # Note: We can't do type coercion without loading the function, so we pass strings
    # The worker will handle type coercion when it loads the function
    input_data = dict(request.query_params)
    try:
        body = await request.json()
        if isinstance(body, dict):
            input_data.update(body)
    except Exception:
        pass  # No JSON body or invalid JSON

    # Create execution context using system user (API key executions)
    context = ExecutionContext(
        user_id=SYSTEM_USER_ID,
        name="API Key",
        email=SYSTEM_USER_EMAIL,
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
            workflow_id=workflow_metadata.workflow_id,
            workflow_name=workflow_name,
            input_data=input_data,
            api_key_id=workflow_metadata.workflow_id,
            file_path=workflow_metadata.file_path,
        )

    # Execute synchronously
    return await _execute_sync(
        context=context,
        workflow_id=workflow_metadata.workflow_id,
        workflow_name=workflow_name,
        input_data=input_data,
        timeout_seconds=workflow_metadata.timeout_seconds,
        api_key_id=workflow_metadata.workflow_id,
        file_path=workflow_metadata.file_path,
    )


async def _execute_async(
    context: ExecutionContext,
    workflow_id: str,
    workflow_name: str,
    input_data: dict[str, Any],
    api_key_id: str | None = None,
    file_path: str | None = None,
) -> EndpointExecuteResponse:
    """Execute workflow asynchronously via queue."""
    from src.services.execution.async_executor import enqueue_workflow_execution

    execution_id = await enqueue_workflow_execution(
        context=context,
        workflow_id=workflow_id,
        parameters=input_data,
        form_id=None,
        api_key_id=api_key_id,
        file_path=file_path,
    )

    logger.info(f"Queued async workflow execution: {workflow_name} ({execution_id})")

    return EndpointExecuteResponse(
        execution_id=execution_id,
        status="Pending",
        message="Workflow queued for async execution",
    )


async def _execute_sync(
    context: ExecutionContext,
    workflow_id: str,
    workflow_name: str,
    input_data: dict[str, Any],
    timeout_seconds: int,
    api_key_id: str | None = None,
    file_path: str | None = None,
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
    from src.services.execution.async_executor import enqueue_workflow_execution

    execution_id = str(uuid4())

    # Store pending execution in Redis
    redis_client = get_redis_client()
    await redis_client.set_pending_execution(
        execution_id=execution_id,
        workflow_id=workflow_id,
        parameters=input_data,
        org_id=context.org_id,
        user_id=context.user_id,
        user_name=context.name or "API Key",
        user_email=context.email or "",
        form_id=None,
        api_key_id=api_key_id,
    )

    # Queue execution with sync=True
    await enqueue_workflow_execution(
        context=context,
        workflow_id=workflow_id,
        parameters=input_data,
        form_id=None,
        execution_id=execution_id,
        sync=True,
        api_key_id=api_key_id,
        file_path=file_path,
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
