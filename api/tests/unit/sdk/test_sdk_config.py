"""
Unit tests for Bifrost Config SDK module.

Tests both platform mode (inside workflows) and external mode (CLI).
Uses mocked dependencies for fast, isolated testing.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_context(test_org_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


@pytest.fixture
def admin_context(test_org_id):
    """Create platform admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


class TestConfigPlatformMode:
    """Test config SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_get_returns_config_value_from_cache(self, test_context, test_org_id):
        """Test that config.get() returns value from Redis cache."""
        from bifrost import config

        set_execution_context(test_context)

        # Mock Redis
        mock_redis = AsyncMock()
        cache_data = json.dumps({"value": "https://api.example.com", "type": "string"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("api_url")

        assert result == "https://api.example.com"
        mock_redis.hget.assert_called_once()
        call_args = mock_redis.hget.call_args
        assert test_org_id in call_args[0][0]  # Hash key contains org_id
        assert call_args[0][1] == "api_url"

    @pytest.mark.asyncio
    async def test_get_returns_default_when_key_not_found(self, test_context):
        """Test that config.get() returns default when key not found."""
        from bifrost import config

        set_execution_context(test_context)

        # Mock Redis - return None (key not found)
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("missing_key", default="default_value")

        assert result == "default_value"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_key_not_found_and_no_default(
        self, test_context
    ):
        """Test that config.get() returns None when key not found and no default."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_uses_context_org_when_org_id_not_provided(
        self, test_context, test_org_id
    ):
        """Test that config.get() uses context.org_id when org_id not specified."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        cache_data = json.dumps({"value": "test", "type": "string"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            await config.get("test_key")

        # Verify it used the context's org_id
        call_args = mock_redis.hget.call_args
        assert test_org_id in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_uses_explicit_org_id_when_provided(self, admin_context):
        """Test that config.get(org_id=...) uses the specified org."""
        from bifrost import config

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        mock_redis = AsyncMock()
        cache_data = json.dumps({"value": "other-value", "type": "string"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("test_key", org_id=other_org_id)

        # Verify it used the explicit org_id
        call_args = mock_redis.hget.call_args
        assert other_org_id in call_args[0][0]
        assert result == "other-value"

    @pytest.mark.asyncio
    async def test_get_parses_int_type_correctly(self, test_context):
        """Test that config.get() parses int type correctly."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        cache_data = json.dumps({"value": 30, "type": "int"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("timeout")

        assert result == 30
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_get_parses_bool_type_correctly(self, test_context):
        """Test that config.get() parses bool type correctly."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        cache_data = json.dumps({"value": True, "type": "bool"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("debug")

        assert result is True
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_get_parses_json_type_correctly(self, test_context):
        """Test that config.get() parses json type correctly."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        json_value = {"key": "value", "nested": {"data": 123}}
        cache_data = json.dumps({"value": json_value, "type": "json"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("complex_config")

        assert result == json_value
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_returns_secret_value_directly(self, test_context):
        """Test that config.get() returns decrypted secret value."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        # Secret values are already decrypted when loaded into cache
        cache_data = json.dumps({"value": "decrypted-secret-123", "type": "secret"})
        mock_redis.hget = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("api_key")

        assert result == "decrypted-secret-123"

    @pytest.mark.asyncio
    async def test_get_handles_invalid_json_gracefully(self, test_context):
        """Test that config.get() handles invalid JSON gracefully."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        # Invalid JSON
        mock_redis.hget = AsyncMock(return_value="not-valid-json{")

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.get("bad_key", default="fallback")

        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_set_writes_to_write_buffer(self, test_context, test_org_id):
        """Test that config.set() writes to the write buffer."""
        from bifrost import config

        set_execution_context(test_context)

        # Mock write buffer
        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("api_url", "https://new-api.example.com")

        # Verify buffer was called
        mock_buffer.add_config_change.assert_called_once()
        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["operation"] == "set"
        assert call_kwargs["key"] == "api_url"
        assert call_kwargs["value"] == "https://new-api.example.com"
        assert call_kwargs["org_id"] == test_org_id
        assert call_kwargs["config_type"] == "string"

    @pytest.mark.asyncio
    async def test_set_uses_context_org_when_org_id_not_provided(
        self, test_context, test_org_id
    ):
        """Test that config.set() uses context.org_id when org_id not specified."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("test_key", "test_value")

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["org_id"] == test_org_id

    @pytest.mark.asyncio
    async def test_set_uses_explicit_org_id_when_provided(self, admin_context):
        """Test that config.set(org_id=...) uses the specified org."""
        from bifrost import config

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("test_key", "test_value", org_id=other_org_id)

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["org_id"] == other_org_id

    @pytest.mark.asyncio
    async def test_set_detects_int_type(self, test_context):
        """Test that config.set() correctly detects int type."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("timeout", 60)

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["config_type"] == "int"
        assert call_kwargs["value"] == 60

    @pytest.mark.asyncio
    async def test_set_detects_bool_type(self, test_context):
        """Test that config.set() correctly detects bool type."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("debug", True)

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["config_type"] == "bool"
        assert call_kwargs["value"] is True

    @pytest.mark.asyncio
    async def test_set_detects_json_type(self, test_context):
        """Test that config.set() correctly detects json type."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        complex_value = {"key": "value", "nested": {"data": 123}}

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.set("complex_config", complex_value)

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["config_type"] == "json"
        assert call_kwargs["value"] == complex_value

    @pytest.mark.asyncio
    async def test_set_encrypts_secret_values(self, test_context):
        """Test that config.set(is_secret=True) encrypts the value."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            with patch(
                "src.core.security.encrypt_secret", return_value="encrypted-value"
            ) as mock_encrypt:
                await config.set("api_key", "secret-123", is_secret=True)

        # Verify encryption was called
        mock_encrypt.assert_called_once_with("secret-123")

        # Verify buffer was called with encrypted value
        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["config_type"] == "secret"
        assert call_kwargs["value"] == "encrypted-value"

    @pytest.mark.asyncio
    async def test_list_returns_all_config_values(self, test_context, test_org_id):
        """Test that config.list() returns all config key-value pairs."""
        from bifrost import config

        set_execution_context(test_context)

        # Mock Redis cache with multiple configs
        mock_redis = AsyncMock()
        cache_data = {
            "api_url": json.dumps({"value": "https://api.example.com", "type": "string"}),
            "timeout": json.dumps({"value": 30, "type": "int"}),
            "debug": json.dumps({"value": True, "type": "bool"}),
        }
        mock_redis.hgetall = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.list()

        assert len(result) == 3
        assert result["api_url"] == "https://api.example.com"
        assert result["timeout"] == 30
        assert result["debug"] is True

    @pytest.mark.asyncio
    async def test_list_returns_empty_dict_when_no_configs(self, test_context):
        """Test that config.list() returns empty dict when no configs exist."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.list()

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_uses_context_org_when_org_id_not_provided(
        self, test_context, test_org_id
    ):
        """Test that config.list() uses context.org_id when org_id not specified."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            await config.list()

        # Verify it used the context's org_id
        call_args = mock_redis.hgetall.call_args
        assert test_org_id in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_uses_explicit_org_id_when_provided(self, admin_context):
        """Test that config.list(org_id=...) uses the specified org."""
        from bifrost import config

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            await config.list(org_id=other_org_id)

        # Verify it used the explicit org_id
        call_args = mock_redis.hgetall.call_args
        assert other_org_id in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_handles_invalid_json_entries(self, test_context):
        """Test that config.list() skips invalid JSON entries."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        cache_data = {
            "valid_key": json.dumps({"value": "test", "type": "string"}),
            "invalid_key": "not-valid-json{",
        }
        mock_redis.hgetall = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.list()

        # Should only include valid entry
        assert len(result) == 1
        assert result["valid_key"] == "test"

    @pytest.mark.asyncio
    async def test_list_includes_secret_values(self, test_context):
        """Test that config.list() includes decrypted secret values."""
        from bifrost import config

        set_execution_context(test_context)

        mock_redis = AsyncMock()
        cache_data = {
            "api_key": json.dumps({"value": "decrypted-secret", "type": "secret"}),
        }
        mock_redis.hgetall = AsyncMock(return_value=cache_data)

        @asynccontextmanager
        async def mock_redis_context():
            yield mock_redis

        with patch("src.core.cache.get_redis", return_value=mock_redis_context()):
            result = await config.list()

        assert result["api_key"] == "decrypted-secret"

    @pytest.mark.asyncio
    async def test_delete_writes_to_write_buffer(self, test_context, test_org_id):
        """Test that config.delete() writes to the write buffer."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            result = await config.delete("old_key")

        # Verify buffer was called
        mock_buffer.add_config_change.assert_called_once()
        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["operation"] == "delete"
        assert call_kwargs["key"] == "old_key"
        assert call_kwargs["org_id"] == test_org_id
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_uses_context_org_when_org_id_not_provided(
        self, test_context, test_org_id
    ):
        """Test that config.delete() uses context.org_id when org_id not specified."""
        from bifrost import config

        set_execution_context(test_context)

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            await config.delete("test_key")

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["org_id"] == test_org_id

    @pytest.mark.asyncio
    async def test_delete_uses_explicit_org_id_when_provided(self, admin_context):
        """Test that config.delete(org_id=...) uses the specified org."""
        from bifrost import config

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        mock_buffer = MagicMock()
        mock_buffer.add_config_change = AsyncMock()

        with patch("bifrost._write_buffer.get_write_buffer", return_value=mock_buffer):
            result = await config.delete("test_key", org_id=other_org_id)

        call_kwargs = mock_buffer.add_config_change.call_args[1]
        assert call_kwargs["org_id"] == other_org_id
        assert result is True


class TestConfigExternalMode:
    """Test config SDK methods in external mode (CLI with API key)."""

    @pytest.fixture(autouse=True)
    def clear_context_and_client(self):
        """Ensure no platform context and clean client state."""
        clear_execution_context()
        # Reset client singleton
        from bifrost.client import BifrostClient

        BifrostClient._instance = None
        yield
        BifrostClient._instance = None

    @pytest.mark.asyncio
    async def test_get_calls_api_endpoint(self):
        """Test that config.get() calls API endpoint in external mode."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": "https://api.example.com"}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.get("api_url", org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/config/get",
            json={"key": "api_url", "org_id": "org-123"},
        )
        assert result == "https://api.example.com"

    @pytest.mark.asyncio
    async def test_get_returns_default_when_api_returns_null(self):
        """Test that config.get() returns default when API returns null."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.get("missing_key", default="fallback")

        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_get_returns_default_when_api_call_fails(self):
        """Test that config.get() returns default on API failure."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.get("test_key", default="fallback")

        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_no_default_and_api_fails(self):
        """Test that config.get() returns None when no default and API fails."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.get("test_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_calls_api_endpoint(self):
        """Test that config.set() calls API endpoint in external mode."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            await config.set("api_url", "https://new-api.com", org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/config/set",
            json={
                "key": "api_url",
                "value": "https://new-api.com",
                "org_id": "org-123",
                "is_secret": False,
            },
        )
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_sends_is_secret_parameter(self):
        """Test that config.set(is_secret=True) sends correct parameter."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            await config.set("api_key", "secret-123", is_secret=True)

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["is_secret"] is True

    @pytest.mark.asyncio
    async def test_list_calls_api_endpoint(self):
        """Test that config.list() calls API endpoint in external mode."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "api_url": "https://api.example.com",
            "timeout": 30,
            "debug": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.list(org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/config/list",
            json={"org_id": "org-123"},
        )
        assert result["api_url"] == "https://api.example.com"
        assert result["timeout"] == 30
        assert result["debug"] is True

    @pytest.mark.asyncio
    async def test_delete_calls_api_endpoint(self):
        """Test that config.delete() calls API endpoint in external mode."""
        from bifrost import config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = True
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.config._get_client", return_value=mock_client):
            result = await config.delete("old_key", org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/config/delete",
            json={"key": "old_key", "org_id": "org-123"},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_requires_api_key_in_external_mode(self):
        """Test that external mode requires BIFROST_DEV_URL and BIFROST_DEV_KEY."""
        from bifrost import config

        # Clear env vars
        with patch.dict(
            "os.environ", {"BIFROST_DEV_URL": "", "BIFROST_DEV_KEY": ""}, clear=False
        ):
            with pytest.raises(
                RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"
            ):
                await config.get("test_key")


class TestConfigContextDetection:
    """Test that config SDK correctly detects platform vs external mode."""

    def test_is_platform_context_true_when_context_set(self):
        """Test _is_platform_context() returns True when context is set."""
        from bifrost.config import _is_platform_context
        from src.sdk.context import ExecutionContext, Organization

        org = Organization(id="test-org", name="Test", is_active=True)
        context = ExecutionContext(
            user_id="user",
            email="user@test.com",
            name="User",
            scope="test-org",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="exec-123",
        )

        try:
            set_execution_context(context)
            assert _is_platform_context() is True
        finally:
            clear_execution_context()

    def test_is_platform_context_false_when_no_context(self):
        """Test _is_platform_context() returns False when no context."""
        from bifrost.config import _is_platform_context

        clear_execution_context()
        assert _is_platform_context() is False
