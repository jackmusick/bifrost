from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bifrost import integrations, organizations
from features.dnsfilter.workflows.data_providers import list_dnsfilter_networks
from features.dnsfilter.workflows.sync_networks import sync_dnsfilter_networks
from modules import dnsfilter


def _network(network_id: str | None, name: str | None) -> dict:
    relationships = {}
    if network_id is not None:
        relationships = {"organization": {"data": {"id": 99}}}
    return {
        "id": network_id,
        "attributes": {"name": name} if name is not None else {},
        "relationships": relationships,
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "DNSFilter"
        assert scope == "org-123"
        return SimpleNamespace(config={"api_key": "secret-key"}, entity_id=42)

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await dnsfilter.get_client(scope="org-123")
    try:
        assert client.network_id == "42"
        assert client._base_url == dnsfilter.DNSFilterClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_api_key(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await dnsfilter.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_dnsfilter_networks_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_networks(self):
            return [
                _network("2", "Zulu"),
                _network("1", "Alpha"),
                _network("", "Missing ID"),
                _network("3", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(dnsfilter, "get_client", fake_get_client)

    result = await list_dnsfilter_networks()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_dnsfilter_networks_maps_unmapped_networks(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_networks(self):
            return [
                _network("100", "Already Mapped"),
                _network("200", "Existing Org"),
                _network("300", "New Org"),
                _network(None, "Broken Network"),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()
    created_names: list[str] = []
    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    async def fake_list_mappings(name: str):
        assert name == "DNSFilter"
        return [SimpleNamespace(entity_id="100")]

    existing_org = SimpleNamespace(id="org-existing", name="Existing Org")

    async def fake_list_orgs():
        return [existing_org]

    async def fake_create_org(name: str):
        created_names.append(name)
        return SimpleNamespace(id="org-new", name=name)

    async def fake_upsert_mapping(
        name: str,
        *,
        scope: str,
        entity_id: str,
        entity_name: str,
    ):
        mapping_calls.append((name, scope, entity_id, entity_name))

    monkeypatch.setattr(dnsfilter, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_dnsfilter_networks()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped network with no ID: {'id': None, 'attributes': {'name': 'Broken Network'}, 'relationships': {}}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("DNSFilter", "org-existing", "200", "Existing Org"),
        ("DNSFilter", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
