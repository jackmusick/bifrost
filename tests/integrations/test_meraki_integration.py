from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bifrost import integrations, organizations
from features.meraki.workflows.audit_admin_coverage import (
    audit_meraki_admin_coverage,
)
from features.meraki.workflows.baseline_admins import (
    audit_meraki_admins_against_baseline,
    remove_meraki_admin_across_organizations,
    sync_meraki_admins_from_baseline,
)
from features.meraki.workflows.data_providers import list_meraki_organizations
from features.meraki.workflows.sync_organizations import sync_meraki_organizations
from modules import meraki


def _organization(organization_id: str | None, name: str | None) -> dict:
    payload: dict[str, str | None] = {
        "id": organization_id,
        "name": name,
    }
    return payload


def _admin(
    email: str,
    *,
    name: str | None = None,
    account_status: str = "ok",
    org_access: str = "full",
) -> dict:
    return {
        "id": email,
        "name": name or email.split("@", 1)[0],
        "email": email,
        "accountStatus": account_status,
        "orgAccess": org_access,
        "tags": [],
        "networks": [],
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Meraki"
        assert scope == "org-123"
        return SimpleNamespace(config={"api_key": "secret-key"}, entity_id=42)

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await meraki.get_client(scope="org-123")
    try:
        assert client.organization_id == "42"
        assert client._base_url == meraki.MerakiClient.BASE_URL
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_api_key(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={}, entity_id=None)

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await meraki.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_meraki_organizations_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_organizations(self):
            return [
                _organization("2", "Zulu"),
                _organization("1", "Alpha"),
                _organization("", "Missing ID"),
                _organization("3", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await list_meraki_organizations()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_meraki_organizations_maps_unmapped_organizations(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_organizations(self):
            return [
                _organization("100", "Already Mapped"),
                _organization("200", "Existing Org"),
                _organization("300", "New Org"),
                _organization(None, "Broken Org"),
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
        assert name == "Meraki"
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

    monkeypatch.setattr(meraki, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_meraki_organizations()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped organization with no ID: {'id': None, 'name': 'Broken Org'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Meraki", "org-existing", "200", "Existing Org"),
        ("Meraki", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_audit_meraki_admin_coverage_infers_expected_emails(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_organizations(self):
            return [
                _organization("100", "Alpha"),
                _organization("200", "Beta"),
                _organization("300", "Gamma"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [
                    _admin("alice@midtowntg.com"),
                    _admin("bob@midtowntg.com"),
                    _admin("client@example.com"),
                ],
                "200": [
                    _admin("alice@midtowntg.com"),
                    _admin("client2@example.com"),
                ],
                "300": [
                    _admin("client3@example.com"),
                ],
            }[organization_id]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await audit_meraki_admin_coverage(
        internal_email_domain="midtowntg.com",
        min_presence_ratio=1.0,
    )

    assert result["expected_admins_source"] == "inferred"
    assert result["expected_admins"] == ["alice@midtowntg.com"]
    assert result["organizations_total"] == 3
    assert result["organizations_with_internal_admins"] == 2
    assert result["organizations_missing_expected_admins"] == [
        {
            "organization_id": "300",
            "organization_name": "Gamma",
            "missing_admins": ["alice@midtowntg.com"],
            "current_internal_admins": [],
            "total_admin_count": 1,
            "all_admin_emails": ["client3@example.com"],
        }
    ]
    assert result["organizations_with_no_internal_admins"] == [
        {
            "organization_id": "300",
            "organization_name": "Gamma",
            "total_admin_count": 1,
            "all_admin_emails": ["client3@example.com"],
        }
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_audit_meraki_admin_coverage_honors_explicit_email_list(monkeypatch):
    class FakeClient:
        async def list_organizations(self):
            return [
                _organization("100", "Alpha"),
                _organization("200", "Beta"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [
                    _admin("alice@midtowntg.com"),
                    _admin("bob@midtowntg.com"),
                ],
                "200": [
                    _admin("alice@midtowntg.com"),
                ],
            }[organization_id]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = None):
        return FakeClient()

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await audit_meraki_admin_coverage(
        internal_email_domain="midtowntg.com",
        required_admin_emails_csv="alice@midtowntg.com, bob@midtowntg.com",
    )

    assert result["expected_admins_source"] == "explicit"
    assert result["expected_admins"] == [
        "alice@midtowntg.com",
        "bob@midtowntg.com",
    ]
    assert result["organizations_missing_expected_admins"] == [
        {
            "organization_id": "200",
            "organization_name": "Beta",
            "missing_admins": ["bob@midtowntg.com"],
            "current_internal_admins": ["alice@midtowntg.com"],
            "total_admin_count": 1,
            "all_admin_emails": ["alice@midtowntg.com"],
        }
    ]


@pytest.mark.asyncio
async def test_audit_meraki_admins_against_baseline(monkeypatch):
    class FakeClient:
        async def list_organizations(self):
            return [
                _organization("100", "Midtown Technology Group"),
                _organization("200", "Alpha"),
                _organization("300", "Beta"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("bob@midtowntg.com", name="Bob"),
                ],
                "200": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("client@example.com", name="Client"),
                ],
                "300": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("bob@midtowntg.com", name="Bob"),
                    _admin("extra@example.com", name="Extra"),
                ],
            }[organization_id]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return FakeClient()

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await audit_meraki_admins_against_baseline(
        baseline_org_name="Midtown Technology Group",
        required_admin_emails_csv="alice@midtowntg.com,bob@midtowntg.com",
        extra_valid_admin_emails_csv="",
    )

    assert result["baseline_admins"] == [
        "alice@midtowntg.com",
        "bob@midtowntg.com",
    ]
    assert result["disparities"] == [
        {
            "organization_id": "200",
            "organization_name": "Alpha",
            "missing_admins": ["bob@midtowntg.com"],
            "extra_admins": ["client@example.com"],
            "admin_count": 2,
        },
        {
            "organization_id": "300",
            "organization_name": "Beta",
            "missing_admins": [],
            "extra_admins": ["extra@example.com"],
            "admin_count": 3,
        },
    ]


@pytest.mark.asyncio
async def test_audit_meraki_admins_against_baseline_excludes_orgs(monkeypatch):
    class FakeClient:
        async def list_organizations(self):
            return [
                _organization("100", "Midtown Technology Group"),
                _organization("200", "Alpha"),
                _organization("300", "Legacy Org"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [
                    _admin("alice@midtowntg.com", name="Alice"),
                ],
                "200": [],
                "300": [],
            }[organization_id]

        async def close(self) -> None:
            return None

    async def fake_get_client(scope: str | None = None):
        return FakeClient()

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await audit_meraki_admins_against_baseline(
        baseline_org_name="Midtown Technology Group",
        required_admin_emails_csv="alice@midtowntg.com",
        extra_valid_admin_emails_csv="",
        excluded_org_names_csv="Legacy Org",
    )

    assert result["excluded_org_names"] == ["legacy org"]
    assert result["skipped_excluded"] == [
        {
            "organization_id": "300",
            "organization_name": "Legacy Org",
        }
    ]
    assert result["organizations_audited"] == 2
    assert result["disparities"] == [
        {
            "organization_id": "200",
            "organization_name": "Alpha",
            "missing_admins": ["alice@midtowntg.com"],
            "extra_admins": [],
            "admin_count": 0,
        }
    ]


@pytest.mark.asyncio
async def test_sync_meraki_admins_from_baseline_creates_missing(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.created: list[dict] = []
            self.updated: list[dict] = []

        async def list_organizations(self):
            return [
                _organization("100", "Midtown Technology Group"),
                _organization("200", "Alpha"),
                _organization("300", "Beta"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("bob@midtowntg.com", name="Bob"),
                ],
                "200": [
                    _admin("alice@midtowntg.com", name="Alice"),
                ],
                "300": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("bob@midtowntg.com", name="Old Bob", org_access="read-only"),
                ],
            }[organization_id]

        async def create_organization_admin(self, organization_id: str, **kwargs):
            self.created.append({"organization_id": organization_id, **kwargs})
            return {}

        async def update_organization_admin(self, organization_id: str, **kwargs):
            self.updated.append({"organization_id": organization_id, **kwargs})
            return {}

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await sync_meraki_admins_from_baseline(
        baseline_org_name="Midtown Technology Group",
        required_admin_emails_csv="bob@midtowntg.com",
        dry_run=False,
    )

    assert result["created"] == [
        {
            "organization_id": "200",
            "organization_name": "Alpha",
            "email": "bob@midtowntg.com",
            "action": "create",
        }
    ]
    assert result["updated"] == [
        {
            "organization_id": "300",
            "organization_name": "Beta",
            "email": "bob@midtowntg.com",
            "action": "update",
            "drift": {
                "name": {"current": "Old Bob", "desired": "Bob"},
                "orgAccess": {"current": "read-only", "desired": "full"},
            },
        }
    ]
    assert fake_client.created == [
        {
            "organization_id": "200",
            "email": "bob@midtowntg.com",
            "name": "Bob",
            "org_access": "full",
            "tags": [],
            "networks": [],
        }
    ]
    assert fake_client.updated == [
        {
            "organization_id": "300",
            "admin_id": "bob@midtowntg.com",
            "name": "Bob",
            "org_access": "full",
            "tags": [],
            "networks": [],
        }
    ]


@pytest.mark.asyncio
async def test_sync_meraki_admins_from_baseline_excludes_orgs(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.created: list[dict] = []

        async def list_organizations(self):
            return [
                _organization("100", "Midtown Technology Group"),
                _organization("200", "Alpha"),
                _organization("300", "Legacy Org"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [_admin("alice@midtowntg.com", name="Alice")],
                "200": [],
                "300": [],
            }[organization_id]

        async def create_organization_admin(self, organization_id: str, **kwargs):
            self.created.append({"organization_id": organization_id, **kwargs})
            return {}

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await sync_meraki_admins_from_baseline(
        baseline_org_name="Midtown Technology Group",
        required_admin_emails_csv="alice@midtowntg.com",
        excluded_org_names_csv="Legacy Org",
        dry_run=False,
    )

    assert result["excluded_org_names"] == ["legacy org"]
    assert result["skipped_excluded"] == [
        {
            "organization_id": "300",
            "organization_name": "Legacy Org",
        }
    ]
    assert result["created"] == [
        {
            "organization_id": "200",
            "organization_name": "Alpha",
            "email": "alice@midtowntg.com",
            "action": "create",
        }
    ]
    assert fake_client.created == [
        {
            "organization_id": "200",
            "email": "alice@midtowntg.com",
            "name": "Alice",
            "org_access": "full",
            "tags": [],
            "networks": [],
        }
    ]


@pytest.mark.asyncio
async def test_remove_meraki_admin_across_organizations(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.deleted: list[dict] = []

        async def list_organizations(self):
            return [
                _organization("100", "Midtown Technology Group"),
                _organization("200", "Alpha"),
                _organization("300", "Legacy Org"),
            ]

        async def list_organization_admins(self, organization_id: str, **_: object):
            return {
                "100": [_admin("alice@midtowntg.com", name="Alice")],
                "200": [
                    _admin("alice@midtowntg.com", name="Alice"),
                    _admin("tleuke@midtowntg.com", name="Typo"),
                ],
                "300": [
                    _admin("tleuke@midtowntg.com", name="Typo"),
                ],
            }[organization_id]

        async def delete_organization_admin(self, organization_id: str, *, admin_id: str):
            self.deleted.append(
                {
                    "organization_id": organization_id,
                    "admin_id": admin_id,
                }
            )

        async def close(self) -> None:
            return None

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        return fake_client

    monkeypatch.setattr(meraki, "get_client", fake_get_client)

    result = await remove_meraki_admin_across_organizations(
        admin_email="tleuke@midtowntg.com",
        excluded_org_names_csv="Legacy Org",
        dry_run=False,
    )

    assert result["admin_email"] == "tleuke@midtowntg.com"
    assert result["removed"] == [
        {
            "organization_id": "200",
            "organization_name": "Alpha",
            "email": "tleuke@midtowntg.com",
            "admin_id": "tleuke@midtowntg.com",
        }
    ]
    assert result["skipped_excluded"] == [
        {
            "organization_id": "300",
            "organization_name": "Legacy Org",
        }
    ]
    assert fake_client.deleted == [
        {
            "organization_id": "200",
            "admin_id": "tleuke@midtowntg.com",
        }
    ]
