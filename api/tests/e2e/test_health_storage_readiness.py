import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Response


pytestmark = pytest.mark.e2e

_HEALTH_PATH = Path(__file__).parents[2] / "src" / "routers" / "health.py"
_SPEC = importlib.util.spec_from_file_location("health_router_for_e2e", _HEALTH_PATH)
health = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(health)


class DummyDB:
    async def execute(self, statement):
        return None


async def _healthy_component(name: str, type_: str):
    return name, {"status": "healthy", "type": type_}


def _mock_core_dependency_checks(monkeypatch):
    monkeypatch.setattr(
        health,
        "check_database",
        lambda db: _healthy_component("database", "postgresql"),
    )
    monkeypatch.setattr(
        health, "check_redis", lambda settings: _healthy_component("redis", "redis")
    )
    monkeypatch.setattr(
        health,
        "check_rabbitmq",
        lambda settings: _healthy_component("rabbitmq", "rabbitmq"),
    )


class HealthyAzureBlobStorage:
    def __init__(self, settings):
        self.settings = settings

    async def close(self):
        return None

    def get_client(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return None

    async def head_bucket(self, *, Bucket):
        assert Bucket == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured", "expected_component"),
    [
        (True, {"status": "healthy", "type": "azure_blob"}),
        (False, {"status": "not_configured", "type": "azure_blob"}),
    ],
)
async def test_ready_health_check_reports_azure_blob_readiness(
    monkeypatch, configured, expected_component
):
    settings = SimpleNamespace(
        environment="test",
        object_storage_provider="azure_blob",
        redis_url="redis://redis-secret@example:6379/0",
        rabbitmq_url="amqp://rabbit-secret@example:5672/",
        azure_blob_configured=configured,
    )
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    _mock_core_dependency_checks(monkeypatch)
    monkeypatch.setattr(health, "AzureBlobStorageClient", HealthyAzureBlobStorage)

    response = Response()
    result = await health.ready_health_check(response, DummyDB())

    assert response.status_code == 200
    assert result.status == "healthy"
    assert result.components["s3"] == expected_component
