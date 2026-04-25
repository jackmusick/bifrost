"""POST/DELETE /api/agent-runs/{id}/verdict — e2e tests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.agent_run_verdict_history import AgentRunVerdictHistory
from src.models.orm.agent_runs import AgentRun


pytestmark = pytest.mark.asyncio


async def _create_completed_run(
    db_session: AsyncSession, agent_id: UUID, *, status: str = "completed"
) -> AgentRun:
    """Insert an AgentRun row with the given status, owned by ``agent_id``."""
    run = AgentRun(
        id=uuid4(),
        agent_id=agent_id,
        trigger_type="api",
        status=status,
        iterations_used=1,
        tokens_used=100,
        completed_at=datetime.now(timezone.utc) if status == "completed" else None,
    )
    db_session.add(run)
    await db_session.commit()
    return run


@pytest_asyncio.fixture
async def verdict_test_agent(e2e_client, platform_admin) -> AsyncGenerator[dict, None]:
    """Create an agent for verdict testing; clean up after."""
    resp = e2e_client.post(
        "/api/agents",
        json={
            "name": f"Verdict Test Agent {uuid4().hex[:8]}",
            "description": "test",
            "system_prompt": "test",
            "channels": [],
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


@pytest_asyncio.fixture
async def completed_agent_run(
    verdict_test_agent, db_session: AsyncSession
) -> AsyncGenerator[AgentRun, None]:
    """Insert a completed AgentRun owned by ``verdict_test_agent``."""
    run = await _create_completed_run(db_session, UUID(verdict_test_agent["id"]))
    yield run
    # Cleanup (also clears history rows via FK cascade)
    await db_session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await db_session.commit()


@pytest_asyncio.fixture
async def queued_agent_run(
    verdict_test_agent, db_session: AsyncSession
) -> AsyncGenerator[AgentRun, None]:
    """Insert a queued AgentRun owned by ``verdict_test_agent``."""
    run = await _create_completed_run(
        db_session, UUID(verdict_test_agent["id"]), status="queued"
    )
    yield run
    await db_session.execute(delete(AgentRun).where(AgentRun.id == run.id))
    await db_session.commit()


class TestVerdictEndpoint:
    async def test_set_verdict_up(
        self, e2e_client, platform_admin, completed_agent_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            json={"verdict": "up"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["verdict"] == "up"
        assert body["verdict_note"] is None
        assert body["verdict_set_at"] is not None
        assert body["verdict_set_by"] == str(platform_admin.user_id)

    async def test_set_verdict_down_with_note(
        self, e2e_client, platform_admin, completed_agent_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            json={"verdict": "down", "note": "Wrong routing"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["verdict"] == "down"
        assert body["verdict_note"] == "Wrong routing"

    async def test_set_verdict_on_non_completed_returns_409(
        self, e2e_client, platform_admin, queued_agent_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{queued_agent_run.id}/verdict",
            json={"verdict": "up"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 409, res.text

    async def test_set_verdict_invalid_value_returns_422(
        self, e2e_client, platform_admin, completed_agent_run
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            json={"verdict": "sideways"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 422, res.text

    async def test_set_verdict_unknown_run_returns_404(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.post(
            f"/api/agent-runs/{uuid4()}/verdict",
            json={"verdict": "up"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 404, res.text

    async def test_clear_verdict(
        self,
        e2e_client,
        platform_admin,
        completed_agent_run,
    ):
        # First set
        set_res = e2e_client.post(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            json={"verdict": "up"},
            headers=platform_admin.headers,
        )
        assert set_res.status_code == 200, set_res.text

        # Then clear
        clr_res = e2e_client.delete(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            headers=platform_admin.headers,
        )
        assert clr_res.status_code == 200, clr_res.text
        body = clr_res.json()
        assert body["verdict"] is None
        assert body["verdict_note"] is None

    async def test_verdict_change_creates_audit_rows(
        self,
        e2e_client,
        platform_admin,
        completed_agent_run,
        db_session: AsyncSession,
    ):
        # Two changes: set "down" then clear -> two history rows
        e2e_client.post(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            json={"verdict": "down", "note": "nope"},
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            f"/api/agent-runs/{completed_agent_run.id}/verdict",
            headers=platform_admin.headers,
        )

        result = await db_session.execute(
            select(AgentRunVerdictHistory)
            .where(AgentRunVerdictHistory.run_id == completed_agent_run.id)
            .order_by(AgentRunVerdictHistory.changed_at)
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        assert rows[0].new_verdict == "down"
        assert rows[0].note == "nope"
        assert rows[0].previous_verdict is None
        assert rows[1].new_verdict is None
        assert rows[1].previous_verdict == "down"
