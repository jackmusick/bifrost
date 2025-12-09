"""
Unit tests for secret naming business logic.

These tests validate the secret naming conventions and utilities
without requiring any external dependencies.
"""

import re
import pytest
from src.core.secret_naming import (
    sanitize_scope,
    sanitize_name_component,
    generate_secret_name,
    generate_oauth_secret_name,
    is_secret_reference,
    SecretNameTooLongError,
    InvalidSecretComponentError,
    MAX_SECRET_NAME_LENGTH,
)


class TestSanitizeScope:
    """Tests for sanitize_scope function"""

    def test_sanitize_global(self):
        """GLOBAL scope should be converted to lowercase"""
        assert sanitize_scope("GLOBAL") == "global"

    def test_sanitize_valid_org(self):
        """Valid org IDs should be lowercased, underscores converted to dashes"""
        assert sanitize_scope("acme-corp") == "acme-corp"
        assert sanitize_scope("org-123") == "org-123"
        assert sanitize_scope("my_org_456") == "my-org-456"  # Underscores become dashes

    def test_sanitize_invalid_characters(self):
        """Invalid characters should be replaced with hyphens"""
        assert sanitize_scope("org@123") == "org-123"
        assert sanitize_scope("test.org.name") == "test-org-name"
        assert sanitize_scope("org/123/test") == "org-123-test"

    def test_sanitize_consecutive_hyphens(self):
        """Consecutive hyphens should be collapsed"""
        assert sanitize_scope("org---123") == "org-123"
        assert sanitize_scope("test..org") == "test-org"

    def test_sanitize_leading_trailing_hyphens(self):
        """Leading and trailing hyphens should be removed"""
        assert sanitize_scope("-org-123-") == "org-123"
        assert sanitize_scope("--test--") == "test"


class TestSanitizeNameComponent:
    """Tests for sanitize_name_component function"""

    def test_sanitize_valid_component(self):
        """Valid components should be lowercased, underscores converted to dashes"""
        assert sanitize_name_component("api_key") == "api-key"
        assert sanitize_name_component("smtp-password") == "smtp-password"
        assert sanitize_name_component("config123") == "config123"
        assert sanitize_name_component("MyConfig") == "myconfig"

    def test_sanitize_dotted_component(self):
        """Dots should be replaced with hyphens"""
        assert sanitize_name_component("my.config.key") == "my-config-key"
        assert sanitize_name_component("database.connection.string") == "database-connection-string"

    def test_sanitize_special_characters(self):
        """Special characters should be replaced with hyphens"""
        assert sanitize_name_component("api@key") == "api-key"
        assert sanitize_name_component("test/config") == "test-config"
        assert sanitize_name_component("value#123") == "value-123"


class TestGenerateSecretName:
    """Tests for generate_secret_name function"""

    def test_generate_global_secret(self):
        """Should generate valid secret name for GLOBAL scope"""
        name = generate_secret_name("GLOBAL", "api_key")

        # Should follow pattern: bifrost-global-api-key-{uuid}
        assert name.startswith("bifrost-global-api-key-")
        assert len(name) <= MAX_SECRET_NAME_LENGTH

        # Extract UUID (last 5 dash-separated parts)
        parts = name.split("-")
        uuid_part = "-".join(parts[-5:])
        uuid_pattern = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
        assert uuid_pattern.match(uuid_part)

    def test_generate_org_secret(self):
        """Should generate valid secret name for org scope"""
        name = generate_secret_name("acme-corp", "smtp_password")

        assert name.startswith("bifrost-acme-corp-smtp-password-")
        assert len(name) <= MAX_SECRET_NAME_LENGTH

    def test_generate_with_sanitization(self):
        """Should sanitize scope and component to lowercase with dashes"""
        name = generate_secret_name("org@123", "my.config.key")

        # Should sanitize @ and . to hyphens, convert to lowercase
        assert "org-123" in name
        assert "my-config-key" in name
        assert name.startswith("bifrost-org-123-my-config-key-")

    def test_generate_unique_names(self):
        """Should generate unique names with different UUIDs"""
        name1 = generate_secret_name("GLOBAL", "api_key")
        name2 = generate_secret_name("GLOBAL", "api_key")

        # Same inputs should produce different UUIDs
        assert name1 != name2
        # Same prefix (everything except UUID)
        prefix1 = "-".join(name1.split("-")[:-5])
        prefix2 = "-".join(name2.split("-")[:-5])
        assert prefix1 == prefix2

    def test_generate_custom_prefix(self):
        """Should support custom prefix"""
        name = generate_secret_name("GLOBAL", "test", prefix="custom")

        assert name.startswith("custom-global-test-")

    def test_name_too_long_raises_error(self):
        """Should raise error if generated name exceeds max length"""
        # Create a very long component that will exceed 127 chars
        long_component = "a" * 100

        with pytest.raises(SecretNameTooLongError) as exc_info:
            generate_secret_name("GLOBAL", long_component)

        assert "exceeds maximum of 127" in str(exc_info.value)
        assert str(len("bifrost_GLOBAL_" + long_component + "_" + "a" * 36)) in str(exc_info.value)

    def test_empty_scope_raises_error(self):
        """Should raise error if scope is empty after sanitization"""
        with pytest.raises(InvalidSecretComponentError) as exc_info:
            generate_secret_name("@@@", "test")

        assert "contains only invalid characters" in str(exc_info.value)

    def test_empty_component_raises_error(self):
        """Should raise error if component is empty after sanitization"""
        with pytest.raises(InvalidSecretComponentError) as exc_info:
            generate_secret_name("GLOBAL", "...")

        assert "contains only invalid characters" in str(exc_info.value)


