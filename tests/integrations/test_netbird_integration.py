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
from features.netbird.workflows.tools import (
    get_netbird_account_inventory,
    list_netbird_audit_events,
    list_netbird_groups,
    list_netbird_peers,
    list_netbird_setup_keys,
    list_netbird_users,
)
from modules import netbird


@pytest.mark.asyncio
async def test_get_client_uses_default_base_url(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "NetBird"
        assert scope == "global"
        return SimpleNamespace(config={"api_token": "token"})

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await netbird.get_client()
    try:
        assert client._base_url == netbird.NetBirdClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_api_token(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_token"):
        await netbird.get_client()


def test_normalize_peer_and_user():
    assert netbird.NetBirdClient.normalize_peer(
        {
            "id": "peer-1",
            "hostname": "edge-1",
            "ip": "100.64.0.10",
            "connected": True,
            "groups": [{"id": "grp-1"}],
        }
    ) == {
        "id": "peer-1",
        "name": "edge-1",
        "ip": "100.64.0.10",
        "dns_label": "",
        "connected": True,
        "os": "",
        "version": "",
        "last_seen": "",
        "group_ids": ["grp-1"],
    }

    assert netbird.NetBirdClient.normalize_user(
        {
            "id": "user-1",
            "email": "ADMIN@EXAMPLE.COM",
            "name": "Admin User",
            "role": "admin",
            "is_service_user": False,
            "is_blocked": False,
            "auto_groups": ["grp-1"],
        }
    ) == {
        "id": "user-1",
        "name": "Admin User",
        "email": "admin@example.com",
        "role": "admin",
        "status": "",
        "is_service_user": False,
        "is_blocked": False,
        "pending_approval": False,
        "last_login": "",
        "auto_groups": ["grp-1"],
    }


@pytest.mark.asyncio
async def test_tools_return_netbird_inventory(monkeypatch):
    class FakeClient:
        async def list_peers(self, *, name=None, ip=None):
            return [
                {
                    "id": "peer-1",
                    "name": "edge-1",
                    "ip": "100.64.0.10",
                    "connected": True,
                }
            ]

        async def list_groups(self, *, name=None):
            return [{"id": "grp-1", "name": "Servers", "peers_count": 1}]

        async def list_setup_keys(self):
            return [{"id": 1, "name": "Default key", "valid": True}]

        async def list_users(self, *, service_user=None):
            return [
                {
                    "id": "user-1",
                    "email": "admin@example.com",
                    "name": "Admin User",
                    "role": "admin",
                    "is_service_user": False,
                    "is_blocked": False,
                }
            ]

        async def list_audit_events(self):
            return [
                {
                    "id": 10,
                    "timestamp": "2026-03-27T00:00:00Z",
                    "activity": "Peer created",
                    "activity_code": "peer.add",
                    "initiator_email": "admin@example.com",
                }
            ]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = "global"):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(netbird, "get_client", fake_get_client)

    inventory = await get_netbird_account_inventory()
    peers = await list_netbird_peers(name="edge-1")
    groups = await list_netbird_groups()
    setup_keys = await list_netbird_setup_keys()
    users = await list_netbird_users()
    events = await list_netbird_audit_events()

    assert inventory["summary"]["peer_count"] == 1
    assert inventory["summary"]["valid_setup_key_count"] == 1
    assert peers["count"] == 1
    assert groups["groups"][0]["name"] == "Servers"
    assert setup_keys["setup_keys"][0]["name"] == "Default key"
    assert users["users"][0]["email"] == "admin@example.com"
    assert events["events"][0]["activity_code"] == "peer.add"
