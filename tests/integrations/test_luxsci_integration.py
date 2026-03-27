from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bifrost import integrations
from features.luxsci.workflows.tools import (
    get_luxsci_account_inventory,
    list_luxsci_aliases,
    list_luxsci_domains,
    list_luxsci_users,
)
from modules import luxsci


@pytest.mark.asyncio
async def test_get_client_uses_default_base_url(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "LuxSci"
        assert scope is None
        return SimpleNamespace(
            config={
                "api_token": "token",
                "api_secret": "secret",
                "account_id": "acct-1",
            }
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await luxsci.get_client()
    try:
        assert client._base_url == luxsci.LuxSciClient.BASE_URL
        assert client.account_id == "acct-1"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"api_token": "token"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_secret"):
        await luxsci.get_client()


def test_normalize_helpers():
    user = luxsci.LuxSciClient.normalize_user(
        {
            "uid": 17,
            "contact": "Jane Smith",
            "user": "jane@example.com",
            "status": "enabled",
            "company": "Example Dental",
            "services": ["imap", "smtp"],
        }
    )
    domain = luxsci.LuxSciClient.normalize_domain(
        {
            "id": 55,
            "domain": "example.com",
            "is_enabled": 1,
            "is_verified": 0,
            "is_hipaa": 1,
            "users": 7,
        }
    )
    alias = luxsci.LuxSciClient.normalize_alias(
        {
            "user": "frontdesk",
            "domain": "example.com",
            "status": "enabled",
            "action": "email",
            "dest": "jane@example.com",
            "type": "Alias",
        }
    )

    assert user == {
        "id": "17",
        "name": "Jane Smith",
        "email": "jane@example.com",
        "status": "enabled",
        "domain": "example.com",
        "company": "Example Dental",
        "services": ["imap", "smtp"],
    }
    assert domain == {
        "id": "55",
        "name": "example.com",
        "is_enabled": True,
        "is_verified": False,
        "is_hipaa": True,
        "user_count": 7,
    }
    assert alias == {
        "id": "frontdesk@example.com",
        "address": "frontdesk@example.com",
        "status": "enabled",
        "action": "email",
        "destination": "jane@example.com",
        "type": "Alias",
    }


@pytest.mark.asyncio
async def test_list_users_tool_applies_filters(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_users(self, **kwargs):
            assert kwargs == {
                "status": "enabled",
                "domain": "example.com",
                "younger_than": 30,
                "older_than": None,
            }
            return [
                {
                    "uid": 1,
                    "contact": "Jane Smith",
                    "user": "jane@example.com",
                    "status": "enabled",
                    "company": "Example Dental",
                    "services": ["imap"],
                }
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client():
        return fake_client

    monkeypatch.setattr(luxsci, "get_client", fake_get_client)

    result = await list_luxsci_users(
        status="enabled",
        domain="example.com",
        younger_than=30,
    )

    assert result["count"] == 1
    assert result["users"][0]["email"] == "jane@example.com"
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_inventory_and_list_tools_summarize(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_users(self, **kwargs):
            return [
                {"uid": 1, "contact": "Enabled User", "user": "enabled@example.com", "status": "enabled"},
                {"uid": 2, "contact": "Disabled User", "user": "disabled@example.com", "status": "disabled"},
            ]

        async def list_domains(self):
            return [{"id": 10, "domain": "example.com", "is_enabled": 1, "is_verified": 1, "is_hipaa": 0, "users": 2}]

        async def list_aliases(self):
            return [{"user": "info", "domain": "example.com", "status": "enabled", "action": "email", "dest": "enabled@example.com", "type": "Alias"}]

        async def close(self) -> None:
            self.closed = True

    async def fake_get_client():
        return FakeClient()

    monkeypatch.setattr(luxsci, "get_client", fake_get_client)

    inventory = await get_luxsci_account_inventory()
    domains = await list_luxsci_domains()
    aliases = await list_luxsci_aliases()

    assert inventory["summary"] == {
        "user_count": 2,
        "enabled_user_count": 1,
        "disabled_user_count": 1,
        "domain_count": 1,
        "alias_count": 1,
    }
    assert domains["domains"][0]["name"] == "example.com"
    assert aliases["aliases"][0]["address"] == "info@example.com"
