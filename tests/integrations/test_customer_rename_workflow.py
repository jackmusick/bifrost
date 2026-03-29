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
from features.customer_rename.workflows.execute_rename import execute_customer_rename
from features.customer_rename.workflows.get_rename_plan import get_customer_rename_plan


class _FakeAutotaskClient:
    def __init__(self, company: dict):
        self._company = company
        self.closed = False

    async def get_company(self, company_id: str):
        assert company_id == str(self._company["id"])
        return self._company

    async def close(self):
        self.closed = True


class _FakeDNSFilterClient:
    def __init__(self, networks: dict[str, dict]):
        self._networks = networks
        self.closed = False

    async def get_network(self, network_id: str):
        return self._networks[network_id]

    async def close(self):
        self.closed = True


class _FakeDattoSaaSClient:
    def __init__(self, domains: list[dict]):
        self._domains = domains
        self.closed = False

    async def list_domains(self):
        return self._domains

    async def close(self):
        self.closed = True


class _FakeVipreClient:
    def __init__(self, sites: list[dict]):
        self._sites = sites
        self.closed = False

    async def infer_sites_from_devices(self):
        return self._sites

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_get_customer_rename_plan_by_org(monkeypatch):
    fake_org = SimpleNamespace(id="org-123", name="Old Customer Name")
    fake_autotask_mapping = SimpleNamespace(
        id="mapping-autotask",
        organization_id="org-123",
        entity_id="456",
        entity_name="AutoTask Current Name",
    )
    fake_ninja_mapping = SimpleNamespace(
        id="mapping-ninja",
        organization_id="org-123",
        entity_id="999",
        entity_name="Ninja Old Name",
    )
    fake_meraki_mapping = SimpleNamespace(
        id="mapping-meraki",
        organization_id="org-123",
        entity_id="654",
        entity_name="Source Of Truth Name",
    )
    fake_cove_mapping = SimpleNamespace(
        id="mapping-cove",
        organization_id="org-123",
        entity_id="777",
        entity_name="Source Of Truth Name",
    )
    fake_dattormm_mapping = SimpleNamespace(
        id="mapping-dattormm",
        organization_id="org-123",
        entity_id="888",
        entity_name="Old Customer Name ",
    )
    fake_halopsa_mapping = SimpleNamespace(
        id="mapping-halopsa",
        organization_id="org-123",
        entity_id="222",
        entity_name="Source Of Truth Name",
    )
    fake_huntress_mapping = SimpleNamespace(
        id="mapping-huntress",
        organization_id="org-123",
        entity_id="333",
        entity_name="Old Huntress Name",
    )
    fake_dnsfilter_mapping = SimpleNamespace(
        id="mapping-dnsfilter",
        organization_id="org-123",
        entity_id="1203473",
        entity_name="Park Woody Vaughan, P.C.",
        config={"network_ids": ["1244044"]},
    )
    fake_connectsecure_mapping = SimpleNamespace(
        id="mapping-connectsecure",
        organization_id="org-123",
        entity_id="2541",
        entity_name="Old ConnectSecure Name",
    )
    fake_pax8_mapping = SimpleNamespace(
        id="mapping-pax8",
        organization_id="org-123",
        entity_id="735496a8-d0e9-44bb-89e1-176298c1b2ad",
        entity_name="Old Pax8 Name",
    )

    async def fake_get_org(org_id: str):
        assert org_id == "org-123"
        return fake_org

    async def fake_get_mapping(name: str, scope: str | None = None, entity_id: str | None = None):
        assert entity_id is None
        assert scope == "org-123"
        if name == "Autotask":
            return fake_autotask_mapping
        if name == "Meraki":
            return fake_meraki_mapping
        if name == "Cove Data Protection":
            return fake_cove_mapping
        if name == "Datto RMM":
            return fake_dattormm_mapping
        if name == "HaloPSA":
            return fake_halopsa_mapping
        if name == "Huntress":
            return fake_huntress_mapping
        if name == "DNSFilter":
            return fake_dnsfilter_mapping
        if name == "ConnectSecure":
            return fake_connectsecure_mapping
        if name == "Pax8":
            return fake_pax8_mapping
        if name == "NinjaOne":
            return fake_ninja_mapping
        return None

    async def fake_list_integration_names():
        return [
            "Autotask",
            "ConnectSecure",
            "Cove Data Protection",
            "Datto RMM",
            "DNSFilter",
            "HaloPSA",
            "Huntress",
            "Meraki",
            "NinjaOne",
            "Pax8",
        ]

    async def fake_get_autotask_client(scope: str | None = None):
        assert scope == "org-123"
        return _FakeAutotaskClient({"id": 456, "companyName": "Source Of Truth Name"})

    async def fake_get_dnsfilter_client(scope: str | None = None):
        assert scope == "org-123"
        return _FakeDNSFilterClient(
            {
                "1244044": {
                    "id": "1244044",
                    "attributes": {"name": "Park Woody Vaughan Primary Office"},
                    "relationships": {"organization": {"data": {"id": "1203473"}}},
                }
            }
        )

    async def fake_get_dattosaas_client(scope: str | None = None):
        assert scope == "global"
        return _FakeDattoSaaSClient(
            [
                {
                    "saasCustomerId": "53124",
                    "organizationName": "Unrelated Customer",
                    "domain": "unrelated.example.com",
                }
            ]
        )

    async def fake_get_vipre_client(scope: str | None = None):
        assert scope == "global"
        return _FakeVipreClient(
            [{"id": "bb1565ca-f312-43b8-af4c-5d7d76956680", "name": "findlingpark.myvipre.com"}]
        )

    monkeypatch.setattr(organizations, "get", fake_get_org)
    monkeypatch.setattr(integrations, "get_mapping", fake_get_mapping)
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan._list_integration_names",
        fake_list_integration_names,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_autotask_client",
        fake_get_autotask_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_dnsfilter_client",
        fake_get_dnsfilter_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_dattosaasprotection_client",
        fake_get_dattosaas_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_vipre_client",
        fake_get_vipre_client,
    )

    plan = await get_customer_rename_plan(organization_id="org-123")

    assert plan["organization"] == {"id": "org-123", "name": "Old Customer Name"}
    assert plan["autotask"] == {
        "company_id": "456",
        "current_name": "Source Of Truth Name",
        "desired_name": "Source Of Truth Name",
        "needs_update": False,
        "mapping_id": "mapping-autotask",
    }
    assert plan["systems"][0]["system"] == "Autotask"
    assert plan["systems"][0]["status"] == "ready"
    assert plan["systems"][0]["needs_change"] is False
    assert plan["systems"][1]["system"] == "Bifrost"
    assert plan["systems"][1]["status"] == "ready"
    assert plan["systems"][1]["needs_change"] is True
    assert plan["systems"][2]["system"] == "ConnectSecure"
    assert all(item["system"] != "IT Glue" for item in plan["systems"])
    assert plan["systems"][2]["status"] == "ready"
    assert plan["systems"][2]["needs_change"] is True
    assert plan["systems"][2]["notes"] == ["Rename can be executed directly in ConnectSecure."]
    assert plan["systems"][3]["system"] == "Cove Data Protection"
    assert plan["systems"][3]["status"] == "ready"
    assert plan["systems"][3]["needs_change"] is False
    assert plan["systems"][4]["system"] == "Datto RMM"
    assert plan["systems"][4]["status"] == "ready"
    assert plan["systems"][4]["needs_change"] is True
    assert plan["systems"][5]["system"] == "DNSFilter"
    assert plan["systems"][5]["status"] == "ready"
    assert plan["systems"][5]["needs_change"] is True
    assert plan["systems"][5]["mapping_config"] == {
        "network_ids": ["1244044"],
        "network_actions": [
            {
                "network_id": "1244044",
                "current_name": "Park Woody Vaughan Primary Office",
                "target_name": "Source Of Truth Name Primary Office",
                "needs_change": True,
            }
        ],
    }
    assert "Mapped DNSFilter organization currently contains 1 network." in plan["systems"][5]["notes"]
    assert "1 DNSFilter network will also be renamed." in plan["systems"][5]["notes"]
    assert plan["systems"][6]["system"] == "HaloPSA"
    assert plan["systems"][6]["status"] == "ready"
    assert plan["systems"][6]["needs_change"] is False
    assert plan["systems"][7]["system"] == "Huntress"
    assert plan["systems"][7]["status"] == "ready"
    assert plan["systems"][7]["needs_change"] is True
    assert plan["systems"][8]["system"] == "Meraki"
    assert plan["systems"][8]["status"] == "ready"
    assert plan["systems"][8]["needs_change"] is False
    assert plan["systems"][9]["system"] == "NinjaOne"
    assert plan["systems"][9]["status"] == "ready"
    assert plan["systems"][9]["needs_change"] is True
    assert plan["systems"][10]["system"] == "Pax8"
    assert plan["systems"][10]["status"] == "ready"
    assert plan["systems"][10]["needs_change"] is True
    assert plan["systems"][10]["notes"] == ["Rename can be executed directly in Pax8."]
    assert {item["system"] for item in plan["audit_follow_up"]} == {
        "Datto SaaS Protection",
        "Datto Networking",
        "VIPRE",
    }
    datto_note = next(item["note"] for item in plan["audit_follow_up"] if item["system"] == "Datto SaaS Protection")
    assert datto_note == "Checked protected customer/domain inventory; no obvious match found."
    vipre_note = next(item["note"] for item in plan["audit_follow_up"] if item["system"] == "VIPRE")
    assert vipre_note == (
        "VIPRE footprint found via inferred site host findlingpark.myvipre.com "
        "(siteUuid bb1565ca-f312-43b8-af4c-5d7d76956680). "
        "Manual review required; no validated site rename path is implemented."
    )
    assert "Manual follow-up likely required for:" not in plan["ticket_preview"]["description"]
    assert "Audit recommended for potentially unmanaged presence:" in plan["ticket_preview"]["description"]


