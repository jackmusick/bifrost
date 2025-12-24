"""
Unit tests for Bifrost Integrations SDK module.

Tests both platform mode (inside workflows) and external mode (CLI).
Uses mocked dependencies for fast, isolated testing.
"""

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


class TestIntegrationsPlatformMode:
    """Test integrations SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_get_returns_integration_data(self, test_context, test_org_id):
        """Test that integrations.get() returns complete integration data."""
        from bifrost import integrations

        set_execution_context(test_context)

        # Mock integration without OAuth provider
        mock_integration = MagicMock()
        mock_integration.oauth_provider = None
        mock_integration.default_entity_id = None
        mock_integration.entity_id = None

        # Mock the database context and repository
        from datetime import datetime, timezone

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "tenant-12345"
        mock_mapping.entity_name = "Test Tenant"
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(
            return_value={"api_url": "https://api.example.com", "timeout": 30}
        )

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.get("TestIntegration")

        assert result is not None
        assert result.integration_id == str(mock_mapping.integration_id)
        assert result.entity_id == "tenant-12345"
        assert result.entity_name == "Test Tenant"
        assert result.config["api_url"] == "https://api.example.com"
        assert result.config["timeout"] == 30
        assert result.oauth is None  # No OAuth provider

    @pytest.mark.asyncio
    async def test_get_returns_none_when_integration_not_found(
        self, test_context, test_org_id
    ):
        """Test that integrations.get() returns None when integration doesn't exist."""
        from bifrost import integrations

        set_execution_context(test_context)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=None)
        mock_repo.get_integration_by_name = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.get("NonexistentIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_falls_back_to_defaults_when_no_mapping_for_org(
        self, test_context, test_org_id
    ):
        """Test that integrations.get() falls back to integration defaults when no org mapping."""
        from bifrost import integrations

        set_execution_context(test_context)

        # Mock integration with defaults
        mock_integration = MagicMock()
        mock_integration.id = uuid4()
        mock_integration.default_entity_id = "default-tenant-id"
        mock_integration.entity_id = None
        mock_integration.oauth_provider = None

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=None)  # No mapping
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.get_integration_defaults = AsyncMock(return_value={"default_key": "default_value"})

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.get("TestIntegration")

        assert result is not None
        assert result.integration_id == str(mock_integration.id)
        assert result.entity_id == "default-tenant-id"
        assert result.entity_name is None  # No mapping = no entity name
        assert result.config["default_key"] == "default_value"
        mock_repo.get_integration_for_org.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_uses_context_org_when_org_id_not_provided(
        self, test_context, test_org_id
    ):
        """Test that integrations.get() uses context.org_id when org_id not specified."""
        from bifrost import integrations
        from uuid import UUID
        from datetime import datetime, timezone

        set_execution_context(test_context)

        mock_integration = MagicMock()
        mock_integration.oauth_provider = None
        mock_integration.default_entity_id = None
        mock_integration.entity_id = None

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "tenant-123"
        mock_mapping.entity_name = None
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(return_value={})

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                await integrations.get("TestIntegration")

        # Verify repository was called with the context's org_id
        call_args = mock_repo.get_integration_for_org.call_args
        assert call_args[0][0] == "TestIntegration"
        assert call_args[0][1] == UUID(test_org_id)

    @pytest.mark.asyncio
    async def test_get_with_explicit_org_id_parameter(
        self, admin_context, test_org_id
    ):
        """Test that integrations.get(org_id=...) uses the specified org."""
        from bifrost import integrations
        from uuid import UUID

        set_execution_context(admin_context)

        other_org_id = str(uuid4())

        mock_integration = MagicMock()
        mock_integration.oauth_provider = None
        mock_integration.default_entity_id = None
        mock_integration.entity_id = None

        from datetime import datetime, timezone

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "other-tenant"
        mock_mapping.entity_name = "Other Tenant"
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(return_value={"key": "value"})

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.get(
                    "TestIntegration", org_id=other_org_id
                )

        # Verify repository was called with the explicit org_id
        call_args = mock_repo.get_integration_for_org.call_args
        assert call_args[0][1] == UUID(other_org_id)
        assert result.entity_id == "other-tenant"

    @pytest.mark.asyncio
    async def test_get_returns_merged_config(self, test_context, test_org_id):
        """Test that integrations.get() returns properly merged configuration."""
        from bifrost import integrations
        from datetime import datetime, timezone

        set_execution_context(test_context)

        mock_integration = MagicMock()
        mock_integration.oauth_provider = None
        mock_integration.default_entity_id = None
        mock_integration.entity_id = None

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "tenant-123"
        mock_mapping.entity_name = None
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        # Merged config (defaults + org overrides)
        merged_config = {
            "api_url": "https://api.org-override.com",  # Override
            "timeout": 30,  # Default
            "debug": True,  # Default
        }

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(return_value=merged_config)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.get("TestIntegration")

        assert result.config == merged_config

    @pytest.mark.asyncio
    async def test_get_returns_oauth_details_when_provider_exists(
        self, test_context, test_org_id
    ):
        """Test that integrations.get() includes OAuth details when provider configured."""
        from bifrost import integrations
        from datetime import datetime, timezone

        set_execution_context(test_context)

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider.id = uuid4()
        mock_provider.provider_name = "TestProvider"
        mock_provider.client_id = "oauth-client-123"
        mock_provider.encrypted_client_secret = "encrypted-secret"
        mock_provider.authorization_url = "https://login.example.com/authorize"
        mock_provider.token_url = "https://login.example.com/token"
        mock_provider.token_url_defaults = None
        mock_provider.scopes = ["read", "write", "admin"]

        # Mock OAuth token
        mock_token = MagicMock()
        mock_token.encrypted_access_token = "encrypted-access"
        mock_token.encrypted_refresh_token = "encrypted-refresh"
        mock_token.expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        # Mock integration with OAuth provider
        mock_integration = MagicMock()
        mock_integration.oauth_provider = mock_provider
        mock_integration.entity_id = None
        mock_integration.default_entity_id = None

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "tenant-123"
        mock_mapping.entity_name = "Test Tenant"
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = mock_token
        mock_mapping.oauth_token_id = mock_token.id if hasattr(mock_token, 'id') else uuid4()
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(return_value={})
        mock_repo.get_provider_org_token = AsyncMock(return_value=mock_token)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                with patch(
                    "src.services.oauth_provider.resolve_url_template",
                    return_value="https://login.example.com/token",
                ):
                    with patch(
                        "src.core.security.decrypt_secret",
                        side_effect=lambda x: f"decrypted-{x}",
                    ):
                        result = await integrations.get("TestIntegration")

        assert result.oauth is not None
        assert result.oauth.connection_name == "TestProvider"
        assert result.oauth.client_id == "oauth-client-123"
        assert result.oauth.client_secret == "decrypted-encrypted-secret"
        assert result.oauth.authorization_url == "https://login.example.com/authorize"
        assert result.oauth.token_url == "https://login.example.com/token"
        assert result.oauth.scopes == ["read", "write", "admin"]
        assert result.oauth.access_token == "decrypted-encrypted-access"
        assert result.oauth.refresh_token == "decrypted-encrypted-refresh"
        assert result.oauth.expires_at is not None

    @pytest.mark.asyncio
    async def test_get_resolves_oauth_token_url_with_entity_id(
        self, test_context, test_org_id
    ):
        """Test that OAuth token URL template is resolved with entity_id."""
        from bifrost import integrations

        set_execution_context(test_context)

        # Mock OAuth provider with template URL
        mock_provider = MagicMock()
        mock_provider.id = uuid4()
        mock_provider.provider_name = "TestProvider"
        mock_provider.client_id = "client-123"
        mock_provider.encrypted_client_secret = None
        mock_provider.authorization_url = None
        mock_provider.token_url = "https://login.example.com/{entity_id}/oauth/token"
        mock_provider.token_url_defaults = {"entity_id": "default"}
        mock_provider.scopes = ["read"]

        mock_integration = MagicMock()
        mock_integration.oauth_provider = mock_provider
        mock_integration.entity_id = "global-entity"
        mock_integration.default_entity_id = None

        from datetime import datetime, timezone

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = uuid4()
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "specific-tenant"  # Should be used instead of global
        mock_mapping.entity_name = None
        mock_mapping.integration = mock_integration
        mock_mapping.oauth_token = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=mock_mapping)
        mock_repo.get_config_for_mapping = AsyncMock(return_value={})
        mock_repo.get_provider_org_token = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                with patch(
                    "src.services.oauth_provider.resolve_url_template"
                ) as mock_resolve:
                    mock_resolve.return_value = (
                        "https://login.example.com/specific-tenant/oauth/token"
                    )
                    with patch("src.core.security.decrypt_secret"):
                        result = await integrations.get("TestIntegration")

        # Verify resolve_url_template was called with mapping's entity_id
        mock_resolve.assert_called_once_with(
            url="https://login.example.com/{entity_id}/oauth/token",
            entity_id="specific-tenant",
            defaults={"entity_id": "default"},
        )
        assert (
            result.oauth.token_url
            == "https://login.example.com/specific-tenant/oauth/token"
        )

    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_no_org_id_available(self, test_org_id):
        """Test that integrations.get() returns integration defaults when no org_id is available."""
        from bifrost import integrations
        from src.sdk.context import ExecutionContext, Organization

        # Context without org_id (global context)
        org = Organization(id="", name="", is_active=False)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="",  # Empty scope
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123",
        )
        set_execution_context(context)

        # Mock integration with defaults
        mock_integration = MagicMock()
        mock_integration.id = uuid4()
        mock_integration.default_entity_id = "global-default-entity"
        mock_integration.entity_id = None
        mock_integration.oauth_provider = None

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.get_integration_defaults = AsyncMock(return_value={"global_key": "global_value"})

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        try:
            with patch("src.core.database.get_db_context", mock_db_context):
                with patch(
                    "src.repositories.integrations.IntegrationsRepository",
                    return_value=mock_repo,
                ):
                    result = await integrations.get("TestIntegration")

            # Should return integration defaults since no org_id
            assert result is not None
            assert result.integration_id == str(mock_integration.id)
            assert result.entity_id == "global-default-entity"
            assert result.entity_name is None
            assert result.config["global_key"] == "global_value"
        finally:
            clear_execution_context()

    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_org_id_invalid(self, test_context):
        """Test that integrations.get() falls back to defaults for invalid org_id format."""
        from bifrost import integrations

        set_execution_context(test_context)

        # Mock integration with defaults
        mock_integration = MagicMock()
        mock_integration.id = uuid4()
        mock_integration.default_entity_id = "default-entity"
        mock_integration.entity_id = None
        mock_integration.oauth_provider = None

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.get_integration_defaults = AsyncMock(return_value={})

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                # Pass invalid UUID format - should fall back to defaults
                result = await integrations.get("TestIntegration", org_id="not-a-uuid")

        # Should return integration defaults since org_id was invalid
        assert result is not None
        assert result.entity_id == "default-entity"

    @pytest.mark.asyncio
    async def test_get_returns_oauth_from_integration_defaults(self, test_context, test_org_id):
        """Test that integrations.get() returns OAuth data from integration defaults when no mapping."""
        from bifrost import integrations
        from datetime import datetime, timezone

        set_execution_context(test_context)

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider.id = uuid4()
        mock_provider.provider_name = "HaloPSA"
        mock_provider.client_id = "default-client-id"
        mock_provider.encrypted_client_secret = "encrypted-default-secret"
        mock_provider.authorization_url = "https://auth.halopsa.com/authorize"
        mock_provider.token_url = "https://{entity_id}.halopsa.com/auth/token"
        mock_provider.token_url_defaults = {"entity_id": "default"}
        mock_provider.scopes = ["all"]

        # Mock OAuth token for org-level (user_id=NULL)
        mock_org_token = MagicMock()
        mock_org_token.encrypted_access_token = "encrypted-org-access"
        mock_org_token.encrypted_refresh_token = "encrypted-org-refresh"
        mock_org_token.expires_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

        # Mock integration with defaults (no org mapping)
        mock_integration = MagicMock()
        mock_integration.id = uuid4()
        mock_integration.default_entity_id = "default-halopsa-tenant"
        mock_integration.entity_id = None
        mock_integration.oauth_provider = mock_provider

        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=None)  # No org mapping
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.get_integration_defaults = AsyncMock(return_value={"api_url": "https://api.halo.com"})
        mock_repo.get_provider_org_token = AsyncMock(return_value=mock_org_token)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                with patch(
                    "src.services.oauth_provider.resolve_url_template",
                    return_value="https://default-halopsa-tenant.halopsa.com/auth/token",
                ) as mock_resolve:
                    with patch(
                        "src.core.security.decrypt_secret",
                        side_effect=lambda x: f"decrypted-{x}",
                    ):
                        result = await integrations.get("HaloPSA")

        # Verify we fell back to integration defaults
        assert result is not None
        assert result.integration_id == str(mock_integration.id)
        assert result.entity_id == "default-halopsa-tenant"
        assert result.entity_name is None  # No mapping
        assert result.config["api_url"] == "https://api.halo.com"

        # Verify OAuth data from integration defaults
        assert result.oauth is not None
        assert result.oauth.connection_name == "HaloPSA"
        assert result.oauth.client_id == "default-client-id"
        assert result.oauth.client_secret == "decrypted-encrypted-default-secret"
        assert result.oauth.token_url == "https://default-halopsa-tenant.halopsa.com/auth/token"
        assert result.oauth.scopes == ["all"]
        assert result.oauth.access_token == "decrypted-encrypted-org-access"
        assert result.oauth.refresh_token == "decrypted-encrypted-org-refresh"

        # Verify resolve_url_template was called with default_entity_id
        mock_resolve.assert_called_once_with(
            url="https://{entity_id}.halopsa.com/auth/token",
            entity_id="default-halopsa-tenant",
            defaults={"entity_id": "default"},
        )

    @pytest.mark.asyncio
    async def test_list_mappings_returns_all_mappings(self, test_context, test_org_id):
        """Test that integrations.list_mappings() returns all org mappings."""
        from bifrost import integrations

        set_execution_context(test_context)

        integration_id = uuid4()
        org1_id = uuid4()
        org2_id = uuid4()

        # Mock integration
        mock_integration = MagicMock()
        mock_integration.id = integration_id

        from datetime import datetime, timezone

        # Mock mappings
        mock_mapping1 = MagicMock()
        mock_mapping1.id = uuid4()
        mock_mapping1.integration_id = integration_id
        mock_mapping1.organization_id = org1_id
        mock_mapping1.entity_id = "tenant-1"
        mock_mapping1.entity_name = "Tenant One"
        mock_mapping1.oauth_token_id = None
        mock_mapping1.created_at = datetime.now(timezone.utc)
        mock_mapping1.updated_at = datetime.now(timezone.utc)

        mock_mapping2 = MagicMock()
        mock_mapping2.id = uuid4()
        mock_mapping2.integration_id = integration_id
        mock_mapping2.organization_id = org2_id
        mock_mapping2.entity_id = "tenant-2"
        mock_mapping2.entity_name = "Tenant Two"
        mock_mapping2.oauth_token_id = None
        mock_mapping2.created_at = datetime.now(timezone.utc)
        mock_mapping2.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.list_mappings = AsyncMock(return_value=[mock_mapping1, mock_mapping2])
        mock_repo.get_config_for_mapping = AsyncMock(
            side_effect=[{"key1": "val1"}, {"key2": "val2"}]
        )

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.list_mappings("TestIntegration")

        assert result is not None
        assert len(result) == 2
        assert str(result[0].organization_id) == str(org1_id)
        assert result[0].entity_id == "tenant-1"
        assert result[0].entity_name == "Tenant One"
        assert result[0].config == {"key1": "val1"}
        assert str(result[1].organization_id) == str(org2_id)
        assert result[1].entity_id == "tenant-2"
        assert result[1].config == {"key2": "val2"}

    @pytest.mark.asyncio
    async def test_list_mappings_returns_none_when_integration_not_found(
        self, test_context
    ):
        """Test that list_mappings() returns None when integration doesn't exist."""
        from bifrost import integrations

        set_execution_context(test_context)

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.list_mappings("NonexistentIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_mappings_returns_empty_list_when_no_mappings(
        self, test_context
    ):
        """Test that list_mappings() returns empty list when no mappings exist."""
        from bifrost import integrations

        set_execution_context(test_context)

        mock_integration = MagicMock()
        mock_integration.id = uuid4()

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.list_mappings = AsyncMock(return_value=[])

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.list_mappings("TestIntegration")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_mappings_includes_merged_config_per_mapping(
        self, test_context
    ):
        """Test that list_mappings() includes merged config for each mapping."""
        from bifrost import integrations

        set_execution_context(test_context)

        integration_id = uuid4()

        mock_integration = MagicMock()
        mock_integration.id = integration_id

        from datetime import datetime, timezone

        mock_mapping = MagicMock()
        mock_mapping.id = uuid4()
        mock_mapping.integration_id = integration_id
        mock_mapping.organization_id = uuid4()
        mock_mapping.entity_id = "tenant-1"
        mock_mapping.entity_name = None
        mock_mapping.oauth_token_id = None
        mock_mapping.created_at = datetime.now(timezone.utc)
        mock_mapping.updated_at = datetime.now(timezone.utc)

        mock_repo = MagicMock()
        mock_repo.get_integration_by_name = AsyncMock(return_value=mock_integration)
        mock_repo.list_mappings = AsyncMock(return_value=[mock_mapping])
        mock_repo.get_config_for_mapping = AsyncMock(
            return_value={"merged": "config", "timeout": 60}
        )

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        with patch("src.core.database.get_db_context", mock_db_context):
            with patch(
                "src.repositories.integrations.IntegrationsRepository",
                return_value=mock_repo,
            ):
                result = await integrations.list_mappings("TestIntegration")

        # Verify get_config_for_mapping was called
        mock_repo.get_config_for_mapping.assert_called_once_with(
            integration_id, mock_mapping.organization_id
        )
        assert result[0].config == {"merged": "config", "timeout": 60}


