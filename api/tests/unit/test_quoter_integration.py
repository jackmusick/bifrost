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
from features.quoter.workflows.data_providers import list_quoter_organizations
from features.quoter.workflows.sync_organizations import sync_quoter_organizations
from modules import quoter


def _contact(organization: str | None) -> dict:
    return {
        "id": "cont_123",
        "organization": organization,
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Quoter"
        assert scope == "org-123"
        return SimpleNamespace(
            config={"client_id": "cid", "client_secret": "csecret"},
            entity_id="Acme Corp",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await quoter.get_client(scope="org-123")
    try:
        assert client.organization == "Acme Corp"
        assert client._base_url == quoter.QuoterClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"client_id": "cid"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="client_secret"):
        await quoter.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_quoter_organizations_returns_inferred_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def infer_organizations_from_contacts(self):
            return [
                {"id": "Alpha", "name": "Alpha"},
                {"id": "Zulu", "name": "Zulu"},
                {"id": "", "name": ""},
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(quoter, "get_client", fake_get_client)

    result = await list_quoter_organizations()

    assert result == [
        {"value": "Alpha", "label": "Alpha"},
        {"value": "Zulu", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_quoter_organizations_maps_unmapped_organizations(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def infer_organizations_from_contacts(self):
            return [
                {"id": "Already Mapped", "name": "Already Mapped"},
                {"id": "Existing Org", "name": "Existing Org"},
                {"id": "New Org", "name": "New Org"},
                {"id": "", "name": ""},
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
        assert name == "Quoter"
        return [SimpleNamespace(entity_id="Already Mapped")]

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

    monkeypatch.setattr(quoter, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_quoter_organizations()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped inferred organization with no ID: {'id': '', 'name': ''}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Quoter", "org-existing", "Existing Org", "Existing Org"),
        ("Quoter", "org-new", "New Org", "New Org"),
    ]
    assert fake_client.closed is True

