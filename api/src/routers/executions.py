"""
Executions Router

Provides access to workflow execution history with filtering capabilities.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Import existing Pydantic models for API compatibility
from src.models import (
    ExecutionStatus,
    ExecutionsListResponse,
    WorkflowExecution,
    StuckExecutionsResponse,
    CleanupTriggeredResponse,
    ExecutionLogPublic,
)

from src.core.auth import Context, UserPrincipal
from src.core.pubsub import publish_execution_update
from src.core.redis_client import get_redis_client
from src.models import Execution as ExecutionModel
from src.models import ExecutionLog as ExecutionLogORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/executions", tags=["Executions"])


# =============================================================================
# Repository
# =============================================================================


class ExecutionRepository:
    """PostgreSQL-based execution repository."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_executions(
        self,
        user: UserPrincipal,
        org_id: UUID | None,
        workflow_name: str | None = None,
        status_filter: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[WorkflowExecution], str | None]:
        """List executions with filtering."""
        query = select(ExecutionModel)

        # Organization scoping
        if org_id:
            query = query.where(ExecutionModel.organization_id == org_id)

        # Non-superusers can only see their own executions
        if not user.is_superuser:
            query = query.where(ExecutionModel.executed_by == user.user_id)

        # Filters
        if workflow_name:
            query = query.where(ExecutionModel.workflow_name == workflow_name)

        if status_filter:
            query = query.where(ExecutionModel.status == status_filter)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query = query.where(ExecutionModel.started_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query = query.where(ExecutionModel.started_at <= end_dt)
            except ValueError:
                pass

        # Order by newest first
        query = query.order_by(desc(ExecutionModel.started_at))

        # Pagination
        query = query.offset(offset).limit(limit + 1)  # +1 to check for more

        result = await self.db.execute(query)
        executions = list(result.scalars().all())

        # Check if there are more results
        has_more = len(executions) > limit
        if has_more:
            executions = executions[:limit]

        # Generate continuation token
        next_token = None
        if has_more:
            next_token = str(offset + limit)

        return [self._to_pydantic(e) for e in executions], next_token

    async def get_execution(
        self,
        execution_id: UUID,
        user: UserPrincipal,
    ) -> tuple[WorkflowExecution | None, str | None]:
        """
        Get execution by ID with authorization.

        Returns all execution details including logs (with DEBUG filtered for non-admins),
        and admin-only fields (variables, resource metrics).

        Returns:
            Tuple of (execution, error_code) where error_code is None on success
        """
        # 1. Fetch base execution
        result = await self.db.execute(
            select(ExecutionModel).where(ExecutionModel.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            return None, "NotFound"

        # Check authorization - non-superusers can only see their own
        if not user.is_superuser and execution.executed_by != user.user_id:
            return None, "Forbidden"

        # 2. Fetch logs (DEBUG/TRACEBACK filtered for non-admins)
        logs_query = (
            select(ExecutionLogORM)
            .where(ExecutionLogORM.execution_id == execution_id)
            .order_by(ExecutionLogORM.sequence)
        )
        if not user.is_superuser:
            logs_query = logs_query.where(
                ExecutionLogORM.level.notin_(["DEBUG", "TRACEBACK"])
            )
        logs_result = await self.db.execute(logs_query)
        log_entries = logs_result.scalars().all()

        logs = [
            ExecutionLogPublic(
                timestamp=log.timestamp.isoformat() if log.timestamp else "",
                level=log.level or "info",
                message=log.message or "",
                data=log.log_metadata,
            )
            for log in log_entries
        ]

        # 3. Build response with conditional admin-only fields
        return WorkflowExecution(
            execution_id=str(execution.id),
            workflow_name=execution.workflow_name,
            org_id=str(execution.organization_id) if execution.organization_id else None,
            form_id=str(execution.form_id) if execution.form_id else None,
            executed_by=str(execution.executed_by),
            executed_by_name=execution.executed_by_name or str(execution.executed_by),
            status=ExecutionStatus(execution.status),
            input_data=execution.parameters or {},
            result=execution.result,
            result_type=execution.result_type,
            error_message=execution.error_message,
            duration_ms=execution.duration_ms,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            logs=[log.model_dump() for log in logs],
            # Admin-only fields (null for non-admins)
            variables=execution.variables if user.is_superuser else None,
            peak_memory_bytes=execution.peak_memory_bytes if user.is_superuser else None,
            cpu_total_seconds=execution.cpu_total_seconds if user.is_superuser else None,
        ), None

    async def get_execution_result(
        self,
        execution_id: UUID,
        user: UserPrincipal,
    ) -> tuple[Any, str | None]:
        """Get execution result only."""
        result = await self.db.execute(
            select(
                ExecutionModel.result,
                ExecutionModel.result_type,
                ExecutionModel.executed_by,
            ).where(ExecutionModel.id == execution_id)
        )
        row = result.one_or_none()

        if not row:
            return None, "NotFound"

        if not user.is_superuser and row.executed_by != user.user_id:
            return None, "Forbidden"

        return {"result": row.result, "result_type": row.result_type}, None

    async def get_execution_logs(
        self,
        execution_id: UUID,
        user: UserPrincipal,
    ) -> tuple[list[ExecutionLogPublic] | None, str | None]:
        """Get execution logs from the execution_logs table."""
        # First check if execution exists and user has access
        result = await self.db.execute(
            select(ExecutionModel.executed_by).where(ExecutionModel.id == execution_id)
        )
        row = result.one_or_none()

        if not row:
            return None, "NotFound"

        if not user.is_superuser and row.executed_by != user.user_id:
            return None, "Forbidden"

        # Query logs from execution_logs table (order by sequence for guaranteed ordering)
        logs_query = (
            select(ExecutionLogORM)
            .where(ExecutionLogORM.execution_id == execution_id)
            .order_by(ExecutionLogORM.sequence)
        )

        # Filter debug logs for non-superusers
        if not user.is_superuser:
            logs_query = logs_query.where(ExecutionLogORM.level.notin_(["DEBUG", "TRACEBACK"]))

        logs_result = await self.db.execute(logs_query)
        log_entries = logs_result.scalars().all()

        # Convert ORM models to Pydantic models
        logs = [
            ExecutionLogPublic(
                timestamp=log.timestamp.isoformat() if log.timestamp else "",
                level=log.level or "info",
                message=log.message or "",
                data=log.log_metadata,
            )
            for log in log_entries
        ]

        return logs, None

    async def get_execution_variables(
        self,
        execution_id: UUID,
        user: UserPrincipal,
    ) -> tuple[dict | None, str | None]:
        """Get execution variables (platform admin only)."""
        if not user.is_superuser:
            return None, "Forbidden"

        # Select id and variables to distinguish "not found" from "null variables"
        result = await self.db.execute(
            select(ExecutionModel.id, ExecutionModel.variables)
            .where(ExecutionModel.id == execution_id)
        )
        row = result.one_or_none()

        if row is None:
            return None, "NotFound"

        # row is a tuple of (id, variables)
        return row[1] or {}, None

    async def cancel_execution(
        self,
        execution_id: UUID,
        user: UserPrincipal,
    ) -> tuple[WorkflowExecution | None, str | None]:
        """Cancel a pending or running execution."""
        result = await self.db.execute(
            select(ExecutionModel).where(ExecutionModel.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            return None, "NotFound"

        if not user.is_superuser and execution.executed_by != user.user_id:
            return None, "Forbidden"

        # Can only cancel pending or running executions
        if execution.status not in [ExecutionStatus.PENDING.value, ExecutionStatus.RUNNING.value]:
            return None, "BadRequest"

        # Update status
        execution.status = ExecutionStatus.CANCELLING.value  # type: ignore[assignment]

        await self.db.flush()
        await self.db.refresh(execution)

        # Publish update
        await publish_execution_update(
            execution_id=execution_id,
            status=ExecutionStatus.CANCELLING.value,
        )

        return self._to_pydantic(execution), None

    def _to_pydantic(self, execution: ExecutionModel) -> WorkflowExecution:
        """Convert SQLAlchemy model to Pydantic model.

        Note: logs are NOT included here - they should be fetched separately
        via the /logs endpoint to avoid loading potentially large log data.
        """
        return WorkflowExecution(
            execution_id=str(execution.id),
            workflow_name=execution.workflow_name,
            org_id=str(execution.organization_id) if execution.organization_id else None,
            form_id=str(execution.form_id) if execution.form_id else None,
            executed_by=str(execution.executed_by),
            executed_by_name=execution.executed_by_name or str(execution.executed_by),
            status=ExecutionStatus(execution.status),
            input_data=execution.parameters or {},
            result=execution.result,
            result_type=execution.result_type,
            error_message=execution.error_message,
            duration_ms=execution.duration_ms,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            logs=None,  # Fetched separately via /logs endpoint
            variables=execution.variables,
        )


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "",
    response_model=ExecutionsListResponse,
    summary="List workflow executions",
    description="List workflow executions with filtering and pagination",
)
async def list_executions(
    ctx: Context,
    workflowName: str | None = Query(None, description="Filter by workflow name"),
    status: str | None = Query(None, description="Filter by execution status"),
    startDate: str | None = Query(None, description="Filter by start date (ISO format)"),
    endDate: str | None = Query(None, description="Filter by end date (ISO format)"),
    limit: int = Query(25, ge=1, le=1000, description="Maximum number of results"),
    continuationToken: str | None = Query(None, description="Continuation token"),
) -> ExecutionsListResponse:
    """List workflow executions."""
    repo = ExecutionRepository(ctx.db)

    # Parse continuation token as offset
    offset = 0
    if continuationToken:
        try:
            offset = int(continuationToken)
        except ValueError:
            pass

    executions, next_token = await repo.list_executions(
        user=ctx.user,
        org_id=ctx.org_id,
        workflow_name=workflowName,
        status_filter=status,
        start_date=startDate,
        end_date=endDate,
        limit=limit,
        offset=offset,
    )

    return ExecutionsListResponse(
        executions=executions,
        continuation_token=next_token,
    )


@router.get(
    "/{execution_id}",
    response_model=WorkflowExecution,
    summary="Get execution details",
    description="Get detailed information about a specific execution",
)
async def get_execution(
    execution_id: UUID,
    ctx: Context,
) -> WorkflowExecution:
    """Get execution details."""
    repo = ExecutionRepository(ctx.db)
    execution, error = await repo.get_execution(execution_id, ctx.user)

    if error == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    elif error == "Forbidden":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this execution",
        )

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    return execution


@router.get(
    "/{execution_id}/result",
    summary="Get execution result only",
    description="Get only the result of a specific execution (progressive loading)",
)
async def get_execution_result(
    execution_id: UUID,
    ctx: Context,
) -> Any:
    """Get execution result."""
    repo = ExecutionRepository(ctx.db)
    result, error = await repo.get_execution_result(execution_id, ctx.user)

    if error == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    elif error == "Forbidden":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this execution",
        )

    return result


@router.get(
    "/{execution_id}/logs",
    summary="Get execution logs only",
    description="Get only the logs of a specific execution (progressive loading)",
    response_model=list[ExecutionLogPublic],
)
async def get_execution_logs(
    execution_id: UUID,
    ctx: Context,
) -> list[ExecutionLogPublic]:
    """Get execution logs."""
    repo = ExecutionRepository(ctx.db)
    logs, error = await repo.get_execution_logs(execution_id, ctx.user)

    if error == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    elif error == "Forbidden":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this execution",
        )

    return logs or []


@router.get(
    "/{execution_id}/variables",
    summary="Get execution variables only",
    description="Get only the variables of a specific execution (platform admin only)",
)
async def get_execution_variables(
    execution_id: UUID,
    ctx: Context,
) -> dict:
    """Get execution variables."""
    repo = ExecutionRepository(ctx.db)
    variables, error = await repo.get_execution_variables(execution_id, ctx.user)

    if error == "NotFound":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    elif error == "Forbidden":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )

    return variables or {}


