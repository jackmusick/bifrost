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
from features.pax8.workflows.data_providers import list_pax8_companies
from features.pax8.workflows.sync_companies import sync_pax8_companies
from modules import pax8


def _company(company_id: str | None, name: str | None) -> dict:
    company: dict[str, str] = {}
    if company_id is not None:
        company["id"] = company_id
    if name is not None:
        company["name"] = name
    return company


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    oauth = SimpleNamespace(access_token="access-token")

    async def fake_get(name: str, scope: str | None = None):
        assert name == "Pax8"
        assert scope == "org-123"
        return SimpleNamespace(config={}, entity_id="company-42", oauth=oauth)

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await pax8.get_client(scope="org-123")
    try:
        assert client.company_id == "company-42"
        assert client._base_url == pax8.Pax8Client.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_oauth_token(monkeypatch):
    oauth = SimpleNamespace(access_token=None)

    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None, oauth=oauth)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="OAuth access token"):
        await pax8.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_pax8_companies_returns_sorted_options(monkeypatch):
    class FakeClient:
        async def list_companies(self):
            return [
                _company("2", "Zulu"),
                _company("1", "Alpha"),
                _company("", "Missing ID"),
                _company("3", ""),
            ]

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(pax8, "get_client", fake_get_client)

    result = await list_pax8_companies()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_sync_pax8_companies_maps_unmapped_companies(monkeypatch):
    class FakeClient:
        async def list_companies(self):
            return [
                _company("100", "Already Mapped"),
                _company("200", "Existing Org"),
                _company("300", "New Org"),
                _company(None, "Broken Company"),
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
        assert name == "Pax8"
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

    monkeypatch.setattr(pax8, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_pax8_companies()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped company with no ID: {'name': 'Broken Company'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Pax8", "org-existing", "200", "Existing Org"),
        ("Pax8", "org-new", "300", "New Org"),
    ]
