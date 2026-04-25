"""Verdict column + audit history."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory
from src.models.orm.agent_runs import AgentRun


@pytest.mark.asyncio
async def test_agent_run_accepts_verdict_fields(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
        verdict="up",
        verdict_note="looks right",
        verdict_set_at=datetime.now(timezone.utc),
        verdict_set_by=None,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.verdict == "up"


@pytest.mark.asyncio
async def test_verdict_only_accepts_up_down_null(db_session, seed_agent):
    from sqlalchemy.exc import IntegrityError

    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
        verdict="sideways",
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_verdict_history_row_fields(db_session, seed_agent, seed_user):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
    )
    db_session.add(run)
    await db_session.flush()

    h = AgentRunVerdictHistory(
        id=uuid4(),
        run_id=run.id,
        previous_verdict=None,
        new_verdict="down",
        changed_by=seed_user.id,
        changed_at=datetime.now(timezone.utc),
        note="wrong route",
    )
    db_session.add(h)
    await db_session.flush()
    result = await db_session.execute(
        select(AgentRunVerdictHistory).where(AgentRunVerdictHistory.run_id == run.id)
    )
    assert result.scalar_one().note == "wrong route"
