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

from src.sdk.context import ExecutionContext

logger = logging.getLogger(__name__)

QUEUE_NAME = "workflow-executions"


async def enqueue_workflow_execution(
    context: ExecutionContext,
    workflow_id: str,
    parameters: dict[str, Any],
    form_id: str | None = None,
    execution_id: str | None = None,
    sync: bool = False,
    api_key_id: str | None = None,
) -> str:
    """
    Enqueue a workflow for async execution.

    Stores pending execution in Redis, publishes to RabbitMQ,
    and returns execution ID immediately (<100ms target).

    Args:
        context: Request context with org scope and user info
        workflow_id: UUID of workflow to execute (from database)
        parameters: Workflow parameters
        form_id: Optional form ID if triggered by form
        execution_id: Optional pre-generated execution ID (for sync execution)
        sync: If True, worker will push result to Redis for caller to BLPOP
        api_key_id: Optional workflow ID whose API key triggered this execution

    Returns:
        execution_id: UUID of the queued execution
    """
    from src.core.redis_client import get_redis_client
    from src.jobs.rabbitmq import publish_message
    from src.services.execution.queue_tracker import add_to_queue

    redis_client = get_redis_client()

    # Generate or use provided execution ID
    if execution_id is None:
        execution_id = str(uuid.uuid4())

    # Store pending execution in Redis (worker needs this for execution context)
    await redis_client.set_pending_execution(
        execution_id=execution_id,
        workflow_id=workflow_id,
        parameters=parameters,
        org_id=context.org_id,
        user_id=context.user_id,
        user_name=context.name,
        user_email=context.email,
        form_id=form_id,
        startup=context.startup,  # Pass launch workflow results to worker
        api_key_id=api_key_id,
    )

    # Add to queue tracking (publishes position updates to all queued executions)
    await add_to_queue(execution_id)

    # Prepare queue message (minimal - worker reads full context from Redis)
    message = {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "sync": sync,
    }

    # Enqueue message via RabbitMQ
    await publish_message(QUEUE_NAME, message)

    logger.info(
        f"Enqueued async workflow execution: {workflow_id}",
        extra={
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "org_id": context.org_id
        }
    )

    return execution_id


async def enqueue_code_execution(
    context: ExecutionContext,
    script_name: str,
    code_base64: str,
    parameters: dict[str, Any],
    execution_id: str | None = None,
    sync: bool = False,
) -> str:
    """
    Enqueue inline code for async execution.

    Stores pending execution in Redis, publishes to RabbitMQ,
    and returns execution ID immediately (<100ms target).

    Args:
        context: Request context with org scope and user info
        script_name: Name/identifier for the script
        code_base64: Base64-encoded Python code
        parameters: Script parameters
        execution_id: Optional pre-generated execution ID (for sync execution)
        sync: If True, worker will push result to Redis for caller to BLPOP

    Returns:
        execution_id: UUID of the queued execution
    """
    from src.core.redis_client import get_redis_client
    from src.jobs.rabbitmq import publish_message
    from src.services.execution.queue_tracker import add_to_queue

    redis_client = get_redis_client()

    # Generate or use provided execution ID
    if execution_id is None:
        execution_id = str(uuid.uuid4())

    # Store pending execution in Redis (worker needs this for execution context)
    await redis_client.set_pending_execution(
        execution_id=execution_id,
        workflow_id=None,  # No workflow ID for inline code
        script_name=script_name,
        parameters=parameters,
        org_id=context.org_id,
        user_id=context.user_id,
        user_name=context.name,
        user_email=context.email,
        form_id=None,
    )

    # Add to queue tracking
    await add_to_queue(execution_id)

    # Prepare queue message with code
    message = {
        "execution_id": execution_id,
        "code": code_base64,
        "script_name": script_name,
        "sync": sync,
    }

    # Enqueue message via RabbitMQ
    await publish_message(QUEUE_NAME, message)

    logger.info(
        f"Enqueued async code execution: {script_name}",
        extra={
            "execution_id": execution_id,
            "script_name": script_name,
            "org_id": context.org_id
        }
    )

    return execution_id
