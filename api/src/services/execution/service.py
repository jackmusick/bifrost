"""
Execution Service
Clean service layer for executing workflows, code, and data providers.
All execution runs in isolated subprocess via ExecutionPool.

Workflows are loaded by ID:
1. Look up workflow in database to get file_path and name
2. Load Python module from local workspace (/tmp/bifrost/workspace)
3. Find the @workflow decorated function by name
4. Execute in isolated subprocess
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from src.services.execution.module_loader import get_data_provider, WorkflowMetadata, import_module
from src.models import WorkflowExecutionResponse
from src.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from src.sdk.context import ExecutionContext

logger = logging.getLogger(__name__)

# Local workspace path (synced from S3)
WORKSPACE_PATH = Path("/tmp/bifrost/workspace")


class WorkflowNotFoundError(Exception):
    """Raised when a workflow cannot be found."""

    pass


class WorkflowLoadError(Exception):
    """Raised when a workflow fails to load."""

    pass


class DataProviderNotFoundError(Exception):
    """Raised when a data provider cannot be found."""

    pass


class DataProviderLoadError(Exception):
    """Raised when a data provider fails to load."""

    pass


async def get_workflow_metadata_only(
    workflow_id: str,
) -> WorkflowMetadata:
    """
    Get workflow metadata by ID without loading the module.

    Uses Redis cache first, falls back to DB on miss, populates cache on miss.
    This is much faster than get_workflow_by_id() since it skips module loading.

    Args:
        workflow_id: Workflow UUID from database

    Returns:
        WorkflowMetadata with id, name, file_path, timeout, etc.

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist in database
    """
    from src.core.redis_client import get_redis_client

    redis_client = get_redis_client()

    # Try Redis cache first
    cached = await redis_client.get_workflow_metadata_cache(workflow_id)
    if cached:
        logger.debug(f"Workflow metadata cache hit: {workflow_id}")
        metadata = WorkflowMetadata(
            name=cached["name"],
            timeout_seconds=cached.get("timeout_seconds", 1800),
            time_saved=cached.get("time_saved", 0),
            value=cached.get("value", 0.0),
            execution_mode=cached.get("execution_mode", "async"),
        )
        metadata.id = cached["id"]
        metadata.source_file_path = cached["file_path"]
        return metadata

    # Cache miss - query DB
    logger.debug(f"Workflow metadata cache miss: {workflow_id}, loading from DB")

    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models import Workflow as WorkflowORM

    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(WorkflowORM).where(
            WorkflowORM.id == workflow_id,
            WorkflowORM.is_active == True,  # noqa: E712
        )
        result = await db.execute(stmt)
        workflow_record = result.scalar_one_or_none()

    if not workflow_record:
        raise WorkflowNotFoundError(f"Workflow with ID '{workflow_id}' not found")

    # Build metadata from DB record
    metadata = WorkflowMetadata(
        name=workflow_record.name,
        timeout_seconds=workflow_record.timeout_seconds or 1800,
        time_saved=workflow_record.time_saved or 0,
        value=float(workflow_record.value) if workflow_record.value else 0.0,
        execution_mode=workflow_record.execution_mode or "async",
    )
    metadata.id = str(workflow_record.id)
    metadata.source_file_path = workflow_record.file_path

    # Populate cache for next time
    await redis_client.set_workflow_metadata_cache(
        workflow_id=str(workflow_record.id),
        name=workflow_record.name,
        file_path=workflow_record.file_path,
        timeout_seconds=workflow_record.timeout_seconds or 1800,
        time_saved=workflow_record.time_saved or 0,
        value=float(workflow_record.value) if workflow_record.value else 0.0,
        execution_mode=workflow_record.execution_mode or "async",
    )

    logger.debug(f"Loaded workflow metadata from DB: {workflow_id} -> {workflow_record.name}")
    return metadata


async def get_workflow_by_id(
    workflow_id: str,
) -> tuple[Callable, WorkflowMetadata]:
    """
    Load a workflow by ID from the database and local workspace.

    Args:
        workflow_id: Workflow UUID from database

    Returns:
        Tuple of (function, metadata)

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist in database
        WorkflowLoadError: If workflow file can't be loaded
    """
    from sqlalchemy import select
    from src.core.database import get_session_factory
    from src.models import Workflow as WorkflowORM

    # Look up workflow in database
    session_factory = get_session_factory()
    async with session_factory() as db:
        stmt = select(WorkflowORM).where(
            WorkflowORM.id == workflow_id,
            WorkflowORM.is_active == True,  # noqa: E712
        )
        result = await db.execute(stmt)
        workflow_record = result.scalar_one_or_none()

    if not workflow_record:
        raise WorkflowNotFoundError(f"Workflow with ID '{workflow_id}' not found")

    # Load from local workspace
    file_path = WORKSPACE_PATH / workflow_record.file_path
    if not file_path.exists():
        raise WorkflowLoadError(
            f"Workflow file not found: {workflow_record.file_path}. "
            "Workspace may be out of sync."
        )

    # Import the module
    try:
        module = import_module(file_path)
    except ImportError as e:
        raise WorkflowLoadError(f"Failed to load workflow module: {e}")

    # Find the decorated function by workflow name
    workflow_func = None
    workflow_metadata = None

    for name in dir(module):
        obj = getattr(module, name)
        # Only check callable objects (functions) for workflow metadata
        # This avoids triggering __getattr__ on proxy objects like `context`
        if callable(obj) and hasattr(obj, "_workflow_metadata"):
            meta = getattr(obj, "_workflow_metadata", None)
            if meta and meta.name == workflow_record.name:
                workflow_func = obj
                workflow_metadata = meta
                break

    if not workflow_func or not workflow_metadata:
        raise WorkflowLoadError(
            f"No @workflow function named '{workflow_record.name}' found in {workflow_record.file_path}"
        )

    # Enrich metadata from database record
    workflow_metadata.id = str(workflow_record.id)
    workflow_metadata.source_file_path = workflow_record.file_path

    logger.debug(f"Loaded workflow by ID: {workflow_id} -> {workflow_record.name}")
    return workflow_func, workflow_metadata


async def run_workflow(
    context: "ExecutionContext",
    workflow_id: str,
    input_data: dict[str, Any] | None = None,
    form_id: str | None = None,
    transient: bool = False,
    sync: bool = False,
) -> WorkflowExecutionResponse:
    """
    Execute a workflow by ID.

    All workflows are executed via the worker queue (RabbitMQ). The `sync` parameter
    controls whether we wait for the result or return immediately with PENDING status.

    Args:
        context: ExecutionContext with org scope and user info
        workflow_id: UUID of workflow to execute (from database)
        input_data: Input parameters for the workflow
        form_id: Optional form ID if triggered by form
        transient: If True, don't persist execution record
        sync: If True, wait for result via Redis BLPOP. If False, return PENDING immediately.

    Returns:
        WorkflowExecutionResponse with execution results (or PENDING status if sync=False)

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist
        WorkflowLoadError: If workflow fails to load (syntax error, etc.)
    """
    parameters = input_data or {}

    # Validate workflow exists using metadata-only lookup (Redis-first, no module loading)
    try:
        workflow_metadata = await get_workflow_metadata_only(workflow_id)
        logger.debug(
            f"Validated workflow by ID: {workflow_id} -> {workflow_metadata.name}"
        )
    except WorkflowNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to validate workflow {workflow_id}: {e}", exc_info=True)
        raise WorkflowNotFoundError(
            f"Failed to validate workflow '{workflow_id}': {str(e)}"
        )

    # Determine sync mode - if not explicitly set, use workflow's execution_mode
    use_sync = sync
    if not sync and workflow_metadata.execution_mode == "sync":
        use_sync = True
        logger.debug(f"Workflow {workflow_id} has execution_mode='sync', waiting for result")

    # Enqueue for execution via worker
    return await _enqueue_workflow_async(
        context=context,
        workflow_id=workflow_id,
        workflow_name=workflow_metadata.name,
        parameters=parameters,
        form_id=form_id,
        sync=use_sync,
    )


async def run_code(
    context: "ExecutionContext",
    code: str,
    script_name: str = "inline_script",
    input_data: dict[str, Any] | None = None,
    transient: bool = False,
) -> WorkflowExecutionResponse:
    """
    Execute inline Python code.

    Args:
        context: ExecutionContext with org scope and user info
        code: Python code to execute
        script_name: Name for the script execution
        input_data: Input parameters for the script
        transient: If True, don't persist execution record

    Returns:
        WorkflowExecutionResponse with execution results
    """
    parameters = input_data or {}
    code_base64 = base64.b64encode(code.encode()).decode()

    # Scripts always run async
    return await _enqueue_code_async(
        context=context,
        script_name=script_name,
        code_base64=code_base64,
        parameters=parameters,
    )


async def run_data_provider(
    context: "ExecutionContext",
    provider_name: str,
    params: dict[str, Any] | None = None,
    no_cache: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute a data provider and return options.

    Args:
        context: ExecutionContext with org scope and user info
        provider_name: Name of the data provider
        params: Input parameters for the data provider
        no_cache: If True, bypass cache

    Returns:
        List of data provider options

    Raises:
        DataProviderNotFoundError: If provider doesn't exist
        DataProviderLoadError: If provider fails to load
        RuntimeError: If provider execution fails
    """
    from src.services.execution.pool import get_execution_pool

    # Load data provider to get metadata
    try:
        result = get_data_provider(provider_name)
        if not result:
            raise DataProviderNotFoundError(
                f"Data provider '{provider_name}' not found"
            )

        provider_func, provider_metadata = result
        logger.debug(f"Loaded data provider: {provider_name}")
    except DataProviderNotFoundError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to load data provider {provider_name}: {e}", exc_info=True
        )
        raise DataProviderLoadError(
            f"Failed to load data provider '{provider_name}': {str(e)}"
        )

    execution_id = str(uuid.uuid4())

    # Build context data for subprocess
    org_data = None
    if context.organization:
        org_data = {
            "id": context.organization.id,
            "name": context.organization.name,
            "is_active": context.organization.is_active,
        }

    context_data = {
        "execution_id": execution_id,
        "name": provider_name,
        "code": None,
        "parameters": params or {},
        "caller": {
            "user_id": context.user_id,
            "email": context.email,
            "name": context.name,
        },
        "organization": org_data,
        "config": context._config,
        "tags": ["data_provider"],
        "timeout_seconds": 60,  # Data providers should be quick
        "cache_ttl_seconds": provider_metadata.cache_ttl_seconds,
        "transient": True,  # No execution tracking for data providers
        "no_cache": no_cache,
        "is_platform_admin": context.is_platform_admin,
    }

    # Execute in isolated subprocess
    pool = get_execution_pool()
    result = await pool.execute(
        execution_id=execution_id,
        context_data=context_data,
        timeout_seconds=60,  # Data providers should be quick
    )

    # Check result status
    status_str = result.get("status", "Failed")
    if status_str != "Success":
        raise RuntimeError(
            f"Data provider execution failed: {result.get('error_message')}"
        )

    options = result.get("result")
    if not isinstance(options, list):
        raise RuntimeError(
            f"Data provider must return a list, got {type(options).__name__}"
        )

    return options