@router.post(
    "/{execution_id}/cancel",
    response_model=WorkflowExecution | dict,
    summary="Cancel execution",
    description="Cancel a pending or running execution",
)
async def cancel_execution(
    execution_id: UUID,
    ctx: Context,
) -> WorkflowExecution | dict:
    """
    Cancel an execution.

    With Redis-first architecture, the execution may be in one of three states:
    1. In Redis pending only (worker hasn't picked it up yet)
    2. In PostgreSQL as Running (worker is executing)
    3. In PostgreSQL as completed (already done - return error)

    We handle all cases by:
    1. First check PostgreSQL for authorization and status
    2. If found and Running/Pending, set Redis cancel flag for pool
    3. If not in PostgreSQL yet, try to cancel Redis pending record
    """
    redis_client = get_redis_client()
    repo = ExecutionRepository(ctx.db)

    # First, try to find in PostgreSQL to check authorization
    execution, error = await repo.cancel_execution(execution_id, ctx.user)

    if error == "Forbidden":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to cancel this execution",
        )
    elif error == "BadRequest":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel execution {execution_id} - must be Pending or Running",
        )
    elif execution is not None:
        # Found in PostgreSQL and status is cancellable
        # Set Redis cancel flag so the execution pool can terminate the worker
        await redis_client.set_cancel_flag(str(execution_id))
        logger.info(f"Set cancel flag for running execution: {execution_id}")
        return execution

    # Not found in PostgreSQL - check if it's still pending in Redis
    # (worker hasn't created the PostgreSQL record yet)
    pending_cancelled = await redis_client.set_pending_cancelled(str(execution_id))

    if pending_cancelled:
        # Execution was in Redis pending, now marked as cancelled
        # Worker will see this flag and skip execution
        logger.info(f"Cancelled pending execution in Redis: {execution_id}")
        return {
            "execution_id": str(execution_id),
            "status": "Cancelled",
            "message": "Execution cancelled before it started",
        }

    # Not found anywhere
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Execution {execution_id} not found",
    )


