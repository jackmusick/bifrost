"""
Execution Logs Repository

PostgreSQL-based repository for execution log entries.
Replaces the Azure Table Storage implementation.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ExecutionLog


class ExecutionLogRepository:
    """
    Repository for execution log entries.

    Logs are stored in the execution_logs table with:
    - execution_id: Foreign key to executions table
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - message: Log message text
    - log_metadata: Optional JSONB metadata/data
    - timestamp: When the log was created
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def append_log(
        self,
        execution_id: UUID,
        level: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> ExecutionLog:
        """
        Append a log entry for an execution.

        Args:
            execution_id: Execution UUID
            level: Log level (INFO, WARNING, ERROR, DEBUG, CRITICAL)
            message: Log message
            metadata: Optional structured metadata
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Created log entry
        """
        log = ExecutionLog(
            execution_id=execution_id,
            level=level.upper(),
            message=message,
            log_metadata=metadata,
            timestamp=timestamp or datetime.utcnow(),
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def append_logs_batch(
        self,
        execution_id: UUID,
        logs: list[dict[str, Any]],
    ) -> list[ExecutionLog]:
        """
        Append multiple log entries in a single batch.

        Args:
            execution_id: Execution UUID
            logs: List of log dicts with keys: level, message, data (optional), timestamp (optional)

        Returns:
            List of created log entries
        """
        log_entries = []
        for log_dict in logs:
            log = ExecutionLog(
                execution_id=execution_id,
                level=log_dict.get("level", "INFO").upper(),
                message=log_dict.get("message", ""),
                log_metadata=log_dict.get("data"),
                timestamp=log_dict.get("timestamp") or datetime.utcnow(),
            )
            self.session.add(log)
            log_entries.append(log)

        await self.session.flush()
        return log_entries

    async def get_logs(
        self,
        execution_id: UUID,
        since_timestamp: datetime | None = None,
        level_filter: list[str] | None = None,
        limit: int = 5000,
    ) -> list[ExecutionLog]:
        """
        Get logs for an execution.

        Args:
            execution_id: Execution UUID
            since_timestamp: Only fetch logs after this timestamp
            level_filter: Only fetch logs with these levels
            limit: Maximum number of logs to return

        Returns:
            List of log entries (sorted by timestamp ascending)
        """
        query = (
            select(ExecutionLog)
            .where(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.timestamp)
            .limit(limit)
        )

        if since_timestamp:
            query = query.where(ExecutionLog.timestamp > since_timestamp)

        if level_filter:
            query = query.where(ExecutionLog.level.in_([lvl.upper() for lvl in level_filter]))

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_logs_as_dicts(
        self,
        execution_id: UUID,
        since_timestamp: datetime | None = None,
        exclude_levels: list[str] | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """
        Get logs as dictionaries (for API responses).

        Args:
            execution_id: Execution UUID
            since_timestamp: Only fetch logs after this timestamp
            exclude_levels: Exclude logs with these levels (e.g., ["DEBUG"])
            limit: Maximum number of logs to return

        Returns:
            List of log dicts with keys: id, timestamp, level, message, data
        """
        query = (
            select(ExecutionLog)
            .where(ExecutionLog.execution_id == execution_id)
            .order_by(ExecutionLog.timestamp)
            .limit(limit)
        )

        if since_timestamp:
            query = query.where(ExecutionLog.timestamp > since_timestamp)

        if exclude_levels:
            query = query.where(ExecutionLog.level.notin_([lvl.upper() for lvl in exclude_levels]))

        result = await self.session.execute(query)
        logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "level": log.level,
                "message": log.message,
                "data": log.log_metadata,
            }
            for log in logs
        ]

    async def count_logs(self, execution_id: UUID) -> int:
        """
        Count total logs for an execution.

        Args:
            execution_id: Execution UUID

        Returns:
            Total number of logs
        """
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(ExecutionLog.id)).where(
                ExecutionLog.execution_id == execution_id
            )
        )
        return result.scalar_one()

    async def delete_logs(self, execution_id: UUID) -> int:
        """
        Delete all logs for an execution.

        Note: This is typically handled by CASCADE delete on the execution.

        Args:
            execution_id: Execution UUID

        Returns:
            Number of logs deleted
        """
        from sqlalchemy import delete
        from sqlalchemy.engine import CursorResult

        result: CursorResult = await self.session.execute(  # type: ignore[assignment]
            delete(ExecutionLog).where(ExecutionLog.execution_id == execution_id)
        )
        await self.session.flush()
        return result.rowcount


def get_execution_logs_repository() -> "ExecutionLogRepository":
    """
    Factory function for backward compatibility.

    Note: In the new architecture, repositories are instantiated with a database
    session. This function exists for compatibility with code that expects
    a no-argument factory.

    New code should use dependency injection with DbSession instead.
    """
    from src.core.database import get_session_factory

    class _CompatExecutionLogRepository:
        """Wrapper that creates session on demand."""

        def __init__(self):
            self._session_factory = get_session_factory()
            self._session = None
            self._repo = None

        async def _ensure_session(self):
            if self._session is None:
                self._session = self._session_factory()
                self._repo = ExecutionLogRepository(self._session)
            return self._repo

        async def append_log(self, execution_id, level, message, metadata=None, timestamp=None, source=None):
            repo = await self._ensure_session()
            exec_uuid = UUID(execution_id) if isinstance(execution_id, str) else execution_id
            # Include source in metadata if provided
            if source and metadata is None:
                metadata = {"source": source}
            elif source and metadata:
                metadata = {**metadata, "source": source}
            return await repo.append_log(exec_uuid, level, message, metadata, timestamp)

        async def get_logs(self, execution_id, since_timestamp=None, level_filter=None, limit=5000):
            repo = await self._ensure_session()
            exec_uuid = UUID(execution_id) if isinstance(execution_id, str) else execution_id
            return await repo.get_logs(exec_uuid, since_timestamp, level_filter, limit)

        async def get_logs_as_dicts(self, execution_id, since_timestamp=None, exclude_levels=None, limit=5000):
            repo = await self._ensure_session()
            exec_uuid = UUID(execution_id) if isinstance(execution_id, str) else execution_id
            return await repo.get_logs_as_dicts(exec_uuid, since_timestamp, exclude_levels, limit)

        async def close(self):
            if self._session:
                await self._session.close()
                self._session = None
                self._repo = None

    return _CompatExecutionLogRepository()
