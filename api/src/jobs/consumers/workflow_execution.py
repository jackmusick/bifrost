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
        "workflow_id": "uuid" (optional, for workflow execution),
        "code": "base64-encoded-script" (optional, for inline scripts),
        "script_name": "name" (optional, for inline scripts),
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
        from src.services.execution.queue_tracker import remove_from_queue

        execution_id = message_data.get("execution_id", "")
        workflow_id = message_data.get("workflow_id")
        code_base64 = message_data.get("code")
        script_name = message_data.get("script_name")
        is_sync = message_data.get("sync", False)
        file_path = message_data.get("file_path")  # For fast direct loading
        start_time = datetime.utcnow()

        # Remove from queue tracking (execution is now being processed)
        await remove_from_queue(execution_id)

        # Read execution context from Redis
        pending = await self._redis_client.get_pending_execution(execution_id)

        if pending is None:
            logger.error(f"No pending execution found in Redis: {execution_id}")
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
        parameters = pending["parameters"]
        org_id = pending["org_id"]
        user_id = pending["user_id"]
        user_name = pending["user_name"]
        user_email = pending["user_email"]
        form_id = pending.get("form_id")
        api_key_id = pending.get("api_key_id")  # Workflow ID whose API key triggered this
        startup = pending.get("startup")  # Launch workflow results

        # Determine if this is a code or workflow execution
        is_script = bool(code_base64)

        try:
            logger.info(
                f"Processing {'code' if is_script else 'workflow'} execution",
                extra={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "script_name": script_name,
                    "org_id": org_id,
                },
            )

            from src.models.enums import ExecutionStatus
            from src.repositories.executions import (
                create_execution,
                update_execution,
            )

            # Check if execution was cancelled in Redis before we started
            if pending.get("cancelled", False):
                logger.info(f"Execution {execution_id} was cancelled before starting")
                await create_execution(
                    execution_id=execution_id,
                    workflow_name=script_name or "workflow",
                    parameters=parameters,
                    org_id=org_id,
                    user_id=user_id,
                    user_name=user_name,
                    form_id=form_id,
                    api_key_id=api_key_id,
                    status=ExecutionStatus.CANCELLED,
                )
                await update_execution(
                    execution_id=execution_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution was cancelled before it could start",
                    duration_ms=0,
                )
                await publish_execution_update(execution_id, "Cancelled")
                await self._redis_client.delete_pending_execution(execution_id)
                if is_sync:
                    await self._redis_client.push_result(
                        execution_id=execution_id,
                        status="Cancelled",
                        error="Execution was cancelled before it could start",
                        duration_ms=0,
                    )
                return

            # Get workflow metadata from database if this is a workflow execution
            workflow_name = script_name or "inline_script"
            timeout_seconds = 1800  # Default 30 minutes
            roi_time_saved = 0
            roi_value = 0.0

            if not is_script and workflow_id:
                from src.services.execution.service import get_workflow_metadata_only, WorkflowNotFoundError

                try:
                    # Use metadata-only lookup (Redis-first, no module loading)
                    metadata = await get_workflow_metadata_only(workflow_id)
                    workflow_name = metadata.name
                    timeout_seconds = metadata.timeout_seconds if metadata else 1800
                    # Initialize ROI from workflow defaults
                    roi_time_saved = metadata.time_saved or 0
                    roi_value = float(metadata.value) if metadata.value else 0.0
                except WorkflowNotFoundError:
                    logger.error(f"Workflow not found: {workflow_id}")
                    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                    error_msg = f"Workflow with ID '{workflow_id}' not found"
                    await create_execution(
                        execution_id=execution_id,
                        workflow_name="unknown",
                        parameters=parameters,
                        org_id=org_id,
                        user_id=user_id,
                        user_name=user_name,
                        form_id=form_id,
                        api_key_id=api_key_id,
                        status=ExecutionStatus.FAILED,
                    )
                    await update_execution(
                        execution_id=execution_id,
                        status=ExecutionStatus.FAILED,
                        result={"error": "WorkflowNotFound", "message": error_msg},
                        duration_ms=duration_ms,
                    )
                    await publish_execution_update(execution_id, "Failed", {"error": error_msg})
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
                # Note: WorkflowLoadError is not caught here since get_workflow_metadata_only()
                # only queries DB/cache and doesn't load the module. Load errors will be
                # caught by the execution pool when it actually loads the workflow.

            # Create PostgreSQL record with RUNNING status
            await create_execution(
                execution_id=execution_id,
                workflow_name=workflow_name,
                parameters=parameters,
                org_id=org_id,
                user_id=user_id,
                user_name=user_name,
                form_id=form_id,
                api_key_id=api_key_id,
                status=ExecutionStatus.RUNNING,
            )
            await publish_execution_update(execution_id, "Running")

            # Load organization and config
            org = None
            org_data = None
            config = {}

            if org_id:
                from src.core.config_resolver import ConfigResolver

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
                from src.core.config_resolver import ConfigResolver

                resolver = ConfigResolver()
                config = await resolver.load_config_for_scope("GLOBAL")

            # Build context for worker process
            context_data = {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
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
                "startup": startup,  # Launch workflow results (available via context.startup)
                "roi": {
                    "time_saved": roi_time_saved,
                    "value": roi_value,
                },
                "file_path": file_path,  # For fast direct loading (skips filesystem scan)
            }

            # Execute in isolated process
            from src.services.execution.pool import get_execution_pool

            pool = get_execution_pool()

            try:
                result = await pool.execute(
                    execution_id=execution_id,
                    context_data=context_data,
                    timeout_seconds=timeout_seconds,
                )
            except asyncio.CancelledError:
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                await update_execution(
                    execution_id=execution_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution cancelled by user",
                    duration_ms=duration_ms,
                )
                await publish_execution_update(execution_id, "Cancelled")
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
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                error_msg = str(e)
                await update_execution(
                    execution_id=execution_id,
                    status=ExecutionStatus.TIMEOUT,
                    error_message=error_msg,
                    error_type="TimeoutError",
                    duration_ms=duration_ms,
                )
                await publish_execution_update(execution_id, "Timeout")
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

            # Extract ROI from result (if available)
            # Use `or {}` to handle both missing keys and explicit None values
            roi_data = result.get("roi") or {}
            final_time_saved = roi_data.get("time_saved", roi_time_saved)
            final_value = roi_data.get("value", roi_value)

            # Update execution with result and metrics
            # Note: logs are NOT passed here - they're persisted via flush_logs_to_postgres()
            # in engine.py from the Redis Stream (single source of truth per _logging.py)
            await update_execution(
                execution_id=execution_id,
                status=status,
                result=result.get("result"),
                error_message=result.get("error_message"),
                error_type=result.get("error_type"),
                duration_ms=result.get("duration_ms", 0),
                variables=result.get("variables"),
                metrics=result.get("metrics"),
                time_saved=final_time_saved,
                value=final_value,
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
            from src.core.metrics import update_daily_metrics, update_workflow_roi_daily
            await update_daily_metrics(
                org_id=org_id,
                status=status.value,
                duration_ms=result.get("duration_ms", 0),
                peak_memory_bytes=metrics.get("peak_memory_bytes") if metrics else None,
                cpu_total_seconds=metrics.get("cpu_total_seconds") if metrics else None,
                time_saved=final_time_saved,
                value=final_value,
                workflow_id=workflow_id,
            )

            # Update per-workflow ROI if this is a workflow execution
            if workflow_id:
                await update_workflow_roi_daily(
                    workflow_id=workflow_id,
                    org_id=org_id,
                    status=status.value,
                    time_saved=final_time_saved,
                    value=final_value,
                )

            logger.info(
                f"Execution completed: {workflow_name}",
                extra={
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "status": status.value,
                    "duration_ms": result.get("duration_ms", 0),
                    "peak_memory_mb": round(metrics.get("peak_memory_bytes", 0) / 1024 / 1024, 1) if metrics else None,
                    "cpu_seconds": metrics.get("cpu_total_seconds") if metrics else None,
                },
            )

        except asyncio.CancelledError:
            logger.info(f"Execution task {execution_id} was cancelled")
            await self._redis_client.delete_pending_execution(execution_id)
            raise

        except Exception as e:
            # Unexpected error
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            error_type = type(e).__name__

            from src.models.enums import ExecutionStatus
            from src.repositories.executions import update_execution

            await update_execution(
                execution_id=execution_id,
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
                    "workflow_id": workflow_id,
                    "error": error_msg,
                    "error_type": error_type,
                },
                exc_info=True,
            )
            raise