@pytest.mark.asyncio
async def test_get_customer_rename_plan_audit_failures_degrade_to_notes(monkeypatch):
    fake_org = SimpleNamespace(id="org-123", name="Old Customer Name")
    fake_autotask_mapping = SimpleNamespace(
        id="mapping-autotask",
        organization_id="org-123",
        entity_id="456",
        entity_name="AutoTask Current Name",
    )

    async def fake_get_org(org_id: str):
        return fake_org

    async def fake_get_mapping(name: str, scope: str | None = None, entity_id: str | None = None):
        if name == "Autotask":
            return fake_autotask_mapping
        return None

    async def fake_list_integration_names():
        return ["Autotask"]

    async def fake_get_autotask_client(scope: str | None = None):
        return _FakeAutotaskClient({"id": 456, "companyName": "Source Of Truth Name"})

    class _FailingDattoSaaSClient:
        async def list_domains(self):
            raise RuntimeError("dattosaas timeout")

        async def close(self):
            return None

    class _FailingVipreClient:
        async def infer_sites_from_devices(self):
            raise RuntimeError("vipre timeout")

        async def close(self):
            return None

    async def fake_get_dattosaas_client(scope: str | None = None):
        return _FailingDattoSaaSClient()

    async def fake_get_vipre_client(scope: str | None = None):
        return _FailingVipreClient()

    monkeypatch.setattr(organizations, "get", fake_get_org)
    monkeypatch.setattr(integrations, "get_mapping", fake_get_mapping)
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan._list_integration_names",
        fake_list_integration_names,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_autotask_client",
        fake_get_autotask_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_dattosaasprotection_client",
        fake_get_dattosaas_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_vipre_client",
        fake_get_vipre_client,
    )

    plan = await get_customer_rename_plan(organization_id="org-123")

    assert {"system": "Datto SaaS Protection", "note": "Audit could not be completed automatically: dattosaas timeout"} in plan["audit_follow_up"]
    assert {"system": "VIPRE", "note": "Audit could not be completed automatically: vipre timeout"} in plan["audit_follow_up"]


