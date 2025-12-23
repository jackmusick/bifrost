"""
E2E tests for Integrations API.

Tests CRUD operations for integrations and integration mappings.
Tests OAuth configuration and authorization endpoints.
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from sqlalchemy import select
from src.models.orm import OAuthProvider


@pytest.mark.e2e
class TestIntegrationsCRUD:
    """Test Integration CRUD operations."""

    @pytest.fixture
    def integration(self, e2e_client, platform_admin):
        """Create an integration and clean up after."""
        integration_name = f"e2e_test_integration_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {
                        "key": "api_endpoint",
                        "type": "string",
                        "required": True,
                        "description": "API endpoint URL",
                    }
                ],
            },
        )
        assert response.status_code == 201, f"Create integration failed: {response.text}"
        integration = response.json()

        yield integration

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_create_integration(self, e2e_client, platform_admin):
        """Platform admin can create an integration."""
        integration_name = f"e2e_create_test_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {
                        "key": "tenant_id",
                        "type": "string",
                        "required": True,
                        "description": "Tenant ID",
                    }
                ],
            },
        )
        assert response.status_code == 201, f"Create failed: {response.text}"
        integration = response.json()
        assert integration["name"] == integration_name
        assert integration["config_schema"] is not None
        assert len(integration["config_schema"]) == 1
        assert integration["is_deleted"] is False

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_list_integrations(self, e2e_client, platform_admin, integration):
        """Platform admin can list integrations."""
        response = e2e_client.get(
            "/api/integrations",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        integrations = data.get("items", data)
        assert isinstance(integrations, list)
        names = [i["name"] for i in integrations]
        assert integration["name"] in names

    def test_get_integration(self, e2e_client, platform_admin, integration):
        """Platform admin can get integration by ID."""
        response = e2e_client.get(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get failed: {response.text}"
        data = response.json()
        assert data["id"] == integration["id"]
        assert data["name"] == integration["name"]

    def test_get_integration_by_name(self, e2e_client, platform_admin, integration):
        """Platform admin can get integration by name."""
        response = e2e_client.get(
            f"/api/integrations/by-name/{integration['name']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get by name failed: {response.text}"
        data = response.json()
        assert data["id"] == integration["id"]
        assert data["name"] == integration["name"]

    def test_update_integration(self, e2e_client, platform_admin, integration):
        """Platform admin can update an integration."""
        new_name = f"updated_{integration['name']}"
        response = e2e_client.put(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
            json={
                "name": new_name,
            },
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        updated = response.json()
        assert updated["name"] == new_name

    def test_delete_integration(self, e2e_client, platform_admin):
        """Platform admin can soft-delete an integration."""
        # Create an integration to delete
        integration_name = f"e2e_delete_test_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        # Delete it
        response = e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete failed: {response.text}"

        # Verify it's soft-deleted (not in normal list)
        response = e2e_client.get(
            "/api/integrations",
            headers=platform_admin.headers,
        )
        integrations = response.json().get("items", response.json())
        ids = [i["id"] for i in integrations]
        assert integration["id"] not in ids


@pytest.mark.e2e
class TestIntegrationMappingsCRUD:
    """Test IntegrationMapping CRUD operations."""

    @pytest.fixture
    def integration_for_mapping(self, e2e_client, platform_admin):
        """Create an integration for mapping tests."""
        integration_name = f"e2e_mapping_integration_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        yield integration

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    @pytest.fixture
    def mapping(self, e2e_client, platform_admin, integration_for_mapping, org1):
        """Create a mapping and clean up after."""
        response = e2e_client.post(
            f"/api/integrations/{integration_for_mapping['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "tenant-12345",
                "entity_name": "Test Tenant",
            },
        )
        assert response.status_code == 201, f"Create mapping failed: {response.text}"
        mapping = response.json()

        yield mapping

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )

    def test_create_mapping(self, e2e_client, platform_admin, integration_for_mapping, org1):
        """Platform admin can create an integration mapping."""
        response = e2e_client.post(
            f"/api/integrations/{integration_for_mapping['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "tenant-create-test",
                "entity_name": "Create Test Tenant",
            },
        )
        assert response.status_code == 201, f"Create failed: {response.text}"
        mapping = response.json()
        assert mapping["entity_id"] == "tenant-create-test"
        assert mapping["entity_name"] == "Create Test Tenant"
        assert mapping["organization_id"] == str(org1["id"])

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )

    def test_list_mappings(self, e2e_client, platform_admin, integration_for_mapping, mapping):
        """Platform admin can list integration mappings."""
        response = e2e_client.get(
            f"/api/integrations/{integration_for_mapping['id']}/mappings",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        mappings = data.get("items", data)
        assert isinstance(mappings, list)
        assert len(mappings) >= 1
        ids = [m["id"] for m in mappings]
        assert mapping["id"] in ids

    def test_get_mapping(self, e2e_client, platform_admin, integration_for_mapping, mapping):
        """Platform admin can get a mapping by ID."""
        response = e2e_client.get(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get failed: {response.text}"
        data = response.json()
        assert data["id"] == mapping["id"]
        assert data["entity_id"] == mapping["entity_id"]

    def test_get_mapping_by_org(self, e2e_client, platform_admin, integration_for_mapping, mapping, org1):
        """Platform admin can get a mapping by organization."""
        response = e2e_client.get(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/by-org/{org1['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get by org failed: {response.text}"
        data = response.json()
        assert data["id"] == mapping["id"]
        assert data["organization_id"] == str(org1["id"])

    def test_update_mapping(self, e2e_client, platform_admin, integration_for_mapping, mapping):
        """Platform admin can update a mapping."""
        response = e2e_client.put(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
            json={
                "entity_name": "Updated Tenant Name",
            },
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        updated = response.json()
        assert updated["entity_name"] == "Updated Tenant Name"

    def test_delete_mapping(self, e2e_client, platform_admin, integration_for_mapping, org1):
        """Platform admin can delete a mapping."""
        # Create a mapping to delete
        response = e2e_client.post(
            f"/api/integrations/{integration_for_mapping['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "tenant-delete-test",
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        # Delete it
        response = e2e_client.delete(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete failed: {response.text}"

        # Verify it's gone
        response = e2e_client.get(
            f"/api/integrations/{integration_for_mapping['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


@pytest.mark.e2e
class TestIntegrationsSDK:
    """Test Integration SDK endpoint."""

    @pytest.fixture
    def integration_with_mapping(self, e2e_client, platform_admin, org1):
        """Create an integration with a mapping for SDK tests."""
        integration_name = f"e2e_sdk_integration_{uuid4().hex[:8]}"

        # Create integration
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "entity_id": "global-tenant-123",
                "entity_id_name": "Tenant ID",
                "config_schema": [
                    {
                        "key": "api_url",
                        "type": "string",
                        "required": False,
                        "default": "https://api.example.com",
                    }
                ],
            },
        )
        assert response.status_code == 201
        integration = response.json()

        # Create mapping
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "org-tenant-456",
                "entity_name": "Org Tenant",
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        yield {"integration": integration, "mapping": mapping, "org": org1}

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_get_sdk_data(self, e2e_client, platform_admin, integration_with_mapping):
        """SDK endpoint returns integration data for an org."""
        integration = integration_with_mapping["integration"]
        org = integration_with_mapping["org"]

        response = e2e_client.get(
            f"/api/integrations/sdk/{integration['name']}",
            headers=platform_admin.headers,
            params={"org_id": str(org["id"])},
        )
        assert response.status_code == 200, f"Get SDK data failed: {response.text}"
        data = response.json()

        assert data["integration_id"] == integration["id"]
        assert data["entity_id"] == "org-tenant-456"  # From mapping
        assert "config" in data

    def test_get_sdk_data_not_found(self, e2e_client, platform_admin, org1):
        """SDK endpoint returns 404 for non-existent integration."""
        response = e2e_client.get(
            "/api/integrations/sdk/nonexistent_integration",
            headers=platform_admin.headers,
            params={"org_id": str(org1["id"])},
        )
        assert response.status_code == 404

    def test_get_sdk_data_no_mapping(self, e2e_client, platform_admin, org1):
        """SDK endpoint returns 404 when org has no mapping."""
        # Create integration without mapping
        integration_name = f"e2e_no_mapping_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        try:
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration_name}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 404
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )


@pytest.mark.e2e
class TestIntegrationOAuth:
    """Test Integration OAuth configuration and authorization endpoints."""

    @pytest_asyncio.fixture
    async def integration_with_oauth(self, e2e_client, platform_admin, db_session):
        """Create an integration with OAuth provider."""
        integration_name = f"e2e_oauth_integration_{uuid4().hex[:8]}"

        # Create integration
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {
                        "key": "tenant_id",
                        "type": "string",
                        "required": True,
                    }
                ],
            },
        )
        assert response.status_code == 201
        integration = response.json()

        # Create OAuth provider directly in database
        from uuid import UUID
        integration_id = UUID(integration["id"])
        oauth_provider = OAuthProvider(
            provider_name="test_provider",
            display_name="Test OAuth Provider",
            oauth_flow_type="authorization_code",
            client_id="test-client-id",
            encrypted_client_secret=b"encrypted_secret",
            authorization_url="https://provider.example.com/authorize",
            token_url="https://provider.example.com/token",
            scopes=["read", "write"],
            redirect_uri="/api/oauth/callback/test_provider",
            integration_id=integration_id,
        )
        db_session.add(oauth_provider)
        await db_session.commit()

        yield {"integration": integration, "oauth_provider": oauth_provider}

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_get_oauth_config(self, e2e_client, platform_admin, integration_with_oauth):
        """Platform admin can get OAuth configuration for an integration."""
        integration = integration_with_oauth["integration"]
        oauth_provider = integration_with_oauth["oauth_provider"]

        response = e2e_client.get(
            f"/api/integrations/{integration['id']}/oauth",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get OAuth config failed: {response.text}"
        data = response.json()

        assert data["provider_name"] == oauth_provider.provider_name
        assert data["display_name"] == oauth_provider.display_name
        assert data["oauth_flow_type"] == oauth_provider.oauth_flow_type
        assert data["client_id"] == oauth_provider.client_id
        assert data["authorization_url"] == oauth_provider.authorization_url
        assert data["token_url"] == oauth_provider.token_url
        assert data["scopes"] == oauth_provider.scopes

    def test_get_oauth_config_not_found(self, e2e_client, platform_admin):
        """Returns 404 if no OAuth config exists for integration."""
        # Create integration without OAuth provider
        integration_name = f"e2e_no_oauth_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        try:
            response = e2e_client.get(
                f"/api/integrations/{integration['id']}/oauth",
                headers=platform_admin.headers,
            )
            assert response.status_code == 404
            assert "No OAuth configuration" in response.json()["detail"]
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )

    def test_get_oauth_authorize_url(
        self, e2e_client, platform_admin, integration_with_oauth
    ):
        """Platform admin can get OAuth authorization URL."""
        integration = integration_with_oauth["integration"]

        response = e2e_client.get(
            f"/api/integrations/{integration['id']}/oauth/authorize",
            headers=platform_admin.headers,
            params={"redirect_uri": "http://localhost:3000/callback"},
        )
        assert response.status_code == 200, f"Get authorize URL failed: {response.text}"
        data = response.json()

        assert "authorization_url" in data
        assert "state" in data
        assert "Redirect user" in data["message"]

        # Verify authorization URL contains expected parameters
        auth_url = data["authorization_url"]
        assert "https://provider.example.com/authorize?" in auth_url
        assert "client_id=test-client-id" in auth_url
        assert "response_type=code" in auth_url
        assert "state=" in auth_url
        assert "scope=read+write" in auth_url
        assert "redirect_uri=" in auth_url

    def test_get_oauth_authorize_url_missing_redirect_uri(
        self, e2e_client, platform_admin, integration_with_oauth
    ):
        """Returns 422 if redirect_uri is not provided."""
        integration = integration_with_oauth["integration"]

        response = e2e_client.get(
            f"/api/integrations/{integration['id']}/oauth/authorize",
            headers=platform_admin.headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_oauth_authorize_url_client_credentials_flow(
        self, e2e_client, platform_admin, db_session
    ):
        """Returns 400 for client_credentials flow (no user authorization needed)."""
        integration_name = f"e2e_client_creds_{uuid4().hex[:8]}"

        # Create integration
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        # Create OAuth provider with client_credentials flow (no authorization_url)
        from uuid import UUID
        integration_id = UUID(integration["id"])
        oauth_provider = OAuthProvider(
            provider_name="client_creds_provider",
            oauth_flow_type="client_credentials",
            client_id="test-client-id",
            encrypted_client_secret=b"encrypted_secret",
            token_url="https://provider.example.com/token",
            # No authorization_url for client_credentials flow
            integration_id=integration_id,
        )
        db_session.add(oauth_provider)
        await db_session.commit()

        try:
            response = e2e_client.get(
                f"/api/integrations/{integration['id']}/oauth/authorize",
                headers=platform_admin.headers,
                params={"redirect_uri": "http://localhost:3000/callback"},
            )
            assert response.status_code == 400
            assert "client_credentials" in response.json()["detail"]
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )


@pytest.mark.e2e
class TestIntegrationConfig:
    """Test Integration config defaults and merging."""

    @pytest.fixture
    def integration_with_schema(self, e2e_client, platform_admin):
        """Create an integration with config schema for testing."""
        integration_name = f"e2e_config_test_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {"key": "api_url", "type": "string", "required": True},
                    {"key": "timeout", "type": "int", "required": False},
                    {"key": "debug", "type": "bool", "required": False},
                ],
            },
        )
        assert response.status_code == 201
        integration = response.json()

        yield integration

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_set_integration_config_defaults(self, e2e_client, platform_admin, integration_with_schema):
        """Platform admin can set integration-level config defaults."""
        integration = integration_with_schema

        # Set default config
        response = e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://api.default.com",
                    "timeout": 30,
                    "debug": False,
                }
            },
        )
        assert response.status_code == 200, f"Set config failed: {response.text}"
        data = response.json()
        assert data["integration_id"] == integration["id"]
        assert data["config"]["api_url"] == "https://api.default.com"
        assert data["config"]["timeout"] == 30
        assert data["config"]["debug"] is False

    def test_get_integration_config_defaults(self, e2e_client, platform_admin, integration_with_schema):
        """Platform admin can get integration-level config defaults."""
        integration = integration_with_schema

        # Set default config first
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://api.example.com",
                    "timeout": 60,
                }
            },
        )

        # Get default config
        response = e2e_client.get(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get config failed: {response.text}"
        data = response.json()
        assert data["integration_id"] == integration["id"]
        assert data["config"]["api_url"] == "https://api.example.com"
        assert data["config"]["timeout"] == 60

    def test_config_merging_defaults_with_overrides(self, e2e_client, platform_admin, integration_with_schema, org1):
        """Config merging: org overrides take precedence over defaults."""
        integration = integration_with_schema

        # Set integration defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://api.default.com",
                    "timeout": 30,
                    "debug": False,
                }
            },
        )

        # Create mapping with org-specific override
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "tenant-123",
                "config": {
                    "api_url": "https://api.org-override.com",  # Override
                    "timeout": 60,  # Override
                    # debug not provided - should use default
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Verify SDK endpoint returns merged config
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200, f"Get SDK data failed: {response.text}"
            data = response.json()

            # Org overrides should take precedence
            assert data["config"]["api_url"] == "https://api.org-override.com"
            assert data["config"]["timeout"] == 60
            # Default should be used where no override exists
            assert data["config"]["debug"] is False
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_org_config_override_precedence(self, e2e_client, platform_admin, integration_with_schema, org1):
        """Org config values override integration defaults."""
        integration = integration_with_schema

        # Set integration defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://default.com",
                    "timeout": 10,
                }
            },
        )

        # Create mapping with org override
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "override-test",
                "config": {
                    "timeout": 999,  # Override only timeout
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Get SDK data
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            # api_url should use default, timeout should use override
            assert data["config"]["api_url"] == "https://default.com"
            assert data["config"]["timeout"] == 999
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_clearing_override_falls_back_to_default(self, e2e_client, platform_admin, integration_with_schema, org1):
        """Clearing an org override falls back to integration default."""
        integration = integration_with_schema

        # Set integration defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://default.com",
                }
            },
        )

        # Create mapping with override
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "clear-test",
                "config": {
                    "api_url": "https://override.com",
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Verify override is active
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            data = response.json()
            assert data["config"]["api_url"] == "https://override.com"

            # Clear override by updating mapping with null value for the key
            response = e2e_client.put(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
                json={
                    "config": {"api_url": None},
                },
            )
            assert response.status_code == 200

            # Verify fallback to default
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            data = response.json()
            assert data["config"]["api_url"] == "https://default.com"
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_sdk_returns_default_when_org_has_no_override(self, e2e_client, platform_admin, integration_with_schema, org1):
        """SDK returns integration default when org has no override for a key."""
        integration = integration_with_schema

        # Set integration defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://default-only.com",
                    "timeout": 45,
                }
            },
        )

        # Create mapping WITHOUT config overrides
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "no-override",
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Call SDK endpoint, verify defaults are returned
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            # Should return defaults
            assert data["config"]["api_url"] == "https://default-only.com"
            assert data["config"]["timeout"] == 45
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_sdk_returns_org_override_when_set(self, e2e_client, platform_admin, integration_with_schema, org1):
        """SDK returns org override when set."""
        integration = integration_with_schema

        # Set integration defaults
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://default.com",
                }
            },
        )

        # Create mapping WITH config overrides
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "with-override",
                "config": {
                    "api_url": "https://org-specific.com",
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Call SDK endpoint, verify overrides are returned
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            # Should return org override
            assert data["config"]["api_url"] == "https://org-specific.com"
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )

    def test_sdk_returns_empty_dict_when_no_config(self, e2e_client, platform_admin, org1):
        """SDK returns empty config dict when no schema/defaults/overrides."""
        # Create integration WITHOUT config_schema
        integration_name = f"e2e_no_config_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        assert response.status_code == 201
        integration = response.json()

        try:
            # Create mapping without config
            response = e2e_client.post(
                f"/api/integrations/{integration['id']}/mappings",
                headers=platform_admin.headers,
                json={
                    "organization_id": str(org1["id"]),
                    "entity_id": "no-config",
                },
            )
            assert response.status_code == 201
            mapping = response.json()

            # Call SDK endpoint, verify config is empty dict
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration_name}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["config"] == {}

            # Cleanup mapping
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )
        finally:
            # Cleanup integration
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )

    def test_sdk_handles_null_config_values_gracefully(self, e2e_client, platform_admin, integration_with_schema, org1):
        """SDK handles null/missing config values gracefully."""
        integration = integration_with_schema

        # Set partial config (some keys null/missing)
        e2e_client.put(
            f"/api/integrations/{integration['id']}/config",
            headers=platform_admin.headers,
            json={
                "config": {
                    "api_url": "https://partial.com",
                    # timeout not set
                }
            },
        )

        # Create mapping
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "null-test",
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        try:
            # Verify SDK returns correctly merged config
            response = e2e_client.get(
                f"/api/integrations/sdk/{integration['name']}",
                headers=platform_admin.headers,
                params={"org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()

            # Should have api_url, timeout not present (not in config dict)
            assert data["config"]["api_url"] == "https://partial.com"
            assert "timeout" not in data["config"]
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
                headers=platform_admin.headers,
            )


@pytest.mark.e2e
class TestIntegrationsCLI:
    """Test CLI SDK endpoints for integrations."""

    @pytest_asyncio.fixture
    async def integration_with_mapping_and_oauth(self, e2e_client, platform_admin, org1, db_session):
        """Create integration with mapping and OAuth for CLI tests."""
        integration_name = f"e2e_cli_test_{uuid4().hex[:8]}"

        # Create integration with entity_id templating support
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={
                "name": integration_name,
                "config_schema": [
                    {"key": "api_url", "type": "string", "required": True},
                ],
            },
        )
        assert response.status_code == 201
        integration = response.json()

        # Create OAuth provider with token_url containing {entity_id}
        from uuid import UUID
        integration_id = UUID(integration["id"])
        oauth_provider = OAuthProvider(
            provider_name=f"cli_test_provider_{uuid4().hex[:8]}",
            display_name="CLI Test OAuth Provider",
            oauth_flow_type="client_credentials",
            client_id="cli-test-client",
            encrypted_client_secret=b"encrypted_secret",
            token_url="https://login.provider.com/{entity_id}/oauth/token",
            token_url_defaults={"entity_id": "default-tenant"},
            scopes=["read", "write"],
            integration_id=integration_id,
        )
        db_session.add(oauth_provider)
        await db_session.commit()

        # Create mapping with entity_id
        response = e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "specific-tenant-789",
                "entity_name": "Specific Tenant",
                "config": {
                    "api_url": "https://cli.example.com",
                },
            },
        )
        assert response.status_code == 201
        mapping = response.json()

        yield {
            "integration": integration,
            "oauth_provider": oauth_provider,
            "mapping": mapping,
            "org": org1,
        }

        # Cleanup
        e2e_client.delete(
            f"/api/integrations/{integration['id']}/mappings/{mapping['id']}",
            headers=platform_admin.headers,
        )
        e2e_client.delete(
            f"/api/integrations/{integration['id']}",
            headers=platform_admin.headers,
        )

    def test_cli_integrations_get(self, e2e_client, platform_admin, integration_with_mapping_and_oauth):
        """CLI endpoint returns integration data."""
        integration = integration_with_mapping_and_oauth["integration"]
        org = integration_with_mapping_and_oauth["org"]

        # Create developer API key for CLI access
        response = e2e_client.post(
            "/api/cli/keys",
            headers=platform_admin.headers,
            json={"name": "CLI Test Key"},
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"
        api_key_data = response.json()
        api_key = api_key_data["key"]

        try:
            # POST /api/cli/integrations/get with dev API key
            response = e2e_client.post(
                "/api/cli/integrations/get",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": integration["name"],
                    "org_id": str(org["id"]),
                },
            )
            assert response.status_code == 200, f"CLI get failed: {response.text}"
            data = response.json()

            assert data is not None
            assert data["integration_id"] == integration["id"]
            assert data["entity_id"] == "specific-tenant-789"
            assert data["entity_name"] == "Specific Tenant"
            assert data["config"]["api_url"] == "https://cli.example.com"
            assert data["oauth"] is not None
            assert data["oauth"]["client_id"] == "cli-test-client"
            assert data["oauth"]["scopes"] == ["read", "write"]
        finally:
            # Cleanup API key
            e2e_client.delete(
                f"/api/cli/keys/{api_key_data['id']}",
                headers=platform_admin.headers,
            )

    def test_cli_integrations_get_not_found(self, e2e_client, platform_admin, org1):
        """CLI endpoint returns null for non-existent integration."""
        # Create developer API key
        response = e2e_client.post(
            "/api/cli/keys",
            headers=platform_admin.headers,
            json={"name": "CLI Test Key 2"},
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"
        api_key_data = response.json()
        api_key = api_key_data["key"]

        try:
            response = e2e_client.post(
                "/api/cli/integrations/get",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": "nonexistent_integration",
                    "org_id": str(org1["id"]),
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data is None
        finally:
            e2e_client.delete(
                f"/api/cli/keys/{api_key_data['id']}",
                headers=platform_admin.headers,
            )

    def test_cli_integrations_list_mappings(self, e2e_client, platform_admin, integration_with_mapping_and_oauth):
        """CLI endpoint returns all mappings for an integration."""
        integration = integration_with_mapping_and_oauth["integration"]

        # Create developer API key
        response = e2e_client.post(
            "/api/cli/keys",
            headers=platform_admin.headers,
            json={"name": "CLI Test Key 3"},
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"
        api_key_data = response.json()
        api_key = api_key_data["key"]

        try:
            # POST /api/cli/integrations/list_mappings
            response = e2e_client.post(
                "/api/cli/integrations/list_mappings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": integration["name"],
                },
            )
            assert response.status_code == 200, f"CLI list_mappings failed: {response.text}"
            data = response.json()

            assert data is not None
            assert "items" in data
            assert len(data["items"]) >= 1

            # Find our mapping
            mapping = next(
                (m for m in data["items"] if m["entity_id"] == "specific-tenant-789"),
                None
            )
            assert mapping is not None
            assert mapping["entity_name"] == "Specific Tenant"
            assert mapping["config"]["api_url"] == "https://cli.example.com"
        finally:
            e2e_client.delete(
                f"/api/cli/keys/{api_key_data['id']}",
                headers=platform_admin.headers,
            )

    def test_cli_integrations_list_mappings_not_found(self, e2e_client, platform_admin):
        """CLI endpoint returns null for non-existent integration."""
        # Create developer API key
        response = e2e_client.post(
            "/api/cli/keys",
            headers=platform_admin.headers,
            json={"name": "CLI Test Key 4"},
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"
        api_key_data = response.json()
        api_key = api_key_data["key"]

        try:
            response = e2e_client.post(
                "/api/cli/integrations/list_mappings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": "nonexistent_integration",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data is None
        finally:
            e2e_client.delete(
                f"/api/cli/keys/{api_key_data['id']}",
                headers=platform_admin.headers,
            )

    def test_cli_oauth_token_url_resolution(self, e2e_client, platform_admin, integration_with_mapping_and_oauth):
        """CLI endpoint resolves {entity_id} in OAuth token URL."""
        integration = integration_with_mapping_and_oauth["integration"]
        org = integration_with_mapping_and_oauth["org"]

        # Create developer API key
        response = e2e_client.post(
            "/api/cli/keys",
            headers=platform_admin.headers,
            json={"name": "CLI Test Key 5"},
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"
        api_key_data = response.json()
        api_key = api_key_data["key"]

        try:
            response = e2e_client.post(
                "/api/cli/integrations/get",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": integration["name"],
                    "org_id": str(org["id"]),
                },
            )
            assert response.status_code == 200
            data = response.json()

            # Verify token_url has {entity_id} replaced with actual entity_id
            assert data["oauth"] is not None
            assert data["oauth"]["token_url"] == "https://login.provider.com/specific-tenant-789/oauth/token"
        finally:
            e2e_client.delete(
                f"/api/cli/keys/{api_key_data['id']}",
                headers=platform_admin.headers,
            )


@pytest.mark.e2e
class TestIntegrationsAuthorization:
    """Test authorization for integrations endpoints."""

    def test_non_superuser_cannot_list_integrations(self, e2e_client, org1_user):
        """Non-superuser should get 403 when listing integrations."""
        response = e2e_client.get(
            "/api/integrations",
            headers=org1_user.headers,
        )
        assert response.status_code == 403

    def test_non_superuser_cannot_create_integration(self, e2e_client, org1_user):
        """Non-superuser should get 403 when creating integrations."""
        response = e2e_client.post(
            "/api/integrations",
            headers=org1_user.headers,
            json={"name": "test_integration"},
        )
        assert response.status_code == 403

    def test_non_superuser_cannot_modify_integration(self, e2e_client, org1_user, platform_admin):
        """Non-superuser should get 403 when modifying integrations."""
        # First create as admin
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": f"auth_test_{uuid4().hex[:8]}"},
        )
        integration = response.json()

        try:
            # Try to update as non-superuser
            response = e2e_client.put(
                f"/api/integrations/{integration['id']}",
                headers=org1_user.headers,
                json={"name": "hacked"},
            )
            assert response.status_code == 403

            # Try to delete as non-superuser
            response = e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=org1_user.headers,
            )
            assert response.status_code == 403
        finally:
            # Cleanup as admin
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )

    def test_non_superuser_cannot_access_mappings(self, e2e_client, org1_user, platform_admin, org1):
        """Non-superuser should get 403 when accessing mappings."""
        # Create integration as admin
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": f"mapping_auth_test_{uuid4().hex[:8]}"},
        )
        integration = response.json()

        try:
            # Try to list mappings as non-superuser
            response = e2e_client.get(
                f"/api/integrations/{integration['id']}/mappings",
                headers=org1_user.headers,
            )
            assert response.status_code == 403

            # Try to create mapping as non-superuser
            response = e2e_client.post(
                f"/api/integrations/{integration['id']}/mappings",
                headers=org1_user.headers,
                json={
                    "organization_id": str(org1["id"]),
                    "entity_id": "test",
                },
            )
            assert response.status_code == 403
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )

    # Note: SDK endpoint (/api/integrations/sdk/{name}) authentication is tested
    # implicitly in other test classes that use it successfully with auth headers.
    # The endpoint requires Context dependency which enforces authentication.


@pytest.mark.e2e
class TestIntegrationsCLIAuth:
    """Test CLI SDK endpoints authentication."""

    @pytest.fixture
    def cli_api_key(self, e2e_client, platform_admin):
        """Create a CLI API key for testing."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Integration Auth Test Key"},
            headers=platform_admin.headers,
        )
        assert response.status_code == 201
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_cli_requires_auth(self, e2e_client):
        """CLI endpoint should return 401 without auth."""
        # Use a fresh client without cookies to test unauthenticated access
        # (e2e_client has cookies from previous auth which triggers CSRF check)
        import httpx
        with httpx.Client(base_url=e2e_client.base_url) as fresh_client:
            response = fresh_client.post(
                "/api/cli/integrations/get",
                json={"name": "test", "org_id": str(uuid4())},
            )
            assert response.status_code == 401

    def test_cli_with_api_key(self, e2e_client, cli_api_key, platform_admin, org1):
        """CLI endpoint should work with valid API key."""
        # Create integration
        integration_name = f"cli_auth_test_{uuid4().hex[:8]}"
        response = e2e_client.post(
            "/api/integrations",
            headers=platform_admin.headers,
            json={"name": integration_name},
        )
        integration = response.json()

        # Create mapping
        e2e_client.post(
            f"/api/integrations/{integration['id']}/mappings",
            headers=platform_admin.headers,
            json={
                "organization_id": str(org1["id"]),
                "entity_id": "test-entity",
            },
        )

        try:
            # Call CLI endpoint with API key
            response = e2e_client.post(
                "/api/cli/integrations/get",
                headers={"Authorization": f"Bearer {cli_api_key['key']}"},
                json={"name": integration_name, "org_id": str(org1["id"])},
            )
            assert response.status_code == 200
            data = response.json()
            assert data is not None
            assert data["entity_id"] == "test-entity"
        finally:
            e2e_client.delete(
                f"/api/integrations/{integration['id']}",
                headers=platform_admin.headers,
            )

    # Note: The SDK endpoint (/api/integrations/sdk/{name}) requires JWT authentication
    # (via Context dependency), not CLI API keys. CLI API keys only work for /api/cli/* endpoints.
    # SDK endpoint authentication is tested in other test classes that use JWT tokens.

    def test_cli_with_invalid_api_key(self, e2e_client):
        """CLI endpoint should reject invalid API keys."""
        response = e2e_client.post(
            "/api/cli/integrations/get",
            headers={"Authorization": "Bearer bfsk_invalid_key_123"},
            json={"name": "test", "org_id": str(uuid4())},
        )
        assert response.status_code == 401
