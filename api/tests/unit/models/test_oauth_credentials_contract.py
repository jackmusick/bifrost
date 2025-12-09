"""
Contract Tests for OAuth Credentials API
Tests for GET /api/oauth/credentials/{connection_name} endpoint (User Story 3)
"""

import pytest
from pydantic import ValidationError

from src.models.models import OAuthCredentialsModel as OAuthCredentials, OAuthCredentialsResponse


class TestOAuthCredentialsContract:
    """Test OAuth credentials retrieval contract"""

    def test_valid_oauth_credentials_model(self):
        """Test that OAuthCredentials model accepts valid data"""
        credentials = OAuthCredentials(
            connection_name="microsoft_graph",
            access_token="eyJ0eXAiOiJKV1QiLCJhbGci...",
            token_type="Bearer",
            expires_at="2025-10-12T15:30:00Z",
            scopes="User.Read Mail.Read"
        )

        assert credentials.connection_name == "microsoft_graph"
        assert credentials.access_token.startswith("eyJ0")
        assert credentials.token_type == "Bearer"
        assert credentials.expires_at == "2025-10-12T15:30:00Z"
        assert credentials.scopes == "User.Read Mail.Read"

    def test_oauth_credentials_with_refresh_token(self):
        """Test that refresh_token is optional"""
        credentials = OAuthCredentials(
            connection_name="google_api",
            access_token="ya29.a0AfH6...",
            token_type="Bearer",
            expires_at="2025-10-12T16:00:00Z",
            refresh_token="1//0eW9...",
            scopes="https://www.googleapis.com/auth/userinfo.email"
        )

        assert credentials.refresh_token == "1//0eW9..."

    def test_oauth_credentials_without_refresh_token(self):
        """Test that refresh_token is optional"""
        credentials = OAuthCredentials(
            connection_name="github",
            access_token="gho_16C7e42F...",
            token_type="Bearer",
            expires_at="2025-10-12T16:00:00Z",
            scopes="repo user"
        )

        assert credentials.refresh_token is None

    def test_oauth_credentials_response(self):
        """Test OAuthCredentialsResponse wrapper model"""
        response = OAuthCredentialsResponse(
            connection_name="azure_ad",
            credentials=OAuthCredentials(
                connection_name="azure_ad",
                access_token="eyJ0eXAiOiJKV1Qi...",
                token_type="Bearer",
                expires_at="2025-10-12T17:00:00Z",
                scopes=".default"
            ),
            status="completed",
            expires_at="2025-10-12T17:00:00Z"
        )

        assert response.connection_name == "azure_ad"
        assert response.status == "completed"
        assert response.credentials.access_token.startswith("eyJ0")

    def test_oauth_credentials_missing_required_field(self):
        """Test that required fields are enforced"""
        with pytest.raises(ValidationError) as exc_info:
            OAuthCredentials(
                connection_name="test",
                # Missing access_token
                token_type="Bearer",
                expires_at="2025-10-12T15:00:00Z"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("access_token",) for e in errors)

    def test_oauth_credentials_invalid_connection_name(self):
        """Test that connection_name follows naming rules"""
        with pytest.raises(ValidationError) as exc_info:
            OAuthCredentials(
                connection_name="invalid name!",  # Spaces and special chars
                access_token="token123",
                token_type="Bearer",
                expires_at="2025-10-12T15:00:00Z"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("connection_name",) for e in errors)

    def test_oauth_credentials_empty_access_token(self):
        """Test that access_token cannot be empty"""
        with pytest.raises(ValidationError) as exc_info:
            OAuthCredentials(
                connection_name="test",
                access_token="",  # Empty token
                token_type="Bearer",
                expires_at="2025-10-12T15:00:00Z"
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("access_token",) for e in errors)

    def test_oauth_credentials_serialization(self):
        """Test that credentials can be serialized to JSON"""
        credentials = OAuthCredentials(
            connection_name="slack",
            access_token="xoxb-1234567890",
            token_type="Bearer",
            expires_at="2025-10-12T18:00:00Z",
            scopes="chat:write users:read"
        )

        json_data = credentials.model_dump()
        assert json_data["connection_name"] == "slack"
        assert json_data["access_token"] == "xoxb-1234567890"
        assert "access_token" in json_data  # Ensure token is present

    def test_oauth_credentials_response_serialization(self):
        """Test that response wrapper serializes correctly"""
        response = OAuthCredentialsResponse(
            connection_name="dropbox",
            credentials=OAuthCredentials(
                connection_name="dropbox",
                access_token="sl.B1234567890",
                token_type="Bearer",
                expires_at="2025-10-12T19:00:00Z",
                scopes="files.content.read"
            ),
            status="completed",
            expires_at="2025-10-12T19:00:00Z"
        )

        json_data = response.model_dump()
        assert json_data["connection_name"] == "dropbox"
        assert json_data["credentials"]["access_token"] == "sl.B1234567890"
        assert json_data["status"] == "completed"

    def test_oauth_credentials_expired_status(self):
        """Test handling of expired credentials in response"""
        response = OAuthCredentialsResponse(
            connection_name="expired_conn",
            credentials=OAuthCredentials(
                connection_name="expired_conn",
                access_token="expired_token",
                token_type="Bearer",
                expires_at="2025-01-01T00:00:00Z",  # Past date
                scopes="read"
            ),
            status="failed",
            expires_at="2025-01-01T00:00:00Z"
        )

        assert response.status == "failed"

    def test_oauth_credentials_pending_status(self):
        """Test handling of not_connected status"""
        response = OAuthCredentialsResponse(
            connection_name="pending_conn",
            credentials=None,  # No credentials yet
            status="not_connected",
            expires_at=None
        )

        assert response.status == "not_connected"
        assert response.credentials is None
