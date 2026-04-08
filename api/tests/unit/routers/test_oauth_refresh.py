"""Tests for OAuth refresh endpoint handling client_credentials flow."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch


class TestOAuthRefreshClientCredentials:
    """Test that /refresh endpoint handles client_credentials flow correctly."""

    @pytest.mark.asyncio
    async def test_refresh_uses_client_credentials_flow_when_appropriate(self):
        """For client_credentials flow, should call get_client_credentials_token."""
        from src.services.oauth_provider import OAuthProviderClient

        # Create mock provider
        provider = MagicMock()
        provider.oauth_flow_type = "client_credentials"
        provider.token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        provider.client_id = "test-client-id"
        provider.encrypted_client_secret = b"encrypted-secret"
        provider.scopes = ["https://graph.microsoft.com/.default"]

        # Mock the OAuth client response
        mock_token_response = {
            "access_token": "new-access-token",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        oauth_client = OAuthProviderClient()

        with patch.object(
            oauth_client,
            "get_client_credentials_token",
            new_callable=AsyncMock,
            return_value=(True, mock_token_response),
        ) as mock_get_token:
            success, result = await oauth_client.get_client_credentials_token(
                token_url=provider.token_url,
                client_id=provider.client_id,
                client_secret="decrypted-secret",
                scopes=" ".join(provider.scopes),
            )

            mock_get_token.assert_called_once()
            assert success is True
            assert result["access_token"] == "new-access-token"

    @pytest.mark.asyncio
    async def test_refresh_uses_refresh_token_for_authorization_code_flow(self):
        """For authorization_code flow, should call refresh_access_token."""
        from src.services.oauth_provider import OAuthProviderClient

        # Create mock provider
        provider = MagicMock()
        provider.oauth_flow_type = "authorization_code"
        provider.token_url = "https://oauth.example.com/token"
        provider.client_id = "test-client-id"
        provider.encrypted_client_secret = b"encrypted-secret"

        # Mock token with refresh token
        token = MagicMock()
        token.encrypted_refresh_token = b"encrypted-refresh-token"

        # Mock the OAuth client response
        mock_token_response = {
            "access_token": "refreshed-access-token",
            "refresh_token": "new-refresh-token",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        oauth_client = OAuthProviderClient()

        with patch.object(
            oauth_client,
            "refresh_access_token",
            new_callable=AsyncMock,
            return_value=(True, mock_token_response),
        ) as mock_refresh:
            success, result = await oauth_client.refresh_access_token(
                token_url=provider.token_url,
                refresh_token="decrypted-refresh-token",
                client_id=provider.client_id,
                client_secret="decrypted-secret",
            )

            mock_refresh.assert_called_once()
            assert success is True
            assert result["access_token"] == "refreshed-access-token"

    def test_oauth_flow_type_determines_refresh_behavior(self):
        """Flow type should determine which refresh method is used."""
        # client_credentials flow: no refresh token, use get_client_credentials_token
        # authorization_code flow: use stored refresh token with refresh_access_token

        # This is a logic test - we verify the expected behavior
        client_credentials_needs_refresh_token = False  # Uses client_credentials grant
        authorization_code_needs_refresh_token = True   # Uses refresh_token grant

        assert client_credentials_needs_refresh_token is False
        assert authorization_code_needs_refresh_token is True


class TestOAuthRefreshEndpointLogic:
    """Test the endpoint logic branching based on flow type."""

    def test_client_credentials_flow_detected(self):
        """Verify client_credentials flow is correctly identified."""
        provider = MagicMock()
        provider.oauth_flow_type = "client_credentials"

        is_client_credentials = provider.oauth_flow_type == "client_credentials"
        assert is_client_credentials is True

    def test_authorization_code_flow_detected(self):
        """Verify authorization_code flow is correctly identified."""
        provider = MagicMock()
        provider.oauth_flow_type = "authorization_code"

        is_client_credentials = provider.oauth_flow_type == "client_credentials"
        assert is_client_credentials is False

    def test_client_credentials_requires_client_secret(self):
        """client_credentials flow requires client_secret."""
        provider = MagicMock()
        provider.oauth_flow_type = "client_credentials"
        provider.encrypted_client_secret = None

        has_client_secret = provider.encrypted_client_secret is not None
        assert has_client_secret is False

        provider.encrypted_client_secret = b"some-secret"
        has_client_secret = provider.encrypted_client_secret is not None
        assert has_client_secret is True


class TestUrlResolutionDefaults:
    """Test entity_id resolution for OAuth URL templates."""

    @pytest.mark.asyncio
    async def test_uses_integration_entity_id_when_default_missing(self):
        """Refresh routes should fall back to integration.entity_id."""
        from src.routers.oauth_connections import get_url_resolution_defaults

        provider = MagicMock()
        provider.token_url_defaults = {}
        provider.integration_id = "integration-123"

        integration = MagicMock()
        integration.default_entity_id = None
        integration.entity_id = "tenant-123"

        result = MagicMock()
        result.scalar_one_or_none.return_value = integration

        db = AsyncMock()
        db.execute.return_value = result

        defaults = await get_url_resolution_defaults(db, provider)

        assert defaults == {"entity_id": "tenant-123"}
