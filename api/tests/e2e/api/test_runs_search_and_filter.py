"""Full-text search, verdict filter, and metadata filter on agent-runs list."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import AgentAccessLevel
from src.models.orm.agent_runs import AgentRun
from src.models.orm.agents import Agent


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def seeded_runs(db_session: AsyncSession) -> AsyncGenerator[dict, None]:
    """Seed an agent + multiple runs with known asked/did/metadata/verdict."""
    agent = Agent(
        id=uuid4(),
        name=f"Search Test Agent {uuid4().hex[:8]}",
        description="search-test",
        system_prompt="test",
        channels=["chat"],
        access_level=AgentAccessLevel.AUTHENTICATED,
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

    # Use a unique tag in metadata so we can find OUR seeded runs reliably
    # in a session-scoped DB that may already contain unrelated runs.
    seed_tag = f"seed-{uuid4().hex[:8]}"

    runs: list[AgentRun] = []
    fixtures = [
        (
            "How do I reset my password?",
            "Routed to support",
            {"ticket_id": "4821", "customer": "Acme", "seed_tag": seed_tag},
            "up",
        ),
        (
            "VPN won't connect",
            "Created ticket",
            {"ticket_id": "4822", "customer": "Acme", "seed_tag": seed_tag},
            "down",
        ),
        (
            "Add me to a group",
            "Added to ad group",
            {"ticket_id": "4823", "customer": "Globex", "seed_tag": seed_tag},
            None,
        ),
    ]
    for asked, did, md, verdict in fixtures:
        r = AgentRun(
            id=uuid4(),
            agent_id=agent.id,
            trigger_type="test",
            status="completed",
            iterations_used=1,
            tokens_used=10,
            asked=asked,
            did=did,
            run_metadata=md,
            verdict=verdict,
            verdict_set_at=datetime.now(timezone.utc) if verdict else None,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(r)
        runs.append(r)
    # Commit so the API request (separate connection) can see them.
    await db_session.commit()

    yield {"agent": agent, "runs": runs, "seed_tag": seed_tag}

    # Cleanup
    for r in runs:
        await db_session.execute(delete(AgentRun).where(AgentRun.id == r.id))
    await db_session.execute(delete(Agent).where(Agent.id == agent.id))
    await db_session.commit()


class TestRunsSearchAndFilter:
    async def test_search_by_ticket_id(self, e2e_client, platform_admin, seeded_runs):
        res = e2e_client.get(
            "/api/agent-runs",
            params={"q": "4821"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        # Find our seeded run by ticket_id; allow other unrelated runs in the result
        ours = [r for r in items if r.get("metadata", {}).get("ticket_id") == "4821"]
        assert len(ours) >= 1, f"Expected at least one match for ticket_id 4821, got: {items}"

    async def test_search_across_asked(self, e2e_client, platform_admin, seeded_runs):
        res = e2e_client.get(
            "/api/agent-runs",
            params={"q": "password"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        # Restrict to our seeded agent so a co-tenant test row can't pollute
        ours = [r for r in items if r["agent_id"] == str(seeded_runs["agent"].id)]
        assert len(ours) >= 1
        assert all("password" in (r.get("asked") or "").lower() for r in ours)

    async def test_search_across_did(self, e2e_client, platform_admin, seeded_runs):
        res = e2e_client.get(
            "/api/agent-runs",
            params={"q": "ad group"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        ours = [r for r in items if r["agent_id"] == str(seeded_runs["agent"].id)]
        assert len(ours) >= 1

    async def test_metadata_filter_exact_match(
        self, e2e_client, platform_admin, seeded_runs
    ):
        # New shape: list of {key, op, value} conditions. Default op is
        # 'contains', so we pin it to 'eq' for an exact-match assertion.
        mf = json.dumps(
            [
                {"key": "customer", "op": "eq", "value": "Acme"},
                {"key": "seed_tag", "op": "eq", "value": seeded_runs["seed_tag"]},
            ]
        )
        res = e2e_client.get(
            "/api/agent-runs",
            params={"metadata_filter": mf},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 2, f"Expected exactly 2 Acme runs, got: {items}"
        for r in items:
            assert r["metadata"]["customer"] == "Acme"
            assert r["metadata"]["seed_tag"] == seeded_runs["seed_tag"]

    async def test_metadata_filter_contains_case_insensitive(
        self, e2e_client, platform_admin, seeded_runs
    ):
        """'contains' is case-insensitive substring — the intended default for
        the captured-data filter ('security' in 'security > network')."""
        mf = json.dumps(
            [
                {
                    "key": "seed_tag",
                    "op": "eq",
                    "value": seeded_runs["seed_tag"],
                },
                {"key": "customer", "op": "contains", "value": "acm"},
            ]
        )
        res = e2e_client.get(
            "/api/agent-runs",
            params={"metadata_filter": mf},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 2
        for r in items:
            assert "acme" in r["metadata"]["customer"].lower()

    async def test_verdict_filter_down(
        self, e2e_client, platform_admin, seeded_runs
    ):
        mf = json.dumps(
            [{"key": "seed_tag", "op": "eq", "value": seeded_runs["seed_tag"]}]
        )
        res = e2e_client.get(
            "/api/agent-runs",
            params={"verdict": "down", "metadata_filter": mf},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["verdict"] == "down"

    async def test_verdict_filter_unreviewed(
        self, e2e_client, platform_admin, seeded_runs
    ):
        mf = json.dumps(
            [{"key": "seed_tag", "op": "eq", "value": seeded_runs["seed_tag"]}]
        )
        res = e2e_client.get(
            "/api/agent-runs",
            params={"verdict": "unreviewed", "metadata_filter": mf},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        items = res.json()["items"]
        assert len(items) == 1
        assert items[0]["verdict"] is None
        assert items[0]["status"] == "completed"

    async def test_invalid_verdict_returns_422(self, e2e_client, platform_admin):
        res = e2e_client.get(
            "/api/agent-runs",
            params={"verdict": "sideways"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 422

    async def test_invalid_metadata_filter_not_json_returns_422(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.get(
            "/api/agent-runs",
            params={"metadata_filter": "not_json"},
            headers=platform_admin.headers,
        )
        assert res.status_code == 422

    async def test_invalid_metadata_filter_not_list_returns_422(
        self, e2e_client, platform_admin
    ):
        """Old-format {key:value} object is no longer accepted — must be a list."""
        res = e2e_client.get(
            "/api/agent-runs",
            params={"metadata_filter": '{"customer":"Acme"}'},
            headers=platform_admin.headers,
        )
        assert res.status_code == 422

    async def test_invalid_metadata_filter_unknown_op_returns_422(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.get(
            "/api/agent-runs",
            params={
                "metadata_filter": json.dumps(
                    [{"key": "customer", "op": "startswith", "value": "A"}]
                )
            },
            headers=platform_admin.headers,
        )
        assert res.status_code == 422

    async def test_metadata_keys_returns_distinct_keys_for_agent(
        self, e2e_client, platform_admin, seeded_runs
    ):
        res = e2e_client.get(
            "/api/agent-runs/metadata-keys",
            params={"agent_id": str(seeded_runs["agent"].id)},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        keys = set(res.json()["keys"])
        # seeded_runs seeds metadata with at least customer + seed_tag.
        assert "customer" in keys
        assert "seed_tag" in keys

    async def test_metadata_values_returns_distinct_values_for_key(
        self, e2e_client, platform_admin, seeded_runs
    ):
        res = e2e_client.get(
            "/api/agent-runs/metadata-values",
            params={
                "agent_id": str(seeded_runs["agent"].id),
                "key": "customer",
            },
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        values = set(res.json()["values"])
        # Acme appears on at least one seeded run.
        assert "Acme" in values

    async def test_metadata_keys_requires_agent_id(
        self, e2e_client, platform_admin
    ):
        res = e2e_client.get(
            "/api/agent-runs/metadata-keys",
            headers=platform_admin.headers,
        )
        # FastAPI treats a missing required Query param as a 422.
        assert res.status_code == 422
