"""PUT /api/agents/{id} budget field gating — e2e tests.

Validates the Task 19 behavior: ``max_iterations``, ``max_token_budget``,
and ``llm_max_tokens`` can only be set by platform admins. Non-admins
attempting to set any of those get 403 with a detail mentioning ``budget``.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio


logger = logging.getLogger(__name__)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def admin_authenticated_agent(
    e2e_client, platform_admin
) -> AsyncGenerator[dict, None]:
    """Create an agent owned by the platform admin (authenticated access)."""
    resp = e2e_client.post(
        "/api/agents",
        json={
            "name": f"Budget Test Agent {uuid4().hex[:8]}",
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
    except Exception as e:
        # Best-effort fixture cleanup; teardown shouldn't fail the test
        logger.debug(f"fixture cleanup error: {e}")


@pytest_asyncio.fixture
async def org_user_private_agent(
    e2e_client, org1_user
) -> AsyncGenerator[dict, None]:
    """Create a private agent owned by ``org1_user`` for non-admin update tests."""
    resp = e2e_client.post(
        "/api/agents",
        json={
            "name": f"Org User Private Agent {uuid4().hex[:8]}",
            "description": "test",
            "system_prompt": "test",
            "channels": [],
            "access_level": "private",
        },
        headers=org1_user.headers,
    )
    assert resp.status_code == 201, resp.text
    agent = resp.json()
    yield agent


class TestBudgetFieldGating:
    async def test_admin_can_set_max_iterations(
        self, e2e_client, platform_admin, admin_authenticated_agent
    ):
        """Admin update with budget field succeeds."""
        res = e2e_client.put(
            f"/api/agents/{admin_authenticated_agent['id']}",
            json={"max_iterations": 100},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["max_iterations"] == 100

    async def test_admin_can_set_max_token_budget(
        self, e2e_client, platform_admin, admin_authenticated_agent
    ):
        """Admin can set max_token_budget."""
        res = e2e_client.put(
            f"/api/agents/{admin_authenticated_agent['id']}",
            json={"max_token_budget": 50000},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["max_token_budget"] == 50000

    async def test_admin_can_set_llm_max_tokens(
        self, e2e_client, platform_admin, admin_authenticated_agent
    ):
        """Admin can set llm_max_tokens."""
        res = e2e_client.put(
            f"/api/agents/{admin_authenticated_agent['id']}",
            json={"llm_max_tokens": 8000},
            headers=platform_admin.headers,
        )
        assert res.status_code == 200, res.text
        assert res.json()["llm_max_tokens"] == 8000

    async def test_non_admin_cannot_set_max_iterations(
        self, e2e_client, org1_user, org_user_private_agent
    ):
        """Non-admin update with max_iterations gets 403."""
        res = e2e_client.put(
            f"/api/agents/{org_user_private_agent['id']}",
            json={"max_iterations": 50},
            headers=org1_user.headers,
        )
        assert res.status_code == 403, res.text
        assert "budget" in res.text.lower()

    async def test_non_admin_cannot_set_max_token_budget(
        self, e2e_client, org1_user, org_user_private_agent
    ):
        """Non-admin update with max_token_budget gets 403."""
        res = e2e_client.put(
            f"/api/agents/{org_user_private_agent['id']}",
            json={"max_token_budget": 25000},
            headers=org1_user.headers,
        )
        assert res.status_code == 403, res.text
        assert "budget" in res.text.lower()

    async def test_non_admin_cannot_set_llm_max_tokens(
        self, e2e_client, org1_user, org_user_private_agent
    ):
        """Non-admin update with llm_max_tokens gets 403."""
        res = e2e_client.put(
            f"/api/agents/{org_user_private_agent['id']}",
            json={"llm_max_tokens": 4000},
            headers=org1_user.headers,
        )
        assert res.status_code == 403, res.text
        assert "budget" in res.text.lower()

    async def test_non_admin_can_update_non_budget_field(
        self, e2e_client, org1_user, org_user_private_agent
    ):
        """Non-admin update without budget fields still succeeds (sanity)."""
        res = e2e_client.put(
            f"/api/agents/{org_user_private_agent['id']}",
            json={"description": "Updated description"},
            headers=org1_user.headers,
        )
        assert res.status_code == 200, res.text
