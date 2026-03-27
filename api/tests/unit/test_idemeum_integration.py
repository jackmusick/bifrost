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
from features.idemeum.workflows.data_providers import list_idemeum_customers
from features.idemeum.workflows.sync_customers import sync_idemeum_customers
from modules import idemeum


def _customer(
    customer_id: str | None,
    slug: str | None,
    display_name: str | None,
) -> dict:
    return {
        "id": customer_id,
        "name": slug,
        "displayName": display_name,
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Idemeum"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_url": "https://midtowntg.idemeum.com",
                "api_key": "secret",
            },
            entity_id="cust-123",
            entity_name="Acme Dental",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await idemeum.get_client(scope="org-123")
    try:
        assert client.customer_id == "cust-123"
        assert client.customer_name == "Acme Dental"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_url": "https://midtowntg.idemeum.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await idemeum.get_client(scope="global")


def test_normalize_customer_prefers_display_name():
    normalized = idemeum.IdemeumClient.normalize_customer(
        {
            "id": "cust-1",
            "name": "acme",
            "displayName": "Acme Dental",
            "url": "https://acme.idemeum.com",
        }
    )

    assert normalized == {
        "id": "cust-1",
        "name": "Acme Dental",
        "slug": "acme",
        "url": "https://acme.idemeum.com",
    }


@pytest.mark.asyncio
async def test_list_idemeum_customers_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_customers(self):
            return [
                _customer("2", "zulu", "Zulu Dental"),
                _customer("1", "alpha", "Alpha Dental"),
                _customer("", "broken", "Missing ID"),
                _customer("3", "nameless", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(idemeum, "get_client", fake_get_client)

    result = await list_idemeum_customers()

    assert result == [
        {"value": "1", "label": "Alpha Dental"},
        {"value": "2", "label": "Zulu Dental"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_idemeum_customers_maps_unmapped_customers(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_customers(self):
            return [
                _customer("100", "mapped", "Already Mapped"),
                _customer("200", "existing-org", "Existing Org"),
                _customer("300", "new-org", "New Org"),
                _customer(None, "broken", "Broken Customer"),
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
        assert name == "Idemeum"
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

    monkeypatch.setattr(idemeum, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_idemeum_customers()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped customer with no ID: {'id': None, 'name': 'broken', 'displayName': 'Broken Customer'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Idemeum", "org-existing", "200", "Existing Org"),
        ("Idemeum", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
