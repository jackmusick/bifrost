"""
Schedules Router

Lists scheduled workflows from the database.

Note: Schedules are read from the workflows database table (schedule column)
which is populated by the discovery watcher. This avoids expensive file system
scans on every request.

Manual triggering of scheduled workflows should use POST /api/workflows/execute.
Automatic scheduled execution is handled by the cron_scheduler job via RabbitMQ.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from src.models import ScheduleInfo, SchedulesListResponse
from src.models import Workflow as WorkflowORM
from src.core.auth import Context, CurrentSuperuser
from src.core.database import DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules", tags=["Schedules"])


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SchedulesListResponse,
    summary="List scheduled workflows",
    description="List all scheduled workflows (Platform admin only)",
)
async def list_schedules(
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> SchedulesListResponse:
    """
    List all scheduled workflows.

    Returns a list of workflows that have cron schedules configured.
    Queries the database for workflows with non-null schedule column.
    """
    try:
        # Try to import cron_parser, but don't fail if croniter isn't installed
        try:
            from src.services.cron_parser import cron_to_human_readable
            get_human_readable = cron_to_human_readable
        except ImportError:
            get_human_readable = lambda x: x  # noqa: E731

        # Query workflows with schedules from database (fast O(1) lookup)
        query = (
            select(WorkflowORM)
            .where(WorkflowORM.is_active.is_(True))
            .where(WorkflowORM.schedule.isnot(None))
            .order_by(WorkflowORM.name)
        )
        result = await db.execute(query)
        workflows = result.scalars().all()

        schedules = []
        for workflow in workflows:
            # Schedule is guaranteed non-null by the query filter
            cron_expr = workflow.schedule
            if not cron_expr:  # Should never happen due to query filter, but satisfies type checker
                continue
            human_readable = get_human_readable(cron_expr) or cron_expr
            schedule = ScheduleInfo(
                workflow_name=workflow.name,
                workflow_description=workflow.description or workflow.name,
                cron_expression=cron_expr,
                human_readable=human_readable,
                next_run_at=None,
                last_run_at=None,
                last_execution_id=None,
                execution_count=0,
                enabled=True,
                validation_status=None,
                validation_message=None,
                is_overdue=False,
            )
            schedules.append(schedule)

        logger.info(f"Listed {len(schedules)} scheduled workflows from database")
        return SchedulesListResponse(schedules=schedules, total_count=len(schedules))

    except Exception as e:
        logger.error(f"Error listing schedules: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list schedules",
        )
