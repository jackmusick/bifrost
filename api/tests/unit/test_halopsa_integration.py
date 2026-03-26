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

from shared.halopsa import data_providers


@pytest.mark.asyncio
async def test_halo_client_sites_returns_empty_list_when_mapping_missing(monkeypatch):
    async def fake_resolve_client_id(org_id: str) -> int:
        assert org_id == "org-123"
        raise RuntimeError("mapping missing")

    fake_context = SimpleNamespace(org_id=None, set_scope=lambda org_id: None)

    monkeypatch.setattr(data_providers, "resolve_client_id", fake_resolve_client_id)
    monkeypatch.setattr(data_providers, "context", fake_context)

    result = await data_providers.halo_client_sites("org-123")

    assert result == []
