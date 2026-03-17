"""RabbitMQ consumer for autonomous agent runs."""
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.core.pubsub import publish_agent_run_update
from src.core.cache.redis_client import get_redis
from src.core.database import get_session_factory
from src.jobs.rabbitmq import BaseConsumer
from src.models.orm.agents import Agent
from src.models.orm.agent_runs import AgentRun
from src.services.execution.autonomous_agent_executor import AutonomousAgentExecutor

logger = logging.getLogger(__name__)

QUEUE_NAME = "agent-runs"
REDIS_PREFIX = "bifrost:agent_run"


class AgentRunConsumer(BaseConsumer):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            queue_name=QUEUE_NAME,
            prefetch_count=settings.max_concurrency,
        )
        self._session_factory = get_session_factory()

    async def process_message(self, body: dict) -> None:
        run_id = body["run_id"]
        agent_id = body["agent_id"]
        trigger_type = body["trigger_type"]
        sync = body.get("sync", False)

        logger.info(f"Processing agent run {run_id} (agent={agent_id}, trigger={trigger_type})")

        # Read full context from Redis
        redis_key = f"{REDIS_PREFIX}:{run_id}:context"
        async with get_redis() as redis:
            context_raw = await redis.get(redis_key)

        if not context_raw:
            logger.error(f"Agent run {run_id}: context not found in Redis")
            return

        context = json.loads(context_raw)
        start_time = time.time()

        async with self._session_factory() as db:
            agent_run: AgentRun | None = None
            agent: Agent | None = None
            try:
                # Load agent with relationships
                result = await db.execute(
                    select(Agent)
                    .options(
                        selectinload(Agent.tools),
                        selectinload(Agent.delegated_agents),
                        selectinload(Agent.roles),
                    )
                    .where(Agent.id == UUID(agent_id))
                )
                agent = result.scalar_one_or_none()
                if not agent:
                    logger.error(f"Agent run {run_id}: agent {agent_id} not found")
                    return

                # Create AgentRun record
                agent_run = AgentRun(
                    id=UUID(run_id),
                    agent_id=agent.id,
                    trigger_type=trigger_type,
                    trigger_source=context.get("trigger_source"),
                    event_delivery_id=UUID(context["event_delivery_id"]) if context.get("event_delivery_id") else None,
                    input=context.get("input"),
                    output_schema=context.get("output_schema"),
                    status="running",
                    org_id=UUID(context["org_id"]) if context.get("org_id") else None,
                    caller_user_id=context["caller"].get("user_id") if context.get("caller") else None,
                    caller_email=context["caller"].get("email") if context.get("caller") else None,
                    caller_name=context["caller"].get("name") if context.get("caller") else None,
                    budget_max_iterations=agent.max_iterations,
                    budget_max_tokens=agent.max_token_budget,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(agent_run)
                await db.commit()

                await publish_agent_run_update(agent_run, agent.name)

                # Run the agent
                async with get_redis() as redis_for_executor:
                    executor = AutonomousAgentExecutor(db, redis_client=redis_for_executor)
                    run_result = await executor.run(
                        agent=agent,
                        input_data=context.get("input"),
                        output_schema=context.get("output_schema"),
                        run_id=run_id,
                        _caller=context.get("caller"),
                    )

                # Update run record
                duration_ms = int((time.time() - start_time) * 1000)
                agent_run.status = run_result.get("status", "completed")
                agent_run.output = run_result.get("output") if isinstance(run_result.get("output"), dict) else {"text": run_result.get("output")}
                agent_run.iterations_used = run_result.get("iterations_used", 0)
                agent_run.tokens_used = run_result.get("tokens_used", 0)
                agent_run.llm_model = run_result.get("llm_model")
                agent_run.duration_ms = duration_ms
                agent_run.completed_at = datetime.now(timezone.utc)
                if run_result.get("error"):
                    agent_run.error = run_result["error"]
                await db.commit()

                await publish_agent_run_update(agent_run, agent.name)

                # Update event delivery status if triggered by event
                if context.get("event_delivery_id"):
                    await self._update_event_delivery(
                        db,
                        event_delivery_id=context["event_delivery_id"],
                        agent_run_id=run_id,
                        run_status=agent_run.status,
                        error_message=agent_run.error,
                    )

                # If sync, push result for BLPOP waiter
                if sync:
                    result_key = f"{REDIS_PREFIX}:{run_id}:result"
                    async with get_redis() as r:
                        # redis-py 7.x stubs type lpush as -> int, but it's async at runtime
                        await r.lpush(result_key, json.dumps({  # pyright: ignore[reportGeneralTypeIssues]
                            "output": run_result.get("output"),
                            "status": run_result.get("status", "completed"),
                            "iterations_used": run_result.get("iterations_used", 0),
                            "tokens_used": run_result.get("tokens_used", 0),
                        }))
                        await r.expire(result_key, 300)

            except Exception as e:
                logger.exception(f"Agent run {run_id} failed: {e}")
                if agent_run is not None:
                    try:
                        agent_run.status = "failed"
                        agent_run.error = str(e)
                        agent_run.duration_ms = int((time.time() - start_time) * 1000)
                        agent_run.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                    except Exception:
                        logger.exception(f"Failed to update agent_run {run_id} after error")

                    try:
                        await publish_agent_run_update(
                            agent_run, agent.name if agent else "Unknown"
                        )
                    except Exception:
                        pass

                if sync:
                    result_key = f"{REDIS_PREFIX}:{run_id}:result"
                    async with get_redis() as r:
                        await r.lpush(result_key, json.dumps({  # pyright: ignore[reportGeneralTypeIssues]
                            "output": None,
                            "status": "failed",
                            "error": str(e),
                        }))
                        await r.expire(result_key, 300)

            finally:
                try:
                    async with get_redis() as r:
                        await r.delete(f"{REDIS_PREFIX}:{run_id}:context")
                except Exception:
                    pass

    @staticmethod
    async def _update_event_delivery(
        db,
        event_delivery_id: str,
        agent_run_id: str,
        run_status: str,
        error_message: str | None = None,
    ) -> None:
        """Update EventDelivery status after agent run completes."""
        from src.models.orm.events import EventDelivery
        from src.models.enums import EventDeliveryStatus
        from src.repositories.events import EventDeliveryRepository

        try:
            result = await db.execute(
                select(EventDelivery).where(
                    EventDelivery.id == UUID(event_delivery_id)
                )
            )
            delivery = result.scalar_one_or_none()
            if not delivery:
                return

            # Map agent run status to delivery status
            if run_status == "completed":
                delivery.status = EventDeliveryStatus.SUCCESS
            else:
                delivery.status = EventDeliveryStatus.FAILED
                delivery.error_message = error_message

            delivery.agent_run_id = UUID(agent_run_id)
            delivery.completed_at = datetime.now(timezone.utc)
            delivery.attempt_count += 1
            await db.flush()

            # Update parent event status
            delivery_repo = EventDeliveryRepository(db)
            await delivery_repo.update_event_status(delivery.event_id)

            await db.commit()
        except Exception:
            logger.exception(f"Failed to update event delivery {event_delivery_id}")
