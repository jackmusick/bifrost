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

from bifrost import integrations
from modules import autoelevate


@pytest.mark.asyncio
async def test_get_client_uses_global_integration_config(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        assert name == "AutoElevate"
        assert scope == "global"
        return SimpleNamespace(
            config={
                "username": "tech@example.com",
                "password": "secret",
                "totp_secret": "JBSWY3DPEHPK3PXP",
            }
        )

    monkeypatch.setattr(integrations, "get", fake_get)

    client = await autoelevate.get_client()

    assert client.username == "tech@example.com"
    assert client.password == "secret"
    assert client.totp_secret == "JBSWY3DPEHPK3PXP"


@pytest.mark.asyncio
async def test_get_client_requires_all_credentials(monkeypatch):
    async def fake_get(name: str, scope: str | None = None):
        return SimpleNamespace(config={"username": "tech@example.com"})

    monkeypatch.setattr(integrations, "get", fake_get)

    with pytest.raises(RuntimeError, match="username, password, and totp_secret"):
        await autoelevate.get_client()
