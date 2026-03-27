"""Tests for OAuth connection repository behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.routers.oauth_connections import OAuthConnectionRepository


@pytest.mark.asyncio
async def test_list_connections_includes_global_for_platform_org(monkeypatch):
    """Org-scoped OAuth listings should include global connections."""
    org_id = uuid4()
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    repo = OAuthConnectionRepository(db)

    async def fake_to_summary(provider):
        return provider

    monkeypatch.setattr(repo, "_to_summary", fake_to_summary)

    await repo.list_connections(org_id)

    query = db.execute.await_args.args[0]
    where_clause = str(query.whereclause)

    assert "oauth_providers.organization_id =" in where_clause
    assert "oauth_providers.organization_id IS NULL" in where_clause
