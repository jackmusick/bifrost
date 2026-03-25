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
from features.dattonetworking.workflows.data_providers import (
    list_dattonetworking_networks,
)
from features.dattonetworking.workflows.sync_networks import (
    sync_dattonetworking_networks,
)
from modules import dattonetworking


def _network(network_id: str | None, name: str | None) -> dict:
    return {
        "id": network_id,
        "name": name,
    }


def test_build_headers_matches_cloudtrax_hmac_example():
    client = dattonetworking.DattoNetworkingClient(
        api_key="api-key",
        api_secret="super-secret",
    )

    headers = client._build_headers(
        "/network/list",
        timestamp=1700000000,
        nonce="abc123",
    )

    assert headers["OpenMesh-API-Version"] == "1"
    assert headers["Authorization"] == "key=api-key,timestamp=1700000000,nonce=abc123"
    assert headers["Signature"] == "7614c0ac3d21a2da982fadf34fd49be4090456fbde0e8e3d89946e3a71fc9cab"


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Datto Networking"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "api_key": "api-key",
                "api_secret": "secret-key",
            },
            entity_id="net-42",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await dattonetworking.get_client(scope="org-123")
    try:
        assert client.network_id == "net-42"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"api_key": "api-key"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_secret"):
        await dattonetworking.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_dattonetworking_networks_returns_sorted_options(monkeypatch):
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

    monkeypatch.setattr(dattonetworking, "get_client", fake_get_client)

    result = await list_dattonetworking_networks()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_dattonetworking_networks_maps_unmapped_networks(monkeypatch):
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
        assert name == "Datto Networking"
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

    monkeypatch.setattr(dattonetworking, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_dattonetworking_networks()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped network with no ID: {'id': None, 'name': 'Broken Network'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Datto Networking", "org-existing", "200", "Existing Org"),
        ("Datto Networking", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
