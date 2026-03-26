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
from features.itglue.workflows.data_providers import list_itglue_organizations
from features.itglue.workflows.sync_organizations import sync_itglue_organizations
from modules import itglue


def _organization(organization_id: str | None, name: str | None) -> dict:
    organization: dict[str, object] = {}
    if organization_id is not None:
        organization["id"] = organization_id
    if name is not None:
        organization["attributes"] = {"name": name}
    return organization


@pytest.mark.asyncio
async def test_get_client_uses_global_integration_config(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "IT Glue"
        assert scope == "global"
        return SimpleNamespace(
            config={
                "api_key": "glue-key",
                "region": "EU",
            }
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await itglue.get_client(scope="global")

    assert client.api_key == "glue-key"
    assert client.base_url == "https://api.eu.itglue.com"


@pytest.mark.asyncio
async def test_get_client_requires_api_key(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await itglue.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_itglue_organizations_returns_sorted_options(monkeypatch):
    class FakeClient:
        def list_organizations(self):
            return [
                _organization("2", "Zulu"),
                _organization("1", "Alpha"),
                _organization("", "Missing ID"),
                _organization("3", ""),
            ]

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(itglue, "get_client", fake_get_client)

    result = await list_itglue_organizations()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_sync_itglue_organizations_maps_unmapped_organizations(monkeypatch):
    class FakeClient:
        def list_organizations(self):
            return [
                _organization("100", "Already Mapped"),
                _organization("200", "Existing Org"),
                _organization("300", "New Org"),
                _organization(None, "Broken Organization"),
            ]

    created_names: list[str] = []
    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    async def fake_list_mappings(name: str):
        assert name == "IT Glue"
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

    monkeypatch.setattr(itglue, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_itglue_organizations()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped organization with no ID: {'attributes': {'name': 'Broken Organization'}}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("IT Glue", "org-existing", "200", "Existing Org"),
        ("IT Glue", "org-new", "300", "New Org"),
    ]