class TestIntegrationsExternalMode:
    """Test integrations SDK methods in external mode (CLI with API key)."""

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
        """Test that integrations.get() calls API endpoint in external mode."""
        from bifrost import integrations

        integration_id = uuid4()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "integration_id": str(integration_id),
            "entity_id": "api-tenant",
            "entity_name": "API Tenant",
            "config": {"api_key": "secret"},
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "oauth": {
                "connection_name": "TestProvider",
                "client_id": "client-123",
                "client_secret": "secret-value",
                "authorization_url": "https://auth.example.com",
                "token_url": "https://token.example.com",
                "scopes": ["read", "write"],
                "access_token": "access-token-value",
                "refresh_token": "refresh-token-value",
                "expires_at": "2025-12-31T23:59:59Z",
            },
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.get("TestIntegration", org_id="org-123")

        mock_client.post.assert_called_once_with(
            "/api/cli/integrations/get",
            json={"name": "TestIntegration", "org_id": "org-123"},
        )
        assert result.entity_id == "api-tenant"
        assert result.config["api_key"] == "secret"
        assert result.oauth.client_id == "client-123"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_api_returns_null(self):
        """Test that integrations.get() returns None when API returns null."""
        from bifrost import integrations

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.get("NonexistentIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_when_api_call_fails(self):
        """Test that integrations.get() returns None on API failure."""
        from bifrost import integrations

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.get("TestIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_handles_uuid_dict_in_response(self):
        """Test that integrations.get() handles UUID as dict in API response."""
        from bifrost import integrations

        # Some JSON serializers return UUID as dict
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": str(uuid4()),
            "integration_id": {"uuid": "abc123"},  # Unusual format
            "entity_id": "tenant",
            "entity_name": None,
            "config": {},
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "oauth": None,
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.get("TestIntegration")

        # Should convert dict to string
        assert isinstance(result.integration_id, str)

    @pytest.mark.asyncio
    async def test_list_mappings_calls_api_endpoint(self):
        """Test that list_mappings() calls API endpoint in external mode."""
        from bifrost import integrations

        org1_id = str(uuid4())
        org2_id = str(uuid4())
        integration_id = str(uuid4())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": str(uuid4()),
                "integration_id": integration_id,
                "organization_id": org1_id,
                "entity_id": "tenant-1",
                "entity_name": "Tenant 1",
                "config": {"key": "val1"},
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "integration_id": integration_id,
                "organization_id": org2_id,
                "entity_id": "tenant-2",
                "entity_name": None,
                "config": {},
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
            },
        ]

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.list_mappings("TestIntegration")

        mock_client.post.assert_called_once_with(
            "/api/cli/integrations/list_mappings",
            json={"name": "TestIntegration"},
        )
        assert len(result) == 2
        assert result[0].entity_id == "tenant-1"
        assert result[1].entity_id == "tenant-2"

    @pytest.mark.asyncio
    async def test_list_mappings_returns_none_when_api_returns_null(self):
        """Test that list_mappings() returns None when API returns null."""
        from bifrost import integrations

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.list_mappings("NonexistentIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_mappings_returns_none_on_api_failure(self):
        """Test that list_mappings() returns None on API failure."""
        from bifrost import integrations

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("bifrost.integrations._get_client", return_value=mock_client):
            result = await integrations.list_mappings("TestIntegration")

        assert result is None

    @pytest.mark.asyncio
    async def test_requires_api_key_in_external_mode(self):
        """Test that external mode requires BIFROST_DEV_URL and BIFROST_DEV_KEY."""
        from bifrost import integrations
        import os

        # Clear env vars - need to actually remove them
        old_url = os.environ.get("BIFROST_DEV_URL")
        old_key = os.environ.get("BIFROST_DEV_KEY")

        try:
            if "BIFROST_DEV_URL" in os.environ:
                del os.environ["BIFROST_DEV_URL"]
            if "BIFROST_DEV_KEY" in os.environ:
                del os.environ["BIFROST_DEV_KEY"]

            with pytest.raises(
                RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"
            ):
                await integrations.get("TestIntegration")
        finally:
            # Restore env vars
            if old_url is not None:
                os.environ["BIFROST_DEV_URL"] = old_url
            if old_key is not None:
                os.environ["BIFROST_DEV_KEY"] = old_key


class TestIntegrationsContextDetection:
    """Test that integrations SDK correctly detects platform vs external mode."""

    def test_is_platform_context_true_when_context_set(self):
        """Test _is_platform_context() returns True when context is set."""
        from bifrost.integrations import _is_platform_context
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
        from bifrost.integrations import _is_platform_context

        clear_execution_context()
        assert _is_platform_context() is False
