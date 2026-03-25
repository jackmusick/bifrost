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
from features.dattormm.workflows.data_providers import list_dattormm_sites
from features.dattormm.workflows.sync_sites import sync_dattormm_sites
from modules import dattormm


def _site(site_uid: str | None, name: str | None) -> dict:
    return {
        "siteUid": site_uid,
        "siteName": name,
    }


@pytest.mark.asyncio
async def test_get_client_uses_scoped_mapping(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "Datto RMM"
        assert scope == "org-123"
        return SimpleNamespace(
            config={
                "base_uri": "https://concord-api.centrastage.net",
                "api_key": "access-key",
                "api_secret": "secret-key",
            },
            entity_id="site-42",
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await dattormm.get_client(scope="org-123")
    try:
        assert client.site_uid == "site-42"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_requires_all_fields(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"base_uri": "https://concord-api.centrastage.net"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="api_key"):
        await dattormm.get_client(scope="global")


@pytest.mark.asyncio
async def test_list_dattormm_sites_returns_sorted_options(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_sites(self):
            return [
                _site("2", "Zulu"),
                _site("1", "Alpha"),
                _site("", "Missing ID"),
                _site("3", ""),
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeClient()

    async def fake_get_client(scope: str | None = None):
        assert scope == "global"
        return fake_client

    monkeypatch.setattr(dattormm, "get_client", fake_get_client)

    result = await list_dattormm_sites()

    assert result == [
        {"value": "1", "label": "Alpha"},
        {"value": "2", "label": "Zulu"},
    ]
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_sync_dattormm_sites_maps_unmapped_sites(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def list_sites(self):
            return [
                _site("100", "Already Mapped"),
                _site("200", "Existing Org"),
                _site("300", "New Org"),
                _site(None, "Broken Site"),
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
        assert name == "Datto RMM"
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

    monkeypatch.setattr(dattormm, "get_client", fake_get_client)
    monkeypatch.setattr(integrations, "list_mappings", fake_list_mappings)
    monkeypatch.setattr(integrations, "upsert_mapping", fake_upsert_mapping)
    monkeypatch.setattr(organizations, "list", fake_list_orgs)
    monkeypatch.setattr(organizations, "create", fake_create_org)

    result = await sync_dattormm_sites()

    assert result == {
        "total": 4,
        "mapped": 2,
        "already_mapped": 1,
        "created_orgs": 1,
        "errors": ["Skipped site with no ID: {'siteUid': None, 'siteName': 'Broken Site'}"],
    }
    assert created_names == ["New Org"]
    assert mapping_calls == [
        ("Datto RMM", "org-existing", "200", "Existing Org"),
        ("Datto RMM", "org-new", "300", "New Org"),
    ]
    assert fake_client.closed is True
