"""Validate new AgentRun columns: asked, did, run_metadata, confidence, confidence_reason, summary_generated_at, summary_status, summary_error.

Note: the DB column is named ``metadata`` per the spec, but the Python
attribute is ``run_metadata`` because ``metadata`` collides with SQLAlchemy's
``DeclarativeBase.metadata`` reserved attribute. The ORM uses
``mapped_column("metadata", ...)`` to keep the column name on disk.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.models.orm.agent_runs import AgentRun


@pytest.mark.asyncio
async def test_agent_run_accepts_new_summary_fields(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=100,
        asked="How do I reset my password?",
        did="Routed to Support team",
        run_metadata={"ticket_id": "4821", "customer": "Acme"},
        confidence=0.87,
        confidence_reason="High keyword match with known-good routing",
        summary_generated_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    result = await db_session.execute(select(AgentRun).where(AgentRun.id == run.id))
    reloaded = result.scalar_one()
    assert reloaded.asked == "How do I reset my password?"
    assert reloaded.did == "Routed to Support team"
    assert reloaded.run_metadata == {"ticket_id": "4821", "customer": "Acme"}
    assert reloaded.confidence == 0.87
    assert reloaded.confidence_reason.startswith("High keyword")
    assert reloaded.summary_generated_at is not None


@pytest.mark.asyncio
async def test_agent_run_metadata_defaults_to_empty_dict(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="queued",
        iterations_used=0,
        tokens_used=0,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.run_metadata == {}


@pytest.mark.asyncio
async def test_agent_run_confidence_is_not_db_constrained(db_session, seed_agent):
    """Confidence is clamped at write time in the summarizer, not enforced by DB."""
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=1,
        confidence=1.5,
    )
    db_session.add(run)
    await db_session.flush()  # should not raise
    await db_session.refresh(run)
    assert run.confidence == 1.5


@pytest.mark.asyncio
async def test_summary_status_defaults_to_pending(db_session, seed_agent):
    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="queued",
        iterations_used=0,
        tokens_used=0,
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.refresh(run)
    assert run.summary_status == "pending"


@pytest.mark.asyncio
async def test_summary_status_check_constraint_rejects_invalid(db_session, seed_agent):
    from sqlalchemy.exc import IntegrityError

    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="queued",
        iterations_used=0,
        tokens_used=0,
        summary_status="bogus",
    )
    db_session.add(run)
    with pytest.raises(IntegrityError):
        await db_session.flush()
