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
from features.autotask.workflows.data_providers import list_autotask_companies
from features.autotask.workflows.sync_customers import sync_autotask_customers
from modules import autotask


def _company(company_id: int | None, name: str | None) -> dict:
    return {"id": company_id, "companyName": name}


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Autotask"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_url": "https://webservices.example.com/atservicesrest",
                "api_integration_code": "code",
                "username": "user",
                "secret": "secret",
            },
            entity_id="456",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await autotask.get_client(scope="org-123")
    try:
        assert client.company_id == "456"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_url": "https://webservices.example.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_integration_code"):
        await autotask.get_client(scope="global")


def test_normalize_company():
    normalized = autotask.AutotaskClient.normalize_company(
        {"id": 123, "companyName": "Acme Dental"}
    )

    assert normalized == {"id": "123", "name": "Acme Dental"}


@pytest.mark.asyncio
async def test_list_autotask_companies_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_active_companies(self):
            return [
                _company(2, "Zulu Dental"),
                _company(1, "Alpha Dental"),
                _company(None, "Missing ID"),
                _company(3, ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(autotask, "get_client", fake_get_client)

    result = await list_autotask_companies()

    assert result == [
        {"value": "1", "label": "Alpha Dental"},
        {"value": "2", "label": "Zulu Dental"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_autotask_customers_maps_unmapped_customers(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_active_companies(self):
            return [
                _company(100, "Already Mapped"),
                _company(200, "Existing Org"),
                _company(300, "New Org"),
                _company(None, "Broken Company"),
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
        assert name == "Autotask"
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

    monkeypatch.setattr(autotask, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_autotask_customers()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped company with no ID: {'id': None, 'companyName': 'Broken Company'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Autotask", "org-existing", "200", "Existing Org"),
        ("Autotask", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
