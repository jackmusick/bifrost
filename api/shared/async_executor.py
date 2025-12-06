"""
Async Workflow Execution
Handles queueing of workflows via Redis + RabbitMQ

Flow:
1. API stores pending execution in Redis
2. API publishes message to RabbitMQ
3. API returns execution_id immediately (<100ms)
4. Worker reads from Redis, writes to PostgreSQL, executes

For sync execution (sync=True):
- Caller provides execution_id (already stored in Redis)
- Worker pushes result to Redis
- Caller waits on Redis BLPOP
"""

import logging
import uuid
from typing import Any

from shared.context import ExecutionContext

logger = logging.getLogger(__name__)

QUEUE_NAME = "workflow-executions"


async def enqueue_workflow_execution(
    context: ExecutionContext,
    workflow_name: str,
    parameters: dict[str, Any],
    form_id: str | None = None,
    code_base64: str | None = None,
    execution_id: str | None = None,
    sync: bool = False,
) -> str:
    """
    Enqueue a workflow or script for async execution.

    Stores pending execution in Redis, publishes to RabbitMQ,
    and returns execution ID immediately (<100ms target).

    Args:
        context: Request context with org scope and user info
        workflow_name: Name of workflow to execute (or script name for inline scripts)
        parameters: Workflow/script parameters
        form_id: Optional form ID if triggered by form
        code_base64: Optional base64-encoded inline script code
        execution_id: Optional pre-generated execution ID (for sync execution)
        sync: If True, worker will push result to Redis for caller to BLPOP

    Returns:
        execution_id: UUID of the queued execution
    """
    from src.core.redis_client import get_redis_client
    from src.jobs.rabbitmq import publish_message

    redis_client = get_redis_client()

    # Generate or use provided execution ID
    # If execution_id is provided (sync execution), pending record may already exist
    if execution_id is None:
        execution_id = str(uuid.uuid4())

    # Store pending execution in Redis (unless sync with pre-existing record)
    # For sync execution, the caller already created the pending record
    if not sync:
        await redis_client.set_pending_execution(
            execution_id=execution_id,
            workflow_name=workflow_name,
            parameters=parameters,
            org_id=context.org_id,
            user_id=context.user_id,
            user_name=context.name,
            user_email=context.email,
            form_id=form_id,
        )

    # Prepare queue message (minimal - worker reads full context from Redis)
    message = {
        "execution_id": execution_id,
        "workflow_name": workflow_name,
        "code": code_base64,  # Optional: for inline scripts
        "sync": sync,  # If True, worker pushes result to Redis
    }

    # Enqueue message via RabbitMQ
    await publish_message(QUEUE_NAME, message)

    logger.info(
        f"Enqueued async workflow execution: {workflow_name}",
        extra={
            "execution_id": execution_id,
            "workflow_name": workflow_name,
            "org_id": context.org_id
        }
    )

    return execution_id
