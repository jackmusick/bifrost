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
from features.ninjaone.workflows.data_providers import list_ninjaone_organizations
from features.ninjaone.workflows.sync_organizations import sync_ninjaone_organizations
from modules import ninjaone


def _organization(organization_id: str | None, name: str | None) -> dict:
    organization: dict[str, str] = {}
    if organization_id is not None:
        organization["id"] = organization_id
    if name is not None:
        organization["name"] = name
    return organization


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    oauth = SimpleNamespace(access_token="access-token")

    async def fake_get(name: str, scope: str | None = None):
        assert name == "NinjaOne"
        assert scope == "org-123"
        return SimpleNamespace(
            config={"base_url": "https://app.ninjarmm.com"},
            entity_id="42",
            oauth=oauth,
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await ninjaone.get_client(scope="org-123")
    try:
        assert client.organization_id == "42"
        assert client._base_url == "https://app.ninjarmm.com"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_oauth_token(monkeypatch):
    oauth = SimpleNamespace(access_token=None)

    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_url": "https://app.ninjarmm.com"}, entity_id=None, oauth=oauth)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="missing an access token"):
        await ninjaone.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_ninjaone_organizations_returns_sorted_options(monkeypatch):
    class FakeClient:
        async def list_organizations(self):
            return [
                _organization("2", "Zulu"),
                _organization("1", "Alpha"),
                _organization("", "Missing ID"),
                _organization("3", ""),
            ]

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(ninjaone, "get_client", fake_get_client)

    result = await list_ninjaone_organizations()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_sync_ninjaone_organizations_maps_unmapped_organizations(monkeypatch):
    class FakeClient:
        async def list_organizations(self):
            return [
                _organization("100", "Already Mapped"),
                _organization("200", "Existing Org"),
                _organization("300", "New Org"),
                _organization(None, "Broken Organization"),
            ]

        async def close(self) -> None:
            return None

    fake_client = FakeClient()
    created_names: list[str] = []
    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    async def fake_list_mappings(name: str):
        assert name == "NinjaOne"
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

    monkeypatch.setattr(ninjaone, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_ninjaone_organizations()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped organization with no ID: {'name': 'Broken Organization'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("NinjaOne", "org-existing", "200", "Existing Org"),
        ("NinjaOne", "org-new", "300", "New Org"),
    ]
