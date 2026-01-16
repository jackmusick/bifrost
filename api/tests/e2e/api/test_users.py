"""
E2E tests for user management.

Tests user creation, listing, and profile operations.
"""

import pytest


@pytest.mark.e2e
class TestUserCreation:
    """Test user creation flows."""

    def test_org1_user_created(self, org1_user, org1):
        """Org1 user should be created via fixture."""
        assert org1_user.email == "alice@gobifrost.dev"
        assert org1_user.organization_id == org1["id"] or str(org1_user.organization_id) == org1["id"]
        assert org1_user.is_superuser is False
        assert org1_user.access_token is not None

    def test_org2_user_created(self, org2_user, org2):
        """Org2 user should be created via fixture."""
        assert org2_user.email == "bob@org2.gobifrost.com"
        assert org2_user.organization_id == org2["id"] or str(org2_user.organization_id) == org2["id"]
        assert org2_user.is_superuser is False
        assert org2_user.access_token is not None


@pytest.mark.e2e
class TestUserListing:
    """Test user listing."""

    def test_platform_admin_can_list_users(self, e2e_client, platform_admin, org1_user, org2_user):
        """Platform admin can list all users."""
        response = e2e_client.get(
            "/api/users",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List users failed: {response.text}"
        users = response.json()
        # Should have at least 3 users: admin + 2 org users
        assert len(users) >= 3

        emails = [u["email"] for u in users]
        assert platform_admin.email in emails
        assert org1_user.email in emails
        assert org2_user.email in emails


@pytest.mark.e2e
class TestUserProfile:
    """Test user profile operations."""

    def test_org_user_can_see_own_profile(self, e2e_client, org1_user):
        """Org user can access their own profile."""
        response = e2e_client.get("/auth/me", headers=org1_user.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == org1_user.email
        assert data["is_superuser"] is False

    def test_org_user_can_view_mfa_status(self, e2e_client, org1_user):
        """Org user can check their MFA status."""
        response = e2e_client.get(
            "/auth/mfa/status",
            headers=org1_user.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["mfa_enabled"] is True
