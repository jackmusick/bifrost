"""
Workflow Execution Consumer

Processes async workflow executions from RabbitMQ queue.

Architecture (Redis-first):
1. API stores pending execution in Redis, publishes to RabbitMQ
2. Consumer reads pending execution from Redis
3. Consumer creates PostgreSQL record when starting
4. Consumer routes execution to ProcessPoolManager
5. ProcessPoolManager executes in worker process, returns result via callback
6. Consumer handles result: updates DB, flushes logs, cleans up Redis

For sync execution requests (sync=True in message):
- Pushes result to Redis after completion
- API waits on Redis BLPOP for the result

Execution Model:
- All executions use ProcessPoolManager (process isolation)
- Worker processes are pooled and reused for efficiency
- Timeouts and crashes are handled by the pool manager
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session_factory
from src.core.pubsub import publish_execution_update, publish_history_update
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
        from src.services.execution.process_pool import get_process_pool

        settings = get_settings()
        super().__init__(
            queue_name=QUEUE_NAME,
            prefetch_count=settings.max_concurrency,
        )
        self._redis_client = get_redis_client()

        # Get the global ProcessPoolManager instance
        # This ensures package_install consumer can also update it
        self._pool = get_process_pool()
        # Set the result callback on the global pool
        self._pool.on_result = self._handle_result
        self._pool_started = False

        # Persistent DB session for read operations
        self._session_factory = get_session_factory()
        self._db_session: "AsyncSession | None" = None

    async def start(self) -> None:
        """Start the consumer and process pool."""
        # Call parent start to set up RabbitMQ connection
        await super().start()

        # Create persistent DB session for read operations
        self._db_session = self._session_factory()
        logger.info("Persistent DB session created")

        # Start process pool
        await self._pool.start()
        self._pool_started = True
        logger.info("Process pool started")

    async def stop(self) -> None:
        """Stop the consumer and process pool."""
        # Stop process pool
        if self._pool_started:
            await self._pool.stop()
            self._pool_started = False
            logger.info("Process pool stopped")

        # Close persistent DB session
        if self._db_session:
            await self._db_session.close()
            self._db_session = None
            logger.info("Persistent DB session closed")

        # Call parent stop
        await super().stop()

    async def _get_db_session(self) -> "AsyncSession":
        """
        Get the persistent DB session, reconnecting if needed.

        Performs a health check and reconnects if the connection is stale.
        This is important for long-running consumers where connections may drop.

        Returns:
            Healthy AsyncSession instance
        """
        from sqlalchemy import text

        # Create session if None
        if self._db_session is None:
            self._db_session = self._session_factory()
            logger.debug("Created new persistent DB session")

        # Health check - try a simple query
        try:
            await self._db_session.execute(text("SELECT 1"))
        except Exception as e:
            logger.warning(f"DB session stale ({type(e).__name__}), reconnecting...")
            try:
                await self._db_session.close()
            except Exception:
                pass  # Ignore close errors on stale session
            self._db_session = self._session_factory()
            logger.info("Reconnected persistent DB session")

        return self._db_session

    async def _handle_result(self, result: dict[str, Any]) -> None:
        """
        Handle result from process pool.

        This callback is invoked by the pool when a worker reports
        a result (success or failure, including timeouts and crashes).

        All DB operations are batched into a single transaction.
        """
        from src.core.database import get_session_factory

        execution_id = result.get("execution_id", "")

        # Single session for all DB operations
        session_factory = get_session_factory()
        async with session_factory() as session:
            try:
                if result.get("success"):
                    await self._process_success(execution_id, result, session)
                else:
                    await self._process_failure(execution_id, result, session)

                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to process result for {execution_id}: {e}")
                raise

    async def _process_success(
        self,
        execution_id: str,
        result: dict[str, Any],
        session: "AsyncSession",
    ) -> None:
        """
        Process a successful execution result.

        Updates the database, flushes logs, and publishes status updates.

        The result dict from simple_worker contains:
        - result["result"]: The workflow's return value (e.g., {"message": "Hello"})
        - result["status"]: Execution status (e.g., "Success")
        - result["roi"]: ROI data
        - result["error"]/result["error_type"]: Error info if any
        - result["variables"]: Runtime variables
        - result["metrics"]: Resource metrics
        - result["duration_ms"]: Execution duration

        Args:
            execution_id: The execution ID
            result: Result dict from worker process
            session: Database session (caller manages commit)
        """
        from src.core.metrics import update_daily_metrics, update_workflow_roi_daily
        from src.models.enums import ExecutionStatus
        from src.repositories.executions import update_execution

        # Extract workflow return value (what the @workflow function returned)
        workflow_result = result.get("result")
        duration_ms = result.get("duration_ms", 0)

        # Get additional context from Redis for pubsub updates
        pending = await self._redis_client.get_pending_execution(execution_id)
        if not pending:
            logger.warning(f"No pending record found for result: {execution_id}")
            return

        workflow_id = pending.get("workflow_id")
        workflow_name = pending.get("workflow_name", "unknown")
        org_id = pending.get("org_id")
        user_id = pending.get("user_id")
        user_name = pending.get("user_name")
        is_sync = pending.get("sync", False)

        # Determine status from result (at top level, not nested)
        status_str = result.get("status", "Success")
        status = (
            ExecutionStatus(status_str)
            if status_str in [s.value for s in ExecutionStatus]
            else ExecutionStatus.SUCCESS
        )

        # Extract ROI from result (at top level)
        roi_data = result.get("roi") or {}
        roi_time_saved = roi_data.get("time_saved", 0)
        roi_value = roi_data.get("value", 0.0)

        # Update database
        await update_execution(
            execution_id=execution_id,
            status=status,
            result=workflow_result,
            error_message=result.get("error"),
            error_type=result.get("error_type"),
            duration_ms=duration_ms,
            variables=result.get("variables"),
            metrics=result.get("metrics"),
            time_saved=roi_time_saved,
            value=roi_value,
            session=session,
        )

        # Update event delivery status if this execution was triggered by an event
        try:
            from src.services.events.processor import update_delivery_from_execution
            await update_delivery_from_execution(execution_id, status.value, session=session)
        except Exception as e:
            # Don't fail the execution result if delivery update fails
            logger.warning(f"Failed to update event delivery for {execution_id[:8]}...: {e}")

        # Flush pending changes (SDK writes) from Redis to Postgres BEFORE publishing
        # This ensures data is in PostgreSQL when client refetches after receiving update
        try:
            from bifrost._sync import flush_pending_changes
            changes_count = await flush_pending_changes(execution_id, session=session)
            if changes_count > 0:
                logger.info(f"Flushed {changes_count} pending changes for {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush pending changes for {execution_id[:8]}...: {e}")

        # Flush logs from Redis Stream to Postgres BEFORE publishing
        # This ensures logs are in PostgreSQL when client refetches after receiving update
        try:
            from bifrost._logging import flush_logs_to_postgres
            logs_count = await flush_logs_to_postgres(execution_id, session=session)
            if logs_count > 0:
                logger.debug(f"Flushed {logs_count} logs for {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush logs for {execution_id[:8]}...: {e}")

        # Publish updates AFTER flushing data to PostgreSQL
        # Client will refetch and get the complete data including logs
        # (pubsub operations don't need the session)
        await publish_execution_update(
            execution_id,
            status.value,
            {"result": workflow_result, "durationMs": duration_ms},
        )

        completed_at = datetime.now(timezone.utc)
        await publish_history_update(
            execution_id=execution_id,
            status=status.value,
            executed_by=user_id,
            executed_by_name=user_name,
            workflow_name=workflow_name,
            org_id=org_id,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

        # Cleanup execution cache (remove temporary Redis keys)
        try:
            from src.core.cache import cleanup_execution_cache
            await cleanup_execution_cache(execution_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup cache for {execution_id[:8]}...: {e}")

        # Delete pending execution from Redis
        await self._redis_client.delete_pending_execution(execution_id)

        # Push sync result if needed
        if is_sync:
            await self._redis_client.push_result(
                execution_id=execution_id,
                status=status.value,
                result=workflow_result,
                error=result.get("error"),
                error_type=result.get("error_type"),
                duration_ms=duration_ms,
            )

        # Update metrics
        metrics = result.get("metrics") or {}
        await update_daily_metrics(
            org_id=org_id,
            status=status.value,
            duration_ms=duration_ms,
            peak_memory_bytes=metrics.get("peak_memory_bytes"),
            cpu_total_seconds=metrics.get("cpu_total_seconds"),
            time_saved=roi_time_saved,
            value=roi_value,
            workflow_id=workflow_id,
            db=session,
        )

        if workflow_id:
            await update_workflow_roi_daily(
                workflow_id=workflow_id,
                org_id=org_id,
                status=status.value,
                time_saved=roi_time_saved,
                value=roi_value,
                db=session,
            )

        logger.info(
            f"Execution result processed: {execution_id[:8]}... status={status.value}",
            extra={
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "status": status.value,
                "duration_ms": duration_ms,
                "execution_model": "process",
            },
        )

    async def _process_failure(
        self,
        execution_id: str,
        result: dict[str, Any],
        session: "AsyncSession",
    ) -> None:
        """
        Process a failed execution result.

        Handles various failure types (timeout, crash, execution error).

        Args:
            execution_id: The execution ID
            result: Result dict from worker process
            session: Database session (caller manages commit)
        """
        from src.core.metrics import update_daily_metrics
        from src.models.enums import ExecutionStatus
        from src.repositories.executions import update_execution

        error = result.get("error", "Unknown error")
        error_type = result.get("error_type", "ExecutionError")
        duration_ms = result.get("duration_ms", 0)

        # Get additional context from Redis for pubsub updates
        pending = await self._redis_client.get_pending_execution(execution_id)
        if not pending:
            logger.warning(f"No pending record found for failed result: {execution_id}")
            return

        workflow_id = pending.get("workflow_id")
        workflow_name = pending.get("workflow_name", "unknown")
        org_id = pending.get("org_id")
        user_id = pending.get("user_id")
        user_name = pending.get("user_name")
        is_sync = pending.get("sync", False)

        # Determine status based on error type
        if error_type == "TimeoutError":
            status = ExecutionStatus.TIMEOUT
        elif error_type == "CancelledError":
            status = ExecutionStatus.CANCELLED
        else:
            status = ExecutionStatus.FAILED

        # Update database
        await update_execution(
            execution_id=execution_id,
            status=status,
            error_message=error,
            error_type=error_type,
            duration_ms=duration_ms,
            session=session,
        )

        # Update event delivery status if this execution was triggered by an event
        try:
            from src.services.events.processor import update_delivery_from_execution
            await update_delivery_from_execution(
                execution_id, status.value, error_message=error, session=session
            )
        except Exception as e:
            # Don't fail the execution result if delivery update fails
            logger.warning(f"Failed to update event delivery for {execution_id[:8]}...: {e}")

        # Flush pending changes (SDK writes) from Redis to Postgres BEFORE publishing
        # Even failed executions may have buffered writes
        # This ensures data is in PostgreSQL when client refetches after receiving update
        try:
            from bifrost._sync import flush_pending_changes
            changes_count = await flush_pending_changes(execution_id, session=session)
            if changes_count > 0:
                logger.info(f"Flushed {changes_count} pending changes for failed {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush pending changes for {execution_id[:8]}...: {e}")

        # Flush logs from Redis Stream to Postgres BEFORE publishing
        # This ensures logs are in PostgreSQL when client refetches after receiving update
        try:
            from bifrost._logging import flush_logs_to_postgres
            logs_count = await flush_logs_to_postgres(execution_id, session=session)
            if logs_count > 0:
                logger.debug(f"Flushed {logs_count} logs for failed {execution_id[:8]}...")
        except Exception as e:
            logger.warning(f"Failed to flush logs for {execution_id[:8]}...: {e}")

        # Publish updates AFTER flushing data to PostgreSQL
        # Client will refetch and get the complete data including logs
        # (pubsub operations don't need the session)
        await publish_execution_update(
            execution_id,
            status.value,
            {"error": error, "errorType": error_type},
        )

        completed_at = datetime.now(timezone.utc)
        await publish_history_update(
            execution_id=execution_id,
            status=status.value,
            executed_by=user_id,
            executed_by_name=user_name,
            workflow_name=workflow_name,
            org_id=org_id,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

        # Cleanup execution cache (remove temporary Redis keys)
        try:
            from src.core.cache import cleanup_execution_cache
            await cleanup_execution_cache(execution_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup cache for {execution_id[:8]}...: {e}")

        # Delete pending execution from Redis
        await self._redis_client.delete_pending_execution(execution_id)

        # Push sync result if needed
        if is_sync:
            await self._redis_client.push_result(
                execution_id=execution_id,
                status=status.value,
                error=error,
                error_type=error_type,
                duration_ms=duration_ms,
            )

        # Update metrics
        await update_daily_metrics(
            org_id=org_id,
            status=status.value,
            duration_ms=duration_ms,
            workflow_id=workflow_id,
            db=session,
        )

        logger.warning(
            f"Execution failed: {execution_id[:8]}... status={status.value} error={error_type}",
            extra={
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "status": status.value,
                "error_type": error_type,
                "duration_ms": duration_ms,
                "execution_model": "process",
            },
        )

    async def process_message(self, message_data: dict[str, Any]) -> None:
        """Process a workflow execution message."""
        from src.services.execution.queue_tracker import remove_from_queue

        # Get persistent session for read operations
        db = await self._get_db_session()

        execution_id = message_data.get("execution_id", "")
        workflow_id = message_data.get("workflow_id")
        code_base64 = message_data.get("code")
        script_name = message_data.get("script_name")
        is_sync = message_data.get("sync", False)
        file_path: str | None = None  # Will be set from workflow metadata lookup
        start_time = datetime.now(timezone.utc)

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
                    "execution_model": "process",
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
                    execution_model="process",
                    workflow_id=workflow_id,
                )
                await update_execution(
                    execution_id=execution_id,
                    status=ExecutionStatus.CANCELLED,
                    error_message="Execution was cancelled before it could start",
                    duration_ms=0,
                )
                await publish_execution_update(execution_id, "Cancelled")
                await publish_history_update(
                    execution_id=execution_id,
                    status="Cancelled",
                    executed_by=user_id,
                    executed_by_name=user_name,
                    workflow_name=script_name or "workflow",
                    org_id=org_id,
                )
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
            workflow_function_name: str | None = None  # Function name for exec_from_db()
            content_hash: str | None = None  # Content hash pinned at dispatch time

            if not is_script and workflow_id:
                from src.services.execution.service import get_workflow_for_execution, WorkflowNotFoundError

                try:
                    # Get workflow metadata (no code — worker loads via Redis→S3)
                    workflow_data = await get_workflow_for_execution(workflow_id, db=db)
                    workflow_name = workflow_data["name"]
                    workflow_function_name = workflow_data["function_name"]
                    file_path = workflow_data["path"]  # Used for __file__ injection and Redis/S3 loading

                    # Pin execution to content hash for reproducibility.
                    # Worker validates loaded code matches this hash.
                    from sqlalchemy import select as sa_select
                    from src.models.orm.file_index import FileIndex

                    hash_result = await db.execute(
                        sa_select(FileIndex.content_hash).where(
                            FileIndex.path == file_path
                        )
                    )
                    content_hash = hash_result.scalar_one_or_none()

                    timeout_seconds = workflow_data["timeout_seconds"]
                    # Initialize ROI from workflow defaults
                    roi_time_saved = workflow_data["time_saved"]
                    roi_value = workflow_data["value"]

                    # Scope resolution: org-scoped workflows use workflow's org,
                    # global workflows use caller's org
                    workflow_org_id = workflow_data.get("organization_id")
                    if workflow_org_id:
                        # Org-scoped workflow: always use workflow's org
                        org_id = workflow_org_id
                        logger.info(f"Scope: workflow org {org_id} (org-scoped workflow)")
                    else:
                        # Global workflow: use caller's org (already set from pending["org_id"])
                        logger.info(f"Scope: caller org {org_id or 'GLOBAL'} (global workflow)")
                except WorkflowNotFoundError:
                    logger.error(f"Workflow not found: {workflow_id}")
                    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
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
                        execution_model="process",
                        workflow_id=workflow_id,
                    )
                    await update_execution(
                        execution_id=execution_id,
                        status=ExecutionStatus.FAILED,
                        result={"error": "WorkflowNotFound", "message": error_msg},
                        duration_ms=duration_ms,
                    )
                    await publish_execution_update(execution_id, "Failed", {"error": error_msg})
                    await publish_history_update(
                        execution_id=execution_id,
                        status="Failed",
                        executed_by=user_id,
                        executed_by_name=user_name,
                        workflow_name="unknown",
                        org_id=org_id,
                        duration_ms=duration_ms,
                    )
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

            # Store additional context in pending record for result handler
            # (needed when pool reports results asynchronously)
            await self._redis_client.update_pending_execution(
                execution_id=execution_id,
                updates={
                    "workflow_name": workflow_name,
                    "workflow_id": workflow_id,
                    "org_id": org_id,  # Resolved scope for result handlers
                },
            )

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
                execution_model="process",
                workflow_id=workflow_id,
            )
            await publish_execution_update(execution_id, "Running")
            await publish_history_update(
                execution_id=execution_id,
                status="Running",
                executed_by=user_id,
                executed_by_name=user_name,
                workflow_name=workflow_name,
                org_id=org_id,
                started_at=start_time,
            )

            # Load organization and config
            org = None
            org_data = None
            config = {}

            if org_id:
                from src.core.config_resolver import ConfigResolver

                resolver = ConfigResolver()
                org = await resolver.get_organization(org_id, db=db)
                config = await resolver.load_config_for_scope(org_id, db=db)
                if org:
                    org_data = {
                        "id": org.id,
                        "name": org.name,
                        "is_active": org.is_active,
                    }
            else:
                from src.core.config_resolver import ConfigResolver

                resolver = ConfigResolver()
                config = await resolver.load_config_for_scope("GLOBAL", db=db)

            # Build context for worker process
            context_data = {
                "execution_id": execution_id,
                "workflow_id": workflow_id,
                "name": workflow_name,
                "function_name": workflow_function_name,  # For exec_from_db()
                "code": code_base64,  # Base64-encoded inline script (different from workflow_code)
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
                "file_path": file_path,  # Path for __file__ injection and fallback loading
                "content_hash": content_hash,  # Pinned hash at dispatch time
            }

            # Pre-warm SDK cache BEFORE dispatching to worker process
            # This runs in the consumer's stable main event loop, avoiding
            # event loop issues with shared async resources (DB, Redis)
            try:
                from src.core.cache import prewarm_sdk_cache
                await prewarm_sdk_cache(
                    execution_id=execution_id,
                    org_id=org_id,
                    user_id=user_id,
                    is_admin=False,  # Workflows run without admin privileges
                )
                logger.debug(f"Pre-warmed SDK cache for execution {execution_id[:8]}...")
            except Exception as e:
                # Log but don't fail - SDK will fall back gracefully
                logger.warning(f"Failed to pre-warm SDK cache: {e}")

            # Route to process pool
            # Results are handled asynchronously via _handle_result callback
            await self._pool.route_execution(
                execution_id=execution_id,
                context=context_data,
            )
            logger.debug(
                f"Execution routed to process pool: {execution_id[:8]}...",
                extra={"execution_model": "process"},
            )
            # Don't wait for result - pool will call back

        except asyncio.CancelledError:
            logger.info(f"Execution task {execution_id} was cancelled")
            await self._redis_client.delete_pending_execution(execution_id)
            raise

        except Exception as e:
            # Unexpected error during setup (before routing to pool)
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            completed_at = datetime.now(timezone.utc)
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
            await publish_history_update(
                execution_id=execution_id,
                status="Failed",
                executed_by=user_id,
                executed_by_name=user_name,
                workflow_name=workflow_name,
                org_id=org_id,
                started_at=start_time,
                completed_at=completed_at,
                duration_ms=duration_ms,
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
                    "execution_model": "process",
                },
                exc_info=True,
            )
            raise
