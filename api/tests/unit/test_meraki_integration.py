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
from features.meraki.workflows.data_providers import list_meraki_organizations
from features.meraki.workflows.sync_organizations import sync_meraki_organizations
from modules import meraki


def _organization(organization_id: str | None, name: str | None) -> dict:
    payload: dict[str, str | None] = {
        "id": organization_id,
        "name": name,
    }
    return payload


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Meraki"
        assert scope == "org-123"
        return SimpleNamespace(config={"api_key": "secret-key"}, entity_id=42)

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await meraki.get_client(scope="org-123")
    try:
        assert client.organization_id == "42"
        assert client._base_url == meraki.MerakiClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_api_key(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await meraki.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_meraki_organizations_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_organizations(self):
            return [
                _organization("2", "Zulu"),
                _organization("1", "Alpha"),
                _organization("", "Missing ID"),
                _organization("3", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await list_meraki_organizations()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_meraki_organizations_maps_unmapped_organizations(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_organizations(self):
            return [
                _organization("100", "Already Mapped"),
                _organization("200", "Existing Org"),
                _organization("300", "New Org"),
                _organization(None, "Broken Org"),
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
        assert name == "Meraki"
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

    monkeypatch.setattr(meraki, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_meraki_organizations()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped organization with no ID: {'id': None, 'name': 'Broken Org'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Meraki", "org-existing", "200", "Existing Org"),
        ("Meraki", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True

