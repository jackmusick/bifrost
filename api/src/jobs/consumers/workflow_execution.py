"""
Workflow Execution Consumer

Processes async workflow executions from RabbitMQ queue.

Architecture (Redis-first):
1. API stores pending execution in Redis, publishes to RabbitMQ
2. Worker reads pending execution from Redis
3. Worker creates PostgreSQL record when starting
4. Worker executes workflow and updates PostgreSQL
5. Worker deletes Redis pending entry on completion

For sync execution requests (sync=True in message):
- Pushes result to Redis after completion
- API waits on Redis BLPOP for the result
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from src.core.pubsub import publish_execution_update
from src.core.redis_client import get_redis_client
from src.jobs.rabbitmq import BaseConsumer

logger = logging.getLogger(__name__)

# Queue name
QUEUE_NAME = "workflow-executions"


class WorkflowExecutionConsumer(BaseConsumer):
    """
    Consumer for workflow execution queue.

    Message format (minimal - context is in Redis):
    {
        "execution_id": "uuid",
        "workflow_name": "workflow-name",
        "code": "base64-encoded-script" (optional, for inline scripts),
        "sync": false (optional, if true pushes result to Redis for API)
    }

    Full execution context is read from Redis pending execution.
    """

    def __init__(self):
        from src.config import get_settings
        settings = get_settings()
        super().__init__(
            queue_name=QUEUE_NAME,
            prefetch_count=settings.max_concurrency,
        )
        self._redis_client = get_redis_client()

    async def process_message(self, message_data: dict[str, Any]) -> None:
        """Process a workflow execution message."""
        execution_id = message_data.get("execution_id", "")
        is_sync = message_data.get("sync", False)
        start_time = datetime.utcnow()

        # Read execution context from Redis
        pending = await self._redis_client.get_pending_execution(execution_id)

        if pending is None:
            logger.error(f"No pending execution found in Redis: {execution_id}")
            # Push error to Redis for sync callers
            if is_sync:
                await self._redis_client.push_result(
                    execution_id=execution_id,
                    status="Failed",
                    error="Pending execution not found in Redis",
                    error_type="PendingNotFound",
                    duration_ms=0,
                )
            return

        # Extract context from Redis pending record
        workflow_name = pending["workflow_name"]
        parameters = pending["parameters"]
        org_id = pending["org_id"]
        user_id = pending["user_id"]
        user_name = pending["user_name"]
        user_email = pending["user_email"]
        form_id = pending.get("form_id")
        code_base64 = message_data.get("code")  # Code comes from queue message

        try:
            logger.info(
                f"Processing workflow execution: {workflow_name}",
                extra={
                    "execution_id": execution_id,
                    "workflow_name": workflow_name,
                    "org_id": org_id,
                },
            )

            from shared.discovery import get_workflow
            from src.models.enums import ExecutionStatus
            from shared.consumers._helpers import (
                create_execution,
                update_execution,
            )

            # Check if execution was cancelled in Redis before we started
            if pending.get("cancelled", False):
                logger.info(f"Execution {execution_id} was cancelled before starting")
                # Create PostgreSQL record as CANCELLED
                await create_execution(
                    execution_id=execution_id,
                    workflow_name=workflow_name,
                    parameters=parameters,
                    org_id=org_id,
                    user_id=user_id,
                    user_name=user_name,
                    form_id=form_id,
                    status=ExecutionStatus.CANCELLED,
                )
                await update_execution(
                    execution_id=execution_id,
                    org_id=org_id,
                    user_id=user_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution was cancelled before it could start",
                    duration_ms=0,
                )
                await publish_execution_update(execution_id, "Cancelled")
                # Delete pending record from Redis
                await self._redis_client.delete_pending_execution(execution_id)
                # Push to Redis for sync callers
                if is_sync:
                    await self._redis_client.push_result(
                        execution_id=execution_id,
                        status="Cancelled",
                        error="Execution was cancelled before it could start",
                        duration_ms=0,
                    )
                return

            # Create PostgreSQL record with RUNNING status
            await create_execution(
                execution_id=execution_id,
                workflow_name=workflow_name,
                parameters=parameters,
                org_id=org_id,
                user_id=user_id,
                user_name=user_name,
                form_id=form_id,
                status=ExecutionStatus.RUNNING,
            )
            await publish_execution_update(execution_id, "Running")

            # Load organization and config
            org = None
            org_data = None
            config = {}

            if org_id:
                from shared.config_resolver import ConfigResolver

                resolver = ConfigResolver()
                org = await resolver.get_organization(org_id)
                config = await resolver.load_config_for_scope(org_id)
                if org:
                    org_data = {
                        "id": org.id,
                        "name": org.name,
                        "is_active": org.is_active,
                    }
            else:
                from shared.config_resolver import ConfigResolver

                resolver = ConfigResolver()
                config = await resolver.load_config_for_scope("GLOBAL")

            # Determine if this is a script or workflow execution
            is_script = bool(code_base64)

            # Get timeout from workflow metadata
            timeout_seconds = 1800  # Default 30 minutes
            if not is_script:
                try:
                    result = get_workflow(workflow_name)
                    if not result:
                        logger.error(f"Workflow not found: {workflow_name}")
                        duration_ms = int(
                            (datetime.utcnow() - start_time).total_seconds() * 1000
                        )
                        error_msg = f"Workflow '{workflow_name}' not found"
                        await update_execution(
                            execution_id=execution_id,
                            org_id=org_id,
                            user_id=user_id,
                            status=ExecutionStatus.FAILED,
                            result={
                                "error": "WorkflowNotFound",
                                "message": error_msg,
                            },
                            duration_ms=duration_ms,
                        )
                        await publish_execution_update(
                            execution_id,
                            "Failed",
                            {"error": error_msg},
                        )
                        # Delete pending from Redis
                        await self._redis_client.delete_pending_execution(execution_id)
                        if is_sync:
                            await self._redis_client.push_result(
                                execution_id=execution_id,
                                status="Failed",
                                error=error_msg,
                                error_type="WorkflowNotFound",
                                duration_ms=duration_ms,
                            )
                        return

                    _, metadata = result
                    timeout_seconds = metadata.timeout_seconds if metadata else 1800

                except Exception as e:
                    logger.error(f"Failed to load workflow {workflow_name}: {e}")
                    duration_ms = int(
                        (datetime.utcnow() - start_time).total_seconds() * 1000
                    )
                    error_msg = f"Failed to load workflow '{workflow_name}': {str(e)}"
                    await update_execution(
                        execution_id=execution_id,
                        org_id=org_id,
                        user_id=user_id,
                        status=ExecutionStatus.FAILED,
                        result={
                            "error": "WorkflowLoadError",
                            "message": error_msg,
                        },
                        duration_ms=duration_ms,
                    )
                    await publish_execution_update(
                        execution_id, "Failed", {"error": str(e)}
                    )
                    # Delete pending from Redis
                    await self._redis_client.delete_pending_execution(execution_id)
                    if is_sync:
                        await self._redis_client.push_result(
                            execution_id=execution_id,
                            status="Failed",
                            error=error_msg,
                            error_type="WorkflowLoadError",
                            duration_ms=duration_ms,
                        )
                    return

            # Build context for worker process
            context_data = {
                "execution_id": execution_id,
                "name": workflow_name,
                "code": code_base64,
                "parameters": parameters,
                "caller": {
                    "user_id": user_id,
                    "email": user_email,
                    "name": user_name,
                },
                "organization": org_data,
                "config": config,
                "tags": ["workflow"] if not is_script else [],
                "timeout_seconds": timeout_seconds,
                "transient": False,
                "is_platform_admin": False,
            }

            # Execute in isolated process
            from shared.execution import get_execution_pool

            pool = get_execution_pool()

            try:
                result = await pool.execute(
                    execution_id=execution_id,
                    context_data=context_data,
                    timeout_seconds=timeout_seconds,
                )
            except asyncio.CancelledError:
                # Cancelled via Redis flag
                duration_ms = int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                )
                await update_execution(
                    execution_id=execution_id,
                    org_id=org_id,
                    user_id=user_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution cancelled by user",
                    duration_ms=duration_ms,
                )
                await publish_execution_update(execution_id, "Cancelled")
                # Delete pending from Redis
                await self._redis_client.delete_pending_execution(execution_id)
                if is_sync:
                    await self._redis_client.push_result(
                        execution_id=execution_id,
                        status="Cancelled",
                        error="Execution cancelled by user",
                        duration_ms=duration_ms,
                    )
                return
            except TimeoutError as e:
                # Timeout from pool
                duration_ms = int(
                    (datetime.utcnow() - start_time).total_seconds() * 1000
                )
                error_msg = str(e)
                await update_execution(
                    execution_id=execution_id,
                    org_id=org_id,
                    user_id=user_id,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=error_msg,
                    error_type="TimeoutError",
                    duration_ms=duration_ms,
                )
                await publish_execution_update(execution_id, "Timeout")
                # Delete pending from Redis
                await self._redis_client.delete_pending_execution(execution_id)
                if is_sync:
                    await self._redis_client.push_result(
                        execution_id=execution_id,
                        status="Timeout",
                        error=error_msg,
                        error_type="TimeoutError",
                        duration_ms=duration_ms,
                    )
                return

            # Map result dict to ExecutionStatus
            status_str = result.get("status", "Failed")
            status = ExecutionStatus(status_str) if status_str in [s.value for s in ExecutionStatus] else ExecutionStatus.FAILED

            # Update execution with result and metrics
            await update_execution(
                execution_id=execution_id,
                org_id=org_id,
                user_id=user_id,
                status=status,
                result=result.get("result"),
                error_message=result.get("error_message"),
                error_type=result.get("error_type"),
                duration_ms=result.get("duration_ms", 0),
                logs=result.get("logs", []),
                variables=result.get("variables"),
                metrics=result.get("metrics"),
            )

            await publish_execution_update(
                execution_id,
                status.value,
                {
                    "result": result.get("result"),
                    "durationMs": result.get("duration_ms", 0),
                },
            )

            # Delete pending from Redis (successful completion)
            await self._redis_client.delete_pending_execution(execution_id)

            if is_sync:
                await self._redis_client.push_result(
                    execution_id=execution_id,
                    status=status.value,
                    result=result.get("result"),
                    error=result.get("error_message"),
                    error_type=result.get("error_type"),
                    duration_ms=result.get("duration_ms", 0),
                )

            # Update daily metrics for dashboards
            metrics = result.get("metrics", {})
            from shared.metrics import update_daily_metrics
            await update_daily_metrics(
                org_id=org_id,
                status=status.value,
                duration_ms=result.get("duration_ms", 0),
                peak_memory_bytes=metrics.get("peak_memory_bytes") if metrics else None,
                cpu_total_seconds=metrics.get("cpu_total_seconds") if metrics else None,
            )

            logger.info(
                f"Workflow execution completed: {workflow_name}",
                extra={
                    "execution_id": execution_id,
                    "status": status.value,
                    "duration_ms": result.get("duration_ms", 0),
                    "peak_memory_mb": round(metrics.get("peak_memory_bytes", 0) / 1024 / 1024, 1) if metrics else None,
                    "cpu_seconds": metrics.get("cpu_total_seconds") if metrics else None,
                },
            )

        except asyncio.CancelledError:
            logger.info(f"Execution task {execution_id} was cancelled")
            # Delete pending from Redis
            await self._redis_client.delete_pending_execution(execution_id)
            raise

        except Exception as e:
            # Unexpected error
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            error_type = type(e).__name__

            from src.models.enums import ExecutionStatus
            from shared.consumers._helpers import update_execution

            await update_execution(
                execution_id=execution_id,
                org_id=org_id,
                user_id=user_id,
                status=ExecutionStatus.FAILED,
                error_message=error_msg,
                error_type=error_type,
                duration_ms=duration_ms,
            )

            await publish_execution_update(
                execution_id,
                "Failed",
                {"error": error_msg, "errorType": error_type},
            )

            # Delete pending from Redis
            await self._redis_client.delete_pending_execution(execution_id)

            if is_sync:
                await self._redis_client.push_result(
                    execution_id=execution_id,
                    status="Failed",
                    error=error_msg,
                    error_type=error_type,
                    duration_ms=duration_ms,
                )

            logger.error(
                f"Workflow execution error: {execution_id}",
                extra={
                    "execution_id": execution_id,
                    "error": error_msg,
                    "error_type": error_type,
                },
                exc_info=True,
            )
            raise
