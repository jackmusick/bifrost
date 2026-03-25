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
from features.vipre.workflows.data_providers import list_vipre_sites
from features.vipre.workflows.sync_sites import sync_vipre_sites
from modules import vipre


def _device(site_uuid: str | None, site_name: str | None) -> dict:
    return {
        "agentUuid": "agent-1",
        "identity": {
            "siteUuid": site_uuid,
            "siteName": site_name,
        },
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "VIPRE"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_uri": "https://api.myvipre.com/api/v1",
                "key_id": "kid",
                "api_key": "secret-key",
            },
            entity_id="site-42",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await vipre.get_client(scope="org-123")
    try:
        assert client.site_uuid == "site-42"
        assert client._base_uri == "https://api.myvipre.com/api/v1"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_required_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_uri": "https://api.myvipre.com/api/v1"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="key_id"):
        await vipre.get_client(scope="global")


@pytest.mark.asyncio
async def test_infer_sites_from_devices_deduplicates(monkeypatch):
    class FakeClient:
        async def infer_sites_from_devices(self):
            return [
                {"id": "2", "name": "Zulu"},
                {"id": "1", "name": "Alpha"},
                {"id": "3", "name": ""},
            ]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(vipre, "get_client", fake_get_client)

    result = await list_vipre_sites()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "3", "label": "3"},
        {"value": "2", "label": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_sync_vipre_sites_maps_unmapped_sites(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def infer_sites_from_devices(self):
            return [
                {"id": "100", "name": "Already Mapped"},
                {"id": "200", "name": "Existing Org"},
                {"id": "300", "name": "New Org"},
                {"id": "", "name": "Broken Site"},
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
        assert name == "VIPRE"
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

    monkeypatch.setattr(vipre, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_vipre_sites()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped inferred site with no ID: {'id': '', 'name': 'Broken Site'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("VIPRE", "org-existing", "200", "Existing Org"),
        ("VIPRE", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True

