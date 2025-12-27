"""
E2E tests for permission enforcement.

Tests that org users are properly restricted and org isolation is maintained.
"""

import pytest


@pytest.mark.e2e
class TestOrgUserRestrictions:
    """Test that org users are properly restricted from admin operations."""

    def test_org_user_cannot_list_all_organizations(self, e2e_client, org1_user):
        """Org user should not be able to list all organizations."""
        response = e2e_client.get(
            "/api/organizations",
            headers=org1_user.headers,
        )
        assert response.status_code == 403

    def test_org_user_cannot_create_organization(self, e2e_client, org1_user):
        """Org user should not be able to create organizations."""
        response = e2e_client.post(
            "/api/organizations",
            headers=org1_user.headers,
            json={"name": "Hacker Corp", "domain": "hacker.com"},
        )
        assert response.status_code == 403

    def test_org_user_cannot_create_roles(self, e2e_client, org1_user):
        """Org user should not be able to create roles."""
        response = e2e_client.post(
            "/api/roles",
            headers=org1_user.headers,
            json={"name": "Hacker Role", "description": "Unauthorized"},
        )
        assert response.status_code == 403

    def test_org_user_cannot_create_forms(self, e2e_client, org1_user):
        """Org user should not be able to create forms."""
        response = e2e_client.post(
            "/api/forms",
            headers=org1_user.headers,
            json={
                "name": "Unauthorized Form",
                "workflow_id": None,
                "form_schema": {"fields": []},
            },
        )
        assert response.status_code == 403

    def test_org_user_cannot_manage_config(self, e2e_client, org1_user):
        """Org user should not be able to create config."""
        response = e2e_client.post(
            "/api/config",
            headers=org1_user.headers,
            json={
                "key": "hacker_config",
                "value": "evil",
                "type": "string",
            },
        )
        assert response.status_code == 403

    def test_org_user_cannot_access_files(self, e2e_client, org1_user):
        """Org user should not be able to access workspace files."""
        response = e2e_client.get(
            "/api/files/editor",
            headers=org1_user.headers,
        )
        assert response.status_code == 403

    def test_org_user_cannot_execute_workflows_directly(self, e2e_client, org1_user):
        """Org user should not be able to execute workflows directly (only via forms)."""
        response = e2e_client.post(
            "/api/workflows/execute",
            headers=org1_user.headers,
            json={
                "workflow_id": "00000000-0000-0000-0000-000000000000",
                "input_data": {},
            },
        )
        assert response.status_code == 403

    def test_org_user_cannot_list_all_users(self, e2e_client, org1_user):
        """Org user cannot list all users (403 or filtered)."""
        response = e2e_client.get(
            "/api/users",
            headers=org1_user.headers,
        )
        # Should be 403 or return only limited/filtered data
        assert response.status_code in [403, 200]
        if response.status_code == 200:
            # If 200, should be filtered (not see all users)
            data = response.json()
            users = data.get("users", []) if isinstance(data, dict) else data
            # Org user should not see platform admin details
            for user in users:
                assert not user.get("is_superuser"), \
                    "Org user should not see superuser details"

    def test_org_user_cannot_create_users(self, e2e_client, org1_user):
        """Org user cannot create users (403)."""
        response = e2e_client.post(
            "/api/users",
            headers=org1_user.headers,
            json={
                "email": "hacker@evil.com",
                "name": "Hacker",
                "organization_id": str(org1_user.organization_id),
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create users: {response.status_code}"

    def test_org_user_cannot_delete_users(self, e2e_client, org1_user, platform_admin):
        """Org user cannot delete users (403)."""
        response = e2e_client.delete(
            f"/api/users/{platform_admin.user_id}",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete users: {response.status_code}"

    def test_org_user_cannot_delete_config(self, e2e_client, org1_user):
        """Org user cannot delete config (403)."""
        response = e2e_client.delete(
            "/api/config/test_key",
            headers=org1_user.headers,
        )
        assert response.status_code in [403, 404], \
            f"Org user should not delete config: {response.status_code}"

    def test_org_user_cannot_uninstall_packages(self, e2e_client, org1_user):
        """Org user cannot uninstall packages (403)."""
        response = e2e_client.delete(
            "/api/packages/some-package",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not uninstall packages: {response.status_code}"

    def test_org_user_cannot_access_oauth_admin(self, e2e_client, org1_user):
        """Org user cannot create OAuth connections (403)."""
        response = e2e_client.post(
            "/api/oauth/connections",
            headers=org1_user.headers,
            json={
                "connection_name": "hacked_oauth",
                "oauth_flow_type": "authorization_code",
                "authorization_url": "https://evil.com/auth",
                "token_url": "https://evil.com/token",
            },
        )
        assert response.status_code == 403, \
            f"Org user should not access OAuth admin: {response.status_code}"

    def test_org_user_cannot_modify_roles(self, e2e_client, org1_user):
        """Org user cannot modify roles (403)."""
        # Try to modify a role (using a dummy ID since we just need to test permissions)
        response = e2e_client.put(
            "/api/roles/00000000-0000-0000-0000-000000000000",
            headers=org1_user.headers,
            json={"name": "Hacked Role"},
        )
        assert response.status_code == 403, \
            f"Org user should not modify roles: {response.status_code}"

    def test_org_user_cannot_delete_roles(self, e2e_client, org1_user):
        """Org user cannot delete roles (403)."""
        response = e2e_client.delete(
            "/api/roles/00000000-0000-0000-0000-000000000000",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete roles: {response.status_code}"


@pytest.mark.e2e
class TestOrgUserCapabilities:
    """Test what org users CAN do."""

    def test_org_user_can_see_own_profile(self, e2e_client, org1_user):
        """Org user can access their own profile."""
        response = e2e_client.get("/auth/me", headers=org1_user.headers)
        assert response.status_code == 200
        assert response.json()["email"] == org1_user.email

    def test_org_user_can_list_own_executions(self, e2e_client, org1_user):
        """Org user can list their execution history."""
        response = e2e_client.get(
            "/api/executions",
            headers=org1_user.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data

    def test_org_user_can_view_mfa_status(self, e2e_client, org1_user):
        """Org user can check their MFA status."""
        response = e2e_client.get(
            "/auth/mfa/status",
            headers=org1_user.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "mfa_enabled" in data

    def test_org_user_can_list_assigned_forms(self, e2e_client, org1_user):
        """Org user can list forms assigned to them."""
        response = e2e_client.get(
            "/api/forms",
            headers=org1_user.headers,
        )
        assert response.status_code == 200, f"List forms failed: {response.text}"
        # Response should be filtered to assigned forms only
        data = response.json()
        # Verify response has expected structure
        assert isinstance(data, (dict, list))


@pytest.mark.e2e
class TestOrgIsolation:
    """Test that organizations are properly isolated from each other."""

    def test_org1_user_only_sees_own_resources(self, e2e_client, org1_user, org2):
        """Org1 user only sees their own org's resources regardless of filter param."""
        # With query param filtering, org users always get their own org's data
        # The scope param is ignored for non-superusers
        response = e2e_client.get(
            "/api/forms",
            params={"scope": org2["id"]},  # Try to filter by org2
            headers=org1_user.headers,
        )
        # Request succeeds but returns only org1's resources
        assert response.status_code == 200
        forms = response.json()
        for form in forms:
            assert form.get("organization_id") in [None, str(org1_user.organization_id)], \
                "Org user should only see their own org's forms"


@pytest.mark.e2e
class TestPlatformAdminCapabilities:
    """Test what platform admins can do."""

    def test_platform_admin_sees_all_executions(self, e2e_client, platform_admin):
        """Platform admin can see all executions."""
        response = e2e_client.get(
            "/api/executions",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
