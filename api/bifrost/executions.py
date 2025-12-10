"""
Execution history SDK for Bifrost.

Provides Python API for execution history operations (list, get).

All methods are async and must be awaited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.core.database import get_session_factory
from src.models import Execution

from ._internal import get_context


def _execution_to_dict(execution: Execution, include_logs: bool = False) -> dict[str, Any]:
    """Convert ORM Execution to dictionary."""
    # Map status enum to string value
    status_value = execution.status.value if hasattr(execution.status, 'value') else str(execution.status)

    result: dict[str, Any] = {
        "id": str(execution.id),
        "workflow_name": execution.workflow_name,
        "workflow_version": execution.workflow_version,
        "status": status_value,
        "executed_by": str(execution.executed_by),
        "executed_by_name": execution.executed_by_name,
        "parameters": execution.parameters,
        "result": execution.result,
        "error_message": execution.error_message,
        "created_at": execution.created_at.isoformat() if execution.created_at else None,
        "started_at": execution.started_at.isoformat() if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "duration_ms": execution.duration_ms,
    }

    if include_logs and hasattr(execution, 'logs'):
        result["logs"] = [
            {
                "level": log.level,
                "message": log.message,
                "metadata": log.log_metadata,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in sorted(execution.logs, key=lambda x: x.timestamp or x.id)
        ]

    return result


class executions:
    """
    Execution history operations.

    Allows workflows to query execution history.
    Queries Postgres directly via PgBouncer (not cached).

    All methods are async - await is required.
    """

    @staticmethod
    async def list(
        workflow_name: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50
    ) -> list[dict[str, Any]]:
        """
        List workflow executions with filtering.

        Platform admins see all executions in their scope.
        Regular users see only their own executions.

        Args:
            workflow_name: Filter by workflow name (optional)
            status: Filter by status (optional)
            start_date: Filter by start date in ISO format (optional)
            end_date: Filter by end date in ISO format (optional)
            limit: Maximum number of results (default: 50, max: 1000)

        Returns:
            list[dict]: List of execution dictionaries

        Raises:
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import executions
            >>> recent = await executions.list(limit=10)
            >>> failed = await executions.list(status="Failed")
            >>> workflow_execs = await executions.list(workflow_name="create_customer")
        """
        context = get_context()

        org_uuid = None
        if context.org_id and context.org_id != "GLOBAL":
            try:
                org_uuid = UUID(context.org_id)
            except ValueError:
                pass

        # Cap limit
        limit = min(limit, 1000)

        session_factory = get_session_factory()
        async with session_factory() as db:
            query = (
                select(Execution)
                .order_by(Execution.created_at.desc())
                .limit(limit)
            )

            # Organization filter
            if org_uuid:
                query = query.where(Execution.organization_id == org_uuid)
            else:
                query = query.where(Execution.organization_id.is_(None))

            # User filter for non-admins
            if not context.is_platform_admin:
                user_uuid = UUID(context.user_id)
                query = query.where(Execution.executed_by == user_uuid)

            # Optional filters
            if workflow_name:
                query = query.where(Execution.workflow_name == workflow_name)

            if status:
                query = query.where(Execution.status == status)

            if start_date:
                query = query.where(Execution.created_at >= start_date)

            if end_date:
                query = query.where(Execution.created_at <= end_date)

            result = await db.execute(query)
            return [_execution_to_dict(e) for e in result.scalars().all()]

    @staticmethod
    async def get(execution_id: str) -> dict[str, Any]:
        """
        Get execution details by ID.

        Platform admins can view any execution in their scope.
        Regular users can only view their own executions.

        Args:
            execution_id: Execution ID (UUID)

        Returns:
            dict: Execution details including logs

        Raises:
            ValueError: If execution not found or access denied
            RuntimeError: If no execution context

        Example:
            >>> from bifrost import executions
            >>> exec_details = await executions.get("exec-123")
            >>> print(exec_details["status"])
            >>> print(exec_details["result"])
        """
        context = get_context()
        exec_uuid = UUID(execution_id)

        org_uuid = None
        if context.org_id and context.org_id != "GLOBAL":
            try:
                org_uuid = UUID(context.org_id)
            except ValueError:
                pass

        session_factory = get_session_factory()
        async with session_factory() as db:
            query = (
                select(Execution)
                .options(joinedload(Execution.logs))
                .where(Execution.id == exec_uuid)
            )
            result = await db.execute(query)
            execution = result.scalars().unique().first()

            if not execution:
                raise ValueError(f"Execution not found: {execution_id}")

            # Check org access
            if org_uuid and execution.organization_id != org_uuid:
                raise PermissionError(f"Access denied to execution: {execution_id}")

            # Check user access for non-admins
            if not context.is_platform_admin:
                user_uuid = UUID(context.user_id)
                if execution.executed_by != user_uuid:
                    raise PermissionError(f"Access denied to execution: {execution_id}")

            return _execution_to_dict(execution, include_logs=True)