# =============================================================================
# Cleanup Endpoints
# =============================================================================


@router.get(
    "/cleanup/stuck",
    response_model=StuckExecutionsResponse,
    summary="Get stuck executions",
    description="Get executions that have been running or pending too long (Platform admin only)",
)
async def get_stuck_executions(
    ctx: Context,
    hours: int = Query(24, description="Hours since start to consider stuck"),
) -> StuckExecutionsResponse:
    """Get stuck executions that may need cleanup."""
    if not ctx.user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )

    # Find executions that have been pending/running for too long
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = select(ExecutionModel).where(
        and_(
            ExecutionModel.status.in_([
                ExecutionStatus.PENDING.value,
                ExecutionStatus.RUNNING.value,
            ]),
            ExecutionModel.started_at < cutoff,
        )
    ).order_by(desc(ExecutionModel.started_at))

    result = await ctx.db.execute(query)
    executions = result.scalars().all()

    repo = ExecutionRepository(ctx.db)
    stuck_executions = [repo._to_pydantic(e) for e in executions]

    return StuckExecutionsResponse(
        executions=stuck_executions,
        count=len(stuck_executions),
    )


@router.post(
    "/cleanup/trigger",
    response_model=CleanupTriggeredResponse,
    summary="Trigger execution cleanup",
    description="Clean up stuck executions by marking them as timed out (Platform admin only)",
)
async def trigger_cleanup(
    ctx: Context,
    hours: int = Query(24, description="Hours since start to consider stuck"),
) -> CleanupTriggeredResponse:
    """Trigger cleanup of stuck executions."""
    if not ctx.user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )

    # Find stuck executions
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Count pending
    pending_query = select(ExecutionModel).where(
        and_(
            ExecutionModel.status == ExecutionStatus.PENDING.value,
            ExecutionModel.started_at < cutoff,
        )
    )
    pending_result = await ctx.db.execute(pending_query)
    pending_executions = pending_result.scalars().all()

    # Count running
    running_query = select(ExecutionModel).where(
        and_(
            ExecutionModel.status == ExecutionStatus.RUNNING.value,
            ExecutionModel.started_at < cutoff,
        )
    )
    running_result = await ctx.db.execute(running_query)
    running_executions = running_result.scalars().all()

    # Update all stuck executions to FAILED with timeout message
    failed_count = 0
    for execution in list(pending_executions) + list(running_executions):
        try:
            execution.status = ExecutionStatus.FAILED.value  # type: ignore[assignment]
            execution.error_message = f"Execution timed out after {hours} hours"
            execution.completed_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Failed to cleanup execution {execution.id}: {e}")
            failed_count += 1

    await ctx.db.flush()

    total_cleaned = len(pending_executions) + len(running_executions) - failed_count

    logger.info(
        f"Cleanup triggered: {total_cleaned} executions cleaned "
        f"({len(pending_executions)} pending, {len(running_executions)} running, {failed_count} failed)"
    )

    return CleanupTriggeredResponse(
        cleaned=total_cleaned,
        pending=len(pending_executions),
        running=len(running_executions),
        failed=failed_count,
    )


