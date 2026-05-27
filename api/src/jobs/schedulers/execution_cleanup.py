"""
Execution Cleanup Scheduler

Cleans up stuck executions that remain in PENDING, RUNNING, or CANCELLING
status for too long.

Runs every 5 minutes to find and timeout stuck executions.
"""

import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_

from src.core.database import get_session_factory
from src.core.pubsub import publish_execution_update, publish_history_update
from src.core.redis_client import get_redis_client
from src.models import Execution as ExecutionModel, ExecutionLog
from src.models.orm.workflows import Workflow

logger = logging.getLogger(__name__)

# Timeout thresholds
PENDING_TIMEOUT_MINUTES = 10  # If PENDING for 10+ minutes, it's stuck in queue
RUNNING_TIMEOUT_MINUTES = 30  # If RUNNING for 30+ minutes, worker likely crashed
CANCELLING_TIMEOUT_MINUTES = 3  # If CANCELLING for 3+ minutes, worker failed to cancel
RESTART_ORPHAN_GRACE_SECONDS = 120


async def _load_worker_heartbeat_state(now: datetime) -> dict[str, Any]:
    """Read Redis worker heartbeats for restart-orphan detection."""
    state: dict[str, Any] = {
        "active_execution_ids": set(),
        "oldest_worker_started_at": None,
        "heartbeat_count": 0,
    }
    redis_client = get_redis_client()
    if not redis_client:
        return state

    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="bifrost:pool:*:heartbeat", count=100)
        for key in keys:
            raw = await redis_client.get(key)
            if not raw:
                continue
            try:
                heartbeat = json.loads(raw)
            except json.JSONDecodeError:
                continue
            state["heartbeat_count"] += 1
            started_at = _parse_heartbeat_time(heartbeat.get("started_at"))
            if started_at is not None:
                oldest = state["oldest_worker_started_at"]
                state["oldest_worker_started_at"] = started_at if oldest is None else min(oldest, started_at)
            for process in heartbeat.get("processes") or []:
                execution = process.get("execution") if isinstance(process, dict) else None
                execution_id = execution.get("execution_id") if isinstance(execution, dict) else None
                if execution_id:
                    state["active_execution_ids"].add(str(execution_id))
        if cursor == 0:
            break

    return state


def _parse_heartbeat_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_restart_orphan(
    execution: ExecutionModel,
    *,
    now: datetime,
    heartbeat_state: dict[str, Any],
) -> bool:
    if not execution.started_at:
        return False
    if heartbeat_state.get("heartbeat_count", 0) <= 0:
        return False
    if str(execution.id) in heartbeat_state.get("active_execution_ids", set()):
        return False

    oldest_worker_started_at = heartbeat_state.get("oldest_worker_started_at")
    if oldest_worker_started_at is None:
        return False

    started_at = execution.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    if started_at >= oldest_worker_started_at:
        return False
    return (now - oldest_worker_started_at).total_seconds() >= RESTART_ORPHAN_GRACE_SECONDS


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
        heartbeat_state = await _load_worker_heartbeat_state(now)

        # Collect data for WebSocket broadcasts (published after session closes)
        pubsub_updates: list[dict] = []

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
                if _is_restart_orphan(execution, now=now, heartbeat_state=heartbeat_state):
                    running_stuck.append(execution)
                    continue
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
                        if _is_restart_orphan(execution, now=now, heartbeat_state=heartbeat_state):
                            timeout_reason = (
                                f"Stuck in RUNNING status for {elapsed_min}+ minutes. "
                                "Execution predates all current worker heartbeats and is not claimed by any live worker."
                            )
                        else:
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

                    # Log orphan execution being swept (before status update, to capture original status)
                    stuck_for_seconds = int((now - execution.started_at).total_seconds()) if execution.started_at else 0
                    logger.warning(
                        "orphan_execution_swept",
                        extra={
                            "execution_id": str(execution.id),
                            "stuck_status": execution.status,
                            "stuck_for_seconds": stuck_for_seconds,
                        },
                    )

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

                    # Collect data for pubsub (published after session closes)
                    pubsub_updates.append({
                        "execution_id": str(execution.id),
                        "final_status": final_status.value,
                        "timeout_reason": timeout_reason,
                        "executed_by": execution.executed_by,
                        "executed_by_name": execution.executed_by_name,
                        "workflow_name": execution.workflow_name,
                        "org_id": execution.organization_id,
                        "started_at": execution.started_at,
                    })

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

        # Publish WebSocket updates AFTER session is closed (no DB connection held)
        for update in pubsub_updates:
            try:
                await publish_execution_update(
                    update["execution_id"],
                    update["final_status"],
                    {"error": update["timeout_reason"]},
                )
                await publish_history_update(
                    execution_id=update["execution_id"],
                    status=update["final_status"],
                    executed_by=update["executed_by"],
                    executed_by_name=update["executed_by_name"],
                    workflow_name=update["workflow_name"],
                    org_id=update["org_id"],
                    started_at=update["started_at"],
                    completed_at=now,
                )
            except Exception as e:
                logger.warning(f"Failed to publish update for {update['execution_id']}: {e}")

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
