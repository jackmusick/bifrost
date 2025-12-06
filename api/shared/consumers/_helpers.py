"""
Consumer Helper Functions

Shared utilities for RabbitMQ consumers that need to interact
with the database and other services.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from src.core.database import get_session_factory
from src.models.database import Execution as ExecutionModel
from src.models.enums import ExecutionStatus

logger = logging.getLogger(__name__)


async def get_execution_status(execution_id: str, org_id: str | None) -> str | None:
    """
    Get the current status of an execution.

    Args:
        execution_id: Execution ID
        org_id: Organization ID (for scoping)

    Returns:
        Status string or None if not found
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(ExecutionModel.status).where(ExecutionModel.id == UUID(execution_id))
        )
        status = result.scalar_one_or_none()
        return status


async def create_execution(
    execution_id: str,
    workflow_name: str,
    parameters: dict[str, Any],
    org_id: str | None,
    user_id: str,
    user_name: str,
    form_id: str | None = None,
    status: "ExecutionStatus" = ExecutionStatus.RUNNING,
) -> None:
    """
    Create a new execution record in PostgreSQL.

    Called by worker when it picks up a job from the queue.
    This replaces the previous flow where API created the record.

    Args:
        execution_id: Execution ID (from Redis pending record)
        workflow_name: Name of workflow to execute
        parameters: Workflow input parameters
        org_id: Organization ID (None for GLOBAL scope)
        user_id: User ID who initiated execution
        user_name: Display name of user
        form_id: Optional form ID if triggered by form
        status: Initial status (default RUNNING)
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        # Parse org_id - strip "ORG:" prefix if present
        parsed_org_id = None
        if org_id and org_id != "GLOBAL":
            if org_id.startswith("ORG:"):
                parsed_org_id = UUID(org_id[4:])
            else:
                parsed_org_id = UUID(org_id)

        # Parse user_id - handle API key format
        parsed_user_id: UUID
        if user_id.startswith("api-key:"):
            # For API key executions, we need a valid UUID
            # Use a deterministic UUID based on the key ID
            key_id = user_id.split(":")[1]
            try:
                parsed_user_id = UUID(key_id)
            except ValueError:
                # If key_id isn't a UUID, generate one deterministically
                import hashlib
                hash_bytes = hashlib.md5(key_id.encode()).digest()
                parsed_user_id = UUID(bytes=hash_bytes)
        else:
            parsed_user_id = UUID(user_id)

        # Parse form_id if present
        parsed_form_id = UUID(form_id) if form_id else None

        execution = ExecutionModel(
            id=UUID(execution_id),
            workflow_name=workflow_name,
            status=status,
            parameters=parameters,
            executed_by=parsed_user_id,
            executed_by_name=user_name,
            organization_id=parsed_org_id,
            form_id=parsed_form_id,
            started_at=datetime.utcnow(),
        )

        db.add(execution)
        await db.commit()

        logger.info(f"Created execution record: {execution_id} (status={status.value})")


async def update_execution(
    execution_id: str,
    org_id: str | None,
    user_id: str,
    status: Any,  # ExecutionStatus enum
    result: Any = None,
    error_message: str | None = None,
    error_type: str | None = None,
    duration_ms: int | None = None,
    logs: list[dict] | None = None,
    variables: dict | None = None,
    metrics: dict | None = None,
) -> None:
    """
    Update an execution record.

    Args:
        execution_id: Execution ID
        org_id: Organization ID
        user_id: User who initiated the execution
        status: New status
        result: Execution result
        error_message: Error message if failed
        error_type: Error type if failed
        duration_ms: Execution duration in milliseconds
        logs: Execution logs
        variables: Runtime variables
        metrics: Resource metrics (peak_memory_bytes, cpu_user_seconds, etc.)
    """
    session_factory = get_session_factory()
    async with session_factory() as db:
        # Get status value if it's an enum
        status_value = status.value if hasattr(status, "value") else status

        # Build update values - only include columns that exist in Execution model
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

        # Note: error_type is passed but not stored - Execution model doesn't have this column
        # Error type can be inferred from error_message if needed

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
        await db.execute(
            update(ExecutionModel)
            .where(ExecutionModel.id == UUID(execution_id))
            .values(**update_values)
        )

        # Store logs in ExecutionLog table
        if logs:
            from src.models.database import ExecutionLog

            for log_entry in logs:
                log_record = ExecutionLog(
                    execution_id=UUID(execution_id),
                    timestamp=datetime.fromisoformat(log_entry["timestamp"]) if isinstance(log_entry.get("timestamp"), str) else datetime.utcnow(),
                    level=log_entry.get("level", "info").upper(),
                    message=log_entry.get("message", ""),
                    log_metadata=log_entry.get("data"),
                )
                db.add(log_record)

        await db.commit()

        logger.debug(f"Updated execution {execution_id} to status {status_value}")
