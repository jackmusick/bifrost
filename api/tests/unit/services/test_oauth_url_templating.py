"""Unit tests for OAuth URL templating functionality.

Tests the resolve_url_template function that supports placeholder replacement
in OAuth token URLs for multi-tenant scenarios.
"""

import pytest

from src.services.oauth_provider import resolve_url_template


class TestResolveUrlTemplateBasic:
    """Test basic URL templating functionality"""

    def test_no_placeholders(self):
        """Should return URL unchanged if no placeholders present"""
        url = "https://oauth.example.com/token"
        result = resolve_url_template(url)
        assert result == url

    def test_empty_url(self):
        """Should handle empty URL gracefully"""
        result = resolve_url_template("")
        assert result == ""

    def test_none_url(self):
        """Should handle None URL gracefully"""
        result = resolve_url_template(None)
        assert result is None


class TestResolveUrlTemplateEntityId:
    """Test {entity_id} placeholder resolution"""

    def test_entity_id_replacement_with_value(self):
        """Should replace {entity_id} with provided value"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token"

    def test_entity_id_replacement_with_default(self):
        """Should replace {entity_id} with default value"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(url, defaults={"entity_id": "common"})
        assert result == "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    def test_entity_id_value_takes_precedence_over_default(self):
        """Should prefer entity_id value over defaults"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-456",
            defaults={"entity_id": "common"}
        )
        assert result == "https://login.microsoftonline.com/tenant-456/oauth2/v2.0/token"

    def test_entity_id_no_value_no_default(self):
        """Should leave placeholder unresolved if no value or default"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(url)
        assert result == "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"


class TestResolveUrlTemplateMultiplePlaceholders:
    """Test URLs with multiple placeholders"""

    def test_multiple_different_placeholders(self):
        """Should replace multiple different placeholders"""
        url = "https://{domain}/v1/{entity_id}/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-123",
            defaults={"domain": "oauth.example.com"}
        )
        assert result == "https://oauth.example.com/v1/tenant-123/token"

    def test_same_placeholder_multiple_times(self):
        """Should replace same placeholder in multiple locations"""
        url = "https://{entity_id}.oauth.example.com/{entity_id}/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://tenant-123.oauth.example.com/tenant-123/token"

    def test_mixed_resolved_and_unresolved(self):
        """Should resolve available placeholders, leave others"""
        url = "https://{domain}/v1/{entity_id}/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://{domain}/v1/tenant-123/token"


class TestResolveUrlTemplateEdgeCases:
    """Test edge cases and special scenarios"""

    def test_placeholder_at_different_positions(self):
        """Should resolve placeholders at different positions in URL"""
        # Start of path
        url = "{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "tenant-123/oauth2/v2.0/token"

        # End of path
        url = "https://login.example.com/oauth2/v2.0/{entity_id}"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://login.example.com/oauth2/v2.0/tenant-123"

    def test_placeholder_with_special_characters(self):
        """Should handle entity IDs with special characters"""
        url = "https://oauth.example.com/{entity_id}/token"
        entity_id = "tenant-abc_123.456"
        result = resolve_url_template(url, entity_id=entity_id)
        assert result == f"https://oauth.example.com/{entity_id}/token"

    def test_empty_entity_id_value(self):
        """Should treat empty string as no value"""
        url = "https://oauth.example.com/{entity_id}/token"
        result = resolve_url_template(url, entity_id="")
        assert result == "https://oauth.example.com/{entity_id}/token"

    def test_entity_id_with_forward_slashes(self):
        """Should handle entity IDs containing slashes (be careful with URLs)"""
        url = "https://oauth.example.com/{entity_id}/token"
        entity_id = "parent/child/tenant"
        result = resolve_url_template(url, entity_id=entity_id)
        assert result == "https://oauth.example.com/parent/child/tenant/token"

    def test_none_entity_id_with_default(self):
        """Should use default when entity_id is None"""
        url = "https://oauth.example.com/{entity_id}/token"
        result = resolve_url_template(
            url,
            entity_id=None,
            defaults={"entity_id": "common"}
        )
        assert result == "https://oauth.example.com/common/token"