@pytest.mark.asyncio
async def test_get_customer_rename_plan_by_autotask_company_with_override(monkeypatch):
    fake_org = SimpleNamespace(id="org-456", name="Current Org")
    fake_autotask_mapping = SimpleNamespace(
        id="mapping-autotask",
        organization_id="org-456",
        entity_id="789",
        entity_name="Old PSA Name",
    )

    async def fake_get_org(org_id: str):
        assert org_id == "org-456"
        return fake_org

    async def fake_get_mapping(name: str, scope: str | None = None, entity_id: str | None = None):
        if name != "Autotask":
            return None
        if entity_id is not None:
            assert entity_id == "789"
            return fake_autotask_mapping
        assert scope == "org-456"
        return fake_autotask_mapping

    async def fake_list_integration_names():
        return ["Autotask"]

    async def fake_get_autotask_client(scope: str | None = None):
        assert scope == "org-456"
        return _FakeAutotaskClient({"id": 789, "companyName": "Old PSA Name"})

    monkeypatch.setattr(organizations, "get", fake_get_org)
    monkeypatch.setattr(integrations, "get_mapping", fake_get_mapping)
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan._list_integration_names",
        fake_list_integration_names,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.get_rename_plan.get_autotask_client",
        fake_get_autotask_client,
    )

    plan = await get_customer_rename_plan(
        autotask_company_id="789",
        desired_name="New Canonical Name",
        create_ticket_preview=False,
    )

    assert plan["autotask"]["needs_update"] is True
    assert plan["autotask"]["desired_name"] == "New Canonical Name"
    assert plan["ticket_preview"] is None
    assert plan["systems"] == [
        {
            "system": "Autotask",
            "mapping_id": "mapping-autotask",
            "entity_id": "789",
            "current_name": "Old PSA Name",
            "target_name": "New Canonical Name",
            "status": "ready",
            "needs_change": True,
            "notes": ["Rename can be executed directly in AutoTask."],
            "mapping_config": None,
        },
        {
            "system": "Bifrost",
            "mapping_id": None,
            "entity_id": "org-456",
            "current_name": "Current Org",
            "target_name": "New Canonical Name",
            "status": "ready",
            "needs_change": True,
            "notes": ["Rename can be executed directly in Bifrost."],
            "mapping_config": None,
        },
    ]


