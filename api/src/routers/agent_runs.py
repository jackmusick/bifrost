"""
Agent Runs Router

CRUD + execute endpoints for autonomous agent runs.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from src.core.auth import CurrentActiveUser
from src.core.database import DbSession
from src.models.contracts.agent_runs import (
    AgentRunCreateRequest,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunRerunResponse,
    AgentRunResponse,
    AgentRunStepResponse,
)
from src.models.contracts.executions import AIUsagePublicSimple, AIUsageTotalsSimple
from src.models.orm.agent_runs import AgentRun
from src.models.orm.ai_usage import AIUsage
from src.models.orm.agents import Agent
from src.core.redis_client import get_redis_client
from src.services.execution.agent_run_service import (
    enqueue_agent_run,
    wait_for_agent_run_result,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-runs", tags=["Agent Runs"])


def _run_to_response(run: AgentRun) -> AgentRunResponse:
    """Convert AgentRun ORM to AgentRunResponse."""
    return AgentRunResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_name=run.agent.name if run.agent else None,
        trigger_type=run.trigger_type,
        trigger_source=run.trigger_source,
        conversation_id=run.conversation_id,
        event_delivery_id=run.event_delivery_id,
        input=run.input,
        output=run.output,
        status=run.status,
        error=run.error,
        org_id=run.org_id,
        caller_user_id=run.caller_user_id,
        caller_email=run.caller_email,
        caller_name=run.caller_name,
        iterations_used=run.iterations_used,
        tokens_used=run.tokens_used,
        budget_max_iterations=run.budget_max_iterations,
        budget_max_tokens=run.budget_max_tokens,
        duration_ms=run.duration_ms,
        llm_model=run.llm_model,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        parent_run_id=run.parent_run_id,
    )


@router.get("")
async def list_agent_runs(
    db: DbSession,
    user: CurrentActiveUser,
    agent_id: UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    trigger_type: str | None = None,
    org_id: UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AgentRunListResponse:
    """List agent runs with optional filters."""
    # Build base query — exclude delegation sub-runs from top-level list
    query = select(AgentRun).join(AgentRun.agent).where(AgentRun.parent_run_id.is_(None))

    # Org filter: non-superusers see only their org's runs
    if not user.is_superuser:
        if user.organization_id:
            query = query.where(AgentRun.org_id == user.organization_id)

    # Apply optional filters
    if agent_id is not None:
        query = query.where(AgentRun.agent_id == agent_id)
    if status_filter is not None:
        query = query.where(AgentRun.status == status_filter)
    if trigger_type is not None:
        query = query.where(AgentRun.trigger_type == trigger_type)
    if org_id is not None:
        query = query.where(AgentRun.org_id == org_id)
    if start_date is not None:
        query = query.where(AgentRun.created_at >= start_date)
    if end_date is not None:
        query = query.where(AgentRun.created_at <= end_date)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Fetch paginated results
    query = query.order_by(desc(AgentRun.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    runs = result.scalars().all()

    return AgentRunListResponse(
        items=[_run_to_response(run) for run in runs],
        total=total,
    )


@router.get("/{run_id}")
async def get_agent_run(
    run_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentRunDetailResponse:
    """Get agent run detail with steps."""
    query = (
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .where(AgentRun.id == run_id)
    )

    # Org filter: non-superusers see only their org's runs
    if not user.is_superuser:
        if user.organization_id:
            query = query.where(AgentRun.org_id == user.organization_id)

    result = await db.execute(query)
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )

    # Fetch AI usage records for this run
    ai_usage_result = await db.execute(
        select(AIUsage)
        .where(AIUsage.agent_run_id == run_id)
        .order_by(AIUsage.timestamp)
    )
    ai_usage_entries = ai_usage_result.scalars().all()

    ai_usage_list: list[AIUsagePublicSimple] | None = None
    ai_totals_response: AIUsageTotalsSimple | None = None

    if ai_usage_entries:
        ai_usage_list = [
            AIUsagePublicSimple(
                provider=entry.provider,
                model=entry.model,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                cost=str(entry.cost) if entry.cost else None,
                duration_ms=entry.duration_ms,
                timestamp=entry.timestamp.isoformat(),
                sequence=entry.sequence,
            )
            for entry in ai_usage_entries
        ]

        # Calculate totals
        totals_result = await db.execute(
            select(
                func.sum(AIUsage.input_tokens).label("total_input"),
                func.sum(AIUsage.output_tokens).label("total_output"),
                func.sum(AIUsage.cost).label("total_cost"),
                func.sum(AIUsage.duration_ms).label("total_duration"),
                func.count(AIUsage.id).label("call_count"),
            ).where(AIUsage.agent_run_id == run_id)
        )
        totals_row = totals_result.one()
        ai_totals_response = AIUsageTotalsSimple(
            total_input_tokens=int(totals_row.total_input or 0),
            total_output_tokens=int(totals_row.total_output or 0),
            total_cost=str(totals_row.total_cost or Decimal("0")),
            total_duration_ms=int(totals_row.total_duration or 0),
            call_count=int(totals_row.call_count or 0),
        )

    # Fetch child run IDs for delegation sub-runs
    child_ids_result = await db.execute(
        select(AgentRun.id)
        .where(AgentRun.parent_run_id == run_id)
        .order_by(AgentRun.created_at)
    )
    child_run_ids = [row[0] for row in child_ids_result.all()]

    return AgentRunDetailResponse(
        id=run.id,
        agent_id=run.agent_id,
        agent_name=run.agent.name if run.agent else None,
        trigger_type=run.trigger_type,
        trigger_source=run.trigger_source,
        conversation_id=run.conversation_id,
        event_delivery_id=run.event_delivery_id,
        input=run.input,
        output=run.output,
        status=run.status,
        error=run.error,
        org_id=run.org_id,
        caller_user_id=run.caller_user_id,
        caller_email=run.caller_email,
        caller_name=run.caller_name,
        iterations_used=run.iterations_used,
        tokens_used=run.tokens_used,
        budget_max_iterations=run.budget_max_iterations,
        budget_max_tokens=run.budget_max_tokens,
        duration_ms=run.duration_ms,
        llm_model=run.llm_model,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        parent_run_id=run.parent_run_id,
        child_run_ids=child_run_ids,
        steps=[
            AgentRunStepResponse(
                id=step.id,
                run_id=step.run_id,
                step_number=step.step_number,
                type=step.type,
                content=step.content,
                tokens_used=step.tokens_used,
                duration_ms=step.duration_ms,
                created_at=step.created_at,
            )
            for step in run.steps
        ],
        ai_usage=ai_usage_list,
        ai_totals=ai_totals_response,
    )


@router.post("/{run_id}/rerun")
async def rerun_agent_run(
    run_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> AgentRunRerunResponse:
    """Rerun an agent run with the same input (async, non-blocking)."""
    query = select(AgentRun).where(AgentRun.id == run_id)

    # Org filter: non-superusers see only their org's runs
    if not user.is_superuser:
        if user.organization_id:
            query = query.where(AgentRun.org_id == user.organization_id)

    result = await db.execute(query)
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )

    new_run_id = await enqueue_agent_run(
        agent_id=str(original.agent_id),
        trigger_type="rerun",
        input_data=original.input,
        trigger_source=str(run_id),
        output_schema=original.output_schema,
        org_id=str(original.org_id) if original.org_id else None,
        caller_user_id=str(user.user_id),
        caller_email=user.email,
        caller_name=getattr(user, "name", None),
        sync=False,
    )

    return AgentRunRerunResponse(run_id=UUID(new_run_id))


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "budget_exceeded", "timeout"}


@router.post("/{run_id}/cancel")
async def cancel_agent_run(
    run_id: UUID,
    db: DbSession,
    user: CurrentActiveUser,
) -> dict:
    """Cancel a queued or running agent run."""
    query = select(AgentRun).where(AgentRun.id == run_id)

    # Org filter: non-superusers see only their org's runs
    if not user.is_superuser:
        if user.organization_id:
            query = query.where(AgentRun.org_id == user.organization_id)

    result = await db.execute(query)
    agent_run = result.scalar_one_or_none()

    if not agent_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent run {run_id} not found",
        )

    if agent_run.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel agent run with status '{agent_run.status}'",
        )

    if agent_run.status == "cancelling":
        # Already cancelling — idempotent
        return {"run_id": str(run_id), "status": "cancelling"}

    redis_client = get_redis_client()

    if agent_run.status == "queued":
        # Not yet picked up by worker — cancel directly
        agent_run.status = "cancelled"
        agent_run.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # Also mark the Redis context so worker skips if it picks up concurrently
        from src.core.cache.redis_client import get_redis
        redis_key = f"bifrost:agent_run:{run_id}:context"
        async with get_redis() as r:
            context_raw = await r.get(redis_key)
            if context_raw:
                import json
                ctx = json.loads(context_raw)
                ctx["cancelled"] = True
                ttl = await r.ttl(redis_key)
                await r.set(redis_key, json.dumps(ctx), ex=max(ttl, 60))

        return {"run_id": str(run_id), "status": "cancelled"}

    # Running — set to cancelling and signal via Redis
    agent_run.status = "cancelling"
    await db.commit()

    await redis_client.set_agent_run_cancel_flag(str(run_id))
    logger.info(f"Set cancel flag for agent run {run_id}")

    try:
        from src.core.pubsub import publish_agent_run_update
        await publish_agent_run_update(agent_run, agent_run.agent.name if agent_run.agent else "Unknown")
    except Exception:
        pass

    return {"run_id": str(run_id), "status": "cancelling"}


@router.post("/execute")
async def execute_agent_run(
    request: AgentRunCreateRequest,
    db: DbSession,
    user: CurrentActiveUser,
) -> dict:
    """Execute an agent synchronously via the SDK."""
    # Look up agent by name (case-insensitive)
    result = await db.execute(
        select(Agent).where(Agent.name.ilike(request.agent_name))
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{request.agent_name}' not found",
        )

    # Enqueue the agent run for sync execution
    run_id = await enqueue_agent_run(
        agent_id=str(agent.id),
        trigger_type="api",
        input_data=request.input,
        output_schema=request.output_schema,
        org_id=str(user.organization_id) if user.organization_id else None,
        caller_user_id=str(user.user_id),
        caller_email=user.email,
        caller_name=getattr(user, "name", None),
        sync=True,
    )

    # Wait for the result
    result_data = await wait_for_agent_run_result(run_id, timeout=request.timeout)

    if result_data is None:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Agent run timed out",
        )

    return result_data
