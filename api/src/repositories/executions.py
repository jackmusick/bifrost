"""
Execution Repository

Database operations for workflow executions.
Handles CRUD operations for Execution and ExecutionLog tables.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, update

from src.models import (
    ExecutionLog as ExecutionLogSchema,
    WorkflowExecution,
)
from src.models.enums import ExecutionStatus
from src.core.auth import UserPrincipal
from src.models import Execution, ExecutionLog
from src.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ExecutionRepository(BaseRepository[Execution]):
    """Repository for execution operations."""

    model = Execution

    # =========================================================================
    # Create / Update Operations (used by workers and sync execution)
    # =========================================================================

    async def create_execution(
        self,
        execution_id: str,
        workflow_name: str,
        parameters: dict[str, Any],
        org_id: str | None,
        user_id: str,
        user_name: str,
        form_id: str | None = None,
        api_key_id: str | None = None,
        status: ExecutionStatus = ExecutionStatus.RUNNING,
        is_local_execution: bool = False,
    ) -> Execution:
        """
        Create a new execution record.

        Called by worker when it picks up a job from the queue,
        or by sync execution path.

        Args:
            execution_id: Execution ID (from Redis pending record)
            workflow_name: Name of workflow to execute
            parameters: Workflow input parameters
            org_id: Organization ID (None for GLOBAL scope)
            user_id: User ID who initiated execution (system user for API key executions)
            user_name: Display name of user
            form_id: Optional form ID if triggered by form
            api_key_id: Optional workflow ID whose API key triggered this execution
            status: Initial status (default RUNNING)
            is_local_execution: Whether this is a local CLI execution

        Returns:
            Created Execution record
        """
        # Parse org_id - strip "ORG:" prefix if present
        parsed_org_id = None
        if org_id and org_id != "GLOBAL":
            if org_id.startswith("ORG:"):
                parsed_org_id = UUID(org_id[4:])
            else:
                parsed_org_id = UUID(org_id)

        # Parse user_id
        parsed_user_id = UUID(user_id)

        # Parse form_id if present
        parsed_form_id = UUID(form_id) if form_id else None

        # Parse api_key_id if present
        parsed_api_key_id = UUID(api_key_id) if api_key_id else None

        execution = Execution(
            id=UUID(execution_id),
            workflow_name=workflow_name,
            status=status,
            parameters=parameters,
            executed_by=parsed_user_id,
            executed_by_name=user_name,
            organization_id=parsed_org_id,
            form_id=parsed_form_id,
            api_key_id=parsed_api_key_id,
            is_local_execution=is_local_execution,
            started_at=datetime.utcnow(),
        )

        self.session.add(execution)
        await self.session.flush()
        await self.session.refresh(execution)

        logger.info(f"Created execution record: {execution_id} (status={status.value})")
        return execution

    async def update_execution(
        self,
        execution_id: str,
        status: ExecutionStatus,
        result: Any = None,
        error_message: str | None = None,
        error_type: str | None = None,
        duration_ms: int | None = None,
        logs: list[dict] | None = None,
        variables: dict | None = None,
        metrics: dict | None = None,
    ) -> None:
        """
        Update an execution record with results.

        Args:
            execution_id: Execution ID
            status: New status
            result: Execution result
            error_message: Error message if failed
            error_type: Error type if failed (not stored, for logging)
            duration_ms: Execution duration in milliseconds
            logs: Execution logs to persist
            variables: Runtime variables
            metrics: Resource metrics (peak_memory_bytes, cpu_*_seconds)
        """
        # Get status value if it's an enum
        status_value = status.value if hasattr(status, "value") else status

        # Build update values
        update_values: dict[str, Any] = {
            "status": status_value,
        }

        if result is not None:
            update_values["result"] = result
            # Normalize result_type to frontend-friendly values
            python_type = type(result).__name__
            if python_type in ("dict", "list"):
                update_values["result_type"] = "json"
            elif python_type == "str":
                # Check if it's HTML
                if isinstance(result, str) and result.strip().startswith("<"):
                    update_values["result_type"] = "html"
                else:
                    update_values["result_type"] = "text"
            else:
                update_values["result_type"] = "json"  # Default to json

        if error_message is not None:
            update_values["error_message"] = error_message

        if duration_ms is not None:
            update_values["duration_ms"] = duration_ms
            update_values["completed_at"] = datetime.utcnow()

        if variables is not None:
            update_values["variables"] = variables

        # Resource metrics
        if metrics is not None:
            if "peak_memory_bytes" in metrics:
                update_values["peak_memory_bytes"] = metrics["peak_memory_bytes"]
            if "cpu_user_seconds" in metrics:
                update_values["cpu_user_seconds"] = metrics["cpu_user_seconds"]
            if "cpu_system_seconds" in metrics:
                update_values["cpu_system_seconds"] = metrics["cpu_system_seconds"]
            if "cpu_total_seconds" in metrics:
                update_values["cpu_total_seconds"] = metrics["cpu_total_seconds"]

        # Execute update
        await self.session.execute(
            update(Execution)
            .where(Execution.id == UUID(execution_id))
            .values(**update_values)
        )

        # Store logs in ExecutionLog table
        if logs:
            for idx, log_entry in enumerate(logs):
                log_record = ExecutionLog(
                    execution_id=UUID(execution_id),
                    sequence=idx,
                    timestamp=datetime.fromisoformat(log_entry["timestamp"]) if isinstance(log_entry.get("timestamp"), str) else datetime.utcnow(),
                    level=log_entry.get("level", "info").upper(),
                    message=log_entry.get("message", ""),
                    log_metadata=log_entry.get("data"),
                )
                self.session.add(log_record)

        await self.session.flush()
        logger.debug(f"Updated execution {execution_id} to status {status_value}")

    # =========================================================================
    # Read Operations (used by API endpoints)
    # =========================================================================

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
        query = select(Execution)

        # Organization scoping
        if org_id:
            query = query.where(Execution.organization_id == org_id)

        # Non-superusers can only see their own executions
        if not user.is_superuser:
            query = query.where(Execution.executed_by == user.user_id)

        # Filters
        if workflow_name:
            query = query.where(Execution.workflow_name == workflow_name)

        if status_filter:
            query = query.where(Execution.status == status_filter)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query = query.where(Execution.started_at >= start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query = query.where(Execution.started_at <= end_dt)
            except ValueError:
                pass

        # Order by newest first
        query = query.order_by(desc(Execution.started_at))

        # Pagination
        query = query.offset(offset).limit(limit + 1)  # +1 to check for more

        result = await self.session.execute(query)
        executions = list(result.scalars().all())

        # Check if there are more results
        has_more = len(executions) > limit
        if has_more:
            executions = executions[:limit]

        # Generate continuation token
        next_token = None
        if has_more:
            next_token = str(offset + limit)

        return [self._to_pydantic(e, user) for e in executions], next_token

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
        result = await self.session.execute(
            select(Execution).where(Execution.id == execution_id)
        )
        execution = result.scalar_one_or_none()

        if not execution:
            return None, "NotFound"

        # Check authorization - non-superusers can only see their own
        if not user.is_superuser and execution.executed_by != user.user_id:
            return None, "Forbidden"

        # 2. Fetch logs (DEBUG/TRACEBACK filtered for non-admins)
        logs_query = (
            select(ExecutionLog)
            .where(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.sequence)
        )
        if not user.is_superuser:
            logs_query = logs_query.where(
                ExecutionLog.level.notin_(["DEBUG", "TRACEBACK"])
            )
        logs_result = await self.session.execute(logs_query)
        log_entries = logs_result.scalars().all()

        logs = [
            ExecutionLogSchema(
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
            session_id=str(execution.session_id) if execution.session_id else None,
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
        result = await self.session.execute(
            select(
                Execution.result,
                Execution.result_type,
                Execution.executed_by,
            ).where(Execution.id == execution_id)
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
    ) -> tuple[list[ExecutionLogSchema] | None, str | None]:
        """Get execution logs from the execution_logs table."""
        # First check if execution exists and user has access
        result = await self.session.execute(
            select(Execution.executed_by).where(Execution.id == execution_id)
        )
        row = result.one_or_none()

        if not row:
            return None, "NotFound"

        if not user.is_superuser and row.executed_by != user.user_id:
            return None, "Forbidden"

        # Query logs from execution_logs table (order by sequence for guaranteed ordering)
        logs_query = (
            select(ExecutionLog)
            .where(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.sequence)
        )

        # Filter debug logs for non-superusers
        if not user.is_superuser:
            logs_query = logs_query.where(ExecutionLog.level.notin_(["DEBUG", "TRACEBACK"]))

        logs_result = await self.session.execute(logs_query)
        log_entries = logs_result.scalars().all()

        # Convert ORM models to Pydantic models
        logs = [
            ExecutionLogSchema(
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
        result = await self.session.execute(
            select(Execution.id, Execution.variables)
            .where(Execution.id == execution_id)
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
        from src.core.pubsub import publish_execution_update

        result = await self.session.execute(
            select(Execution).where(Execution.id == execution_id)
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

        await self.session.flush()
        await self.session.refresh(execution)

        # Publish update
        await publish_execution_update(
            execution_id=execution_id,
            status=ExecutionStatus.CANCELLING.value,
        )

        return self._to_pydantic(execution, user), None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _to_pydantic(
        self, execution: Execution, user: UserPrincipal | None = None
    ) -> WorkflowExecution:
        """Convert SQLAlchemy model to Pydantic model.

        Note: logs are NOT included here - they should be fetched separately
        via the /logs endpoint to avoid loading potentially large log data.

        Args:
            execution: The SQLAlchemy execution model
            user: Optional user for permission checks. If provided, admin-only
                  fields (variables) are gated based on is_superuser.
        """
        is_admin = user.is_superuser if user else False
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
            variables=execution.variables if is_admin else None,
            session_id=str(execution.session_id) if execution.session_id else None,
        )


# =============================================================================
# Standalone Functions (for use by workers/consumers that manage their own sessions)
# =============================================================================


async def create_execution(
    execution_id: str,
    workflow_name: str,
    parameters: dict[str, Any],
    org_id: str | None,
    user_id: str,
    user_name: str,
    form_id: str | None = None,
    api_key_id: str | None = None,
    status: ExecutionStatus = ExecutionStatus.RUNNING,
    is_local_execution: bool = False,
) -> None:
    """
    Create a new execution record in PostgreSQL.

    Standalone function for workers/consumers that manage their own DB sessions.
    """
    from src.core.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = ExecutionRepository(session)
        await repo.create_execution(
            execution_id=execution_id,
            workflow_name=workflow_name,
            parameters=parameters,
            org_id=org_id,
            user_id=user_id,
            user_name=user_name,
            form_id=form_id,
            api_key_id=api_key_id,
            status=status,
            is_local_execution=is_local_execution,
        )
        await session.commit()


async def update_execution(
    execution_id: str,
    status: ExecutionStatus,
    result: Any = None,
    error_message: str | None = None,
    error_type: str | None = None,
    duration_ms: int | None = None,
    logs: list[dict] | None = None,
    variables: dict | None = None,
    metrics: dict | None = None,
) -> None:
    """
    Update an execution record with results.

    Standalone function for workers/consumers that manage their own DB sessions.
    """
    from src.core.database import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = ExecutionRepository(session)
        await repo.update_execution(
            execution_id=execution_id,
            status=status,
            result=result,
            error_message=error_message,
            error_type=error_type,
            duration_ms=duration_ms,
            logs=logs,
            variables=variables,
            metrics=metrics,
        )
        await session.commit()