async def _enqueue_workflow_async(
    context: "ExecutionContext",
    workflow_id: str,
    workflow_name: str,
    parameters: dict[str, Any],
    form_id: str | None = None,
    sync: bool = False,
) -> WorkflowExecutionResponse:
    """
    Enqueue workflow for execution via RabbitMQ.

    If sync=True, waits for result via Redis BLPOP.
    If sync=False, returns immediately with PENDING status.
    """
    from src.services.execution.async_executor import enqueue_workflow_execution
    from src.core.redis_client import get_redis_client

    execution_id = await enqueue_workflow_execution(
        context=context,
        workflow_id=workflow_id,
        parameters=parameters,
        form_id=form_id,
        execution_id=context.execution_id,  # Pass through for log streaming
        sync=sync,
    )

    if not sync:
        # Return immediately with pending status
        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.PENDING,
        )

    # Wait for result via Redis BLPOP
    redis_client = get_redis_client()
    result = await redis_client.wait_for_result(execution_id, timeout_seconds=1800)

    if result is None:
        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.TIMEOUT,
            error="Execution timed out waiting for result",
            error_type="TimeoutError",
        )

    # Map result to response
    status_str = result.get("status", "Failed")
    status = (
        ExecutionStatus(status_str)
        if status_str in [s.value for s in ExecutionStatus]
        else ExecutionStatus.FAILED
    )

    return WorkflowExecutionResponse(
        execution_id=execution_id,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        status=status,
        result=result.get("result"),
        error=result.get("error"),
        error_type=result.get("error_type"),
        duration_ms=result.get("duration_ms"),
    )


