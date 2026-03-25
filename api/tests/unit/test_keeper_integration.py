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
from features.keepermsp.workflows.data_providers import list_keeper_managed_companies
from features.keepermsp.workflows.sync_managed_companies import (
    sync_keeper_managed_companies,
)
from modules import keeper


def _company(company_id: str | None, company_name: str | None) -> dict:
    return {
        "company_id": company_id,
        "company_name": company_name,
    }


def test_normalize_base_url_strips_api_path():
    client = keeper.KeeperMSPClient(
        base_url="https://keeper.internal/api/v2/",
        api_key="svc-key",
    )
    assert client._base_url == "https://keeper.internal"


@pytest.mark.asyncio
async def test_execute_command_v2_polls_until_complete(monkeypatch):
    client = keeper.KeeperMSPClient(
        base_url="https://keeper.internal/api/v2",
        api_key="svc-key",
        poll_interval=0,
    )

    calls: list[tuple[str, str, dict | None]] = []
    statuses = iter(
        [
            {"success": True, "status": "processing"},
            {"success": True, "status": "completed"},
        ]
    )

    async def fake_request(method: str, path: str, *, json_body: dict | None = None):
        calls.append((method, path, json_body))
        if path == "/api/v2/executecommand-async":
            return {"success": True, "request_id": "req-1", "status": "queued"}
        if path == "/api/v2/status/req-1":
            return next(statuses)
        if path == "/api/v2/result/req-1":
            return {
                "status": "success",
                "command": "msp-info",
                "data": [_company("1", "Alpha")],
            }
        raise AssertionError(f"Unexpected request: {(method, path, json_body)}")

    monkeypatch.setattr(client, "_request", fake_request)

    result = await client.list_managed_companies()

    assert result == [_company("1", "Alpha")]
    assert calls[0] == (
        "POST",
        "/api/v2/executecommand-async",
        {"command": "msp-info --format=json"},
    )


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Keeper MSP"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_url": "https://keeper.internal",
                "api_key": "svc-key",
                "api_version": "v1",
            },
            entity_id="mc-42",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await keeper.get_client(scope="org-123")
    try:
        assert client.company_id == "mc-42"
        assert client._api_version == "v1"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_url": "https://keeper.internal"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await keeper.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_keeper_managed_companies_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_managed_companies(self):
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

    monkeypatch.setattr(keeper, "get_client", fake_get_client)

    result = await list_keeper_managed_companies()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_keeper_managed_companies_maps_unmapped_companies(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_managed_companies(self):
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
        assert name == "Keeper MSP"
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

    monkeypatch.setattr(keeper, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_keeper_managed_companies()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped managed company with no ID: {'company_id': None, 'company_name': 'Broken Company'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Keeper MSP", "org-existing", "200", "Existing Org"),
        ("Keeper MSP", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
