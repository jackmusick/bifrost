"""Agent prompt version history."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select

from src.models.orm.agent_prompt_history import AgentPromptHistory


@pytest.mark.asyncio
async def test_prompt_history_persists(db_session, seed_agent, seed_user):
    h = AgentPromptHistory(
        id=uuid4(),
        agent_id=seed_agent.id,
        previous_prompt="Old prompt",
        new_prompt="New prompt with clarification rules",
        changed_by=seed_user.id,
        changed_at=datetime.now(timezone.utc),
        tuning_session_id=None,
        reason="Pattern: over-aggressive duplicate matching",
    )
    db_session.add(h)
    await db_session.flush()
    result = await db_session.execute(
        select(AgentPromptHistory).where(AgentPromptHistory.agent_id == seed_agent.id)
    )
    assert result.scalar_one().reason.startswith("Pattern")
