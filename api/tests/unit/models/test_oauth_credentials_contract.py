"""
Contract Tests for OAuth Credentials API
Tests for GET /api/oauth/credentials/{connection_name} endpoint (User Story 3)
"""

import pytest
from pydantic import ValidationError

from src.models import OAuthCredentialsModel as OAuthCredentials


class TestOAuthCredentialsContract:
    """Test OAuth credentials retrieval contract"""

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

