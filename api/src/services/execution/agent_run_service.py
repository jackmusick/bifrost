"""Agent run enqueue and result waiting."""
import json
import logging
from uuid import uuid4

from src.core.cache.redis_client import get_redis
from src.jobs.rabbitmq import publish_message

logger = logging.getLogger(__name__)

QUEUE_NAME = "agent-runs"
REDIS_PREFIX = "bifrost:agent_run"


async def enqueue_agent_run(
    agent_id: str,
    trigger_type: str,
    input_data: dict | None = None,
    *,
    trigger_source: str | None = None,
    output_schema: dict | None = None,
    org_id: str | None = None,
    caller_user_id: str | None = None,
    caller_email: str | None = None,
    caller_name: str | None = None,
    event_delivery_id: str | None = None,
    sync: bool = False,
    run_id: str | None = None,
) -> str:
    """Enqueue an agent run for worker processing. Returns run_id."""
    if run_id is None:
        run_id = str(uuid4())

    context = {
        "run_id": run_id,
        "agent_id": agent_id,
        "trigger_type": trigger_type,
        "trigger_source": trigger_source,
        "input": input_data,
        "output_schema": output_schema,
        "org_id": org_id,
        "caller": {
            "user_id": caller_user_id,
            "email": caller_email,
            "name": caller_name,
        },
        "event_delivery_id": event_delivery_id,
        "sync": sync,
    }

    # Store full context in Redis
    redis_key = f"{REDIS_PREFIX}:{run_id}:context"
    async with get_redis() as redis:
        await redis.set(redis_key, json.dumps(context), ex=3600)

    # Publish lightweight message to queue
    message = {
        "run_id": run_id,
        "agent_id": agent_id,
        "trigger_type": trigger_type,
        "sync": sync,
    }
    await publish_message(QUEUE_NAME, message)

    logger.info(f"Enqueued agent run {run_id} for agent {agent_id} (trigger={trigger_type})")
    return run_id


async def wait_for_agent_run_result(run_id: str, timeout: int = 1800) -> dict | None:
    """Block until agent run completes. Used for sync SDK calls."""
    result_key = f"{REDIS_PREFIX}:{run_id}:result"
    async with get_redis() as redis:
        # redis-py 7.x stubs type blpop as -> list, but it's async at runtime
        result = await redis.blpop(result_key, timeout=timeout)  # pyright: ignore[reportGeneralTypeIssues]
        if result:
            return json.loads(result[1])
    return None
