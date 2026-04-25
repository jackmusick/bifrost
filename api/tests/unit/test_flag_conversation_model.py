"""Per-flag tuning conversation."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.models.contracts.agent_run_flag_conversations import (
    AssistantTurn,
    UserTurn,
)
from src.models.orm.agent_run_flag_conversations import AgentRunFlagConversation


@pytest.mark.asyncio
async def test_flag_conversation_persists_messages(db_session, seed_agent):
    from src.models.orm.agent_runs import AgentRun

    run = AgentRun(
        id=uuid4(),
        agent_id=seed_agent.id,
        trigger_type="test",
        status="completed",
        iterations_used=1,
        tokens_used=1,
        verdict="down",
    )
    db_session.add(run)
    await db_session.flush()

    conv = AgentRunFlagConversation(
        id=uuid4(),
        run_id=run.id,
        messages=[
            {
                "kind": "user",
                "content": "wrong route",
                "at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "kind": "assistant",
                "content": "I see why. Let me investigate.",
                "at": datetime.now(timezone.utc).isoformat(),
            },
        ],
        created_at=datetime.now(timezone.utc),
        last_updated_at=datetime.now(timezone.utc),
    )
    db_session.add(conv)
    await db_session.flush()

    result = await db_session.execute(
        select(AgentRunFlagConversation).where(
            AgentRunFlagConversation.run_id == run.id
        )
    )
    reloaded = result.scalar_one()
    assert len(reloaded.messages) == 2
    assert reloaded.messages[0]["content"] == "wrong route"


def test_flag_conversation_message_contract_validates():
    msg = UserTurn(content="wrong route")
    assert msg.kind == "user"
    assert msg.content == "wrong route"
    asst = AssistantTurn(content="I'll investigate")
    assert asst.kind == "assistant"
