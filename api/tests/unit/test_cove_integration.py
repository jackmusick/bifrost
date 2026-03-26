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
from features.cove.workflows.data_providers import list_cove_customers
from features.cove.workflows.sync_customers import sync_cove_customers
from modules import cove


def _partner(partner_id: int | None, name: str | None, level: str | None) -> dict:
    partner: dict[str, object] = {}
    if partner_id is not None:
        partner["Id"] = partner_id
    if name is not None:
        partner["Name"] = name
    if level is not None:
        partner["Level"] = level
    return partner


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Cove Data Protection"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "partner_name": "Midtown Technology Group (doug@midtowntg.com)",
                "username": "MidBot",
                "password": "secret",
            },
            entity_id="2544869",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await cove.get_client(scope="org-123")
    try:
        assert client.partner_id == 2544869
        assert client.partner_name == "Midtown Technology Group (doug@midtowntg.com)"
        assert client.root_partner_id == cove.CoveClient.ROOT_PARTNER_ID
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_partner_username_and_password(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="partner_name, username, or password"):
        await cove.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_cove_customers_returns_sorted_endcustomers(monkeypatch):
    class FakeClient:
        async def enumerate_partners(self):
            return [
                _partner(2, "Zulu", "EndCustomer"),
                _partner(1, "Alpha", "EndCustomer"),
                _partner(3, "Parent MSP", "Reseller"),
                _partner(None, "Broken", "EndCustomer"),
                _partner(4, "", "EndCustomer"),
            ]

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(cove, "get_client", fake_get_client)

    result = await list_cove_customers()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_sync_cove_customers_maps_unmapped_endcustomers(monkeypatch):
    class FakeClient:
        async def enumerate_partners(self):
            return [
                _partner(100, "Already Mapped", "EndCustomer"),
                _partner(200, "Existing Org", "EndCustomer"),
                _partner(300, "New Org", "EndCustomer"),
                _partner(400, "Parent MSP", "Reseller"),
                _partner(None, "Broken Customer", "EndCustomer"),
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
        assert name == "Cove Data Protection"
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

    monkeypatch.setattr(cove, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_cove_customers()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped partner with no ID: {'Name': 'Broken Customer', 'Level': 'EndCustomer'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Cove Data Protection", "org-existing", "200", "Existing Org"),
        ("Cove Data Protection", "org-new", "300", "New Org"),
    ]
