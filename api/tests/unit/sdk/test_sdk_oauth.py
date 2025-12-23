"""
Unit tests for Bifrost OAuth SDK module.

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


class TestOAuthPlatformMode:
    """Test oauth SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_get_returns_complete_oauth_connection(self, test_context, test_org_id):
        """Test that oauth.get() returns complete OAuth connection data."""
        from bifrost import oauth

        set_execution_context(test_context)

        # Mock cached OAuth data
        cached_oauth_data = json.dumps({
            "provider_name": "microsoft",
            "client_id": "client-12345",
            "client_secret": "secret-67890",
            "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "scopes": ["openid", "profile", "email"],
            "access_token": "access-token-xyz",
            "refresh_token": "refresh-token-abc",
            "expires_at": "2025-12-24T12:00:00Z"
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("microsoft")

        assert result is not None
        assert result["connection_name"] == "microsoft"
        assert result["client_id"] == "client-12345"
        assert result["client_secret"] == "secret-67890"
        assert result["authorization_url"] == "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        assert result["token_url"] == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        assert result["scopes"] == ["openid", "profile", "email"]
        assert result["access_token"] == "access-token-xyz"
        assert result["refresh_token"] == "refresh-token-abc"
        assert result["expires_at"] == "2025-12-24T12:00:00Z"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_provider_not_found(self, test_context, test_org_id):
        """Test that oauth.get() returns None when provider doesn't exist."""
        from bifrost import oauth

        set_execution_context(test_context)

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=None)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("nonexistent_provider")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_invalid_json(self, test_context, test_org_id):
        """Test that oauth.get() returns None when cached data is invalid JSON."""
        from bifrost import oauth

        set_execution_context(test_context)

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value="invalid{json")

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("microsoft")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_uses_context_org_when_org_id_not_provided(self, test_context, test_org_id):
        """Test that oauth.get() uses context.org_id when org_id not specified."""
        from bifrost import oauth

        set_execution_context(test_context)

        cached_oauth_data = json.dumps({
            "provider_name": "google",
            "client_id": "google-client",
            "client_secret": "google-secret",
            "authorization_url": None,
            "token_url": None,
            "scopes": [],
            "access_token": None,
            "refresh_token": None,
            "expires_at": None
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            with patch('src.core.cache.oauth_hash_key') as mock_hash_key:
                mock_redis = AsyncMock()
                mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

                @asynccontextmanager
                async def mock_redis_context():
                    yield mock_redis

                mock_get_redis.return_value = mock_redis_context()
                mock_hash_key.return_value = f"oauth:{test_org_id}"

                result = await oauth.get("google")

                # Verify hash_key was called with context's org_id
                mock_hash_key.assert_called_once_with(test_org_id)
                assert result is not None
                assert result["connection_name"] == "google"

    @pytest.mark.asyncio
    async def test_get_with_explicit_org_id_parameter(self, admin_context, test_org_id):
        """Test that oauth.get(org_id=...) uses the specified org."""
        from bifrost import oauth

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        cached_oauth_data = json.dumps({
            "provider_name": "partner_center",
            "client_id": "partner-client",
            "client_secret": "partner-secret",
            "authorization_url": "https://login.partner.com/authorize",
            "token_url": "https://login.partner.com/token",
            "scopes": ["read", "write"],
            "access_token": "partner-access",
            "refresh_token": "partner-refresh",
            "expires_at": None
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            with patch('src.core.cache.oauth_hash_key') as mock_hash_key:
                mock_redis = AsyncMock()
                mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

                @asynccontextmanager
                async def mock_redis_context():
                    yield mock_redis

                mock_get_redis.return_value = mock_redis_context()
                mock_hash_key.return_value = f"oauth:{other_org_id}"

                result = await oauth.get("partner_center", org_id=other_org_id)

                # Verify hash_key was called with the explicit org_id
                mock_hash_key.assert_called_once_with(other_org_id)
                assert result is not None
                assert result["connection_name"] == "partner_center"
                assert result["client_id"] == "partner-client"

    @pytest.mark.asyncio
    async def test_get_returns_connection_with_minimal_fields(self, test_context, test_org_id):
        """Test that oauth.get() handles connection with only required fields."""
        from bifrost import oauth

        set_execution_context(test_context)

        # Minimal OAuth data (only required fields)
        cached_oauth_data = json.dumps({
            "provider_name": "minimal_provider",
            "client_id": "minimal-client",
            "client_secret": "minimal-secret"
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("minimal_provider")

        assert result is not None
        assert result["connection_name"] == "minimal_provider"
        assert result["client_id"] == "minimal-client"
        assert result["client_secret"] == "minimal-secret"
        # Optional fields should be None or empty list
        assert result["authorization_url"] is None
        assert result["token_url"] is None
        assert result["scopes"] == []
        assert result["access_token"] is None
        assert result["refresh_token"] is None
        assert result["expires_at"] is None

    @pytest.mark.asyncio
    async def test_get_handles_missing_optional_fields(self, test_context, test_org_id):
        """Test that oauth.get() handles missing optional fields gracefully."""
        from bifrost import oauth

        set_execution_context(test_context)

        # OAuth data with some fields missing
        cached_oauth_data = json.dumps({
            "provider_name": "incomplete_provider",
            "client_id": "incomplete-client",
            "client_secret": "incomplete-secret",
            "scopes": ["read"]
            # Missing: authorization_url, token_url, tokens, expires_at
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("incomplete_provider")

        assert result is not None
        assert result["connection_name"] == "incomplete_provider"
        assert result["scopes"] == ["read"]
        assert result["authorization_url"] is None
        assert result["token_url"] is None

    @pytest.mark.asyncio
    async def test_get_with_empty_scopes_list(self, test_context, test_org_id):
        """Test that oauth.get() handles empty scopes list correctly."""
        from bifrost import oauth

        set_execution_context(test_context)

        cached_oauth_data = json.dumps({
            "provider_name": "no_scopes",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": []  # Empty scopes
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("no_scopes")

        assert result is not None
        assert result["scopes"] == []

    @pytest.mark.asyncio
    async def test_get_handles_missing_scopes_field(self, test_context, test_org_id):
        """Test that oauth.get() defaults to empty list when scopes missing."""
        from bifrost import oauth

        set_execution_context(test_context)

        cached_oauth_data = json.dumps({
            "provider_name": "missing_scopes",
            "client_id": "client",
            "client_secret": "secret"
            # Missing: scopes
        })

        with patch('src.core.cache.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

            @asynccontextmanager
            async def mock_redis_context():
                yield mock_redis

            mock_get_redis.return_value = mock_redis_context()

            result = await oauth.get("missing_scopes")

        assert result is not None
        assert result["scopes"] == []  # Should default to empty list

    @pytest.mark.asyncio
    async def test_get_uses_scope_as_fallback_org_id(self, test_org_id):
        """Test that oauth.get() uses context.scope when org_id not available."""
        from bifrost import oauth
        from src.sdk.context import ExecutionContext, Organization

        # Context with scope but no explicit org_id
        org = Organization(id=test_org_id, name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope=test_org_id,  # Has scope
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123",
        )
        set_execution_context(context)

        try:
            cached_oauth_data = json.dumps({
                "provider_name": "test",
                "client_id": "client",
                "client_secret": "secret"
            })

            with patch('src.core.cache.get_redis') as mock_get_redis:
                with patch('src.core.cache.oauth_hash_key') as mock_hash_key:
                    mock_redis = AsyncMock()
                    mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

                    @asynccontextmanager
                    async def mock_redis_context():
                        yield mock_redis

                    mock_get_redis.return_value = mock_redis_context()
                    mock_hash_key.return_value = f"oauth:{test_org_id}"

                    result = await oauth.get("test")

                    # Verify it used the scope as org_id
                    mock_hash_key.assert_called_once_with(test_org_id)
                    assert result is not None
        finally:
            clear_execution_context()


class TestOAuthExternalMode:
    """Test oauth SDK methods in external mode (CLI with API key)."""

    @pytest.fixture(autouse=True)
    def clear_context_and_client(self):
        """Ensure no platform context and clean client state."""
        clear_execution_context()
        # Reset client singleton
        from bifrost import client as client_module

        client_module._client = None
        yield
        client_module._client = None

    @pytest.mark.asyncio
    async def test_get_calls_api_endpoint(self):
        """Test that oauth.get() calls API endpoint in external mode."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "connection_name": "api_provider",
            "client_id": "api-client-123",
            "client_secret": "api-secret-456",
            "authorization_url": "https://login.api.com/authorize",
            "token_url": "https://login.api.com/token",
            "scopes": ["admin", "read", "write"],
            "access_token": "api-access-token",
            "refresh_token": "api-refresh-token",
            "expires_at": "2025-12-25T00:00:00Z"
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("api_provider", org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/oauth/get",
            json={"provider": "api_provider", "org_id": "org-123"},
        )
        assert result is not None
        assert result["connection_name"] == "api_provider"
        assert result["client_id"] == "api-client-123"
        assert result["client_secret"] == "api-secret-456"
        assert result["authorization_url"] == "https://login.api.com/authorize"
        assert result["token_url"] == "https://login.api.com/token"
        assert result["scopes"] == ["admin", "read", "write"]
        assert result["access_token"] == "api-access-token"
        assert result["refresh_token"] == "api-refresh-token"
        assert result["expires_at"] == "2025-12-25T00:00:00Z"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_api_returns_null(self):
        """Test that oauth.get() returns None when API returns null."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("nonexistent_provider")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_api_call_fails(self):
        """Test that oauth.get() returns None on API failure."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("test_provider")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_on_404(self):
        """Test that oauth.get() returns None when provider not found (404)."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("unknown_provider")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_without_org_id_parameter(self):
        """Test that oauth.get() in external mode can be called without org_id."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "connection_name": "default_provider",
            "client_id": "default-client",
            "client_secret": "default-secret",
            "authorization_url": None,
            "token_url": None,
            "scopes": [],
            "access_token": None,
            "refresh_token": None,
            "expires_at": None
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("default_provider")

        # org_id should be None in the request
        mock_client.post.assert_called_once_with(
            "/api/cli/oauth/get",
            json={"provider": "default_provider", "org_id": None},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_handles_api_response_with_minimal_fields(self):
        """Test that oauth.get() handles API response with minimal fields."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "connection_name": "minimal",
            "client_id": "min-client",
            "client_secret": "min-secret"
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("minimal")

        assert result is not None
        assert result["connection_name"] == "minimal"
        assert result["client_id"] == "min-client"
        assert result["client_secret"] == "min-secret"
        # Missing fields should be None or empty list
        assert result["authorization_url"] is None
        assert result["token_url"] is None
        assert result["scopes"] == []

    @pytest.mark.asyncio
    async def test_get_handles_missing_scopes_in_api_response(self):
        """Test that oauth.get() defaults to empty list when scopes missing from API."""
        from bifrost import oauth

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "connection_name": "no_scopes",
            "client_id": "client",
            "client_secret": "secret"
            # scopes field missing
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.oauth._get_client", return_value=mock_client):
            result = await oauth.get("no_scopes")

        assert result is not None
        assert result["scopes"] == []

    @pytest.mark.asyncio
    async def test_requires_api_key_in_external_mode(self):
        """Test that external mode requires BIFROST_DEV_URL and BIFROST_DEV_KEY."""
        from bifrost import oauth

        # Clear env vars
        with patch.dict(
            "os.environ", {"BIFROST_DEV_URL": "", "BIFROST_DEV_KEY": ""}, clear=False
        ):
            with pytest.raises(
                RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"
            ):
                await oauth.get("test_provider")


class TestOAuthContextDetection:
    """Test that oauth SDK correctly detects platform vs external mode."""

    def test_is_platform_context_true_when_context_set(self):
        """Test _is_platform_context() returns True when context is set."""
        from bifrost.oauth import _is_platform_context
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
        from bifrost.oauth import _is_platform_context

        clear_execution_context()
        assert _is_platform_context() is False
