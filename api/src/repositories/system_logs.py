"""
System Logs Repository

PostgreSQL-based repository for system log entries (platform events, audits).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import SystemLog


class SystemLogRepository:
    """
    Repository for system log entries.

    Logs are stored in the system_logs table with:
    - id: UUID primary key
    - category: Event category (discovery, organization, user, role, config, secret, form, oauth, execution, system, error)
    - level: Event severity (info, warning, error, critical)
    - message: Human-readable event description
    - executed_by: User ID (nullable FK to users)
    - executed_by_name: Display name or "System"
    - details: JSONB metadata
    - timestamp: When the event occurred (indexed)
    """

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def create_log(
        self,
        category: str,
        level: str,
        message: str,
        executed_by: UUID | None = None,
        executed_by_name: str = "System",
        details: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> SystemLog:
        """
        Create a system log entry.

        Args:
            category: Event category (discovery, organization, user, etc.)
            level: Severity level (info, warning, error, critical)
            message: Human-readable event description
            executed_by: User UUID (None for system events)
            executed_by_name: Display name (defaults to "System")
            details: Optional event-specific data as JSONB
            timestamp: Optional timestamp (defaults to now)

        Returns:
            Created log entry
        """
        log = SystemLog(
            category=category,
            level=level.lower(),
            message=message,
            executed_by=executed_by,
            executed_by_name=executed_by_name,
            details=details,
            timestamp=timestamp or datetime.utcnow(),
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def get_log(self, log_id: UUID) -> SystemLog | None:
        """
        Get a single system log entry by ID.

        Args:
            log_id: Log UUID

        Returns:
            Log entry or None if not found
        """
        result = await self.session.execute(
            select(SystemLog).where(SystemLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def list_logs(
        self,
        category: str | None = None,
        level: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        executed_by: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SystemLog], int]:
        """
        List system logs with filtering and pagination.

        Args:
            category: Optional filter by category
            level: Optional filter by level
            start_date: Optional filter by start date (inclusive)
            end_date: Optional filter by end date (inclusive)
            executed_by: Optional filter by user
            limit: Maximum number of results (default 50, max 1000)
            offset: Offset for pagination

        Returns:
            Tuple of (logs list, total count)
        """
        # Cap limit at 1000
        limit = min(limit, 1000)

        # Build query
        query = select(SystemLog)

        # Apply filters
        if category:
            query = query.where(SystemLog.category == category)
        if level:
            query = query.where(SystemLog.level == level.lower())
        if start_date:
            query = query.where(SystemLog.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLog.timestamp <= end_date)
        if executed_by:
            query = query.where(SystemLog.executed_by == executed_by)

        # Get total count (before pagination)
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Apply ordering and pagination
        query = query.order_by(SystemLog.timestamp.desc()).limit(limit).offset(offset)

        # Execute query
        result = await self.session.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def count_logs(
        self,
        category: str | None = None,
        level: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        """
        Count system logs with optional filters.

        Args:
            category: Optional filter by category
            level: Optional filter by level
            start_date: Optional filter by start date (inclusive)
            end_date: Optional filter by end date (inclusive)

        Returns:
            Total number of matching logs
        """
        query = select(func.count(SystemLog.id))

        # Apply filters
        if category:
            query = query.where(SystemLog.category == category)
        if level:
            query = query.where(SystemLog.level == level.lower())
        if start_date:
            query = query.where(SystemLog.timestamp >= start_date)
        if end_date:
            query = query.where(SystemLog.timestamp <= end_date)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def delete_old_logs(self, before_date: datetime) -> int:
        """
        Delete logs older than specified date (for log rotation/cleanup).

        Args:
            before_date: Delete logs before this date

        Returns:
            Number of logs deleted
        """
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(SystemLog).where(SystemLog.timestamp < before_date)
        )
        await self.session.flush()
        return result.rowcount
