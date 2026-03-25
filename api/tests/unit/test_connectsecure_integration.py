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
from features.connectsecure.workflows.data_providers import list_connectsecure_companies
from features.connectsecure.workflows.sync_companies import sync_connectsecure_companies
from modules import connectsecure


def _company(company_id: str | None, name: str | None) -> dict:
    return {
        "id": company_id,
        "name": name,
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "ConnectSecure"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_uri": "https://api.myconnectsecure.com",
                "pod_id": "pod103",
                "tenant": "midtowntg",
                "api_key": "cid",
                "api_secret": "secret",
            },
            entity_id=42,
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await connectsecure.get_client(scope="org-123")
    try:
        assert client.company_id == "42"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_uri": "https://api.myconnectsecure.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="pod_id"):
        await connectsecure.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_connectsecure_companies_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_companies(self):
            return [
                _company("2", "Zulu"),
                _company("1", "Alpha"),
                _company("", "Missing ID"),
                _company("3", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(connectsecure, "get_client", fake_get_client)

    result = await list_connectsecure_companies()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_connectsecure_companies_maps_unmapped_companies(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_companies(self):
            return [
                _company("100", "Already Mapped"),
                _company("200", "Existing Org"),
                _company("300", "New Org"),
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
        assert name == "ConnectSecure"
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

    monkeypatch.setattr(connectsecure, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_connectsecure_companies()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped company with no ID: {'id': None, 'name': 'Broken Company'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("ConnectSecure", "org-existing", "200", "Existing Org"),
        ("ConnectSecure", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True

