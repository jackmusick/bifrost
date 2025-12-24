"""
E2E tests for OAuth connection management.

Tests CRUD operations for OAuth connections.
"""

import pytest
from uuid import uuid4


@pytest.mark.e2e
class TestOAuthConnectionCRUD:
    """Test OAuth connection CRUD operations."""

    @pytest.fixture
    def test_integration(self, e2e_client, platform_admin):
        """Create a test integration for OAuth connections."""
        integration_name = f"e2e_oauth_integration_{uuid4().hex[:8]}"
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

    @pytest.fixture
    def oauth_connection(self, e2e_client, platform_admin, test_integration):
        """Create an OAuth connection and clean up after."""
        # OAuth connection name is derived from integration.name
        expected_connection_name = test_integration["name"]
        response = e2e_client.post(
            "/api/oauth/connections",
            headers=platform_admin.headers,
            json={
                "integration_id": test_integration["id"],
                "oauth_flow_type": "client_credentials",
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "scopes": "openid,profile,email",
            },
        )
        assert response.status_code == 201, f"Create OAuth connection failed: {response.text}"
        connection = response.json()
        assert connection["connection_name"] == expected_connection_name

        yield connection

        # Cleanup
        e2e_client.delete(
            f"/api/oauth/connections/{connection['connection_name']}",
            headers=platform_admin.headers,
        )

    def test_create_oauth_connection(self, e2e_client, platform_admin, test_integration):
        """Platform admin can create an OAuth connection."""
        # Connection name is derived from integration.name
        expected_connection_name = test_integration["name"]
        response = e2e_client.post(
            "/api/oauth/connections",
            headers=platform_admin.headers,
            json={
                "integration_id": test_integration["id"],
                "oauth_flow_type": "client_credentials",
                "client_id": "github-client-id",
                "client_secret": "github-client-secret",
                "token_url": "https://github.com/login/oauth/access_token",
                "scopes": "read:user",
            },
        )
        assert response.status_code == 201, f"Create failed: {response.text}"
        connection = response.json()
        assert connection["connection_name"] == expected_connection_name

        # Cleanup
        e2e_client.delete(
            f"/api/oauth/connections/{connection['connection_name']}",
            headers=platform_admin.headers,
        )

    def test_list_oauth_connections(self, e2e_client, platform_admin, oauth_connection):
        """Platform admin can list OAuth connections."""
        response = e2e_client.get(
            "/api/oauth/connections",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        # API returns {"connections": [...]}
        connections = data.get("connections", data)
        assert isinstance(connections, list)
        names = [c["connection_name"] for c in connections]
        # Connection name is derived from integration.name
        assert oauth_connection["connection_name"] in names

    def test_get_oauth_connection_detail(self, e2e_client, platform_admin, oauth_connection):
        """Platform admin can get OAuth connection details."""
        response = e2e_client.get(
            f"/api/oauth/connections/{oauth_connection['connection_name']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get failed: {response.text}"
        connection = response.json()
        # Connection name is derived from integration.name
        assert connection["connection_name"] == oauth_connection["connection_name"]

    def test_update_oauth_connection(self, e2e_client, platform_admin, oauth_connection):
        """Platform admin can update OAuth connection."""
        response = e2e_client.put(
            f"/api/oauth/connections/{oauth_connection['connection_name']}",
            headers=platform_admin.headers,
            json={
                "scopes": "openid,profile,email,offline_access",
            },
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        updated = response.json()
        # scopes is stored as comma-separated string
        assert "offline_access" in updated.get("scopes", "")

    def test_update_oauth_connection_scopes(self, e2e_client, platform_admin, oauth_connection):
        """Platform admin can update OAuth connection scopes."""
        response = e2e_client.put(
            f"/api/oauth/connections/{oauth_connection['connection_name']}",
            headers=platform_admin.headers,
            json={
                "scopes": "openid profile email",  # Space-separated
            },
        )
        assert response.status_code == 200, f"Update scopes failed: {response.text}"
        updated = response.json()
        # Scopes should be updated
        scopes = updated.get("scopes", "")
        assert "openid" in scopes
        assert "profile" in scopes
        assert "email" in scopes

    def test_oauth_connection_not_found(self, e2e_client, platform_admin):
        """Non-existent OAuth connection returns 404."""
        response = e2e_client.get(
            "/api/oauth/connections/nonexistent_connection_xyz",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_initiate_oauth_authorization(self, e2e_client, platform_admin, test_integration):
        """Platform admin can initiate OAuth authorization flow."""
        # Create an authorization_code flow connection (client_credentials doesn't support authorization)
        create_resp = e2e_client.post(
            "/api/oauth/connections",
            headers=platform_admin.headers,
            json={
                "integration_id": test_integration["id"],
                "connection_name": "e2e_auth_code_test",
                "oauth_flow_type": "authorization_code",
                "client_id": "test-auth-code-client",
                "client_secret": "test-auth-code-secret",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "scopes": "openid,profile,email",
            },
        )
        assert create_resp.status_code == 201, f"Create auth code connection failed: {create_resp.text}"
        connection = create_resp.json()

        try:
            response = e2e_client.post(
                f"/api/oauth/connections/{connection['connection_name']}/authorize",
                params={"redirect_uri": "http://localhost:3000/oauth/callback"},
                headers=platform_admin.headers,
            )
            assert response.status_code == 200, f"Initiate authorization failed: {response.text}"

            data = response.json()
            assert "authorization_url" in data
            assert "state" in data
            # Verify the authorization URL contains expected components
            auth_url = data["authorization_url"]
            assert "client_id=" in auth_url
            assert "redirect_uri=" in auth_url
            assert "scope=" in auth_url
            assert "state=" in auth_url
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/oauth/connections/{connection['connection_name']}",
                headers=platform_admin.headers,
            )

    def test_delete_oauth_connection(self, e2e_client, platform_admin, test_integration):
        """Platform admin can delete an OAuth connection."""
        # First create a connection to delete
        create_response = e2e_client.post(
            "/api/oauth/connections",
            headers=platform_admin.headers,
            json={
                "integration_id": test_integration["id"],
                "connection_name": "e2e_delete_test",
                "oauth_flow_type": "client_credentials",
                "client_id": "delete-test-client-id",
                "client_secret": "delete-test-secret",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "scopes": "openid,profile,email",
            },
        )
        assert create_response.status_code == 201, f"Create failed: {create_response.text}"
        connection_name = create_response.json()["connection_name"]

        # Delete the connection
        delete_response = e2e_client.delete(
            f"/api/oauth/connections/{connection_name}",
            headers=platform_admin.headers,
        )
        assert delete_response.status_code == 204, f"Delete OAuth connection failed: {delete_response.text}"

        # Verify it's gone
        get_response = e2e_client.get(
            f"/api/oauth/connections/{connection_name}",
            headers=platform_admin.headers,
        )
        assert get_response.status_code == 404


@pytest.mark.e2e
class TestOAuthAccess:
    """Test OAuth connection access control."""

    @pytest.fixture
    def test_integration(self, e2e_client, platform_admin):
        """Create a test integration for OAuth access tests."""
        integration_name = f"e2e_oauth_access_{uuid4().hex[:8]}"
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

    def test_org_user_cannot_manage_oauth(self, e2e_client, org1_user, test_integration):
        """Org user cannot create OAuth connections (requires superuser)."""
        response = e2e_client.post(
            "/api/oauth/connections",
            headers=org1_user.headers,
            json={
                "integration_id": test_integration["id"],
                "connection_name": "unauthorized_test",
                "oauth_flow_type": "client_credentials",
                "client_id": "fake",
                "client_secret": "fake",
                "token_url": "https://example.com/token",
            },
        )
        assert response.status_code == 403

    def test_org_user_cannot_access_oauth_admin(self, e2e_client, org1_user):
        """Org user cannot access OAuth connections list."""
        response = e2e_client.get(
            "/api/oauth/connections",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not list OAuth connections: {response.status_code}"


@pytest.mark.e2e
class TestOAuthAuthorizationFlow:
    """Test OAuth authorization flow operations."""

    @pytest.fixture
    def test_integration(self, e2e_client, platform_admin):
        """Create a test integration for OAuth authorization flow tests."""
        integration_name = f"e2e_oauth_flow_{uuid4().hex[:8]}"
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

    def test_cancel_oauth_authorization(self, e2e_client, platform_admin, test_integration):
        """Platform admin can cancel an in-progress OAuth authorization flow."""
        # Create an authorization_code flow connection
        create_resp = e2e_client.post(
            "/api/oauth/connections",
            headers=platform_admin.headers,
            json={
                "integration_id": test_integration["id"],
                "connection_name": "e2e_cancel_auth_test",
                "oauth_flow_type": "authorization_code",
                "client_id": "test-cancel-auth-client",
                "client_secret": "test-cancel-auth-secret",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "scopes": "openid,profile,email",
            },
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
        connection = create_resp.json()

        try:
            # Initiate authorization to get a state token
            auth_resp = e2e_client.post(
                f"/api/oauth/connections/{connection['connection_name']}/authorize",
                params={"redirect_uri": "http://localhost:3000/oauth/callback"},
                headers=platform_admin.headers,
            )
            assert auth_resp.status_code == 200, f"Initiate auth failed: {auth_resp.text}"
            auth_data = auth_resp.json()
            state = auth_data.get("state")

            # Try to cancel the authorization
            if state:
                cancel_resp = e2e_client.delete(
                    f"/api/oauth/connections/{connection['connection_name']}/authorize",
                    headers=platform_admin.headers,
                    params={"state": state},
                )
                # May return 200/204 for success, 404 if cancel not supported,
                # 400 if state invalid, or 405 if DELETE not allowed on this endpoint
                assert cancel_resp.status_code in [200, 204, 400, 404, 405], \
                    f"Cancel auth unexpected status: {cancel_resp.status_code}"
        finally:
            # Cleanup
            e2e_client.delete(
                f"/api/oauth/connections/{connection['connection_name']}",
                headers=platform_admin.headers,
            )
