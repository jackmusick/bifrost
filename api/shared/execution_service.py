"""
Execution Service
Clean service layer for executing workflows, code, and data providers.
All execution runs in isolated subprocess via ExecutionPool.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from shared.discovery import get_workflow, get_data_provider
from shared.models import ExecutionStatus, WorkflowExecutionResponse

if TYPE_CHECKING:
    from shared.context import ExecutionContext

logger = logging.getLogger(__name__)


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


async def run_workflow(
    context: "ExecutionContext",
    workflow_name: str,
    input_data: dict[str, Any] | None = None,
    form_id: str | None = None,
    transient: bool = False,
) -> WorkflowExecutionResponse:
    """
    Execute a named workflow.

    Args:
        context: ExecutionContext with org scope and user info
        workflow_name: Name of workflow to execute
        input_data: Input parameters for the workflow
        form_id: Optional form ID if triggered by form
        transient: If True, don't persist execution record

    Returns:
        WorkflowExecutionResponse with execution results

    Raises:
        WorkflowNotFoundError: If workflow doesn't exist
        WorkflowLoadError: If workflow fails to load (syntax error, etc.)
    """
    parameters = input_data or {}

    # Load workflow
    try:
        result = get_workflow(workflow_name)
        if not result:
            raise WorkflowNotFoundError(f"Workflow '{workflow_name}' not found")

        workflow_func, workflow_metadata = result
        logger.debug(f"Loaded workflow: {workflow_name}")
    except WorkflowNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to load workflow {workflow_name}: {e}", exc_info=True)
        raise WorkflowLoadError(f"Failed to load workflow '{workflow_name}': {str(e)}")

    # Check if async execution is required
    if workflow_metadata.execution_mode == "async":
        return await _enqueue_async_execution(
            context=context,
            workflow_name=workflow_name,
            parameters=parameters,
            form_id=form_id,
        )

    # Synchronous execution
    return await _execute_sync(
        context=context,
        workflow_name=workflow_name,
        workflow_func=workflow_func,
        workflow_metadata=workflow_metadata,
        parameters=parameters,
        form_id=form_id,
        transient=transient,
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
    return await _enqueue_async_execution(
        context=context,
        workflow_name=script_name,
        parameters=parameters,
        code_base64=code_base64,
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
    from shared.execution import get_execution_pool

    # Load data provider to get metadata
    try:
        result = get_data_provider(provider_name)
        if not result:
            raise DataProviderNotFoundError(f"Data provider '{provider_name}' not found")

        provider_func, provider_metadata = result
        logger.debug(f"Loaded data provider: {provider_name}")
    except DataProviderNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Failed to load data provider {provider_name}: {e}", exc_info=True)
        raise DataProviderLoadError(f"Failed to load data provider '{provider_name}': {str(e)}")

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
        raise RuntimeError(f"Data provider execution failed: {result.get('error_message')}")

    options = result.get("result")
    if not isinstance(options, list):
        raise RuntimeError(f"Data provider must return a list, got {type(options).__name__}")

    return options


async def _enqueue_async_execution(
    context: "ExecutionContext",
    workflow_name: str,
    parameters: dict[str, Any],
    form_id: str | None = None,
    code_base64: str | None = None,
) -> WorkflowExecutionResponse:
    """Enqueue workflow for async execution via RabbitMQ."""
    from shared.async_executor import enqueue_workflow_execution

    execution_id = await enqueue_workflow_execution(
        context=context,
        workflow_name=workflow_name,
        parameters=parameters,
        form_id=form_id,
        code_base64=code_base64
    )

    return WorkflowExecutionResponse(
        execution_id=execution_id,
        workflow_name=workflow_name,
        status=ExecutionStatus.PENDING,
    )


async def _execute_sync(
    context: "ExecutionContext",
    workflow_name: str,
    workflow_func,
    workflow_metadata,
    parameters: dict[str, Any],
    form_id: str | None = None,
    transient: bool = False,
) -> WorkflowExecutionResponse:
    """Execute workflow synchronously in isolated subprocess."""
    from shared.execution import get_execution_pool
    from shared.execution_logger import get_execution_logger
    from shared.webpubsub_broadcaster import WebPubSubBroadcaster

    execution_id = str(uuid.uuid4())
    exec_logger = get_execution_logger()
    start_time = datetime.utcnow()
    broadcaster = WebPubSubBroadcaster()
    timeout_seconds = workflow_metadata.timeout_seconds if workflow_metadata else 1800

    try:
        # Create execution record
        if not transient:
            await exec_logger.create_execution(
                execution_id=execution_id,
                org_id=context.org_id,
                user_id=context.user_id,
                user_name=context.name,
                workflow_name=workflow_name,
                input_data=parameters,
                form_id=form_id,
                webpubsub_broadcaster=broadcaster
            )

        logger.info(
            f"Starting sync workflow execution: {workflow_name}",
            extra={
                "execution_id": execution_id,
                "org_id": context.org_id,
                "user_id": context.user_id
            }
        )

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
            "name": workflow_name,
            "code": None,  # Not a script
            "parameters": parameters,
            "caller": {
                "user_id": context.user_id,
                "email": context.email,
                "name": context.name,
            },
            "organization": org_data,
            "config": context._config,
            "tags": ["workflow"],
            "timeout_seconds": timeout_seconds,
            "transient": transient,
            "is_platform_admin": context.is_platform_admin,
        }

        # Execute in isolated subprocess
        pool = get_execution_pool()
        result = await pool.execute(
            execution_id=execution_id,
            context_data=context_data,
            timeout_seconds=timeout_seconds,
        )

        # Map result status
        status_str = result.get("status", "Failed")
        status = ExecutionStatus(status_str) if status_str in [s.value for s in ExecutionStatus] else ExecutionStatus.FAILED

        # Update execution record
        if not transient:
            await exec_logger.update_execution(
                execution_id=execution_id,
                org_id=context.org_id,
                user_id=context.user_id,
                status=status,
                result=result.get("result"),
                error_message=result.get("error_message"),
                error_type=result.get("error_type"),
                duration_ms=result.get("duration_ms", 0),
                integration_calls=result.get("integration_calls"),
                logs=result.get("logs"),
                variables=result.get("variables"),
                webpubsub_broadcaster=broadcaster
            )

        end_time = datetime.utcnow()

        # Build response with appropriate error/log filtering
        error = None
        error_type = None
        if status != ExecutionStatus.SUCCESS and result.get("error_message"):
            if context.is_platform_admin:
                error = result.get("error_message")
                error_type = result.get("error_type")
            elif result.get("error_type") == "UserError":
                error = result.get("error_message")
            else:
                error = "An error occurred during execution"

        # Filter logs for non-admins
        logs = None
        if result.get("logs"):
            if context.is_platform_admin:
                logs = result.get("logs")
            else:
                logs = [
                    log for log in result.get("logs", [])
                    if log.get('level') not in ['debug', 'traceback']
                ]

        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_name=workflow_name,
            status=status,
            result=result.get("result") if status == ExecutionStatus.SUCCESS else None,
            error=error,
            error_type=error_type,
            duration_ms=result.get("duration_ms", 0),
            started_at=start_time,
            completed_at=end_time,
            logs=logs,
            variables=result.get("variables") if context.is_platform_admin else None,
            is_transient=transient,
        )

    except asyncio.CancelledError:
        # Execution was cancelled
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=context.user_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution cancelled by user",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(f"Failed to update execution record: {update_error}")

        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.CANCELLED,
            error="Execution cancelled by user",
            duration_ms=duration_ms,
            started_at=start_time,
            completed_at=end_time,
            is_transient=transient,
        )

    except TimeoutError as e:
        # Execution timed out
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=context.user_id,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=str(e),
                    error_type="TimeoutError",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(f"Failed to update execution record: {update_error}")

        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.TIMEOUT,
            error=str(e),
            error_type="TimeoutError",
            duration_ms=duration_ms,
            started_at=start_time,
            completed_at=end_time,
            is_transient=transient,
        )

    except Exception as e:
        # Catch-all to prevent stuck executions
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        logger.error(
            f"Unexpected error in workflow execution: {workflow_name}",
            extra={"execution_id": execution_id, "error": str(e)},
            exc_info=True
        )

        # Try to update execution record
        if not transient:
            try:
                await exec_logger.update_execution(
                    execution_id=execution_id,
                    org_id=context.org_id,
                    user_id=context.user_id,
                    status=ExecutionStatus.FAILED,
                    error_message=f"Unexpected error: {str(e)}",
                    error_type="InternalError",
                    duration_ms=duration_ms
                )
            except Exception as update_error:
                logger.error(f"Failed to update execution record: {update_error}")

        return WorkflowExecutionResponse(
            execution_id=execution_id,
            workflow_name=workflow_name,
            status=ExecutionStatus.FAILED,
            error=str(e),
            error_type="InternalError",
            duration_ms=duration_ms,
            started_at=start_time,
            completed_at=end_time,
            is_transient=transient,
        )