class TestGenerateOAuthSecretName:
    """Tests for generate_oauth_secret_name function"""

    def test_generate_client_secret(self):
        """Should generate valid OAuth client secret name"""
        name = generate_oauth_secret_name("acme-corp", "github", "client-secret")

        assert name.startswith("bifrost-acme-corp-oauth-github-client-secret-")
        assert len(name) <= MAX_SECRET_NAME_LENGTH

        # UUID should be valid (last 5 parts)
        parts = name.split("-")
        uuid_part = "-".join(parts[-5:])
        uuid_pattern = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$")
        assert uuid_pattern.match(uuid_part)

    def test_generate_token_response(self):
        """Should generate valid OAuth token response name"""
        name = generate_oauth_secret_name("org-123", "microsoft", "response")

        assert name.startswith("bifrost-org-123-oauth-microsoft-response-")
        assert len(name) <= MAX_SECRET_NAME_LENGTH

    def test_generate_global_oauth(self):
        """Should generate valid OAuth secret for GLOBAL scope"""
        name = generate_oauth_secret_name("GLOBAL", "slack", "client-secret")

        assert name.startswith("bifrost-global-oauth-slack-client-secret-")

    def test_oauth_with_sanitization(self):
        """Should sanitize all components"""
        name = generate_oauth_secret_name("org@123", "my.connection", "client.secret")

        assert "org-123" in name
        assert "my-connection" in name
        assert "client-secret" in name

    def test_oauth_unique_names(self):
        """Should generate unique OAuth names"""
        name1 = generate_oauth_secret_name("acme-corp", "github", "client-secret")
        name2 = generate_oauth_secret_name("acme-corp", "github", "client-secret")

        assert name1 != name2

    def test_oauth_name_too_long_raises_error(self):
        """Should raise error if OAuth name exceeds max length"""
        long_connection = "a" * 80

        with pytest.raises(SecretNameTooLongError) as exc_info:
            generate_oauth_secret_name("GLOBAL", long_connection, "client-secret")

        assert "exceeds maximum of 127" in str(exc_info.value)


class TestIsSecretReference:
    """Tests for is_secret_reference function"""

    def test_bifrost_format_is_reference(self):
        """Should recognize bifrost format as reference"""
        ref = "bifrost-global-api-key-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert is_secret_reference(ref) is True

    def test_bifrost_oauth_format_is_reference(self):
        """Should recognize bifrost OAuth format as reference"""
        ref = "bifrost-acme-corp-oauth-github-client-secret-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert is_secret_reference(ref) is True

    def test_legacy_format_is_reference(self):
        """Should recognize legacy format as reference"""
        assert is_secret_reference("org-123--my-secret") is True
        assert is_secret_reference("GLOBAL--smtp-password") is True

    def test_plain_value_not_reference(self):
        """Should not recognize plain values as references"""
        assert is_secret_reference("my-actual-secret-value") is False
        assert is_secret_reference("just-some-password-123") is False
        assert is_secret_reference("abc123def456") is False

    def test_bifrost_without_uuid_not_reference(self):
        """Should not recognize bifrost format without valid UUID"""
        assert is_secret_reference("bifrost_GLOBAL_api_key_not-a-uuid") is False
        assert is_secret_reference("bifrost_GLOBAL_api_key") is False

    def test_malformed_legacy_not_reference(self):
        """Should not recognize malformed legacy format"""
        assert is_secret_reference("org-123-my-secret") is False  # Single hyphen
        assert is_secret_reference("org-123--my--secret--key") is False  # Multiple --


class TestSecretNamingIntegration:
    """Integration tests combining multiple naming functions"""

    def test_generate_and_verify_reference(self):
        """Generated names should be recognized as references"""
        name = generate_secret_name("GLOBAL", "test_key")

        assert is_secret_reference(name) is True

    def test_oauth_generate_and_verify(self):
        """Generated OAuth names should be recognized as references"""
        name = generate_oauth_secret_name("org-123", "github", "client-secret")

        assert is_secret_reference(name) is True
