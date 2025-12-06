"""
Metrics Helper Functions

Functions for updating execution metrics on completion.
Called by the workflow execution consumer.
"""

import logging
from datetime import datetime, date
from uuid import UUID

from sqlalchemy import select, update, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session_factory
from src.models.orm import ExecutionMetricsDaily
from src.models.enums import ExecutionStatus

logger = logging.getLogger(__name__)


async def update_daily_metrics(
    org_id: str | None,
    status: str,
    duration_ms: int | None = None,
    peak_memory_bytes: int | None = None,
    cpu_total_seconds: float | None = None,
    db: AsyncSession | None = None,
) -> None:
    """
    Update daily execution metrics.

    Called on each execution completion to update the daily aggregates.
    Uses upsert to create row if not exists, then increment counters.

    Args:
        org_id: Organization ID (None for global/platform executions)
        status: Final execution status
        duration_ms: Execution duration in milliseconds
        peak_memory_bytes: Peak memory usage
        cpu_total_seconds: Total CPU time
    """
    today = date.today()
    org_uuid = (
        UUID(org_id.replace("ORG:", ""))
        if org_id and org_id.startswith("ORG:")
        else None
    )

    try:
        # Use provided session if given; otherwise open a new one
        if db is None:
            session_factory = get_session_factory()
            async with session_factory() as session:
                await _upsert_daily_metrics(
                    session,
                    today,
                    org_uuid,
                    status,
                    duration_ms,
                    peak_memory_bytes,
                    cpu_total_seconds,
                )

                await _upsert_daily_metrics(
                    session,
                    today,
                    None,
                    status,
                    duration_ms,
                    peak_memory_bytes,
                    cpu_total_seconds,
                )

                await session.commit()
        else:
            await _upsert_daily_metrics(
                db,
                today,
                org_uuid,
                status,
                duration_ms,
                peak_memory_bytes,
                cpu_total_seconds,
            )

            await _upsert_daily_metrics(
                db,
                today,
                None,
                status,
                duration_ms,
                peak_memory_bytes,
                cpu_total_seconds,
            )

            await db.commit()

    except Exception as e:
        logger.error(f"Error updating daily metrics: {e}", exc_info=True)
        # Don't raise - metrics update failure shouldn't fail the execution