@pytest.mark.asyncio
async def test_execute_customer_rename_dry_run(monkeypatch):
    async def fake_plan(**kwargs):
        return {
            "organization": {"id": "org-1", "name": "Old Name"},
            "autotask": {
                "company_id": "123",
                "current_name": "Old Name",
                "desired_name": "New Name",
                "needs_update": True,
                "mapping_id": "mapping-1",
            },
            "change_reason": None,
            "systems": [
                {
                    "system": "Bifrost",
                    "mapping_id": None,
                    "entity_id": "org-1",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                }
            ],
            "audit_follow_up": [
                {
                    "system": "Datto SaaS Protection",
                    "note": "Audit for unmanaged presence. Current repo surface is read-only.",
                },
                {
                    "system": "VIPRE",
                    "note": "Audit for unmanaged presence. Site inference exists, but no validated rename path is implemented.",
                },
                {
                    "system": "Datto Networking",
                    "note": "Audit for unmanaged presence. Current repo surface is read-only.",
                },
            ],
            "ticket_preview": {"title": "Customer rename", "description": "desc"},
        }

    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.get_customer_rename_plan",
        fake_plan,
    )

    result = await execute_customer_rename(organization_id="org-1", dry_run=True)

    assert result["dry_run"] is True
    assert result["ticket"] is None
    assert result["actions"] == []