@router.post(
    "/cleanup/redis-orphans",
    summary="Cleanup orphaned Redis pending executions",
    description="Clean up Redis pending executions that are too old (Platform admin only)",
)
async def cleanup_redis_orphans(
    ctx: Context,
    minutes: int = Query(10, description="Minutes since creation to consider orphaned"),
) -> dict:
    """
    Clean up orphaned Redis pending executions.

    With Redis-first architecture, pending executions are stored in Redis until
    the worker picks them up. If the worker fails to pick up an execution within
    a reasonable time (default 10 minutes), we mark it as failed.

    This endpoint:
    1. Scans Redis for pending executions older than `minutes`
    2. Checks if they exist in PostgreSQL (worker should have created record)
    3. If not in PostgreSQL, creates a FAILED record
    4. Deletes the Redis pending entry
    """
    if not ctx.user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )

    # For now, Redis pending entries have 1 hour TTL and will auto-expire
    # This endpoint is a placeholder for more sophisticated cleanup
    # A full implementation would:
    # 1. SCAN Redis for keys matching bifrost:exec:*:pending
    # 2. Check each key's created_at timestamp
    # 3. If too old, create FAILED PostgreSQL record and delete Redis entry

    # For Redis-first architecture, the worker should pick up jobs within seconds
    # Redis TTL (1 hour) provides automatic cleanup for truly orphaned entries
    # Manual cleanup via this endpoint is optional

    logger.info(f"Redis orphan cleanup triggered (threshold: {minutes} minutes)")

    return {
        "message": "Redis pending entries auto-expire via TTL. Use /cleanup/trigger for PostgreSQL cleanup.",
        "redis_ttl_hours": 1,
        "threshold_minutes": minutes,
    }
