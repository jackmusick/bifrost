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
from features.googleworkspace.workflows.sync_tenant import sync_google_workspace_tenant
from features.googleworkspacereseller.workflows.data_providers import (
    list_google_workspace_reseller_customers,
)
from features.googleworkspacereseller.workflows.sync_customers import (
    sync_google_workspace_reseller_customers,
)
from modules import googleworkspace


def _customer(customer_id: str | None, domain: str | None) -> dict:
    customer: dict[str, str] = {}
    if customer_id is not None:
        customer["customerId"] = customer_id
    if domain is not None:
        customer["customerDomain"] = domain
    return customer


@pytest.mark.asyncio
async def test_get_workspace_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Google Workspace"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "service_account_json": '{"client_email":"svc@example.com","private_key":"-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n"}',
                "delegated_admin_email": "admin@example.com",
            },
            entity_id="C012345",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await googleworkspace.get_workspace_client(scope="org-123")
    try:
        assert client.customer_id == "C012345"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_reseller_client_requires_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"delegated_admin_email": "admin@example.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="service_account_json"):
        await googleworkspace.get_reseller_client(scope="global")


@pytest.mark.asyncio
async def test_list_google_workspace_reseller_customers_returns_sorted_options(monkeypatch):
    class FakeClient:
        async def list_customers(self):
            return [
                _customer("2", "zulu.example.com"),
                _customer("1", "alpha.example.com"),
                _customer("", "missing-id.example.com"),
                _customer("3", ""),
            ]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(googleworkspace, "get_reseller_client", fake_get_client)

    result = await list_google_workspace_reseller_customers()

    assert result == [
        {"value": "1", "label": "alpha.example.com"},
        {"value": "2", "label": "zulu.example.com"},
    ]


@pytest.mark.asyncio
async def test_sync_google_workspace_reseller_customers_maps_unmapped_customers(monkeypatch):
    class FakeClient:
        async def list_customers(self):
            return [
                _customer("100", "mapped.example.com"),
                _customer("200", "existing.example.com"),
                _customer("300", "new.example.com"),
                _customer(None, "broken.example.com"),
            ]

        async def close(self) -> None:
            return None

    created_names: list[str] = []
    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    async def fake_list_mappings(name: str):
        assert name == "Google Workspace Reseller"
        return [SimpleNamespace(entity_id="100")]

    async def fake_list_orgs():
        return [SimpleNamespace(id="org-existing", name="existing.example.com")]

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

    monkeypatch.setattr(googleworkspace, "get_reseller_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_google_workspace_reseller_customers()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped customer with no ID: {'customerDomain': 'broken.example.com'}"],
    }
    assert created_names == ["new.example.com"]
    assert mapping_calls == [
        ("Google Workspace Reseller", "org-existing", "200", "existing.example.com"),
        ("Google Workspace Reseller", "org-new", "300", "new.example.com"),
    ]


@pytest.mark.asyncio
async def test_sync_google_workspace_tenant_upserts_mapping_for_current_org(monkeypatch):
    class FakeClient:
        async def get_tenant_summary(self):
            return {
                "customer": {
                    "id": "C999999",
                    "customerDomain": "tenant.example.com",
                },
                "domains": [{"domainName": "tenant.example.com", "isPrimary": True}],
            }

        async def close(self) -> None:
            return None

    mapping_calls: list[tuple[str, str, str, str]] = []

    async def fake_get_client(scope: str | None = None):
        assert scope == "org-123"
        return FakeClient()

    async def fake_get_org(org_id: str):
        assert org_id == "org-123"
        return SimpleNamespace(id=org_id, name="Tenant Org")

    async def fake_upsert_mapping(
        name: str,
        *,
        scope: str,
        entity_id: str,
        entity_name: str,
    ):
        mapping_calls.append((name, scope, entity_id, entity_name))

    monkeypatch.setattr(googleworkspace, "get_workspace_client", fake_get_client)
    monkeypatch.setattr(organizations, "get", fake_get_org)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)

    result = await sync_google_workspace_tenant("org-123")

    assert result == {
        "org_id": "org-123",
        "org_name": "Tenant Org",
        "customer_id": "C999999",
        "customer_name": "tenant.example.com",
        "primary_domain": "tenant.example.com",
        "domain_count": 1,
    }
    assert mapping_calls == [
        ("Google Workspace", "org-123", "C999999", "tenant.example.com"),
    ]
