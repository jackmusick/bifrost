"""Unit test fixtures shared across the unit suite."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import AgentAccessLevel
from src.models.orm.agents import Agent


@pytest_asyncio.fixture
async def seed_agent(db_session: AsyncSession) -> AsyncGenerator[Agent, None]:
    """Create a minimal global Agent row for tests that need an agent FK.

    Uses ``flush()`` (not ``commit()``) so the agent is visible to subsequent
    queries on the same session but rolled back after the test by the
    ``db_session`` fixture.
    """
    agent = Agent(
        id=uuid4(),
        name=f"seed_agent_{uuid4().hex[:8]}",
        description="Seed agent for unit tests",
        system_prompt="You are a test agent.",
        channels=["chat"],
        access_level=AgentAccessLevel.ROLE_BASED,
        organization_id=None,
        is_active=True,
        knowledge_sources=[],
        system_tools=[],
        created_by="test@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(agent)
    await db_session.flush()

    yield agent

    # db_session.rollback() in the parent fixture undoes the insert, but be
    # defensive in case the session was committed mid-test.
    try:
        await db_session.execute(delete(Agent).where(Agent.id == agent.id))
        await db_session.flush()
    except Exception:
        pass