async def _upsert_daily_metrics(
    db,
    today: date,
    org_id: UUID | None,
    status: str,
    duration_ms: int | None,
    peak_memory_bytes: int | None,
    cpu_total_seconds: float | None,
) -> None:
    """
    Upsert a single daily metrics row.

    Uses PostgreSQL INSERT ... ON CONFLICT to atomically update.
    """
    # Determine which counter to increment based on status
    is_success = status == ExecutionStatus.SUCCESS.value
    is_failed = status == ExecutionStatus.FAILED.value
    is_timeout = status == ExecutionStatus.TIMEOUT.value
    is_cancelled = status == ExecutionStatus.CANCELLED.value

    # Build base values for insert
    insert_values = {
        "date": today,
        "organization_id": org_id,
        "execution_count": 1,
        "success_count": 1 if is_success else 0,
        "failed_count": 1 if is_failed else 0,
        "timeout_count": 1 if is_timeout else 0,
        "cancelled_count": 1 if is_cancelled else 0,
        "total_duration_ms": duration_ms or 0,
        "avg_duration_ms": duration_ms or 0,
        "max_duration_ms": duration_ms or 0,
        "total_memory_bytes": peak_memory_bytes or 0,
        "peak_memory_bytes": peak_memory_bytes or 0,
        "total_cpu_seconds": cpu_total_seconds or 0.0,
        "peak_cpu_seconds": cpu_total_seconds or 0.0,
    }

    # PostgreSQL upsert
    stmt = insert(ExecutionMetricsDaily).values(**insert_values)

    # On conflict, increment counters
    # Use different conflict target based on whether this is org-specific or global:
    # - org_id is not None: use named constraint "uq_metrics_daily_date_org"
    # - org_id is None (global): use index_elements with index_where for partial unique index
    #   (PostgreSQL's ON CONFLICT ON CONSTRAINT only works with constraints, not indexes)
    if org_id is not None:
        stmt = stmt.on_conflict_do_update(
            constraint="uq_metrics_daily_date_org",
            set_={
                "execution_count": ExecutionMetricsDaily.execution_count + 1,
                "success_count": ExecutionMetricsDaily.success_count
                + (1 if is_success else 0),
                "failed_count": ExecutionMetricsDaily.failed_count
                + (1 if is_failed else 0),
                "timeout_count": ExecutionMetricsDaily.timeout_count
                + (1 if is_timeout else 0),
                "cancelled_count": ExecutionMetricsDaily.cancelled_count
                + (1 if is_cancelled else 0),
                "total_duration_ms": ExecutionMetricsDaily.total_duration_ms
                + (duration_ms or 0),
                "max_duration_ms": func.greatest(
                    ExecutionMetricsDaily.max_duration_ms, duration_ms or 0
                ),
                "total_memory_bytes": ExecutionMetricsDaily.total_memory_bytes
                + (peak_memory_bytes or 0),
                "peak_memory_bytes": func.greatest(
                    ExecutionMetricsDaily.peak_memory_bytes, peak_memory_bytes or 0
                ),
                "total_cpu_seconds": ExecutionMetricsDaily.total_cpu_seconds
                + (cpu_total_seconds or 0.0),
                "peak_cpu_seconds": func.greatest(
                    ExecutionMetricsDaily.peak_cpu_seconds, cpu_total_seconds or 0.0
                ),
                "updated_at": datetime.utcnow(),
            },
        )
    else:
        # For global metrics (org_id IS NULL), use index_elements with index_where
        # to match the partial unique index
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            index_where=text("organization_id IS NULL"),
            set_={
                "execution_count": ExecutionMetricsDaily.execution_count + 1,
                "success_count": ExecutionMetricsDaily.success_count
                + (1 if is_success else 0),
                "failed_count": ExecutionMetricsDaily.failed_count
                + (1 if is_failed else 0),
                "timeout_count": ExecutionMetricsDaily.timeout_count
                + (1 if is_timeout else 0),
                "cancelled_count": ExecutionMetricsDaily.cancelled_count
                + (1 if is_cancelled else 0),
                "total_duration_ms": ExecutionMetricsDaily.total_duration_ms
                + (duration_ms or 0),
                "max_duration_ms": func.greatest(
                    ExecutionMetricsDaily.max_duration_ms, duration_ms or 0
                ),
                "total_memory_bytes": ExecutionMetricsDaily.total_memory_bytes
                + (peak_memory_bytes or 0),
                "peak_memory_bytes": func.greatest(
                    ExecutionMetricsDaily.peak_memory_bytes, peak_memory_bytes or 0
                ),
                "total_cpu_seconds": ExecutionMetricsDaily.total_cpu_seconds
                + (cpu_total_seconds or 0.0),
                "peak_cpu_seconds": func.greatest(
                    ExecutionMetricsDaily.peak_cpu_seconds, cpu_total_seconds or 0.0
                ),
                "updated_at": datetime.utcnow(),
            },
        )

    await db.execute(stmt)

    # Recalculate average duration
    # (We do this separately to get the new count)
    # Build org filter correctly for NULL handling
    if org_id is not None:
        org_filter = ExecutionMetricsDaily.organization_id == org_id
    else:
        org_filter = ExecutionMetricsDaily.organization_id.is_(None)

    result = await db.execute(
        select(
            ExecutionMetricsDaily.execution_count,
            ExecutionMetricsDaily.total_duration_ms,
        )
        .where(ExecutionMetricsDaily.date == today)
        .where(org_filter)
    )
    row = result.one_or_none()
    if row and row.execution_count > 0:
        avg_duration = row.total_duration_ms // row.execution_count
        await db.execute(
            update(ExecutionMetricsDaily)
            .where(ExecutionMetricsDaily.date == today)
            .where(org_filter)
            .values(avg_duration_ms=avg_duration)
        )
