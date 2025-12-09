"""
Logs Router

System logging endpoints.
Stub implementation - proper logging to PostgreSQL coming later.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status

from src.models.models import SystemLog, SystemLogsListResponse
from src.core.auth import Context, CurrentSuperuser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["Logs"])


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SystemLogsListResponse,
    summary="List system logs",
    description="List system logs (stub - returns empty for now)",
)
async def list_logs(
    ctx: Context,
    user: CurrentSuperuser,
    category: str | None = Query(None, description="Log category filter"),
    start_date: str | None = Query(None, description="Start date filter"),
    end_date: str | None = Query(None, description="End date filter"),
    limit: int = Query(100, le=1000, description="Result limit"),
    offset: int = Query(0, ge=0, description="Result offset"),
) -> SystemLogsListResponse:
    """
    List system logs.

    Stub implementation - returns empty list.
    Proper logging to PostgreSQL will be implemented later.

    Args:
        category: Optional log category filter
        start_date: Optional start date filter (ISO 8601)
        end_date: Optional end date filter (ISO 8601)
        limit: Maximum results to return
        offset: Result offset for pagination

    Returns:
        List of system logs
    """
    # Stub implementation - return empty logs
    logger.debug("Logs list requested (stub implementation)")
    return SystemLogsListResponse(
        logs=[],
        continuation_token=None,
    )


@router.get(
    "/{category}/{row_key}",
    response_model=SystemLog,
    summary="Get single log",
    description="Get a single system log entry (stub - returns 404)",
)
async def get_log(
    category: str,
    row_key: str,
    ctx: Context,
    user: CurrentSuperuser,
) -> SystemLog:
    """
    Get a single system log entry.

    Stub implementation - always returns 404.
    Proper logging to PostgreSQL will be implemented later.

    Args:
        category: Log category
        row_key: Log entry row key

    Returns:
        System log entry
    """
    logger.debug(f"Log requested: {category}/{row_key} (stub implementation)")
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Log entry not found: {category}/{row_key}",
    )