@pytest.mark.asyncio
async def test_execute_customer_rename_updates_bifrost_and_adds_note(monkeypatch):
    async def fake_plan(**kwargs):
        return {
            "organization": {"id": "org-1", "name": "Old Name"},
            "autotask": {
                "company_id": "123",
                "current_name": "Old Name",
                "desired_name": "New Name",
                "needs_update": True,
                "mapping_id": "mapping-1",
            },
            "change_reason": "PSA updated",
            "systems": [
                {
                    "system": "Autotask",
                    "mapping_id": "mapping-1",
                    "entity_id": "123",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Bifrost",
                    "mapping_id": None,
                    "entity_id": "org-1",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "NinjaOne",
                    "mapping_id": "mapping-2",
                    "entity_id": "456",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Meraki",
                    "mapping_id": "mapping-4",
                    "entity_id": "654",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Cove Data Protection",
                    "mapping_id": "mapping-5",
                    "entity_id": "777",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Datto RMM",
                    "mapping_id": "mapping-6",
                    "entity_id": "888",
                    "current_name": "Old Name ",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "HaloPSA",
                    "mapping_id": "mapping-7",
                    "entity_id": "222",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Huntress",
                    "mapping_id": "mapping-8",
                    "entity_id": "333",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "ConnectSecure",
                    "mapping_id": "mapping-connectsecure",
                    "entity_id": "2541",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "Pax8",
                    "mapping_id": "mapping-pax8",
                    "entity_id": "735496a8-d0e9-44bb-89e1-176298c1b2ad",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                },
                {
                    "system": "DNSFilter",
                    "mapping_id": "mapping-dnsfilter",
                    "entity_id": "1203473",
                    "current_name": "Old Name",
                    "target_name": "New Name",
                    "status": "ready",
                    "needs_change": True,
                    "notes": [],
                    "mapping_config": {
                        "network_ids": ["1244044"],
                        "network_actions": [
                            {
                                "network_id": "1244044",
                                "current_name": "Old Name Primary Office",
                                "target_name": "New Name Primary Office",
                                "needs_change": True,
                            }
                        ],
                    },
                },
            ],
            "audit_follow_up": [
                {
                    "system": "Datto SaaS Protection",
                    "note": "Audit for unmanaged presence. Current repo surface is read-only.",
                },
                {
                    "system": "VIPRE",
                    "note": "Audit for unmanaged presence. Site inference exists, but no validated rename path is implemented.",
                },
                {
                    "system": "Datto Networking",
                    "note": "Audit for unmanaged presence. Current repo surface is read-only.",
                },
            ],
            "ticket_preview": {"title": "Customer rename", "description": "desc"},
        }

    calls: dict[str, list] = {"notes": []}
    mapping_calls: list[tuple[str, str, str, str, dict | None]] = []
    sync_calls: list[str] = []

    async def fake_create_ticket(**kwargs):
        return {"ticket": {"id": "ticket-1", "title": kwargs["title"]}}

    async def fake_create_note(**kwargs):
        calls["notes"].append(kwargs)
        return {"note": {"itemId": 1}}

    async def fake_update_org(org_id: str, **updates):
        assert org_id == "org-1"
        assert updates["name"] == "New Name"
        return SimpleNamespace(id="org-1", name="New Name")

    async def fake_update_company(**kwargs):
        assert kwargs["company_id"] == "123"
        assert kwargs["company_name"] == "New Name"
        return {"company": {"id": "123", "name": "New Name"}}

    async def fake_update_connectsecure_company(**kwargs):
        assert kwargs["company_id"] == "2541"
        assert kwargs["name"] == "New Name"
        return {"company": {"id": "2541", "name": "New Name"}}

    async def fake_update_pax8_company(**kwargs):
        assert kwargs["company_id"] == "735496a8-d0e9-44bb-89e1-176298c1b2ad"
        assert kwargs["name"] == "New Name"
        return {"company": {"id": "735496a8-d0e9-44bb-89e1-176298c1b2ad", "name": "New Name"}}

    async def fake_update_ninjaone(**kwargs):
        assert kwargs["organization_id"] == "456"
        assert kwargs["name"] == "New Name"
        return {"organization": {"id": "456", "name": "New Name"}}

    async def fake_update_meraki(**kwargs):
        assert kwargs["organization_id"] == "654"
        assert kwargs["name"] == "New Name"
        return {"organization": {"id": "654", "name": "New Name"}}

    async def fake_update_cove(**kwargs):
        assert kwargs["partner_id"] == "777"
        assert kwargs["name"] == "New Name"
        return {"customer": {"id": "777", "name": "New Name"}}

    async def fake_update_dattormm(**kwargs):
        assert kwargs["site_uid"] == "888"
        assert kwargs["name"] == "New Name"
        return {"site": {"id": "888", "name": "New Name"}}

    async def fake_update_halopsa(**kwargs):
        assert kwargs["client_id"] == "222"
        assert kwargs["name"] == "New Name"
        return {"client": {"id": "222", "name": "New Name"}}

    async def fake_update_huntress(**kwargs):
        assert kwargs["organization_id"] == "333"
        assert kwargs["name"] == "New Name"
        return {"organization": {"id": "333", "name": "New Name"}}

    async def fake_upsert_mapping(
        name: str,
        *,
        scope: str,
        entity_id: str,
        entity_name: str,
        config: dict | None = None,
    ):
        mapping_calls.append((name, scope, entity_id, entity_name, config))

    async def fake_update_dnsfilter_org(**kwargs):
        assert kwargs["organization_id"] == "1203473"
        assert kwargs["name"] == "New Name"
        return {
            "organization": {
                "id": "1203473",
                "name": "New Name",
                "network_ids": ["1244044"],
            }
        }

    class _FakeDNSFilterUpdater:
        async def update_network(self, *, network_id: str, name: str, extra_fields=None):
            assert network_id == "1244044"
            assert name == "New Name Primary Office"
            return {
                "id": "1244044",
                "attributes": {"name": "New Name Primary Office"},
                "relationships": {"organization": {"data": {"id": "1203473"}}},
            }

        async def close(self):
            return None

    async def fake_get_dnsfilter_client(scope: str | None = None):
        assert scope == "org-1"
        return _FakeDNSFilterUpdater()

    async def fake_sync_autotask_customers():
        sync_calls.append("Autotask")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_ninjaone_organizations():
        sync_calls.append("NinjaOne")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_meraki_organizations():
        sync_calls.append("Meraki")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_cove_customers():
        sync_calls.append("Cove Data Protection")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_dattormm_sites():
        sync_calls.append("Datto RMM")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_halopsa_clients():
        sync_calls.append("HaloPSA")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_huntress_organizations():
        sync_calls.append("Huntress")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_dnsfilter_organizations():
        sync_calls.append("DNSFilter")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_connectsecure_companies():
        sync_calls.append("ConnectSecure")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    async def fake_sync_pax8_companies():
        sync_calls.append("Pax8")
        return {"mapped": 1, "already_mapped": 0, "created_orgs": 0, "errors": []}

    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.get_customer_rename_plan",
        fake_plan,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.create_autotask_ticket",
        fake_create_ticket,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.create_autotask_ticket_note",
        fake_create_note,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_autotask_company",
        fake_update_company,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_connectsecure_company",
        fake_update_connectsecure_company,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_pax8_company",
        fake_update_pax8_company,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_ninjaone_organization",
        fake_update_ninjaone,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_meraki_organization",
        fake_update_meraki,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_cove_customer",
        fake_update_cove,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_dattormm_site",
        fake_update_dattormm,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_halopsa_client",
        fake_update_halopsa,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_huntress_organization",
        fake_update_huntress,
    )
    monkeypatch.setattr(
        integrations,
        "upsert_mapping",
        fake_upsert_mapping,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.update_dnsfilter_organization",
        fake_update_dnsfilter_org,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.get_dnsfilter_client",
        fake_get_dnsfilter_client,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_autotask_customers",
        fake_sync_autotask_customers,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_ninjaone_organizations",
        fake_sync_ninjaone_organizations,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_meraki_organizations",
        fake_sync_meraki_organizations,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_cove_customers",
        fake_sync_cove_customers,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_dattormm_sites",
        fake_sync_dattormm_sites,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_huntress_organizations",
        fake_sync_huntress_organizations,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_dnsfilter_networks",
        fake_sync_dnsfilter_organizations,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_connectsecure_companies",
        fake_sync_connectsecure_companies,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.sync_pax8_companies",
        fake_sync_pax8_companies,
    )
    monkeypatch.setattr(
        "features.customer_rename.workflows.execute_rename.POST_RENAME_SYNC_HANDLERS",
        {
            "Autotask": fake_sync_autotask_customers,
            "NinjaOne": fake_sync_ninjaone_organizations,
            "Meraki": fake_sync_meraki_organizations,
            "Cove Data Protection": fake_sync_cove_customers,
            "Datto RMM": fake_sync_dattormm_sites,
            "Huntress": fake_sync_huntress_organizations,
            "DNSFilter": fake_sync_dnsfilter_organizations,
            "ConnectSecure": fake_sync_connectsecure_companies,
            "Pax8": fake_sync_pax8_companies,
        },
    )
    monkeypatch.setattr(organizations, "update", fake_update_org)

    result = await execute_customer_rename(
        organization_id="org-1",
        dry_run=False,
        refresh_mappings=True,
    )

    assert result["dry_run"] is False
    assert result["ticket"] == {"id": "ticket-1", "title": "Customer rename"}
    assert result["actions"][0]["system"] == "Autotask"
    assert result["actions"][0]["status"] == "renamed"
    assert result["actions"][1]["system"] == "Bifrost"
    assert result["actions"][1]["status"] == "renamed"
    assert result["actions"][2]["system"] == "NinjaOne"
    assert result["actions"][2]["status"] == "renamed"
    assert result["actions"][3]["system"] == "Meraki"
    assert result["actions"][3]["status"] == "renamed"
    assert result["actions"][4]["system"] == "Cove Data Protection"
    assert result["actions"][4]["status"] == "renamed"
    assert result["actions"][5]["system"] == "Datto RMM"
    assert result["actions"][5]["status"] == "renamed"
    assert result["actions"][6]["system"] == "HaloPSA"
    assert result["actions"][6]["status"] == "renamed"
    assert result["actions"][7]["system"] == "Huntress"
    assert result["actions"][7]["status"] == "renamed"
    assert result["actions"][8]["system"] == "DNSFilter"
    assert result["actions"][8]["status"] == "renamed"
    assert result["actions"][9]["system"] == "ConnectSecure"
    assert result["actions"][9]["status"] == "renamed"
    assert result["actions"][10]["system"] == "Pax8"
    assert result["actions"][10]["status"] == "renamed"
    assert result["unsupported_systems"] == []
    assert {item["system"] for item in result["sync_results"]} == {
        "Autotask",
        "NinjaOne",
        "Meraki",
        "Cove Data Protection",
        "Datto RMM",
        "Huntress",
        "DNSFilter",
        "ConnectSecure",
        "Pax8",
    }
    assert result["audit_follow_up"] == [
        {"system": "Datto SaaS Protection", "note": "Audit for unmanaged presence. Current repo surface is read-only."},
        {"system": "VIPRE", "note": "Audit for unmanaged presence. Site inference exists, but no validated rename path is implemented."},
        {"system": "Datto Networking", "note": "Audit for unmanaged presence. Current repo surface is read-only."}
    ]
    assert ("Huntress", "org-1", "333", "New Name", None) in mapping_calls
    assert "Autotask" in sync_calls
    assert calls["notes"]
