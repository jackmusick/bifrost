"""Agent stats service: per-agent + fleet aggregations."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.models.enums import AgentAccessLevel
from src.models.orm.agent_runs import AgentRun
from src.models.orm.agents import Agent
from src.models.orm.ai_usage import AIUsage
from src.services.agent_stats import get_agent_stats, get_fleet_stats


@pytest_asyncio.fixture
async def seed_runs_for_agent(db_session, seed_agent):
    """Insert several runs across the last 7 days for the agent, with mixed status/verdict/cost."""
    now = datetime.now(timezone.utc)
    runs = []
    rows = [
        # (days_ago, status, verdict, duration_ms, cost)
        (0, "completed", "up", 1500, Decimal("0.02")),
        (1, "completed", None, 2000, Decimal("0.03")),
        (1, "failed", None, 500, Decimal("0.01")),
        (3, "completed", "down", 1800, Decimal("0.04")),
        (5, "completed", None, 1200, Decimal("0.02")),
    ]
    for days_ago, status, verdict, duration_ms, cost in rows:
        r = AgentRun(
            id=uuid4(),
            agent_id=seed_agent.id,
            trigger_type="test",
            status=status,
            iterations_used=1,
            tokens_used=100,
            duration_ms=duration_ms,
            verdict=verdict,
            verdict_set_at=(now - timedelta(days=days_ago)) if verdict else None,
            created_at=now - timedelta(days=days_ago),
        )
        db_session.add(r)
        await db_session.flush()
        db_session.add(AIUsage(
            agent_run_id=r.id,
            organization_id=None,
            provider="anthropic",
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost=cost,
            timestamp=now - timedelta(days=days_ago),
        ))
        runs.append(r)
    await db_session.commit()
    yield runs
    # Cleanup committed rows
    for r in runs:
        await db_session.execute(delete(AIUsage).where(AIUsage.agent_run_id == r.id))
        await db_session.execute(delete(AgentRun).where(AgentRun.id == r.id))
    await db_session.commit()


@pytest_asyncio.fixture
async def seed_agents_with_runs(db_session):
    """Two agents, both active, each with one completed run."""
    now = datetime.now(timezone.utc)
    agents = []
    runs = []
    for i in range(2):
        a = Agent(
            id=uuid4(),
            name=f"Stats Test Agent {i}_{uuid4().hex[:6]}",
            description="stats test",
            system_prompt="test",
            channels=["chat"],
            access_level=AgentAccessLevel.AUTHENTICATED,
            organization_id=None,
            is_active=True,
            knowledge_sources=[],
            system_tools=[],
            created_by="test@example.com",
            created_at=now,
            updated_at=now,
        )
        db_session.add(a)
        await db_session.flush()
        agents.append(a)

        r = AgentRun(
            id=uuid4(),
            agent_id=a.id,
            trigger_type="test",
            status="completed",
            iterations_used=1,
            tokens_used=10,
            duration_ms=1000,
            created_at=now,
        )
        db_session.add(r)
        await db_session.flush()
        runs.append(r)
    await db_session.commit()
    yield {"agents": agents, "runs": runs}
    for r in runs:
        await db_session.execute(delete(AgentRun).where(AgentRun.id == r.id))
    for a in agents:
        await db_session.execute(delete(Agent).where(Agent.id == a.id))
    await db_session.commit()


@pytest.mark.asyncio
async def test_per_agent_stats(db_session, seed_agent, seed_runs_for_agent):
    stats = await get_agent_stats(seed_agent.id, db_session, window_days=7)
    assert stats.runs_7d == 5
    assert 0.0 <= stats.success_rate <= 1.0
    # 4 completed / 5 total = 0.8
    assert abs(stats.success_rate - 0.8) < 0.001
    assert stats.avg_duration_ms > 0
    assert stats.total_cost_7d > 0
    assert stats.last_run_at is not None
    assert len(stats.runs_by_day) == 7
    assert stats.needs_review == 1  # one verdict='down'
    # Unreviewed: completed runs with verdict=None
    # 4 completed, 1 has 'up', 1 has 'down', 2 unreviewed
    assert stats.unreviewed == 2


@pytest.mark.asyncio
async def test_per_agent_stats_empty(db_session, seed_agent):
    stats = await get_agent_stats(seed_agent.id, db_session, window_days=7)
    assert stats.runs_7d == 0
    assert stats.success_rate == 0.0  # no runs == 0% success
    assert stats.avg_duration_ms == 0
    assert stats.last_run_at is None


@pytest.mark.asyncio
async def test_fleet_stats(db_session, seed_agents_with_runs):
    s = await get_fleet_stats(db_session, org_id=None, window_days=7)
    assert s.total_runs >= 2
    assert s.active_agents >= 2
    assert 0.0 <= s.avg_success_rate <= 1.0
    assert s.needs_review >= 0


@pytest.mark.asyncio
async def test_summarizer_cost_is_included_in_total_cost_7d(
    db_session, seed_agent
):
    """Regression: summarizer-generated AIUsage rows must roll up into
    AgentStats.total_cost_7d so a backfill's $$ impact is visible in the
    UI's Spend (7d) card without separate bookkeeping.
    """
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
        duration_ms=1000,
        created_at=now,
    )
    db_session.add(run)
    await db_session.flush()

    # Primary agent-work AIUsage row (what the autonomous executor writes).
    db_session.add(AIUsage(
        agent_run_id=run.id,
        organization_id=None,
        provider="anthropic",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost=Decimal("0.01"),
        timestamp=now,
    ))
    # Summarizer-generated AIUsage row (what run_summarizer writes).
    # The service sums AIUsage.cost for all usage rows linked to the run,
    # regardless of which model/provider wrote them — this asserts that.
    db_session.add(AIUsage(
        agent_run_id=run.id,
        organization_id=None,
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=80,
        output_tokens=40,
        cost=Decimal("0.005"),
        timestamp=now,
    ))
    await db_session.commit()

    stats = await get_agent_stats(seed_agent.id, db_session, window_days=7)
    assert stats.total_cost_7d == Decimal("0.015"), (
        f"Expected 0.015 (0.01 agent-work + 0.005 summarizer), got {stats.total_cost_7d}. "
        "If this fails, the summarizer's cost is being silently dropped from "
        "the Spend (7d) metric — admins running a backfill will see no $$ "
        "movement and be confused."
    )

    # Cleanup
    await db_session.execute(delete(AIUsage).where(AIUsage.agent_run_id == run.id))
    await db_session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await db_session.commit()
