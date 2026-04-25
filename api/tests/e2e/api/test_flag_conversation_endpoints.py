"""GET + POST ``/api/agent-runs/{id}/flag-conversation`` — e2e tests.

The POST happy-path (assistant reply appended) exercises an LLM call that
this out-of-process test runner can't mock into the API container. That
path is covered end-to-end in ``tests/unit/test_tuning_service.py`` with a
mocked LLM client. Here we exercise the HTTP surface: auth, 404/422/409
status codes, and GET returning an empty/created conversation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agent_run_flag_conversations import AgentRunFlagConversation
from src.models.orm.agent_runs import AgentRun
from src.models.orm.ai_usage import AIUsage


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def flag_conv_agent(e2e_client, platform_admin) -> AsyncGenerator[dict, None]:
    """Create a minimal agent for flag-conversation tests."""
    resp = e2e_client.post(
        "/api/agents",
        json={
            "name": f"FlagConv Test Agent {uuid4().hex[:8]}",
            "description": "flag-conv test",
            "system_prompt": "test",
            "channels": ["chat"],
            "access_level": "authenticated",
        },
        headers=platform_admin.headers,
    )
    assert resp.status_code == 201, resp.text
    agent = resp.json()
    yield agent
    try:
        e2e_client.delete(
            f"/api/agents/{agent['id']}", headers=platform_admin.headers
        )
    except Exception:
        pass


async def _create_run(
    db_session: AsyncSession, agent_id: UUID, *, status: str = "completed"
) -> AgentRun:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=uuid4(),
        agent_id=agent_id,
        trigger_type="test",
        status=status,
        iterations_used=1,
        tokens_used=100,
        input={"message": "help me"},
        output={"text": "routed to support"},
        completed_at=now if status == "completed" else None,
        verdict="down" if status == "completed" else None,
        verdict_set_at=now if status == "completed" else None,
    )
    db_session.add(run)
    await db_session.commit()
    return run


@pytest_asyncio.fixture
async def flagged_run(
    flag_conv_agent, db_session: AsyncSession
) -> AsyncGenerator[AgentRun, None]:
    run = await _create_run(db_session, UUID(flag_conv_agent["id"]))
    yield run
    await db_session.execute(
        delete(AgentRunFlagConversation).where(
            AgentRunFlagConversation.run_id == run.id
        )
    )
    await db_session.execute(delete(AIUsage).where(AIUsage.agent_run_id == run.id))
    await db_session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await db_session.commit()


@pytest_asyncio.fixture
async def queued_run(
    flag_conv_agent, db_session: AsyncSession
) -> AsyncGenerator[AgentRun, None]:
    run = await _create_run(db_session, UUID(flag_conv_agent["id"]), status="queued")
    yield run
    await db_session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await db_session.commit()


class TestFlagConversationGet:
    async def test_get_empty_conversation_returns_empty_messages(
        self, e2e_client, platform_admin, flagged_run
    ):
        res = e2e_client.get(
            f"/api/agent-runs/{flagged_run.id}/flag-conversation",
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["run_id"] == str(flagged_run.id)
        assert body["messages"] == []
        assert body["id"]  # UUID string present

    async def test_get_twice_returns_same_conversation_id(
        self, e2e_client, platform_admin, flagged_run
    ):
        """GET is idempotent — second call must return the same conversation row."""
        r1 = e2e_client.get(
            f"/api/agent-runs/{flagged_run.id}/flag-conversation",
            headers=platform_admin.headers,
        )
        assert r1.status_code == 200, r1.text
        r2 = e2e_client.get(
            f"/api/agent-runs/{flagged_run.id}/flag-conversation",
            headers=platform_admin.headers,
        )
        assert r2.status_code == 200, r2.text
        assert r1.json()["id"] == r2.json()["id"]

    async def test_get_unknown_run_returns_404(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.get(
            f"/api/agent-runs/{uuid4()}/flag-conversation",
            headers=platform_admin.headers,
        )
        assert res.status_code == 404, res.text


class TestFlagConversationPostMessage:
    async def test_post_empty_content_returns_422(
        self, e2e_client, platform_admin, flagged_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{flagged_run.id}/flag-conversation/message",
            json={"content": ""},
            headers=platform_admin.headers,
        )
        assert res.status_code == 422, res.text

    async def test_post_unknown_run_returns_404(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{uuid4()}/flag-conversation/message",
            json={"content": "hello"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 404, res.text

    async def test_post_on_non_completed_run_returns_409(
        self, e2e_client, platform_admin, queued_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{queued_run.id}/flag-conversation/message",
            json={"content": "hello"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 409, res.text
