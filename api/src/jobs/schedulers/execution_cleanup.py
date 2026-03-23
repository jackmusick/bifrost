"""
Execution Cleanup Scheduler

Cleans up stuck executions that remain in PENDING, RUNNING, or CANCELLING
status for too long.

Runs every 5 minutes to find and timeout stuck executions.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_

from src.core.database import get_session_factory
from src.core.pubsub import publish_execution_update, publish_history_update
from src.models import Execution as ExecutionModel, ExecutionLog
from src.models.orm.workflows import Workflow

logger = logging.getLogger(__name__)

# Timeout thresholds
PENDING_TIMEOUT_MINUTES = 10  # If PENDING for 10+ minutes, it's stuck in queue
RUNNING_TIMEOUT_MINUTES = 30  # If RUNNING for 30+ minutes, worker likely crashed
CANCELLING_TIMEOUT_MINUTES = 3  # If CANCELLING for 3+ minutes, worker failed to cancel


async def cleanup_stuck_executions() -> dict[str, Any]:
    """
    Clean up stuck executions.

    Finds executions that have been stuck in PENDING, RUNNING, or CANCELLING
    status for longer than the timeout threshold and marks them as TIMEOUT/CANCELLED.

    Returns:
        Summary of cleanup results
    """
    logger.info("Starting execution cleanup")

    from src.models.enums import ExecutionStatus

    results = {
        "pending_timeouts": 0,
        "running_timeouts": 0,
        "cancelling_timeouts": 0,
        "total_cleaned": 0,
        "errors": [],
    }

    now = datetime.now(timezone.utc)

    try:
        session_factory = get_session_factory()
        async with session_factory() as db:
            # Find stuck PENDING executions
            pending_cutoff = now - timedelta(minutes=PENDING_TIMEOUT_MINUTES)
            pending_result = await db.execute(
                select(ExecutionModel).where(
                    and_(
                        ExecutionModel.status == ExecutionStatus.PENDING.value,
                        ExecutionModel.started_at < pending_cutoff,
                    )
                )
            )
            pending_stuck = list(pending_result.scalars().all())

            # Find stuck RUNNING executions — respect per-workflow timeout
            # Join with Workflow to get configured timeout_seconds.
            # Use workflow timeout + 5 min grace (process pool should kill first).
            # Fallback to RUNNING_TIMEOUT_MINUTES if no workflow found.
            running_result = await db.execute(
                select(ExecutionModel, Workflow.timeout_seconds).where(
                    and_(
                        ExecutionModel.status == ExecutionStatus.RUNNING.value,
                    )
                ).outerjoin(Workflow, ExecutionModel.workflow_id == Workflow.id)
            )
            running_stuck = []
            for execution, wf_timeout in running_result.all():
                # timeout_seconds == 0 means no timeout — skip entirely
                if wf_timeout is not None and wf_timeout == 0:
                    continue
                # Use per-workflow timeout + 5 min grace, or fallback
                effective_timeout_s = (wf_timeout + 300) if wf_timeout else (RUNNING_TIMEOUT_MINUTES * 60)
                elapsed = (now - execution.started_at).total_seconds()
                if elapsed > effective_timeout_s:
                    running_stuck.append(execution)

            # Find stuck CANCELLING executions
            cancelling_cutoff = now - timedelta(minutes=CANCELLING_TIMEOUT_MINUTES)
            cancelling_result = await db.execute(
                select(ExecutionModel).where(
                    and_(
                        ExecutionModel.status == ExecutionStatus.CANCELLING.value,
                        ExecutionModel.started_at < cancelling_cutoff,
                    )
                )
            )
            cancelling_stuck = list(cancelling_result.scalars().all())

            all_stuck = pending_stuck + running_stuck + cancelling_stuck
            logger.info(f"Found {len(all_stuck)} stuck executions to clean up")

            for execution in all_stuck:
                try:
                    # Determine timeout reason and final status
                    if execution.status == ExecutionStatus.PENDING.value:
                        timeout_reason = (
                            f"Stuck in PENDING status for {PENDING_TIMEOUT_MINUTES}+ minutes. "
                            "Likely queue processing issue or worker not running."
                        )
                        final_status = ExecutionStatus.TIMEOUT
                        results["pending_timeouts"] += 1

                    elif execution.status == ExecutionStatus.RUNNING.value:
                        elapsed_min = int((now - execution.started_at).total_seconds() / 60) if execution.started_at else RUNNING_TIMEOUT_MINUTES
                        timeout_reason = (
                            f"Stuck in RUNNING status for {elapsed_min}+ minutes. "
                            "Likely worker crash or workflow hang."
                        )
                        final_status = ExecutionStatus.TIMEOUT
                        results["running_timeouts"] += 1

                    elif execution.status == ExecutionStatus.CANCELLING.value:
                        timeout_reason = (
                            f"Stuck in CANCELLING status for {CANCELLING_TIMEOUT_MINUTES}+ minutes. "
                            "Worker likely crashed during cancellation."
                        )
                        final_status = ExecutionStatus.CANCELLED
                        results["cancelling_timeouts"] += 1

                    else:
                        continue

                    logger.warning(
                        f"Timing out stuck execution: {execution.id}",
                        extra={
                            "execution_id": str(execution.id),
                            "workflow_name": execution.workflow_name,
                            "status": execution.status,
                            "timeout_reason": timeout_reason,
                        },
                    )

                    # Update execution
                    execution.status = final_status.value  # type: ignore[assignment]
                    execution.error_message = timeout_reason
                    execution.completed_at = now

                    # Add timeout log entry
                    log_entry = ExecutionLog(
                        execution_id=execution.id,
                        level="error",
                        message=timeout_reason,
                        log_metadata={
                            "timeout_type": "automatic_cleanup",
                            "original_status": execution.status,
                        },
                        timestamp=now,
                    )
                    db.add(log_entry)

                    results["total_cleaned"] += 1

                    # Publish update via WebSocket
                    await publish_execution_update(
                        str(execution.id),
                        final_status.value,
                        {"error": timeout_reason},
                    )
                    await publish_history_update(
                        execution_id=str(execution.id),
                        status=final_status.value,
                        executed_by=execution.executed_by,
                        executed_by_name=execution.executed_by_name,
                        workflow_name=execution.workflow_name,
                        org_id=execution.organization_id,
                        started_at=execution.started_at,
                        completed_at=now,
                    )

                except Exception as e:
                    logger.error(
                        f"Error processing execution cleanup for {execution.id}",
                        extra={"error": str(e)},
                        exc_info=True,
                    )
                    results["errors"].append({
                        "execution_id": str(execution.id),
                        "error": str(e),
                    })

            # Commit all changes
            await db.commit()

        logger.info(
            "Execution cleanup completed",
            extra={
                "pending_timeouts": results["pending_timeouts"],
                "running_timeouts": results["running_timeouts"],
                "cancelling_timeouts": results["cancelling_timeouts"],
                "total_cleaned": results["total_cleaned"],
            },
        )

    except Exception as e:
        logger.error("Error in execution cleanup", extra={"error": str(e)}, exc_info=True)
        results["errors"].append({"error": str(e)})

    return results
