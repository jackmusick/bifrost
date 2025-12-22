"""
E2E tests for Integrations API.

Tests CRUD operations for integrations and integration mappings.
Tests OAuth configuration and authorization endpoints.
"""

import pytest
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

    @pytest.fixture
    def integration_with_oauth(self, e2e_client, platform_admin, db_session):
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
        db_session.commit()

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

    def test_get_oauth_authorize_url_client_credentials_flow(
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
        db_session.commit()

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