async def _enqueue_code_async(
    context: "ExecutionContext",
    script_name: str,
    code_base64: str,
    parameters: dict[str, Any],
) -> WorkflowExecutionResponse:
    """Enqueue inline code for async execution via RabbitMQ."""
    from src.services.execution.async_executor import enqueue_code_execution

    execution_id = await enqueue_code_execution(
        context=context,
        script_name=script_name,
        code_base64=code_base64,
        parameters=parameters,
    )

    return WorkflowExecutionResponse(
        execution_id=execution_id,
        workflow_name=script_name,
        status=ExecutionStatus.PENDING,
    )


async def execute_tool(
    workflow_id: str,
    workflow_name: str,
    parameters: dict[str, Any],
    user_id: str,
    user_email: str,
    user_name: str,
    org_id: str | None = None,
    org_name: str | None = None,
    is_platform_admin: bool = False,
    execution_id: str | None = None,
) -> WorkflowExecutionResponse:
    """
    Execute a workflow as a tool (for AI agent tool calls).

    Uses sync execution via RabbitMQ with Redis BLPOP for result.

    Args:
        workflow_id: Workflow UUID
        workflow_name: Workflow name for display
        parameters: Tool call arguments
        user_id: User ID executing the tool
        user_email: User email
        user_name: User display name
        org_id: Organization ID (optional)
        org_name: Organization name (optional)
        is_platform_admin: Whether user is platform admin
        execution_id: Optional pre-generated execution ID (for streaming)

    Returns:
        WorkflowExecutionResponse with execution results
    """
    from src.sdk.context import ExecutionContext, Organization

    # Build organization if provided
    org = None
    if org_id:
        org = Organization(
            id=org_id,
            name=org_name or "",
            is_active=True,
        )

    # Use provided execution_id or generate a new one
    if not execution_id:
        execution_id = str(uuid.uuid4())
    context = ExecutionContext(
        user_id=user_id,
        email=user_email,
        name=user_name,
        scope=org_id or "GLOBAL",
        organization=org,
        is_platform_admin=is_platform_admin,
        is_function_key=False,
        execution_id=execution_id,
    )

    # Execute synchronously via queue
    return await _enqueue_workflow_async(
        context=context,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        parameters=parameters,
        sync=True,  # Wait for result
    )