class TestResolveUrlTemplateDefaults:
    """Test defaults dict functionality"""

    def test_defaults_with_custom_placeholders(self):
        """Should support custom placeholder defaults"""
        url = "https://{custom_domain}/api/{entity_id}/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-123",
            defaults={"custom_domain": "oauth.example.com"}
        )
        assert result == "https://oauth.example.com/api/tenant-123/token"

    def test_empty_defaults_dict(self):
        """Should handle empty defaults dict gracefully"""
        url = "https://oauth.example.com/{entity_id}/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-123",
            defaults={}
        )
        assert result == "https://oauth.example.com/tenant-123/token"

    def test_none_defaults(self):
        """Should handle None defaults gracefully"""
        url = "https://oauth.example.com/{entity_id}/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-123",
            defaults=None
        )
        assert result == "https://oauth.example.com/tenant-123/token"


class TestResolveUrlTemplateRealWorldScenarios:
    """Test real-world OAuth provider URL patterns"""

    def test_microsoft_azure_tenant_url(self):
        """Test Microsoft Azure OAuth with tenant variable"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(
            url,
            entity_id="customer-tenant-id-123",
            defaults={"entity_id": "common"}
        )
        assert result == "https://login.microsoftonline.com/customer-tenant-id-123/oauth2/v2.0/token"

    def test_microsoft_azure_fallback_to_common(self):
        """Test Microsoft Azure fallback to 'common' tenant"""
        url = "https://login.microsoftonline.com/{entity_id}/oauth2/v2.0/token"
        result = resolve_url_template(
            url,
            defaults={"entity_id": "common"}
        )
        assert result == "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    def test_quickbooks_realm_url(self):
        """Test QuickBooks OAuth with realm variable"""
        url = "https://quickbooks.example.com/{entity_id}/oauth2/token"
        result = resolve_url_template(
            url,
            entity_id="realm-123",
            defaults={"entity_id": "default"}
        )
        assert result == "https://quickbooks.example.com/realm-123/oauth2/token"

    def test_salesforce_instance_url(self):
        """Test Salesforce OAuth with instance URL"""
        url = "{entity_id}/services/oauth2/token"
        result = resolve_url_template(
            url,
            entity_id="https://customer-instance.salesforce.com",
            defaults={"entity_id": "https://login.salesforce.com"}
        )
        assert result == "https://customer-instance.salesforce.com/services/oauth2/token"


class TestResolveUrlTemplateValidation:
    """Test input validation and error handling"""

    def test_with_url_query_parameters(self):
        """Should preserve query parameters"""
        url = "https://oauth.example.com/{entity_id}/token?scope=read"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://oauth.example.com/tenant-123/token?scope=read"

    def test_with_url_fragment(self):
        """Should preserve URL fragments"""
        url = "https://oauth.example.com/{entity_id}/token#section"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://oauth.example.com/tenant-123/token#section"

    def test_placeholder_name_extraction(self):
        """Should correctly extract placeholder names"""
        # Valid placeholder names contain only word characters
        url = "https://oauth.example.com/{entity_id}/v{version}/token"
        result = resolve_url_template(
            url,
            entity_id="tenant-123",
            defaults={"version": "2"}
        )
        assert result == "https://oauth.example.com/tenant-123/v2/token"

    def test_malformed_placeholder_ignored(self):
        """Should ignore malformed placeholders like {incomplete (missing closing brace)"""
        # Incomplete {placeholder is not captured by regex since it lacks closing brace
        url = "https://oauth.example.com/{entity_id/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        assert result == "https://oauth.example.com/{entity_id/token"

    def test_double_braces_still_replaced(self):
        """Double braces {{entity_id}} still get inner part replaced (no escaping support)"""
        # Note: This behavior may change if brace escaping is implemented
        url = "https://oauth.example.com/{{entity_id}}/token"
        result = resolve_url_template(url, entity_id="tenant-123")
        # Current behavior: {entity_id} inside {{ }} is replaced, leaving outer braces
        assert result == "https://oauth.example.com/{tenant-123}/token"
