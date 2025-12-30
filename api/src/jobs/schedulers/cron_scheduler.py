"""
CRON Scheduler

Processes scheduled workflows based on their CRON expressions.
Replaces the Azure Timer trigger version with APScheduler cron job.

Runs every 5 minutes to check for workflows that need to be executed.
"""

import logging
from datetime import datetime
from typing import Any

from croniter import croniter

from src.core.database import get_db_context
from src.repositories.workflows import WorkflowRepository
from src.services.execution.async_executor import enqueue_system_workflow_execution

logger = logging.getLogger(__name__)


async def process_scheduled_workflows() -> dict[str, Any]:
    """
    Process all scheduled workflows.

    Checks each workflow with a schedule parameter and enqueues
    execution if the next run time has passed.

    Returns:
        Summary of processing results
    """
    logger.info("Schedule processor started")

    results = {
        "total_schedules": 0,
        "executed": 0,
        "updated": 0,
        "errors": [],
    }

    try:
        from src.services.cron_parser import calculate_next_run, is_cron_expression_valid

        # Query scheduled workflows from database (replaces scan_all_workflows)
        async with get_db_context() as db:
            workflow_repo = WorkflowRepository(db)
            scheduled_workflows = await workflow_repo.get_scheduled()

        results["total_schedules"] = len(scheduled_workflows)
        logger.info(f"Found {len(scheduled_workflows)} scheduled workflows")

        now = datetime.utcnow()

        for workflow in scheduled_workflows:
            try:
                workflow_name = workflow.name
                cron_expression = workflow.schedule

                # Validate CRON expression
                if not cron_expression or not is_cron_expression_valid(cron_expression):
                    logger.warning(
                        f"Invalid CRON expression for workflow {workflow_name}: {cron_expression}"
                    )
                    results["errors"].append({
                        "workflow_name": workflow_name,
                        "error": f"Invalid CRON expression: {cron_expression}",
                    })
                    continue

                # Check if schedule interval is too frequent
                try:
                    cron = croniter(cron_expression, now)
                    first_run = cron.get_next(datetime)
                    second_run = cron.get_next(datetime)
                    interval_seconds = (second_run - first_run).total_seconds()

                    if interval_seconds < 300:  # Less than 5 minutes
                        logger.warning(
                            f"Schedule interval for {workflow_name} is {interval_seconds}s (< 5 minutes)"
                        )
                except Exception as e:
                    logger.error(f"Failed to validate schedule interval for {workflow_name}: {e}")

                # Get or create schedule state from database
                # For now, use a simple in-memory check based on CRON
                # In production, this would query the Config table for schedule state
                next_run = calculate_next_run(cron_expression, now)

                # Check if it's time to execute (within the 5-minute window)
                if next_run <= now:
                    logger.info(f"Executing scheduled workflow: {workflow_name}")

                    # Use the centralized system execution helper
                    execution_id = await enqueue_system_workflow_execution(
                        workflow_id=str(workflow.id),
                        parameters={},
                        source="Scheduled Execution",
                        org_id=str(workflow.organization_id) if workflow.organization_id else None,
                    )

                    logger.info(
                        "Enqueued scheduled workflow execution",
                        extra={
                            "workflow_name": workflow_name,
                            "execution_id": execution_id,
                        },
                    )

                    results["executed"] += 1

            except Exception as workflow_error:
                error_info = {
                    "workflow_name": workflow.name,
                    "error": str(workflow_error),
                }
                results["errors"].append(error_info)
                logger.error(
                    "Error processing scheduled workflow",
                    extra=error_info,
                    exc_info=True,
                )

        logger.info(
            f"Schedule processor completed: "
            f"Total={results['total_schedules']}, "
            f"Executed={results['executed']}, "
            f"Errors={len(results['errors'])}"
        )

    except Exception as e:
        logger.error(f"Schedule processor failed: {str(e)}", exc_info=True)
        results["errors"].append({"error": str(e)})

    return results
