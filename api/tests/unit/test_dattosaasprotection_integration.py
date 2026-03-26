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
from features.dattosaasprotection.workflows.data_providers import list_dattosaas_domains
from features.dattosaasprotection.workflows.sync_domains import sync_dattosaas_domains
from modules import dattosaasprotection


def _domain(
    domain_id: str | None,
    saas_customer_id: str | None,
    organization_name: str | None,
    domain_name: str | None,
) -> dict:
    item: dict[str, str] = {}
    if domain_id is not None:
        item["id"] = domain_id
    if saas_customer_id is not None:
        item["saasCustomerId"] = saas_customer_id
    if organization_name is not None:
        item["organizationName"] = organization_name
    if domain_name is not None:
        item["domain"] = domain_name
    return item


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Datto SaaS Protection"
        assert scope == "org-123"
        return SimpleNamespace(
            config={"api_key": "key", "api_secret": "secret"},
            entity_id="domain-42",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await dattosaasprotection.get_client(scope="org-123")
    try:
        assert client.saas_customer_id == "domain-42"
        assert client.domain_id == "domain-42"
        assert client._base_url == dattosaasprotection.DattoSaaSProtectionClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key or api_secret"):
        await dattosaasprotection.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_dattosaas_domains_returns_sorted_options(monkeypatch):
    class FakeClient:
        async def list_domains(self):
            return [
                _domain("legacy-2", "2", "Zulu", "zulu.example.com"),
                _domain("legacy-1", "1", "Alpha", "alpha.example.com"),
                _domain("", "", "Missing ID", "missing.example.com"),
                _domain("legacy-3", "3", None, None),
            ]

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(dattosaasprotection, "get_client", fake_get_client)

    result = await list_dattosaas_domains()

    assert result == [
        {"value": "1", "label": "Alpha (alpha.example.com)"},
        {"value": "2", "label": "Zulu (zulu.example.com)"},
    ]


@pytest.mark.asyncio
async def test_sync_dattosaas_domains_maps_unmapped_domains(monkeypatch):
    class FakeClient:
        async def list_domains(self):
            return [
                _domain("legacy-100", "100", "Already Mapped", "mapped.example.com"),
                _domain("legacy-200", "200", "Existing Org", "existing.example.com"),
                _domain("legacy-300", "300", "New Org", "new.example.com"),
                _domain(None, None, "Broken Domain", "broken.example.com"),
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
        assert name == "Datto SaaS Protection"
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

    monkeypatch.setattr(dattosaasprotection, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_dattosaas_domains()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped domain with no ID: {'organizationName': 'Broken Domain', 'domain': 'broken.example.com'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Datto SaaS Protection", "org-existing", "200", "Existing Org (existing.example.com)"),
        ("Datto SaaS Protection", "org-new", "300", "New Org (new.example.com)"),
    ]


@pytest.mark.asyncio
async def test_list_seats_uses_mapped_saas_customer_id():
    client = dattosaasprotection.DattoSaaSProtectionClient(
        api_key="key",
        api_secret="secret",
        saas_customer_id="53124",
    )

    async def fake_request(method: str, path: str, *, params=None):
        assert method == "GET"
        assert path == "/saas/53124/seats"
        assert params == {"seatType": "User,SharedMailbox"}
        return [{"mainId": "user@example.com", "seatType": "User"}]

    client._request = fake_request  # type: ignore[method-assign]
    try:
        result = await client.list_seats(seat_type=["User", "SharedMailbox"])
    finally:
        await client.close()

    assert result == [{"mainId": "user@example.com", "seatType": "User"}]


@pytest.mark.asyncio
async def test_list_applications_extracts_items_from_payload():
    client = dattosaasprotection.DattoSaaSProtectionClient(
        api_key="key",
        api_secret="secret",
        saas_customer_id="53124",
    )

    async def fake_request(method: str, path: str, *, params=None):
        assert method == "GET"
        assert path == "/saas/53124/applications"
        assert params == {"daysUntil": 7}
        return {
            "pagination": {"total": 1},
            "items": [{"customerId": 53124, "customerName": "Alpha"}],
        }

    client._request = fake_request  # type: ignore[method-assign]
    try:
        result = await client.list_applications(days_until=7)
    finally:
        await client.close()

    assert result == [{"customerId": 53124, "customerName": "Alpha"}]
