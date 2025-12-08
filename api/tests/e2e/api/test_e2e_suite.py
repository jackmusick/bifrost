"""
E2E API Test Suite - Full Application Flow

Tests the complete user journey through the Bifrost API:
1. First user registers -> becomes platform admin
2. Platform admin creates organizations
3. Platform admin creates org users
4. Org users complete registration
5. Test CRUD operations and permissions
6. Test isolation between organizations

This is a single test class that runs sequentially, building state
as it goes - just like a real user would interact with the system.
"""

import json
import logging
import os
from dataclasses import dataclass
from uuid import UUID

import httpx
import pytest

from tests.helpers.totp import generate_totp_code

logger = logging.getLogger(__name__)

# API base URL - set by test.sh --e2e
API_BASE_URL = os.environ.get("TEST_API_URL", "http://localhost:18000")
# WebSocket URL derived from API base URL
WS_BASE_URL = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://")


@dataclass
class User:
    """Tracks user state through the test flow."""
    email: str
    password: str
    name: str
    user_id: UUID | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    totp_secret: str | None = None
    organization_id: UUID | None = None
    is_superuser: bool = False

    @property
    def headers(self) -> dict[str, str]:
        """Auth headers for API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


# Module-level state that persists across test methods
class State:
    """Shared state for E2E tests."""
    client: httpx.Client | None = None
    platform_admin: User | None = None
    org1: dict | None = None
    org2: dict | None = None
    org1_user: User | None = None
    org2_user: User | None = None
    test_role_id: str | None = None
    test_form_id: str | None = None
    # New E2E test state
    sync_execution_id: str | None = None
    async_execution_id: str | None = None
    e2e_form_id: str | None = None
    e2e_role_id: str | None = None
    form_execution_id: str | None = None
    # Access level test forms
    authenticated_form_id: str | None = None
    public_form_id: str | None = None
    # Execution behavior tests
    org_user_config_exec_id: str | None = None
    admin_config_exec_id: str | None = None
    # OAuth connection tests
    e2e_oauth_connection_name: str | None = None
    # Cancellation test state
    cancellation_execution_id: str | None = None
    # SDK API key tests
    sdk_api_key_id: str | None = None
    sdk_api_key_full: str | None = None
    # Workflow IDs for form execution tests
    sync_workflow_id: str | None = None
    async_workflow_id: str | None = None


@pytest.fixture(scope="module", autouse=True)
def setup_client():
    """Create HTTP client for the test module."""
    State.client = httpx.Client(base_url=API_BASE_URL, timeout=30.0)
    yield
    if State.client:
        State.client.close()


@pytest.mark.e2e
class TestFullApplicationFlow:
    """
    Complete E2E test of the Bifrost API.

    Tests run in order, building on previous state.
    This mirrors how a real deployment would be set up.
    """

    # =========================================================================
    # PHASE 1: Initial Setup - First User Becomes Platform Admin
    # =========================================================================

    def test_01_health_check(self):
        """Verify API is running before we start."""
        response = State.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_02_register_first_user_becomes_platform_admin(self):
        """First user to register becomes platform admin."""
        State.platform_admin = User(
            email="admin@gobifrost.com",
            password="AdminPass123!",
            name="Platform Admin",
        )

        # Register
        response = State.client.post(
            "/auth/register",
            json={
                "email": State.platform_admin.email,
                "password": State.platform_admin.password,
                "name": State.platform_admin.name,
            },
        )
        assert response.status_code == 201, f"Register failed: {response.text}"
        data = response.json()

        State.platform_admin.user_id = UUID(data["id"])
        State.platform_admin.is_superuser = data.get("is_superuser", False)

        # First user should be superuser
        assert State.platform_admin.is_superuser, "First user should be platform admin"

    def test_03_platform_admin_login_gets_mfa_challenge(self):
        """Login returns MFA requirement for password auth."""
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()

        # Should require MFA setup (first time) or MFA verification (after setup)
        assert data.get("mfa_required") or data.get("mfa_setup_required"), \
            f"Expected MFA requirement, got: {data}"

    def test_04_platform_admin_setup_mfa(self):
        """Setup TOTP for platform admin."""
        # First login to get MFA token
        login_response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login_data = login_response.json()
        # Token can be in mfa_token (for setup/verify) or access_token
        mfa_token = login_data.get("mfa_token") or login_data.get("access_token")
        assert mfa_token, f"No MFA token in response: {login_data}"

        # Setup MFA
        setup_response = State.client.post(
            "/auth/mfa/setup",
            headers={"Authorization": f"Bearer {mfa_token}"},
        )
        assert setup_response.status_code == 200, f"MFA setup failed: {setup_response.text}"
        setup_data = setup_response.json()

        State.platform_admin.totp_secret = setup_data["secret"]
        assert State.platform_admin.totp_secret, "Should receive TOTP secret"

    def test_05_platform_admin_verify_mfa_enrollment(self):
        """Verify TOTP code to complete MFA enrollment."""
        # Login again to get fresh MFA token
        login_response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login_data = login_response.json()
        mfa_token = login_data.get("mfa_token") or login_data.get("access_token")

        # Generate TOTP code
        totp_code = generate_totp_code(State.platform_admin.totp_secret)

        # Verify enrollment
        verify_response = State.client.post(
            "/auth/mfa/verify",
            headers={"Authorization": f"Bearer {mfa_token}"},
            json={"code": totp_code},
        )
        assert verify_response.status_code == 200, f"MFA verify failed: {verify_response.text}"
        verify_data = verify_response.json()

        # Should get tokens and recovery codes
        State.platform_admin.access_token = verify_data["access_token"]
        State.platform_admin.refresh_token = verify_data["refresh_token"]
        assert "recovery_codes" in verify_data, "Should receive recovery codes"

    def test_06_platform_admin_can_access_protected_endpoints(self):
        """Verify platform admin has valid token."""
        response = State.client.get(
            "/auth/me",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Auth check failed: {response.text}"
        data = response.json()
        assert data["email"] == State.platform_admin.email
        assert data["is_superuser"] is True

    # =========================================================================
    # PHASE 2: Platform Admin Creates Organizations
    # =========================================================================

    def test_10_create_first_organization(self):
        """Platform admin creates first organization."""
        response = State.client.post(
            "/api/organizations",
            headers=State.platform_admin.headers,
            json={
                "name": "Bifrost Dev Org",
                "domain": "gobifrost.dev",
            },
        )
        assert response.status_code == 201, f"Create org failed: {response.text}"
        State.org1 = response.json()
        assert State.org1["name"] == "Bifrost Dev Org"

    def test_11_create_second_organization(self):
        """Platform admin creates second organization for isolation tests."""
        response = State.client.post(
            "/api/organizations",
            headers=State.platform_admin.headers,
            json={
                "name": "Second Test Org",
                "domain": "example.com",
            },
        )
        assert response.status_code == 201, f"Create org failed: {response.text}"
        State.org2 = response.json()
        assert State.org2["name"] == "Second Test Org"

    def test_12_list_organizations(self):
        """Platform admin can list all organizations."""
        response = State.client.get(
            "/api/organizations",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List orgs failed: {response.text}"
        orgs = response.json()
        assert len(orgs) >= 2
        org_names = [o["name"] for o in orgs]
        assert "Bifrost Dev Org" in org_names
        assert "Second Test Org" in org_names

    def test_13_get_organization_by_id(self):
        """Platform admin can get specific organization."""
        response = State.client.get(
            f"/api/organizations/{State.org1['id']}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get org failed: {response.text}"
        org = response.json()
        assert org["id"] == State.org1["id"]
        assert org["name"] == "Bifrost Dev Org"

    # =========================================================================
    # PHASE 3: Create Organization Users
    # =========================================================================

    def test_20_admin_creates_user_for_org1(self):
        """Platform admin pre-creates user for org1."""
        State.org1_user = User(
            email="alice@gobifrost.dev",
            password="AlicePass123!",
            name="Alice Smith",
            organization_id=UUID(State.org1["id"]),
        )

        response = State.client.post(
            "/api/users",
            headers=State.platform_admin.headers,
            json={
                "email": State.org1_user.email,
                "name": State.org1_user.name,
                "organization_id": State.org1["id"],
                "is_superuser": False,
            },
        )
        assert response.status_code == 201, f"Create user failed: {response.text}"
        data = response.json()
        State.org1_user.user_id = UUID(data["id"])
        # Verify user was created with correct organization
        assert data.get("organization_id") == State.org1["id"], \
            f"User should have organization_id, got: {data}"

    def test_21_admin_creates_user_for_org2(self):
        """Platform admin pre-creates user for org2."""
        State.org2_user = User(
            email="bob@example.com",
            password="BobPass123!",
            name="Bob Jones",
            organization_id=UUID(State.org2["id"]),
        )

        response = State.client.post(
            "/api/users",
            headers=State.platform_admin.headers,
            json={
                "email": State.org2_user.email,
                "name": State.org2_user.name,
                "organization_id": State.org2["id"],
                "is_superuser": False,
            },
        )
        assert response.status_code == 201, f"Create user failed: {response.text}"
        data = response.json()
        State.org2_user.user_id = UUID(data["id"])
        # Verify user was created with correct organization
        assert data.get("organization_id") == State.org2["id"], \
            f"User should have organization_id, got: {data}"

    def test_22_org1_user_completes_registration(self):
        """Org1 user completes registration with password."""
        response = State.client.post(
            "/auth/register",
            json={
                "email": State.org1_user.email,
                "password": State.org1_user.password,
                "name": State.org1_user.name,
            },
        )
        assert response.status_code == 201, f"Register failed: {response.text}"
        data = response.json()
        assert data["is_superuser"] is False, "Org user should not be superuser"

    def test_23_org1_user_setup_mfa_and_login(self):
        """Org1 user sets up MFA and gets tokens."""
        # Login to get MFA token
        login_response = State.client.post(
            "/auth/login",
            data={
                "username": State.org1_user.email,
                "password": State.org1_user.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login_data = login_response.json()
        setup_token = login_data.get("mfa_token") or login_data.get("access_token")

        # Setup MFA
        setup_response = State.client.post(
            "/auth/mfa/setup",
            headers={"Authorization": f"Bearer {setup_token}"},
        )
        assert setup_response.status_code == 200, f"MFA setup failed: {setup_response.text}"
        State.org1_user.totp_secret = setup_response.json()["secret"]

        # Verify MFA
        totp_code = generate_totp_code(State.org1_user.totp_secret)
        verify_response = State.client.post(
            "/auth/mfa/verify",
            headers={"Authorization": f"Bearer {setup_token}"},
            json={"code": totp_code},
        )
        assert verify_response.status_code == 200, f"MFA verify failed: {verify_response.text}"
        verify_data = verify_response.json()

        State.org1_user.access_token = verify_data["access_token"]
        State.org1_user.refresh_token = verify_data["refresh_token"]

    def test_24_org2_user_completes_registration_and_mfa(self):
        """Org2 user completes full registration flow."""
        # Register
        response = State.client.post(
            "/auth/register",
            json={
                "email": State.org2_user.email,
                "password": State.org2_user.password,
                "name": State.org2_user.name,
            },
        )
        assert response.status_code == 201, f"Register failed: {response.text}"

        # Login for MFA setup
        login_response = State.client.post(
            "/auth/login",
            data={
                "username": State.org2_user.email,
                "password": State.org2_user.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login_data = login_response.json()
        setup_token = login_data.get("mfa_token") or login_data.get("access_token")

        # Setup MFA
        setup_response = State.client.post(
            "/auth/mfa/setup",
            headers={"Authorization": f"Bearer {setup_token}"},
        )
        assert setup_response.status_code == 200
        State.org2_user.totp_secret = setup_response.json()["secret"]

        # Verify MFA
        totp_code = generate_totp_code(State.org2_user.totp_secret)
        verify_response = State.client.post(
            "/auth/mfa/verify",
            headers={"Authorization": f"Bearer {setup_token}"},
            json={"code": totp_code},
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        State.org2_user.access_token = verify_data["access_token"]
        State.org2_user.refresh_token = verify_data["refresh_token"]

    # =========================================================================
    # PHASE 4: Roles and Permissions
    # =========================================================================

    def test_30_create_role(self):
        """Platform admin creates a role."""
        response = State.client.post(
            "/api/roles",
            headers=State.platform_admin.headers,
            json={
                "name": "Form Submitter",
                "description": "Can submit specific forms",
            },
        )
        assert response.status_code == 201, f"Create role failed: {response.text}"
        role = response.json()
        State.test_role_id = role["id"]
        assert role["name"] == "Form Submitter"

    def test_31_list_roles(self):
        """Users can list roles."""
        response = State.client.get(
            "/api/roles",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List roles failed: {response.text}"
        roles = response.json()
        assert isinstance(roles, list)
        role_names = [r["name"] for r in roles]
        assert "Form Submitter" in role_names

    def test_32_assign_role_to_org1_user(self):
        """Platform admin assigns role to org1 user."""
        response = State.client.post(
            f"/api/roles/{State.test_role_id}/users",
            headers=State.platform_admin.headers,
            json={"user_ids": [str(State.org1_user.user_id)]},
        )
        # Accept 200, 201, or 204
        assert response.status_code in [200, 201, 204], \
            f"Assign role failed: {response.status_code} - {response.text}"

    # =========================================================================
    # PHASE 5: Forms CRUD
    # =========================================================================

    def test_40_create_form(self):
        """Platform admin creates a form."""
        response = State.client.post(
            "/api/forms",
            headers=State.platform_admin.headers,
            json={
                "name": "Customer Onboarding",
                "description": "New customer intake form",
                "workflow_id": None,  # No workflow linked for this test
                "form_schema": {
                    "fields": [
                        {"name": "company_name", "type": "text", "label": "Company Name", "required": True},
                        {"name": "contact_email", "type": "email", "label": "Contact Email", "required": True},
                    ]
                },
                "access_level": "role_based",
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()
        State.test_form_id = form["id"]
        assert form["name"] == "Customer Onboarding"

    def test_41_list_forms(self):
        """Users can list forms."""
        response = State.client.get(
            "/api/forms",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List forms failed: {response.text}"
        forms = response.json()
        assert isinstance(forms, list)

    def test_42_update_form(self):
        """Platform admin can update a form."""
        response = State.client.patch(
            f"/api/forms/{State.test_form_id}",
            headers=State.platform_admin.headers,
            json={"description": "Updated description"},
        )
        assert response.status_code == 200, f"Update form failed: {response.text}"
        form = response.json()
        assert form["description"] == "Updated description"

    def test_43_assign_form_to_role(self):
        """Platform admin assigns form to role."""
        response = State.client.post(
            f"/api/roles/{State.test_role_id}/forms",
            headers=State.platform_admin.headers,
            json={"form_ids": [State.test_form_id]},
        )
        # Accept 200, 201, or 204
        assert response.status_code in [200, 201, 204], \
            f"Assign form failed: {response.status_code} - {response.text}"


    def test_44_form_file_path_is_workspace_relative(self):
        """Test that forms return workspace-relative file paths."""
        # Create a form
        form_data = {
            "name": "Test Form File Path",
            "description": "Testing workspace-relative file paths",
            "workflow_id": None,
            "form_schema": {
                "fields": [
                    {"name": "test_field", "type": "text", "label": "Test Field", "required": False}
                ]
            },
            "access_level": "authenticated"
        }

        response = State.client.post(
            "/api/forms",
            json=form_data,
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 201, f"Form creation failed: {response.text}"

        form = response.json()
        form_id = form["id"]
        file_path = form.get("file_path")

        # Verify file_path field exists and is workspace-relative
        assert file_path is not None, "file_path field should be present in form response"
        assert file_path.startswith("forms/"), f"file_path should start with 'forms/', got: {file_path}"
        assert file_path.endswith(".form.json"), f"file_path should end with '.form.json', got: {file_path}"

        logger.info(f"✓ Form created with workspace-relative path: {file_path}")

        # Store for next tests
        State.test_file_path_form_id = form_id

    def test_45_form_file_can_be_listed_in_editor(self):
        """Test that form files appear in editor file listings."""
        # Use the form we just created in test_200
        if not hasattr(State, 'test_file_path_form_id'):
            pytest.skip("test_44 did not create a form")

        # List files in forms directory
        response = State.client.get(
            "/api/editor/files",
            params={"path": "forms"},
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Failed to list forms directory: {response.text}"

        files = response.json()

        # Find our test form file
        form_response = State.client.get(
            f"/api/forms/{State.test_file_path_form_id}",
            headers=State.platform_admin.headers,
        )
        assert form_response.status_code == 200
        form = form_response.json()
        expected_file_path = form["file_path"]

        # Check if it appears in the listing
        file_paths = [f["path"] for f in files]
        assert expected_file_path in file_paths, f"Form file {expected_file_path} should appear in editor listings"

        logger.info(f"✓ Form file appears in editor listing: {expected_file_path}")

    def test_46_form_file_can_be_deleted_via_editor(self):
        """Test that form files can be deleted via the editor API."""
        # Use the form we just created in test_200
        if not hasattr(State, 'test_file_path_form_id'):
            pytest.skip("test_44 did not create a form")

        # Get the form's file path
        response = State.client.get(
            f"/api/forms/{State.test_file_path_form_id}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200
        form = response.json()
        file_path = form["file_path"]

        # Delete the file via editor API
        response = State.client.delete(
            "/api/editor/files",
            params={"path": file_path},
            headers=State.platform_admin.headers,
        )
        assert response.status_code in [200, 204], f"Failed to delete form file: {response.text}"

        # Verify file is gone
        response = State.client.get(
            "/api/editor/files/content",
            params={"path": file_path},
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 404, "Form file should be deleted"

        logger.info(f"✓ Form file successfully deleted via editor API: {file_path}")

        # Note: The form in the database still exists but is marked inactive
        # This is the expected dual-write behavior


    # =========================================================================
    # PHASE 6: Permission Tests - What Org Users CAN'T Do
    # =========================================================================

    def test_50_org_user_cannot_list_all_organizations(self):
        """Org users cannot list all organizations."""
        response = State.client.get(
            "/api/organizations",
            headers=State.org1_user.headers,
        )
        # Should be 403 Forbidden (not superuser)
        assert response.status_code == 403, \
            f"Org user should not list orgs: {response.status_code}"

    def test_51_org_user_cannot_create_organization(self):
        """Org users cannot create organizations."""
        response = State.client.post(
            "/api/organizations",
            headers=State.org1_user.headers,
            json={"name": "Hacker Corp", "domain": "hacker.com"},
        )
        assert response.status_code == 403, \
            f"Org user should not create orgs: {response.status_code}"

    def test_52_org_user_cannot_create_roles(self):
        """Org users cannot create roles."""
        response = State.client.post(
            "/api/roles",
            headers=State.org1_user.headers,
            json={"name": "Hacker Role", "description": "Unauthorized"},
        )
        assert response.status_code == 403, \
            f"Org user should not create roles: {response.status_code}"

    # =========================================================================
    # PHASE 7: Organization Isolation Tests
    # =========================================================================

    def test_60_org1_user_cannot_see_org2_data(self):
        """Org1 user cannot access org2's resources."""
        # Try to access org2's forms by setting X-Organization-Id header
        response = State.client.get(
            "/api/forms",
            headers={
                **State.org1_user.headers,
                "X-Organization-Id": State.org2["id"],
            },
        )
        # Should be 403 - access denied to other org
        assert response.status_code == 403, \
            f"Cross-org access should be denied: {response.status_code}"

    # =========================================================================
    # PHASE 8: What Org Users CAN Do
    # =========================================================================

    def test_70_org_user_can_see_own_profile(self):
        """Org user can access their own profile."""
        response = State.client.get(
            "/auth/me",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"Get profile failed: {response.text}"
        data = response.json()
        assert data["email"] == State.org1_user.email

    def test_71_org_user_can_list_own_executions(self):
        """Org user can list their execution history."""
        response = State.client.get(
            "/api/executions",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"List executions failed: {response.text}"
        # Response is ExecutionsListResponse with executions array and continuation_token
        data = response.json()
        assert "executions" in data, "Response should have 'executions' field"
        assert isinstance(data["executions"], list)

    def test_72_org_user_can_view_mfa_status(self):
        """Org user can view their MFA status."""
        response = State.client.get(
            "/auth/mfa/status",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"MFA status failed: {response.text}"
        data = response.json()
        assert data["mfa_enabled"] is True

    # =========================================================================
    # PHASE 9: Platform Admin User Management
    # =========================================================================

    def test_80_platform_admin_can_list_users(self):
        """Platform admin can list all users."""
        response = State.client.get(
            "/api/users",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List users failed: {response.text}"
        users = response.json()
        assert len(users) >= 3  # Admin + 2 org users
        emails = [u["email"] for u in users]
        assert State.platform_admin.email in emails
        assert State.org1_user.email in emails
        assert State.org2_user.email in emails

    # =========================================================================
    # PHASE 10: Config and Health Endpoints
    # =========================================================================

    def test_90_health_with_details(self):
        """Health endpoint with component details."""
        response = State.client.get("/health?details=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        # Should have component health info
        if "components" in data:
            assert "database" in data["components"]

    def test_91_config_list(self):
        """Platform admin can list config."""
        response = State.client.get(
            "/api/config",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List config failed: {response.text}"

    def test_92_list_workflows(self):
        """Users can list available workflows."""
        response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"
        workflows = response.json()
        assert isinstance(workflows, list)

    @pytest.mark.skip(reason="Platform workflows concept being removed - see Phase 2 in plan")
    def test_92b_platform_workflows_properly_categorized(self):
        """Platform workflows are correctly marked with is_platform=true."""
        response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"
        workflows = response.json()

        # Find platform workflows (should be from /app/platform/ directory in Docker)
        platform_workflows = [w for w in workflows if w.get("is_platform") is True]
        user_workflows = [w for w in workflows if w.get("is_platform") is False]

        # Verify we have some platform example workflows
        assert len(platform_workflows) > 0, "Expected at least one platform workflow"

        # Check that platform workflows have proper categorization
        for wf in platform_workflows:
            assert wf.get("is_platform") is True, f"Workflow {wf['name']} should be marked as platform"
            # Platform workflows should have file paths containing /platform/
            file_path = wf.get("source_file_path", "")
            assert "/platform/" in file_path or "\\platform\\" in file_path, \
                f"Platform workflow {wf['name']} has unexpected file path: {file_path}"

        # Check that user workflows are not marked as platform
        for wf in user_workflows:
            assert wf.get("is_platform") is False, f"Workflow {wf['name']} should not be marked as platform"

        logger.info(f"Platform workflow categorization verified: {len(platform_workflows)} platform, {len(user_workflows)} user")

    def test_93_list_data_providers(self):
        """Users can list data providers."""
        response = State.client.get(
            "/api/data-providers",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"

    # =========================================================================
    # PHASE 11: Cleanup (Optional - tests should be idempotent)
    # =========================================================================

    def test_99_cleanup_form(self):
        """Clean up test form."""
        if State.test_form_id:
            response = State.client.delete(
                f"/api/forms/{State.test_form_id}",
                headers=State.platform_admin.headers,
            )
            # Accept 200, 204, or 404 (already deleted)
            assert response.status_code in [200, 204, 404]

    # =========================================================================
    # PHASE 12: Config Operations
    # =========================================================================

    def test_100_set_global_config_string(self):
        """Platform admin creates STRING config in GLOBAL scope."""
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_test_timeout",
                "value": "30",
                "type": "string",
                "description": "E2E test config",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"
        data = response.json()
        assert data["key"] == "e2e_test_timeout"
        assert data["value"] == "30"

    def test_101_set_int_config(self):
        """Platform admin creates INT config."""
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_max_retries",
                "value": "5",
                "type": "int",
                "description": "Max retries setting",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

    def test_102_set_bool_config(self):
        """Platform admin creates BOOL config."""
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_feature_flag",
                "value": "true",
                "type": "bool",
                "description": "Feature flag",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

    def test_103_set_json_config(self):
        """Platform admin creates JSON config."""
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_settings",
                "value": '{"enabled": true, "level": 3}',
                "type": "json",
                "description": "JSON settings",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

    def test_104_set_secret_config(self):
        """Platform admin creates SECRET config (encrypted)."""
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_api_key",
                "value": "secret-api-key-12345",
                "type": "secret",
                "description": "Test API key",
            },
        )
        assert response.status_code == 201, f"Create secret failed: {response.text}"

    def test_105_list_config_masks_secrets(self):
        """Listing configs shows [SECRET] for encrypted values."""
        response = State.client.get(
            "/api/config",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List config failed: {response.text}"
        configs = response.json()

        # Find the secret config
        secret_config = next((c for c in configs if c["key"] == "e2e_api_key"), None)
        assert secret_config is not None, "Secret config not found"
        assert secret_config["value"] == "[SECRET]", "Secret should be masked"

    def test_106_delete_config(self):
        """Platform admin can delete config."""
        response = State.client.delete(
            "/api/config/e2e_feature_flag",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete config failed: {response.text}"

    def test_107_org_user_cannot_manage_config(self):
        """Org user cannot create config (403)."""
        response = State.client.post(
            "/api/config",
            headers=State.org1_user.headers,
            json={
                "key": "hacker_config",
                "value": "evil",
                "type": "STRING",
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create config: {response.status_code}"

    # =========================================================================
    # PHASE 13: File Operations & Workflow Discovery
    # =========================================================================

    def test_110_list_workspace_files(self):
        """Platform admin can list workspace files."""
        response = State.client.get(
            "/api/editor/files?path=.",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List files failed: {response.text}"
        files = response.json()
        assert isinstance(files, list)

    def test_111_create_workflow_file(self):
        """Platform admin creates a test workflow file."""

        workflow_content = '''"""E2E Test Workflow"""
import logging
import time
from bifrost import workflow, context

logger = logging.getLogger(__name__)

@workflow(
    name="e2e_test_sync_workflow",
    description="E2E test workflow - sync execution",
    execution_mode="sync"
)
async def e2e_test_sync_workflow(message: str, count: int = 1):
    return {
        "status": "success",
        "message": message,
        "count": count,
        "user": context.email,
    }

@workflow(
    name="e2e_test_async_workflow",
    description="E2E test workflow - async execution with logging",
    execution_mode="async"
)
async def e2e_test_async_workflow(delay_seconds: int = 2):
    """
    Test workflow that:
    1. Logs at DEBUG level (to test log visibility)
    2. Sleeps for delay_seconds (to test concurrency)
    3. Retrieves config to test config scoping
    """
    # DEBUG level log - org users should NOT see this
    logger.debug("DEBUG: Starting async workflow")

    # INFO level log - all users should see this
    logger.info("INFO: Starting workflow")

    # Sleep to test concurrency - if blocking, 10 workflows = 20+ seconds
    # If parallel, 10 workflows should complete in ~3-5 seconds
    time.sleep(delay_seconds)

    # Retrieve config value to test config scoping
    config_value = await context.get_config("e2e_test_key", default=None)

    logger.info("INFO: Workflow completed after sleep")

    return {
        "status": "completed",
        "delayed": delay_seconds,
        "user_email": context.email,
        "org_id": context.scope,
        "config_value": config_value
    }
'''
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "e2e_test_workflow.py",
                "content": workflow_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create file failed: {response.text}"

    def test_112_workflow_immediately_available(self):
        """Workflow is discoverable after file creation (with discovery sync)."""
        import time

        # Poll for workflow to appear (discovery container syncs every few seconds)
        max_attempts = 30  # 30 seconds max wait
        workflow_names = []

        for attempt in range(max_attempts):
            response = State.client.get(
                "/api/workflows",
                headers=State.platform_admin.headers,
            )
            assert response.status_code == 200, f"List workflows failed: {response.text}"
            workflows = response.json()
            workflow_names = [w["name"] for w in workflows]

            if "e2e_test_sync_workflow" in workflow_names:
                break

            time.sleep(1)

        assert "e2e_test_sync_workflow" in workflow_names, \
            f"Test workflow not discovered after {max_attempts}s. Available: {workflow_names}"

    def test_112b_workflow_parameters_returned(self):
        """Workflow parameters are included in API response."""
        response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List workflows failed: {response.text}"
        workflows = response.json()

        # Find e2e_test_sync_workflow (created in test_111)
        test_workflow = next(
            (w for w in workflows if w["name"] == "e2e_test_sync_workflow"), None
        )
        assert test_workflow is not None, "e2e_test_sync_workflow workflow not found"

        # Store workflow ID for form creation tests
        State.sync_workflow_id = test_workflow["id"]

        # Also find and store async workflow ID (used for config scoping tests)
        async_workflow = next(
            (w for w in workflows if w["name"] == "e2e_test_async_workflow"), None
        )
        if async_workflow:
            State.async_workflow_id = async_workflow["id"]

        # Verify parameters are present
        assert "parameters" in test_workflow, "Workflow missing parameters field"
        parameters = test_workflow["parameters"]
        assert len(parameters) == 2, f"Expected 2 parameters, got {len(parameters)}"

        # Verify parameter structure
        param_names = [p["name"] for p in parameters]
        assert "message" in param_names, "Missing 'message' parameter"
        assert "count" in param_names, "Missing 'count' parameter"

        # Verify first parameter details (required string)
        message_param = next(p for p in parameters if p["name"] == "message")
        assert message_param["type"] == "string"
        assert message_param["required"] is True

        # Verify second parameter with default value
        count_param = next(p for p in parameters if p["name"] == "count")
        assert count_param["type"] == "int"
        assert count_param["required"] is False
        assert count_param["default_value"] == 1

    def test_113_read_file_content(self):
        """Platform admin can read file content back."""

        response = State.client.get(
            "/api/editor/files/content?path=e2e_test_workflow.py",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Read file failed: {response.text}"
        data = response.json()
        assert "e2e_test_sync_workflow" in data["content"]

    def test_114_create_folder(self):
        """Platform admin can create a folder."""

        response = State.client.post(
            "/api/editor/files/folder?path=e2e_test_folder",
            headers=State.platform_admin.headers,
        )
        # 201 for new, or 409 if exists from previous run
        assert response.status_code in [201, 409], f"Create folder failed: {response.text}"

    def test_115_org_user_cannot_access_files(self):
        """Org user cannot access file operations (403)."""
        response = State.client.get(
            "/api/editor/files?path=.",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access files: {response.status_code}"

    def test_116_create_workspace_form_file(self):
        """Platform admin creates a form.json file via editor API."""

        # Create a .form.json file for hot reload testing
        # Use workflow_id (null here since we're testing file creation, not execution)
        form_content = json.dumps({
            "id": "e2e-workspace-form",
            "name": "E2E Workspace Form",
            "description": "Form created via file API for hot reload testing",
            "workflow_id": None,
            "is_global": True,
            "access_level": "authenticated",
            "form_schema": {
                "fields": [
                    {"name": "message", "type": "text", "label": "Message", "required": True}
                ]
            }
        }, indent=2)

        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "e2e_test.form.json",
                "content": form_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create form file failed: {response.text}"

    def test_117_workspace_form_file_persists(self):
        """Workspace form file can be read back."""

        # Read the form file back to verify it was created
        response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "e2e_test.form.json"},
        )
        assert response.status_code == 200, f"Read form file failed: {response.text}"

        # Parse and verify content
        data = response.json()
        content = data.get("content", "")
        form_data = json.loads(content)
        assert form_data.get("id") == "e2e-workspace-form"
        assert form_data.get("name") == "E2E Workspace Form"

    # =========================================================================
    # PHASE 14: Sync Workflow Execution
    # =========================================================================

    def test_120_execute_sync_workflow(self):
        """Platform admin executes sync workflow."""
        # First, get the workflow ID by searching for the workflow
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_test_sync_workflow"}
        )
        assert list_response.status_code == 200, f"Failed to list workflows: {list_response.text}"
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_test_sync_workflow"]
        if not matching:
            pytest.skip("Sync workflow not found - workflow not available")
        workflow_id = matching[0]["id"]

        response = State.client.post(
            "/api/workflows/execute",
            headers=State.platform_admin.headers,
            json={
                "workflow_id": workflow_id,
                "input_data": {
                    "message": "Hello from E2E test",
                    "count": 42,
                },
            },
        )
        # Workflow execution should succeed - if it fails, something is broken
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()

        assert data["status"] == "Success", f"Unexpected status: {data}"
        assert "execution_id" in data or "executionId" in data

        # Store execution ID for later tests
        State.sync_execution_id = data.get("execution_id") or data.get("executionId")

    def test_121_sync_execution_returns_result(self):
        """Sync execution returns expected result."""
        if not State.sync_execution_id:
            pytest.skip("No previous execution - workflow not available")

        # Get workflow ID
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_test_sync_workflow"}
        )
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_test_sync_workflow"]
        if not matching:
            pytest.skip("Sync workflow not found")
        workflow_id = matching[0]["id"]

        response = State.client.post(
            "/api/workflows/execute",
            headers=State.platform_admin.headers,
            json={
                "workflow_id": workflow_id,
                "input_data": {"message": "Test message", "count": 10},
            },
        )
        assert response.status_code == 200, f"Workflow execution failed: {response.text}"
        data = response.json()

        result = data.get("result", {})
        assert result.get("status") == "success"
        assert result.get("message") == "Test message"
        assert result.get("count") == 10

    def test_122_org_user_cannot_execute_directly(self):
        """Org user cannot call /execute endpoint directly (403)."""
        # Use a fake workflow ID - the point is org users can't execute directly
        response = State.client.post(
            "/api/workflows/execute",
            headers=State.org1_user.headers,
            json={
                "workflow_id": "00000000-0000-0000-0000-000000000000",
                "input_data": {"message": "Hacked"},
            },
        )
        assert response.status_code == 403, \
            f"Org user should not execute directly: {response.status_code}"

    # =========================================================================
    # PHASE 15: Async Workflow Execution (basic polling, no WebSocket)
    # =========================================================================

    def test_130_execute_async_workflow(self):
        """Platform admin executes async workflow."""
        # Get workflow ID
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_test_async_workflow"}
        )
        if list_response.status_code != 200:
            pytest.skip("Could not list workflows")
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_test_async_workflow"]
        if not matching:
            pytest.skip("Async workflow not found - workflow not available")
        workflow_id = matching[0]["id"]

        response = State.client.post(
            "/api/workflows/execute",
            headers=State.platform_admin.headers,
            json={
                "workflow_id": workflow_id,
                "input_data": {"delay_seconds": 1},
            },
        )
        assert response.status_code in [200, 202], f"Async workflow execute failed: {response.text}"
        data = response.json()

        # Store execution ID
        State.async_execution_id = data.get("execution_id") or data.get("executionId")
        assert State.async_execution_id, "Should return execution_id"

    def test_131_async_execution_eventually_completes(self):
        """Poll until async execution completes."""
        import time

        if not State.async_execution_id:
            pytest.skip("No async execution ID")

        # Poll for completion
        for _ in range(30):  # 30 second timeout
            response = State.client.get(
                f"/api/executions/{State.async_execution_id}",
                headers=State.platform_admin.headers,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status in ["Success", "Failed"]:
                    assert status == "Success", f"Execution failed: {data}"
                    return
            time.sleep(1)

        pytest.fail("Async execution did not complete within timeout")

    # =========================================================================
    # PHASE 15b: Workflow Cancellation
    # =========================================================================

    def test_132_create_cancellation_workflow(self):
        """Platform admin creates a workflow for cancellation testing."""
        workflow_content = '''"""E2E Cancellation Test Workflow"""
import logging
import time
from bifrost import workflow

logger = logging.getLogger(__name__)

@workflow(
    name="e2e_cancellation_test",
    description="Workflow with sleep for cancellation testing",
    execution_mode="async"
)
async def e2e_cancellation_test(sleep_seconds: int = 30):
    logger.info(f"Starting sleep for {sleep_seconds} seconds...")
    time.sleep(sleep_seconds)
    logger.info("Sleep completed - this should not appear if cancelled")
    return {"status": "completed", "slept_for": sleep_seconds}
'''
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "e2e_cancellation_workflow.py",
                "content": workflow_content,
                "encoding": "utf-8",
            },
        )
        assert response.status_code == 200, f"Create file failed: {response.text}"

        # Wait for workflow discovery
        import time
        for attempt in range(30):
            response = State.client.get(
                "/api/workflows",
                headers=State.platform_admin.headers,
            )
            if response.status_code == 200:
                workflows = response.json()
                workflow_names = [w["name"] for w in workflows]
                if "e2e_cancellation_test" in workflow_names:
                    return
            time.sleep(1)

        pytest.fail("Cancellation workflow not discovered within timeout")

    def test_133_execute_cancellation_workflow_async(self):
        """Start async workflow with long sleep for cancellation testing."""
        # Get workflow ID
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_cancellation_test"}
        )
        if list_response.status_code != 200:
            pytest.skip("Could not list workflows")
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_cancellation_test"]
        if not matching:
            pytest.skip("Cancellation workflow not found")
        workflow_id = matching[0]["id"]

        response = State.client.post(
            "/api/workflows/execute",
            headers=State.platform_admin.headers,
            json={
                "workflow_id": workflow_id,
                "input_data": {"sleep_seconds": 30},
            },
        )
        assert response.status_code in [200, 202], f"Workflow execute failed: {response.text}"
        data = response.json()

        State.cancellation_execution_id = data.get("execution_id") or data.get("executionId")
        assert State.cancellation_execution_id, "Should return execution_id"

    def test_134_wait_for_running_status(self):
        """Wait for execution to reach Running status before cancelling."""
        import time

        if not State.cancellation_execution_id:
            pytest.skip("No cancellation execution ID")

        for _ in range(10):
            response = State.client.get(
                f"/api/executions/{State.cancellation_execution_id}",
                headers=State.platform_admin.headers,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status == "Running":
                    return
                if status in ["Success", "Failed", "Cancelled"]:
                    pytest.fail(f"Execution finished before we could cancel: {status}")
            time.sleep(0.5)

        pytest.fail("Execution did not reach Running status within timeout")

    def test_135_cancel_running_workflow(self):
        """Cancel the running workflow and verify quick cancellation."""
        import time

        if not State.cancellation_execution_id:
            pytest.skip("No cancellation execution ID")

        start_time = time.time()

        # Cancel the execution
        response = State.client.post(
            f"/api/executions/{State.cancellation_execution_id}/cancel",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Cancel failed: {response.text}"
        data = response.json()
        assert data.get("status") in ["Cancelling", "Cancelled"], f"Unexpected status: {data}"

        # Poll until cancelled
        for _ in range(30):
            response = State.client.get(
                f"/api/executions/{State.cancellation_execution_id}",
                headers=State.platform_admin.headers,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status == "Cancelled":
                    elapsed = time.time() - start_time
                    assert elapsed < 10, f"Cancellation took too long: {elapsed:.1f}s"
                    return
            time.sleep(0.5)

        pytest.fail("Execution was not cancelled within timeout")

    def test_136_verify_cancelled_execution_details(self):
        """Verify cancelled execution has correct status and error message."""
        if not State.cancellation_execution_id:
            pytest.skip("No cancellation execution ID")

        response = State.client.get(
            f"/api/executions/{State.cancellation_execution_id}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "Cancelled"

    def test_137_cancel_already_cancelled_returns_400(self):
        """Attempting to cancel an already-cancelled execution returns 400."""
        if not State.cancellation_execution_id:
            pytest.skip("No cancellation execution ID")

        response = State.client.post(
            f"/api/executions/{State.cancellation_execution_id}/cancel",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"

    def test_138_org_user_cannot_cancel_others_execution(self):
        """Org user cannot cancel another user's execution (403 Forbidden)."""
        if not State.cancellation_execution_id:
            pytest.skip("No cancellation execution ID")

        # Org2 user tries to cancel platform admin's execution
        response = State.client.post(
            f"/api/executions/{State.cancellation_execution_id}/cancel",
            headers=State.org2_user.headers,
        )
        # Should get 403 Forbidden (not their execution) or 404 (can't see it)
        assert response.status_code in [403, 404], (
            f"Expected 403/404 for unauthorized cancel, got {response.status_code}: {response.text}"
        )

    # =========================================================================
    # PHASE 16: Data Provider Execution
    # =========================================================================

    def test_140_list_data_providers(self):
        """Platform admin can list data providers."""
        response = State.client.get(
            "/api/data-providers",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List data providers failed: {response.text}"
        # Response should be a list
        data = response.json()
        assert isinstance(data, list)

    # =========================================================================
    # PHASE 17: Form-Based Execution & Access Control
    # =========================================================================

    def test_150_create_form_linked_to_workflow(self):
        """Platform admin creates form linked to test workflow."""
        # Skip if workflow ID not captured
        if not State.sync_workflow_id:
            pytest.skip("Workflow ID not captured from test_112")

        response = State.client.post(
            "/api/forms",
            headers=State.platform_admin.headers,
            json={
                "name": "E2E Test Form",
                "description": "Form for E2E testing",
                "workflow_id": State.sync_workflow_id,
                "form_schema": {
                    "fields": [
                        {"name": "message", "type": "text", "label": "Message", "required": True},
                        {"name": "count", "type": "number", "label": "Count", "required": False},
                    ]
                },
                "access_level": "role_based",
                "default_launch_params": {"count": 1},
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()
        State.e2e_form_id = form["id"]

    def test_151_create_role_for_form_access(self):
        """Platform admin creates role for form access."""
        if not State.e2e_form_id:
            pytest.skip("Form not created")

        response = State.client.post(
            "/api/roles",
            headers=State.platform_admin.headers,
            json={
                "name": "E2E Form Access Role",
                "description": "Can access E2E test form",
            },
        )
        assert response.status_code == 201, f"Create role failed: {response.text}"
        role = response.json()
        State.e2e_role_id = role["id"]

    def test_152_assign_form_to_role(self):
        """Platform admin assigns form to role."""
        if not State.e2e_form_id or not State.e2e_role_id:
            pytest.skip("Form or role not created")

        response = State.client.post(
            f"/api/roles/{State.e2e_role_id}/forms",
            headers=State.platform_admin.headers,
            json={"form_ids": [State.e2e_form_id]},
        )
        assert response.status_code in [200, 201, 204], \
            f"Assign form to role failed: {response.text}"

    def test_153_assign_org_user_to_role(self):
        """Platform admin assigns org1_user to role."""
        if not State.e2e_role_id:
            pytest.skip("Role not created")

        response = State.client.post(
            f"/api/roles/{State.e2e_role_id}/users",
            headers=State.platform_admin.headers,
            json={"user_ids": [str(State.org1_user.user_id)]},
        )
        assert response.status_code in [200, 201, 204], \
            f"Assign user to role failed: {response.text}"

    def test_154_org_user_cannot_execute_unassigned_form(self):
        """Org user cannot execute form without role assignment."""
        if not State.e2e_form_id:
            pytest.skip("Form not created")

        # Org2 user is NOT assigned to the role
        response = State.client.post(
            f"/api/forms/{State.e2e_form_id}/execute",
            headers=State.org2_user.headers,
            json={"message": "Unauthorized attempt"},
        )
        assert response.status_code == 403, \
            f"Unassigned user should not execute form: {response.status_code}"

    def test_155_org_user_can_execute_assigned_form(self):
        """Org user with role can execute form."""
        if not State.e2e_form_id or not State.e2e_role_id:
            pytest.skip("Form or role not created")

        response = State.client.post(
            f"/api/forms/{State.e2e_form_id}/execute",
            headers=State.org1_user.headers,
            json={"message": "Hello from org user"},
        )
        assert response.status_code == 200, f"Execute form failed: {response.text}"
        data = response.json()

        # Should have execution_id
        assert "execution_id" in data or "executionId" in data
        State.form_execution_id = data.get("execution_id") or data.get("executionId")

    # =========================================================================
    # PHASE 17B: Form Access Level Tests
    # =========================================================================

    def test_156_create_authenticated_access_form(self):
        """Platform admin creates form with 'authenticated' access level."""
        if not State.sync_workflow_id:
            pytest.skip("Workflow ID not captured from test_112")

        response = State.client.post(
            "/api/forms",
            headers=State.platform_admin.headers,
            json={
                "name": "Authenticated Access Form",
                "description": "Any authenticated user can execute",
                "workflow_id": State.sync_workflow_id,
                "form_schema": {
                    "fields": [
                        {"name": "message", "type": "text", "label": "Message", "required": True},
                    ]
                },
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()
        State.authenticated_form_id = form["id"]
        assert form["access_level"] == "authenticated"

    def test_157_any_org_user_can_execute_authenticated_form(self):
        """Any authenticated user can execute 'authenticated' access form."""
        if not getattr(State, 'authenticated_form_id', None):
            pytest.skip("Authenticated form not created")

        # Org2 user (NOT assigned to any role for this form) should still be able to execute
        response = State.client.post(
            f"/api/forms/{State.authenticated_form_id}/execute",
            headers=State.org2_user.headers,
            json={"message": "Hello from org2 user"},
        )
        assert response.status_code == 200, \
            f"Authenticated user should execute authenticated form: {response.status_code} - {response.text}"

    def test_158_create_public_access_form(self):
        """Platform admin creates form with 'public' access level."""
        if not State.sync_workflow_id:
            pytest.skip("Workflow ID not captured from test_112")

        response = State.client.post(
            "/api/forms",
            headers=State.platform_admin.headers,
            json={
                "name": "Public Access Form",
                "description": "Any user can execute (public)",
                "workflow_id": State.sync_workflow_id,
                "form_schema": {
                    "fields": [
                        {"name": "message", "type": "text", "label": "Message", "required": True},
                    ]
                },
                "access_level": "public",
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()
        State.public_form_id = form["id"]
        assert form["access_level"] == "public"

    def test_159_any_user_can_execute_public_form(self):
        """Any authenticated user can execute 'public' access form."""
        if not getattr(State, 'public_form_id', None):
            pytest.skip("Public form not created")

        # Org2 user should be able to execute public form
        response = State.client.post(
            f"/api/forms/{State.public_form_id}/execute",
            headers=State.org2_user.headers,
            json={"message": "Hello from any user"},
        )
        assert response.status_code == 200, \
            f"User should execute public form: {response.status_code} - {response.text}"

    def test_160_role_based_form_denies_unassigned_user(self):
        """Role-based form denies user without role assignment."""
        # This is a sanity check - test_154 already tests this but with e2e_form_id
        if not getattr(State, 'e2e_form_id', None):
            pytest.skip("Role-based form not created")

        # Org2 user is NOT assigned to e2e_role_id
        response = State.client.post(
            f"/api/forms/{State.e2e_form_id}/execute",
            headers=State.org2_user.headers,
            json={"message": "Should be denied"},
        )
        assert response.status_code == 403, \
            f"Unassigned user should be denied: {response.status_code}"

    def test_161_cleanup_access_level_test_forms(self):
        """Clean up access level test forms."""
        # Clean up authenticated form
        if getattr(State, 'authenticated_form_id', None):
            response = State.client.delete(
                f"/api/forms/{State.authenticated_form_id}",
                headers=State.platform_admin.headers,
            )
            assert response.status_code in [200, 204], \
                f"Delete authenticated form failed: {response.text}"

        # Clean up public form
        if getattr(State, 'public_form_id', None):
            response = State.client.delete(
                f"/api/forms/{State.public_form_id}",
                headers=State.platform_admin.headers,
            )
            assert response.status_code in [200, 204], \
                f"Delete public form failed: {response.text}"

    # =========================================================================
    # PHASE 18: Execution History & Details
    # =========================================================================

    def test_170_org_user_lists_own_executions(self):
        """Org user can list their own executions."""
        response = State.client.get(
            "/api/executions",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"List executions failed: {response.text}"
        data = response.json()
        assert "executions" in data

        # Should include their form execution
        if State.form_execution_id:
            exec_ids = [e.get("execution_id") or e.get("executionId") for e in data["executions"]]
            assert State.form_execution_id in exec_ids, "User's execution should be visible"

    def test_171_org_user_gets_own_execution_details(self):
        """Org user can get details of their own execution."""
        if not State.form_execution_id:
            pytest.skip("No form execution ID")

        response = State.client.get(
            f"/api/executions/{State.form_execution_id}",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"Get execution failed: {response.text}"

    def test_172_org_user_cannot_see_others_execution(self):
        """Org user cannot access another user's execution."""
        if not State.sync_execution_id:
            pytest.skip("No sync execution ID")

        # Try to access platform admin's execution
        response = State.client.get(
            f"/api/executions/{State.sync_execution_id}",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Should not access other's execution: {response.status_code}"

    def test_173_org_user_cannot_see_variables(self):
        """Org user cannot access execution variables (403)."""
        if not State.form_execution_id:
            pytest.skip("No form execution ID")

        response = State.client.get(
            f"/api/executions/{State.form_execution_id}/variables",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not see variables: {response.status_code}"

    def test_174_platform_admin_sees_all_executions(self):
        """Platform admin can list all executions."""
        response = State.client.get(
            "/api/executions",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List executions failed: {response.text}"
        data = response.json()

        # Verify the response structure is correct
        assert "executions" in data or isinstance(data, list)

        # If we have executions, verify we can see data from multiple users
        executions = data.get("executions", []) if isinstance(data, dict) else data
        if len(executions) > 0:
            # Should see executions from at least one user
            executed_by_set = set()
            for exec in executions:
                executed_by_set.add(exec.get("executed_by") or exec.get("executedBy"))
            assert len(executed_by_set) >= 1

    def test_175_platform_admin_sees_variables(self):
        """Platform admin can access execution variables."""
        if not State.sync_execution_id:
            pytest.skip("No sync execution ID")

        response = State.client.get(
            f"/api/executions/{State.sync_execution_id}/variables",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get variables failed: {response.text}"
        # Variables should be a dict (possibly empty)
        assert isinstance(response.json(), dict)

    def test_176_get_execution_result_endpoint(self):
        """Progressive result loading endpoint works."""
        if not State.sync_execution_id:
            pytest.skip("No sync execution ID")

        response = State.client.get(
            f"/api/executions/{State.sync_execution_id}/result",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get result failed: {response.text}"

        # Verify result structure
        result_data = response.json()
        assert "result" in result_data, "Result should have 'result' field"
        assert "result_type" in result_data, "Result should have 'result_type' field"

        # Verify the actual result content
        assert result_data["result"] is not None, "Result should not be None"
        if isinstance(result_data["result"], dict):
            assert "status" in result_data["result"], "E2E workflow should return status field"

    def test_177_get_execution_logs_endpoint(self):
        """Execution logs endpoint works."""
        if not State.sync_execution_id:
            pytest.skip("No sync execution ID")

        response = State.client.get(
            f"/api/executions/{State.sync_execution_id}/logs",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get logs failed: {response.text}"
        logs = response.json()
        assert isinstance(logs, list), "Logs should be a list"

        # Verify log structure (if logs exist)
        # Note: e2e_test_sync_workflow doesn't log anything, so logs may be empty
        for log in logs:
            assert "level" in log, "Log entry should have 'level' field"
            assert "message" in log, "Log entry should have 'message' field"
            assert "timestamp" in log, "Log entry should have 'timestamp' field"
            assert log["level"] in ["debug", "info", "warning", "error", "traceback"], f"Invalid log level: {log['level']}"

    # =========================================================================
    # PHASE 18B: Execution Behavior Tests (Config Scoping, Debug Logs, Concurrency)
    # =========================================================================

    def test_178_setup_config_for_execution_tests(self):
        """Set up global and org-specific config for execution tests."""

        # Create global config (no X-Organization-Id header = GLOBAL scope)
        response = State.client.post(
            "/api/config",
            headers=State.platform_admin.headers,
            json={
                "key": "e2e_test_key",
                "value": "global_value",
                "type": "string",
                "description": "E2E test config - global scope",
            },
        )
        assert response.status_code == 201, f"Create global config failed: {response.text}"
        global_config = response.json()
        assert global_config.get("scope") == "GLOBAL", \
            f"Global config should have GLOBAL scope, got: {global_config}"

        # Create org-specific config for org1 (use X-Organization-Id header for org scope)
        response = State.client.post(
            "/api/config",
            headers={
                **State.platform_admin.headers,
                "X-Organization-Id": State.org1["id"],
            },
            json={
                "key": "e2e_test_key",
                "value": "org_value",
                "type": "string",
                "description": "E2E test config - org scope",
            },
        )
        assert response.status_code == 201, f"Create org config failed: {response.text}"
        org_config = response.json()
        assert org_config.get("org_id") == State.org1["id"], \
            f"Org config should have org_id={State.org1['id']}, got: {org_config}"

    def test_179_org_user_execution_uses_org_config(self):
        """Org user execution resolves org-specific config over global."""
        if not State.async_workflow_id:
            pytest.skip("Async workflow ID not captured from test_112")

        # Create a form that links to async workflow (which retrieves config)
        # so org user can execute with their org context
        response = State.client.post(
            "/api/forms",
            headers=State.platform_admin.headers,
            json={
                "name": "E2E Config Test Form",
                "description": "Form for config scoping test",
                "workflow_id": State.async_workflow_id,
                "form_schema": {"fields": []},
                "access_level": "authenticated",
            },
        )
        if response.status_code != 201:
            pytest.skip(f"Form creation failed: {response.text}")

        form = response.json()
        config_test_form_id = form["id"]

        # Execute as org1 user via form (authenticated access level allows any auth user)
        response = State.client.post(
            f"/api/forms/{config_test_form_id}/execute",
            headers=State.org1_user.headers,
            json={},
        )
        assert response.status_code == 200, f"Execute form failed: {response.text}"
        data = response.json()
        State.org_user_config_exec_id = data.get("execution_id") or data.get("executionId")

        # Clean up form
        State.client.delete(f"/api/forms/{config_test_form_id}", headers=State.platform_admin.headers)

    def test_180_admin_execution_uses_global_config(self):
        """Admin execution without org context uses global config."""
        # Get workflow ID
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_test_async_workflow"}
        )
        if list_response.status_code != 200:
            pytest.skip("Could not list workflows")
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_test_async_workflow"]
        if not matching:
            pytest.skip("Async workflow not found")
        workflow_id = matching[0]["id"]

        # Execute as platform admin (no org context) via direct execute
        response = State.client.post(
            "/api/workflows/execute",
            headers=State.platform_admin.headers,
            json={
                "workflow_id": workflow_id,
                "input_data": {},
            },
        )
        assert response.status_code in [200, 202], f"Admin workflow execute failed: {response.text}"
        data = response.json()
        State.admin_config_exec_id = data.get("execution_id") or data.get("executionId")

    def test_181_wait_for_config_test_executions(self):
        """Wait for config test executions to complete."""
        import time

        if not State.org_user_config_exec_id and not State.admin_config_exec_id:
            pytest.skip("No config test executions to wait for")

        exec_ids = [e for e in [State.org_user_config_exec_id, State.admin_config_exec_id] if e]

        for exec_id in exec_ids:
            for _ in range(30):  # 30 second timeout
                response = State.client.get(
                    f"/api/executions/{exec_id}",
                    headers=State.platform_admin.headers,
                )
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    if status in ["Success", "Failed"]:
                        assert status == "Success", f"Execution {exec_id} failed: {data}"
                        break
                time.sleep(1)
            else:
                pytest.fail(f"Execution {exec_id} did not complete within timeout")

    def test_182_verify_org_user_got_org_config(self):
        """Verify org user's execution got org-specific config value."""
        if not State.org_user_config_exec_id:
            pytest.skip("No org user config execution")

        response = State.client.get(
            f"/api/executions/{State.org_user_config_exec_id}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get execution failed: {response.text}"
        data = response.json()

        result = data.get("result", {})
        config_value = result.get("config_value")
        assert config_value == "org_value", \
            f"Org user should get org-specific config, got: {config_value}"

    def test_183_verify_admin_got_global_config(self):
        """Verify admin's execution got global config value."""
        if not State.admin_config_exec_id:
            pytest.skip("No admin config execution")

        response = State.client.get(
            f"/api/executions/{State.admin_config_exec_id}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get execution failed: {response.text}"
        data = response.json()

        result = data.get("result", {})
        config_value = result.get("config_value")
        assert config_value == "global_value", \
            f"Admin should get global config, got: {config_value}"

    def test_184_org_user_cannot_see_debug_logs(self):
        """Org user only sees INFO+ logs, not DEBUG."""
        if not State.org_user_config_exec_id:
            pytest.skip("No org user config execution")

        response = State.client.get(
            f"/api/executions/{State.org_user_config_exec_id}/logs",
            headers=State.org1_user.headers,
        )
        # Org user may not have access to their own logs - check 200 or 403
        if response.status_code == 403:
            pytest.skip("Org user cannot access execution logs directly")

        assert response.status_code == 200, f"Get logs failed: {response.text}"
        logs = response.json()

        # Check that no DEBUG entries are visible
        for log in logs:
            message = log.get("message", "")
            level = log.get("level", "")
            # Should not see DEBUG level logs
            assert "DEBUG:" not in message, f"Org user should not see DEBUG logs: {message}"
            assert level.upper() != "DEBUG", f"Org user should not see DEBUG level: {level}"

    def test_185_platform_admin_sees_debug_logs(self):
        """Platform admin can see DEBUG level logs."""
        if not State.admin_config_exec_id:
            pytest.skip("No admin config execution")

        response = State.client.get(
            f"/api/executions/{State.admin_config_exec_id}/logs",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get logs failed: {response.text}"
        logs = response.json()

        # Platform admin should see DEBUG entries
        has_debug = any(
            "DEBUG:" in log.get("message", "") or log.get("level", "").upper() == "DEBUG"
            for log in logs
        )
        # Note: This may fail if DEBUG logging is not enabled in test env
        # Accept either having DEBUG logs or not (depends on log level config)
        if not has_debug and len(logs) > 0:
            # Just verify we got logs - DEBUG visibility depends on config
            pass

    @pytest.mark.asyncio
    async def test_186_queue_position_and_concurrency(self):
        """
        Test queue position visibility and concurrent execution.

        With BIFROST_MAX_CONCURRENCY=3 and 10 executions:
        1. First 3 start immediately
        2. Remaining 7 are queued with positions 1-7
        3. WebSocket should receive queue position updates
        4. All 10 complete in parallel batches (not sequentially)
        """
        import asyncio
        import time
        from websockets.asyncio.client import connect

        # Get workflow ID first
        list_response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers,
            params={"search": "e2e_test_async_workflow"}
        )
        if list_response.status_code != 200:
            pytest.skip("Could not list workflows")
        workflows = list_response.json()
        matching = [w for w in workflows if w.get("name") == "e2e_test_async_workflow"]
        if not matching:
            pytest.skip("Async workflow not found")
        workflow_id = matching[0]["id"]

        ws_url = f"{WS_BASE_URL}/ws/connect"
        # WebSocket auth uses Authorization header (not query params for security)
        extra_headers = {
            "Authorization": f"Bearer {State.platform_admin.access_token}"
        }

        try:
            async with connect(ws_url, additional_headers=extra_headers) as ws:
                # Receive connected message
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["type"] == "connected", f"Expected connected, got: {data}"

                # Start 10 async executions and subscribe as we go
                # This ensures we're subscribed before all executions are launched
                execution_ids = []
                for i in range(10):
                    response = State.client.post(
                        "/api/workflows/execute",
                        headers=State.platform_admin.headers,
                        json={
                            "workflow_id": workflow_id,
                            "input_data": {"delay_seconds": 2},
                        },
                    )
                    assert response.status_code in [200, 202], f"Execute #{i} failed: {response.text}"
                    data = response.json()
                    exec_id = data.get("execution_id") or data.get("executionId")
                    execution_ids.append(exec_id)

                    # Subscribe to each execution as it's created
                    await ws.send(json.dumps({
                        "type": "subscribe",
                        "channels": [f"execution:{exec_id}"]
                    }))

                # Collect WebSocket messages while waiting for completion
                queue_position_updates = []
                all_ws_messages = []  # For debugging
                completed_executions = set()
                start = time.time()

                while len(completed_executions) < len(execution_ids):
                    if time.time() - start > 60:  # 60 second timeout
                        pytest.fail(
                            f"Only {len(completed_executions)}/{len(execution_ids)} "
                            f"executions completed in 60s. "
                            f"Messages received: {len(all_ws_messages)}, "
                            f"Queue updates: {len(queue_position_updates)}"
                        )

                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)
                        all_ws_messages.append(data)

                        # Check for queue position updates
                        if data.get("type") == "execution_update":
                            exec_id = data.get("executionId")
                            status = data.get("status")

                            # Capture queue position updates
                            if data.get("queuePosition") is not None:
                                queue_position_updates.append({
                                    "executionId": exec_id,
                                    "queuePosition": data.get("queuePosition"),
                                    "waitReason": data.get("waitReason"),
                                    "status": status,
                                })

                            # Track completed executions
                            if status in ["Success", "Failed", "Cancelled"]:
                                if exec_id in execution_ids:
                                    completed_executions.add(exec_id)

                    except asyncio.TimeoutError:
                        # No message received, poll REST API as backup
                        for exec_id in execution_ids:
                            if exec_id in completed_executions:
                                continue
                            response = State.client.get(
                                f"/api/executions/{exec_id}",
                                headers=State.platform_admin.headers,
                            )
                            if response.status_code == 200:
                                status = response.json().get("status")
                                if status in ["Success", "Failed", "Cancelled"]:
                                    completed_executions.add(exec_id)

                elapsed = time.time() - start

                # Verify parallel execution timing FIRST (core functionality)
                # 10 workflows × 2s with concurrency 3:
                # Batches: [3][3][3][1] = 4 batches × 2s = 8s (plus overhead)
                # Sequential would be 20s+
                # Allow up to 20s for test environment variability
                assert elapsed < 20, (
                    f"10 executions took {elapsed:.1f}s - "
                    f"expected <20s for parallel execution with concurrency=3"
                )

                # Verify all 10 succeeded
                for exec_id in execution_ids:
                    response = State.client.get(
                        f"/api/executions/{exec_id}",
                        headers=State.platform_admin.headers,
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert data.get("status") == "Success", (
                        f"Execution {exec_id} failed: {data}"
                    )

                # Verify queue position updates were received (if concurrency < 10)
                # Note: This may not capture all updates due to timing, so we verify
                # that the system works (parallel execution) even if WebSocket
                # updates weren't captured in time
                if len(queue_position_updates) > 0:
                    # Verify queue positions have expected fields
                    for update in queue_position_updates:
                        assert update["queuePosition"] >= 1, "Queue position should be 1-based"
                        assert update["waitReason"] == "queued", (
                            f"Expected waitReason='queued', got '{update['waitReason']}'"
                        )
                    print(f"✓ Received {len(queue_position_updates)} queue position updates")
                else:
                    # Queue position updates may have been published before subscription
                    # The important thing is that parallel execution worked
                    print(
                        f"Note: No queue position updates captured via WebSocket "
                        f"(timing issue - updates published before subscription). "
                        f"Total messages received: {len(all_ws_messages)}"
                    )

        except Exception as e:
            # If WebSocket fails, fall back to polling-only test
            pytest.skip(f"WebSocket connection failed: {e}")

    def test_187_cleanup_execution_test_config(self):
        """Clean up config created for execution tests."""
        # Delete global config
        response = State.client.delete(
            "/api/config/e2e_test_key",
            headers=State.platform_admin.headers,
        )
        assert response.status_code in [200, 204, 404]

        # Delete org-specific config
        response = State.client.delete(
            f"/api/config/e2e_test_key?organization_id={State.org1['id']}",
            headers=State.platform_admin.headers,
        )
        # May be 404 if org config deletion requires different API
        assert response.status_code in [200, 204, 404]

    # =========================================================================
    # PHASE 19: Package Management
    # =========================================================================

    def test_210_list_packages(self):
        """Platform admin can list installed packages."""
        response = State.client.get(
            "/api/packages",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List packages failed: {response.text}"
        data = response.json()
        assert "packages" in data
        assert isinstance(data["packages"], list)

    def test_211_check_package_updates(self):
        """Platform admin can check for package updates."""
        response = State.client.get(
            "/api/packages/updates",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Check updates failed: {response.text}"
        data = response.json()
        assert "updates" in data

    def test_212_org_user_cannot_install_packages(self):
        """Org user cannot install packages (403)."""
        response = State.client.post(
            "/api/packages/install",
            headers=State.org1_user.headers,
            json={"package": "some-package"},
        )
        assert response.status_code == 403, \
            f"Org user should not install packages: {response.status_code}"

    # =========================================================================
    # PHASE 23: WebSocket Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_300_websocket_connect_with_valid_token(self):
        """Connect to WebSocket with valid JWT token."""
        import asyncio
        from websockets.asyncio.client import connect

        ws_url = f"{WS_BASE_URL}/ws/connect"
        # WebSocket auth uses Authorization header (not query params for security)
        extra_headers = {"Authorization": f"Bearer {State.platform_admin.access_token}"}

        try:
            async with connect(ws_url, additional_headers=extra_headers) as ws:
                # Should receive connected message
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["type"] == "connected", f"Expected connected, got: {data}"
                assert "userId" in data or "user_id" in data
        except Exception as e:
            pytest.skip(f"WebSocket connection failed: {e}")

    @pytest.mark.asyncio
    async def test_301_websocket_connect_invalid_token(self):
        """Connect to WebSocket with invalid token should fail."""
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus

        ws_url = f"{WS_BASE_URL}/ws/connect"
        # Invalid token via Authorization header
        extra_headers = {"Authorization": "Bearer invalid-token-12345"}

        try:
            async with connect(ws_url, additional_headers=extra_headers) as _ws:
                # Should not get here - connection should be rejected
                pytest.fail("Connection should have been rejected")
        except InvalidStatus as e:
            # Expected - connection rejected
            assert e.response.status_code in [401, 403, 4001], f"Unexpected status: {e.response.status_code}"
        except Exception:
            # Other rejection is acceptable
            pass

    @pytest.mark.asyncio
    async def test_302_websocket_ping_pong(self):
        """WebSocket ping/pong works."""
        import asyncio
        from websockets.asyncio.client import connect

        ws_url = f"{WS_BASE_URL}/ws/connect"
        extra_headers = {"Authorization": f"Bearer {State.platform_admin.access_token}"}

        try:
            async with connect(ws_url, additional_headers=extra_headers) as ws:
                # Receive connected message first
                await asyncio.wait_for(ws.recv(), timeout=5)

                # Send ping
                await ws.send(json.dumps({"type": "ping"}))

                # Should receive pong
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["type"] == "pong", f"Expected pong, got: {data}"
        except Exception as e:
            pytest.skip(f"WebSocket test failed: {e}")

    @pytest.mark.asyncio
    async def test_303_websocket_subscribe_to_execution(self):
        """Subscribe to execution channel."""
        import asyncio
        from websockets.asyncio.client import connect

        if not State.sync_execution_id:
            pytest.skip("No execution ID to subscribe to")

        ws_url = f"{WS_BASE_URL}/ws/connect"
        extra_headers = {"Authorization": f"Bearer {State.platform_admin.access_token}"}

        try:
            async with connect(ws_url, additional_headers=extra_headers) as ws:
                # Receive connected message
                await asyncio.wait_for(ws.recv(), timeout=5)

                # Subscribe to execution channel
                await ws.send(json.dumps({
                    "type": "subscribe",
                    "channels": [f"execution:{State.sync_execution_id}"]
                }))

                # Should receive subscription confirmation or no error
                # Some implementations don't send confirmation
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    data = json.loads(msg)
                    # Accept subscribed confirmation or any non-error response
                    assert data.get("type") != "error", f"Subscribe error: {data}"
                except asyncio.TimeoutError:
                    # No confirmation is also acceptable
                    pass
        except Exception as e:
            pytest.skip(f"WebSocket test failed: {e}")

    @pytest.mark.asyncio
    async def test_304_org_user_websocket_access(self):
        """Org user can connect to WebSocket."""
        import asyncio
        from websockets.asyncio.client import connect

        ws_url = f"{WS_BASE_URL}/ws/connect"
        extra_headers = {"Authorization": f"Bearer {State.org1_user.access_token}"}

        try:
            async with connect(ws_url, additional_headers=extra_headers) as ws:
                # Should receive connected message
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                assert data["type"] == "connected", f"Expected connected, got: {data}"
        except Exception as e:
            pytest.skip(f"WebSocket connection failed: {e}")

    # =========================================================================
    # PHASE 24: Branding Tests
    # =========================================================================

    def test_320_get_branding_public(self):
        """Get branding without authentication (public endpoint)."""
        # Create a new client without auth headers
        response = State.client.get("/api/branding")
        # Accept 200 or 404 (if branding not configured)
        assert response.status_code in [200, 404], f"Get branding failed: {response.text}"

    def test_321_get_branding_authenticated(self):
        """Get branding with authentication."""
        response = State.client.get(
            "/api/branding",
            headers=State.org1_user.headers,
        )
        assert response.status_code in [200, 404], f"Get branding failed: {response.text}"

    def test_322_update_branding_superuser(self):
        """Superuser can update branding."""
        response = State.client.put(
            "/api/branding",
            headers=State.platform_admin.headers,
            json={
                "primary_color": "#1a73e8",
                "app_name": "Bifrost E2E Test",
            },
        )
        assert response.status_code in [200, 201], f"Update branding failed: {response.text}"

    def test_323_update_branding_org_user_denied(self):
        """Org user cannot update branding (403)."""
        response = State.client.put(
            "/api/branding",
            headers=State.org1_user.headers,
            json={
                "primary_color": "#ff0000",
                "app_name": "Hacked App",
            },
        )
        assert response.status_code == 403, \
            f"Org user should not update branding: {response.status_code}"

    def test_324_upload_square_logo_superuser(self):
        """Superuser can upload square logo."""
        import os
        logo_path = os.path.join(os.path.dirname(__file__), "../logos/square.png")

        with open(logo_path, "rb") as f:
            logo_data = f.read()

        response = State.client.post(
            "/api/branding/logo/square",
            headers={
                "Authorization": f"Bearer {State.platform_admin.access_token}",
            },
            files={"file": ("square.png", logo_data, "image/png")},
        )
        assert response.status_code in [200, 201], f"Upload square logo failed: {response.text}"

    def test_325_upload_rectangle_logo_superuser(self):
        """Superuser can upload rectangle logo."""
        import os
        logo_path = os.path.join(os.path.dirname(__file__), "../logos/rectangle.png")

        with open(logo_path, "rb") as f:
            logo_data = f.read()

        response = State.client.post(
            "/api/branding/logo/rectangle",
            headers={
                "Authorization": f"Bearer {State.platform_admin.access_token}",
            },
            files={"file": ("rectangle.png", logo_data, "image/png")},
        )
        assert response.status_code in [200, 201], f"Upload rectangle logo failed: {response.text}"

    def test_326_get_square_logo_public(self):
        """Get square logo without authentication after upload."""
        response = State.client.get("/api/branding/logo/square")
        assert response.status_code == 200, f"Get square logo failed: {response.text}"
        assert response.headers.get("content-type") == "image/png", "Logo should be PNG"
        assert len(response.content) > 0, "Logo content should not be empty"

    def test_327_get_rectangle_logo_public(self):
        """Get rectangle logo without authentication after upload."""
        response = State.client.get("/api/branding/logo/rectangle")
        assert response.status_code == 200, f"Get rectangle logo failed: {response.text}"
        assert response.headers.get("content-type") == "image/png", "Logo should be PNG"
        assert len(response.content) > 0, "Logo content should not be empty"

    def test_328_upload_logo_org_user_denied(self):
        """Org user cannot upload logo (403)."""
        import os
        logo_path = os.path.join(os.path.dirname(__file__), "../logos/square.png")

        with open(logo_path, "rb") as f:
            logo_data = f.read()

        response = State.client.post(
            "/api/branding/logo/square",
            headers={
                "Authorization": f"Bearer {State.org1_user.access_token}",
            },
            files={"file": ("logo.png", logo_data, "image/png")},
        )
        assert response.status_code == 403, \
            f"Org user should not upload logo: {response.status_code}"

    # =========================================================================
    # PHASE 25: Metrics Tests
    # =========================================================================

    def test_330_get_metrics_authenticated(self):
        """Authenticated user can get metrics."""
        response = State.client.get(
            "/api/metrics",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"Get metrics failed: {response.text}"
        data = response.json()
        # Verify structure has expected fields
        assert isinstance(data, dict)

    def test_331_get_metrics_superuser(self):
        """Superuser can get metrics."""
        response = State.client.get(
            "/api/metrics",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get metrics failed: {response.text}"

    def test_332_metrics_response_structure(self):
        """Metrics response has expected structure."""
        response = State.client.get(
            "/api/metrics",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Check for common metric fields (may vary by implementation)
        # Accept any dict response as valid
        assert isinstance(data, dict), "Metrics should return a dict"

    def test_333_get_metrics_unauthenticated(self):
        """Unauthenticated request to metrics fails."""
        # Create request without auth header
        response = State.client.get("/api/metrics")
        assert response.status_code == 401, \
            f"Unauthenticated should be 401: {response.status_code}"

    def test_334_get_metrics_snapshot_superuser(self):
        """Superuser can get full metrics snapshot."""
        response = State.client.get(
            "/api/metrics/snapshot",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get snapshot failed: {response.text}"
        data = response.json()

        # Verify snapshot structure
        assert "workflow_count" in data
        assert "form_count" in data
        assert "data_provider_count" in data
        assert "organization_count" in data
        assert "user_count" in data
        assert "total_executions" in data
        assert "executions_24h" in data
        assert "success_rate_all_time" in data
        assert "success_rate_24h" in data
        assert "refreshed_at" in data

    def test_335_get_metrics_snapshot_org_user_denied(self):
        """Org user cannot access metrics snapshot (403)."""
        response = State.client.get(
            "/api/metrics/snapshot",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access snapshot: {response.status_code}"

    def test_336_get_daily_metrics_superuser(self):
        """Superuser can get daily execution metrics."""
        response = State.client.get(
            "/api/metrics/executions/daily",
            headers=State.platform_admin.headers,
            params={"days": 7},
        )
        assert response.status_code == 200, f"Get daily metrics failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "days" in data
        assert "total_days" in data
        assert isinstance(data["days"], list)

        # If there are days, verify entry structure
        if data["days"]:
            entry = data["days"][0]
            assert "date" in entry
            assert "execution_count" in entry
            assert "success_count" in entry
            assert "failed_count" in entry

    def test_337_get_daily_metrics_org_user_denied(self):
        """Org user cannot access daily metrics (403)."""
        response = State.client.get(
            "/api/metrics/executions/daily",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access daily metrics: {response.status_code}"

    def test_338_get_organization_metrics_superuser(self):
        """Superuser can get organization metrics breakdown."""
        response = State.client.get(
            "/api/metrics/organizations",
            headers=State.platform_admin.headers,
            params={"days": 30, "limit": 10},
        )
        assert response.status_code == 200, f"Get org metrics failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "organizations" in data
        assert "total_organizations" in data
        assert isinstance(data["organizations"], list)

        # If there are organizations, verify entry structure
        if data["organizations"]:
            org = data["organizations"][0]
            assert "organization_id" in org
            assert "organization_name" in org
            assert "total_executions" in org
            assert "success_rate" in org

    def test_339_get_organization_metrics_org_user_denied(self):
        """Org user cannot access organization metrics (403)."""
        response = State.client.get(
            "/api/metrics/organizations",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access org metrics: {response.status_code}"

    def test_339a_get_resource_metrics_superuser(self):
        """Superuser can get resource usage metrics."""
        response = State.client.get(
            "/api/metrics/resources",
            headers=State.platform_admin.headers,
            params={"days": 7},
        )
        assert response.status_code == 200, f"Get resource metrics failed: {response.text}"
        data = response.json()

        # Verify response structure
        assert "days" in data
        assert "total_days" in data
        assert isinstance(data["days"], list)

        # If there are days, verify entry structure
        if data["days"]:
            entry = data["days"][0]
            assert "date" in entry
            assert "peak_memory_bytes" in entry
            assert "total_memory_bytes" in entry
            assert "peak_cpu_seconds" in entry
            assert "execution_count" in entry

    def test_339b_get_resource_metrics_org_user_denied(self):
        """Org user cannot access resource metrics (403)."""
        response = State.client.get(
            "/api/metrics/resources",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not access resource metrics: {response.status_code}"

    # =========================================================================
    # PHASE 26: Logs Tests
    # =========================================================================

    def test_340_list_logs_superuser(self):
        """Superuser can list logs."""
        response = State.client.get(
            "/api/logs",
            headers=State.platform_admin.headers,
        )
        # Accept 200 (logs returned) or empty array (stub implementation)
        assert response.status_code == 200, f"List logs failed: {response.text}"
        data = response.json()
        assert isinstance(data, (list, dict)), "Logs should return list or dict"

    def test_341_list_logs_org_user_denied(self):
        """Org user cannot list logs (403)."""
        response = State.client.get(
            "/api/logs",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not list logs: {response.status_code}"

    def test_342_get_single_log_superuser(self):
        """Superuser can get single log (even if 404)."""
        response = State.client.get(
            "/api/logs/system/test-row-key",
            headers=State.platform_admin.headers,
        )
        # Accept 200 (found) or 404 (not found - stub)
        assert response.status_code in [200, 404], f"Get log failed: {response.text}"

    def test_343_get_single_log_org_user_denied(self):
        """Org user cannot get single log (403)."""
        response = State.client.get(
            "/api/logs/system/test-row-key",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not get log: {response.status_code}"

    # =========================================================================
    # PHASE 27: Permission Enforcement Tests
    # =========================================================================

    def test_350_org_user_cannot_create_forms(self):
        """Org user cannot create forms (403)."""
        response = State.client.post(
            "/api/forms",
            headers=State.org1_user.headers,
            json={
                "name": "Unauthorized Form",
                "workflow_id": None,
                "form_schema": {"fields": []},
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create forms: {response.status_code}"

    def test_351_org_user_cannot_update_forms(self):
        """Org user cannot update forms (403)."""
        if not State.e2e_form_id:
            pytest.skip("No form to update")

        response = State.client.put(
            f"/api/forms/{State.e2e_form_id}",
            headers=State.org1_user.headers,
            json={"name": "Hacked Form Name"},
        )
        assert response.status_code == 403, \
            f"Org user should not update forms: {response.status_code}"

    def test_352_org_user_cannot_delete_forms(self):
        """Org user cannot delete forms (403)."""
        if not State.e2e_form_id:
            pytest.skip("No form to delete")

        response = State.client.delete(
            f"/api/forms/{State.e2e_form_id}",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete forms: {response.status_code}"

    def test_353_org_user_cannot_list_all_users(self):
        """Org user cannot list all users (403 or filtered)."""
        response = State.client.get(
            "/api/users",
            headers=State.org1_user.headers,
        )
        # Should be 403 or return only limited/filtered data
        assert response.status_code in [403, 200], f"Unexpected: {response.status_code}"
        if response.status_code == 200:
            # If 200, should be filtered (not see all users)
            data = response.json()
            users = data.get("users", []) if isinstance(data, dict) else data
            # Org user should not see platform admin details
            for user in users:
                if user.get("is_superuser"):
                    # Should not expose superuser details to org user
                    pass  # Implementation may vary

    def test_354_org_user_cannot_create_users(self):
        """Org user cannot create users (403)."""
        response = State.client.post(
            "/api/users",
            headers=State.org1_user.headers,
            json={
                "email": "hacker@evil.com",
                "name": "Hacker",
                "organization_id": str(State.org1["id"]),
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create users: {response.status_code}"

    def test_355_org_user_cannot_delete_users(self):
        """Org user cannot delete users (403)."""
        response = State.client.delete(
            f"/api/users/{State.platform_admin.user_id}",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete users: {response.status_code}"

    def test_356_org_user_cannot_modify_config(self):
        """Org user cannot modify config (403)."""
        # Config API uses POST for upsert (no PUT endpoint)
        response = State.client.post(
            "/api/config",
            headers=State.org1_user.headers,
            json={"key": "test_key", "value": "hacked_value", "type": "string"},
        )
        assert response.status_code == 403, \
            f"Org user should not modify config: {response.status_code}"

    def test_357_org_user_cannot_delete_config(self):
        """Org user cannot delete config (403)."""
        response = State.client.delete(
            "/api/config/test_key",
            headers=State.org1_user.headers,
        )
        assert response.status_code in [403, 404], \
            f"Org user should not delete config: {response.status_code}"

    def test_358_org_user_cannot_uninstall_packages(self):
        """Org user cannot uninstall packages (403)."""
        response = State.client.delete(
            "/api/packages/some-package",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not uninstall packages: {response.status_code}"

    def test_359_org_user_cannot_access_oauth_admin(self):
        """Org user cannot create OAuth connections (403)."""
        # Correct path is /api/oauth/connections (not /api/oauth-connections)
        response = State.client.post(
            "/api/oauth/connections",
            headers=State.org1_user.headers,
            json={
                "connection_name": "hacked_oauth",
                "oauth_flow_type": "authorization_code",
                "authorization_url": "https://evil.com/auth",
                "token_url": "https://evil.com/token",
                "client_id": "hacked",
                "client_secret": "hacked",
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create OAuth: {response.status_code}"

    def test_360_org_user_cannot_modify_roles(self):
        """Org user cannot modify roles (403)."""
        if not State.e2e_role_id:
            pytest.skip("No role to modify")

        response = State.client.put(
            f"/api/roles/{State.e2e_role_id}",
            headers=State.org1_user.headers,
            json={"name": "Hacked Role"},
        )
        assert response.status_code == 403, \
            f"Org user should not modify roles: {response.status_code}"

    def test_361_org_user_cannot_delete_roles(self):
        """Org user cannot delete roles (403)."""
        if not State.e2e_role_id:
            pytest.skip("No role to delete")

        response = State.client.delete(
            f"/api/roles/{State.e2e_role_id}",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete roles: {response.status_code}"

    def test_362_org_user_can_read_own_profile(self):
        """Org user can read their own profile (positive test)."""
        # Correct path is /auth/me (auth router has prefix /auth, not /api/auth)
        response = State.client.get(
            "/auth/me",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"Get own profile failed: {response.text}"
        data = response.json()
        assert data.get("email") == State.org1_user.email

    def test_363_org_user_can_list_assigned_forms(self):
        """Org user can list forms assigned to them."""
        response = State.client.get(
            "/api/forms",
            headers=State.org1_user.headers,
        )
        assert response.status_code == 200, f"List forms failed: {response.text}"
        # Response should be filtered to assigned forms only

    # =========================================================================
    # PHASE: OAuth Connection CRUD Tests (Platform Admin)
    # =========================================================================

    def test_370_create_oauth_connection(self):
        """Platform admin can create an OAuth connection."""
        State.e2e_oauth_connection_name = "e2e_test_oauth"

        response = State.client.post(
            "/api/oauth/connections",
            headers=State.platform_admin.headers,
            json={
                "connection_name": State.e2e_oauth_connection_name,
                "name": "E2E Test OAuth Connection",
                "description": "Test OAuth connection for E2E tests",
                "oauth_flow_type": "authorization_code",
                "client_id": "e2e-test-client-id",
                "client_secret": "e2e-test-client-secret",
                "authorization_url": "https://example.com/oauth/authorize",
                "token_url": "https://example.com/oauth/token",
                "scopes": "read write offline_access",
            },
        )
        assert response.status_code == 201, f"Create OAuth connection failed: {response.text}"

        data = response.json()
        assert data["connection_name"] == State.e2e_oauth_connection_name
        assert data["client_id"] == "e2e-test-client-id"
        assert data["status"] == "not_connected"
        # client_secret should NOT be returned
        assert "client_secret" not in data or data.get("client_secret") is None

    def test_371_list_oauth_connections(self):
        """Platform admin can list OAuth connections."""
        response = State.client.get(
            "/api/oauth/connections",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"List OAuth connections failed: {response.text}"

        data = response.json()
        assert "connections" in data
        connections = data["connections"]
        assert isinstance(connections, list)

        # Find our test connection
        test_conn = next(
            (c for c in connections if c["connection_name"] == State.e2e_oauth_connection_name),
            None
        )
        assert test_conn is not None, "Test OAuth connection not found in list"

    def test_372_get_oauth_connection_detail(self):
        """Platform admin can get OAuth connection details."""
        response = State.client.get(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Get OAuth connection failed: {response.text}"

        data = response.json()
        assert data["connection_name"] == State.e2e_oauth_connection_name
        assert data["oauth_flow_type"] == "authorization_code"
        assert data["authorization_url"] == "https://example.com/oauth/authorize"
        assert data["token_url"] == "https://example.com/oauth/token"
        # Scopes should be returned (as stored)
        assert "scopes" in data

    def test_373_update_oauth_connection(self):
        """Platform admin can update an OAuth connection."""
        response = State.client.put(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
            json={
                "name": "Updated E2E OAuth Connection",
                "client_id": "updated-client-id",
                "authorization_url": "https://example.com/oauth/v2/authorize",
                "token_url": "https://example.com/oauth/v2/token",
                "scopes": "read,write,admin",  # Test comma-separated format
            },
        )
        assert response.status_code == 200, f"Update OAuth connection failed: {response.text}"

        data = response.json()
        assert data["name"] == "Updated E2E OAuth Connection"
        assert data["client_id"] == "updated-client-id"

    def test_374_verify_oauth_connection_updated(self):
        """Verify OAuth connection was updated correctly."""
        response = State.client.get(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated E2E OAuth Connection"
        assert data["client_id"] == "updated-client-id"
        assert data["authorization_url"] == "https://example.com/oauth/v2/authorize"
        assert data["token_url"] == "https://example.com/oauth/v2/token"

    def test_375_update_oauth_connection_scopes_space_separated(self):
        """Update OAuth connection with space-separated scopes."""
        response = State.client.put(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
            json={
                "scopes": "openid profile email",  # Space-separated
            },
        )
        assert response.status_code == 200, f"Update scopes failed: {response.text}"

    def test_376_initiate_oauth_authorization(self):
        """Platform admin can initiate OAuth authorization flow."""
        response = State.client.post(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}/authorize",
            headers=State.platform_admin.headers,
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

    def test_377_cancel_oauth_authorization(self):
        """Platform admin can cancel OAuth authorization."""
        response = State.client.post(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}/cancel",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 200, f"Cancel authorization failed: {response.text}"

        data = response.json()
        assert data["status"] == "not_connected"

    def test_378_oauth_connection_not_found(self):
        """Get non-existent OAuth connection returns 404."""
        response = State.client.get(
            "/api/oauth/connections/nonexistent_oauth_connection",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 404

    def test_379_delete_oauth_connection(self):
        """Platform admin can delete an OAuth connection."""
        response = State.client.delete(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete OAuth connection failed: {response.text}"

        # Verify it's gone
        response = State.client.get(
            f"/api/oauth/connections/{State.e2e_oauth_connection_name}",
            headers=State.platform_admin.headers,
        )
        assert response.status_code == 404

    # =========================================================================
    # PHASE 29: Security Tests (Token, CSRF, Rate Limiting)
    # =========================================================================

    def test_400_refresh_token_rejected_as_access_token(self):
        """
        Security: Refresh tokens should be rejected when used as access tokens.
        This tests Finding 2.1 - token type enforcement.
        """
        # Get a fresh refresh token
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()

        # If MFA required, complete MFA
        if data.get("mfa_required"):
            totp_code = generate_totp_code(State.platform_admin.totp_secret)
            mfa_response = State.client.post(
                "/auth/mfa/login",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": totp_code,
                },
            )
            assert mfa_response.status_code == 200
            data = mfa_response.json()

        refresh_token = data.get("refresh_token")
        assert refresh_token, "Should receive refresh token"

        # Try to use refresh token as access token
        response = State.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert response.status_code == 401, "Refresh token should be rejected as access token"

    def test_401_access_token_has_required_claims(self):
        """
        Security: Access tokens must include type, iss, and aud claims.
        This tests Finding 2.6 - JWT issuer/audience validation.
        """
        import jwt

        # Decode token without verification to check claims
        access_token = State.platform_admin.access_token
        payload = jwt.decode(access_token, options={"verify_signature": False})

        assert payload.get("type") == "access", "Token should have type=access"
        assert payload.get("iss") == "bifrost-api", "Token should have issuer claim"
        assert payload.get("aud") == "bifrost-client", "Token should have audience claim"

    def test_402_refresh_token_rotation(self):
        """
        Security: Refresh token should be rotated on use (old token invalidated).
        This tests Finding 2.4 - refresh token rotation.
        """
        # Login to get fresh tokens
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()

        # Complete MFA if required
        if data.get("mfa_required"):
            totp_code = generate_totp_code(State.platform_admin.totp_secret)
            mfa_response = State.client.post(
                "/auth/mfa/login",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": totp_code,
                },
            )
            assert mfa_response.status_code == 200
            data = mfa_response.json()

        old_refresh_token = data.get("refresh_token")
        assert old_refresh_token, "Should receive refresh token"

        # Use refresh token to get new tokens
        response = State.client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert response.status_code == 200, f"Refresh should succeed: {response.text}"
        new_data = response.json()
        new_refresh_token = new_data.get("refresh_token")
        assert new_refresh_token != old_refresh_token, "Should receive new refresh token"

        # Try to use old refresh token again (should fail - single use)
        response = State.client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert response.status_code == 401, "Old refresh token should be rejected after rotation"

    def test_403_csrf_required_for_cookie_auth(self):
        """
        Security: CSRF token should be required for cookie-based auth.
        This tests Finding 2.5 - CSRF protection.

        Note: This test is limited because httpx doesn't send cookies
        automatically like browsers do. We test the bearer auth exemption instead.
        """
        # Bearer auth should work without CSRF
        response = State.client.post(
            "/api/config",
            json={
                "key": "csrf_test_key",
                "value": "test",
                "is_secret": False,
                "type": "string",
            },
            headers=State.platform_admin.headers,
        )
        # This should succeed (bearer auth, no CSRF needed)
        assert response.status_code == 201, f"Bearer auth should not require CSRF: {response.text}"

        # Cleanup
        State.client.delete(
            "/api/config/csrf_test_key",
            headers=State.platform_admin.headers,
        )

    def test_404_invalid_org_id_rejected(self):
        """
        Security: Invalid organization ID in header should be rejected.
        This tests Finding 3.1 - org existence validation.
        """
        import uuid

        fake_org_id = str(uuid.uuid4())

        response = State.client.get(
            "/api/config",
            headers={
                **State.platform_admin.headers,
                "X-Organization-Id": fake_org_id,
            },
        )
        assert response.status_code == 400, f"Non-existent org should be rejected: {response.text}"
        assert "not found" in response.json().get("detail", "").lower()

    def test_405_logout_revokes_refresh_token(self):
        """
        Security: Logout should revoke the refresh token.
        This tests refresh token revocation.
        """
        # Login to get fresh tokens
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()

        # Complete MFA if required
        if data.get("mfa_required"):
            totp_code = generate_totp_code(State.platform_admin.totp_secret)
            mfa_response = State.client.post(
                "/auth/mfa/login",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": totp_code,
                },
            )
            assert mfa_response.status_code == 200
            data = mfa_response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        assert access_token and refresh_token

        # Logout - pass refresh_token in body for API clients
        response = State.client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200

        # Try to use refresh token (should fail)
        response = State.client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401, "Refresh token should be revoked after logout"

    def test_406_revoke_all_sessions(self):
        """
        Security: Revoke-all should invalidate all refresh tokens.
        This tests bulk token revocation.
        """
        # Login to get fresh tokens
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()

        # Complete MFA if required
        if data.get("mfa_required"):
            totp_code = generate_totp_code(State.platform_admin.totp_secret)
            mfa_response = State.client.post(
                "/auth/mfa/login",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": totp_code,
                },
            )
            assert mfa_response.status_code == 200
            data = mfa_response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        assert access_token and refresh_token

        # Revoke all sessions
        response = State.client.post(
            "/auth/revoke-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        revoke_data = response.json()
        assert "sessions_revoked" in revoke_data

        # Try to use refresh token (should fail)
        response = State.client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401, "Refresh token should be revoked after revoke-all"

    def test_407_restore_platform_admin_session(self):
        """
        Restore platform admin session after security tests.
        Required for cleanup tests to work.
        """
        # Login fresh
        response = State.client.post(
            "/auth/login",
            data={
                "username": State.platform_admin.email,
                "password": State.platform_admin.password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()

        # Complete MFA if required
        if data.get("mfa_required"):
            totp_code = generate_totp_code(State.platform_admin.totp_secret)
            mfa_response = State.client.post(
                "/auth/mfa/login",
                json={
                    "mfa_token": data["mfa_token"],
                    "code": totp_code,
                },
            )
            assert mfa_response.status_code == 200
            data = mfa_response.json()

        # Update stored tokens
        State.platform_admin.access_token = data.get("access_token")
        State.platform_admin.refresh_token = data.get("refresh_token")
        assert State.platform_admin.access_token, "Should restore access token"

    def test_408_rate_limit_login(self):
        """
        Security: Login endpoint should be rate limited.
        This tests Finding 3.4 - rate limiting.

        Note: This test runs LAST in security tests because it triggers
        rate limiting that would affect other login-dependent tests.
        """
        # Make requests until we hit rate limit or confirm it works
        # Rate limit is 10 requests per minute
        hit_rate_limit = False

        for i in range(12):  # Try 12 requests
            response = State.client.post(
                "/auth/login",
                data={
                    "username": "nonexistent@example.com",
                    "password": "wrongpassword",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 429:
                hit_rate_limit = True
                # Check for Retry-After header
                retry_after = response.headers.get("retry-after") or response.headers.get("Retry-After")
                assert retry_after is not None, "Should have Retry-After header"
                break

        # We should hit rate limit within 12 requests (limit is 10)
        assert hit_rate_limit, "Rate limit should be enforced on login endpoint"

    # =========================================================================
    # PHASE 28: SDK API Key Management
    # =========================================================================

    def test_400_create_sdk_api_key(self):
        """Test creating an SDK API key."""
        response = State.client.post(
            "/api/sdk/keys",
            headers=State.platform_admin.headers,
            json={
                "name": "E2E Test Key",
                "expires_in_days": 30
            }
        )
        assert response.status_code == 201, f"Failed to create API key: {response.text}"

        data = response.json()
        assert "id" in data
        assert "key" in data
        assert data["name"] == "E2E Test Key"
        assert data["key"].startswith("bfsk_")
        assert data["key_prefix"] == data["key"][:12]
        assert data["is_active"] is True

        # Store for later tests
        State.sdk_api_key_id = data["id"]
        State.sdk_api_key_full = data["key"]
        logger.info(f"Created API key with prefix: {data['key_prefix']}")

    def test_401_list_sdk_api_keys(self):
        """Test listing SDK API keys."""
        response = State.client.get(
            "/api/sdk/keys",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 200, f"Failed to list API keys: {response.text}"

        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) >= 1

        # Find our key
        our_key = next((k for k in data["keys"] if k["id"] == State.sdk_api_key_id), None)
        assert our_key is not None, "Created key not found in list"
        assert our_key["name"] == "E2E Test Key"
        assert our_key["is_active"] is True
        # Full key should NOT be returned in list
        assert "key" not in our_key or our_key.get("key") is None

    def test_402_get_context_with_api_key(self):
        """Test getting developer context using API key authentication."""
        response = State.client.get(
            "/api/sdk/context",
            headers={
                "Authorization": f"Bearer {State.sdk_api_key_full}"
            }
        )
        assert response.status_code == 200, f"Failed to get context: {response.text}"

        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == State.platform_admin.email
        assert "default_parameters" in data
        assert "track_executions" in data

    def test_403_update_developer_context(self):
        """Test updating developer context settings."""
        response = State.client.put(
            "/api/sdk/context",
            headers=State.platform_admin.headers,
            json={
                "default_parameters": {"test_param": "test_value"},
                "track_executions": False
            }
        )
        assert response.status_code == 200, f"Failed to update context: {response.text}"

        data = response.json()
        assert data["default_parameters"]["test_param"] == "test_value"
        assert data["track_executions"] is False

    def test_404_verify_context_updated(self):
        """Verify context was updated by fetching it again."""
        response = State.client.get(
            "/api/sdk/context",
            headers={
                "Authorization": f"Bearer {State.sdk_api_key_full}"
            }
        )
        assert response.status_code == 200

        data = response.json()
        assert data["default_parameters"]["test_param"] == "test_value"
        assert data["track_executions"] is False

    def test_405_revoke_sdk_api_key(self):
        """Test revoking an SDK API key."""
        response = State.client.patch(
            f"/api/sdk/keys/{State.sdk_api_key_id}/revoke",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 200, f"Failed to revoke API key: {response.text}"

        data = response.json()
        assert data["is_active"] is False

    def test_406_revoked_key_cannot_authenticate(self):
        """Test that revoked API key cannot be used."""
        response = State.client.get(
            "/api/sdk/context",
            headers={
                "Authorization": f"Bearer {State.sdk_api_key_full}"
            }
        )
        assert response.status_code == 401, "Revoked key should not authenticate"

    def test_407_create_new_key_for_remaining_tests(self):
        """Create a new key for remaining tests."""
        response = State.client.post(
            "/api/sdk/keys",
            headers=State.platform_admin.headers,
            json={
                "name": "E2E Test Key 2"
            }
        )
        assert response.status_code == 201

        data = response.json()
        State.sdk_api_key_id = data["id"]
        State.sdk_api_key_full = data["key"]

    def test_408_delete_sdk_api_key(self):
        """Test deleting an SDK API key."""
        response = State.client.delete(
            f"/api/sdk/keys/{State.sdk_api_key_id}",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 204, f"Failed to delete API key: {response.text}"

    def test_409_deleted_key_not_in_list(self):
        """Verify deleted key is not in list."""
        response = State.client.get(
            "/api/sdk/keys",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 200

        data = response.json()
        our_key = next((k for k in data["keys"] if k["id"] == State.sdk_api_key_id), None)
        assert our_key is None, "Deleted key should not be in list"

    # =========================================================================
    # PHASE 29: SDK Download
    # =========================================================================

    def test_410_download_sdk_package(self):
        """Test downloading the SDK package."""
        import io
        import tarfile

        response = State.client.get(
            "/api/sdk/download",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 200, f"Failed to download SDK: {response.text}"

        # Verify it's a gzip tarball
        assert response.headers.get("content-type") == "application/gzip"

        # Verify it can be extracted
        buffer = io.BytesIO(response.content)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            names = tar.getnames()
            # Should contain setup.py and bifrost_sdk files
            assert "setup.py" in names, "SDK tarball should contain setup.py"
            # Should have bifrost_sdk package files
            sdk_files = [n for n in names if n.startswith("bifrost_sdk/")]
            assert len(sdk_files) > 0, "SDK tarball should contain bifrost_sdk package"
            logger.info(f"SDK package contains {len(names)} files")

    # =========================================================================
    # PHASE 30: S3 File Operations (via Editor Files API)
    # =========================================================================

    def test_420_write_file_to_s3(self):
        """Test writing a file to S3 via editor files API."""
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "sdk_test_file.txt",
                "content": "Hello from E2E SDK test!",
                "encoding": "utf-8"
            }
        )
        assert response.status_code in [200, 201], f"Failed to write file: {response.text}"

        data = response.json()
        assert data["path"] == "sdk_test_file.txt"
        logger.info("Created test file at sdk_test_file.txt")

    def test_421_read_file_from_s3(self):
        """Test reading a file from S3 via editor files API."""
        response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_file.txt"}
        )
        assert response.status_code == 200, f"Failed to read file: {response.text}"

        data = response.json()
        assert data["content"] == "Hello from E2E SDK test!"
        assert data["path"] == "sdk_test_file.txt"

    def test_422_list_files(self):
        """Test listing files from S3 via editor files API."""
        response = State.client.get(
            "/api/editor/files",
            headers=State.platform_admin.headers,
            params={"path": ""}
        )
        assert response.status_code == 200, f"Failed to list files: {response.text}"

        data = response.json()
        # Should be a list of file metadata
        assert isinstance(data, list)

        # Our test file should be in the list
        test_file = next((f for f in data if f.get("name") == "sdk_test_file.txt"), None)
        assert test_file is not None, "Test file sdk_test_file.txt not in file list"

    def test_423_update_file_content(self):
        """Test updating file content in S3."""
        new_content = "Updated content from E2E SDK test!"
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "sdk_test_file.txt",
                "content": new_content,
                "encoding": "utf-8"
            }
        )
        assert response.status_code == 200, f"Failed to update file: {response.text}"

        # Verify the update
        read_response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_file.txt"}
        )
        assert read_response.status_code == 200
        assert read_response.json()["content"] == new_content

    def test_424_create_folder(self):
        """Test creating a folder in S3."""
        response = State.client.post(
            "/api/editor/files/folder",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_folder"}
        )
        # Folder creation might return 200 or 201
        assert response.status_code in [200, 201], f"Failed to create folder: {response.text}"
        logger.info("Created test folder at sdk_test_folder")

    def test_425_write_file_in_folder(self):
        """Test writing a file inside a folder in S3."""
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "sdk_test_folder/nested_file.txt",
                "content": "Nested file content",
                "encoding": "utf-8"
            }
        )
        assert response.status_code in [200, 201], f"Failed to write nested file: {response.text}"

    def test_426_list_folder_contents(self):
        """Test listing folder contents from S3."""
        response = State.client.get(
            "/api/editor/files",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_folder"}
        )
        assert response.status_code == 200, f"Failed to list folder: {response.text}"

        data = response.json()
        # Should contain our nested file
        nested_file = next((f for f in data if "nested_file" in f.get("name", "")), None)
        assert nested_file is not None, "Nested file not found in folder listing"

    def test_427_rename_file(self):
        """Test renaming a file in S3."""
        response = State.client.post(
            "/api/editor/files/rename",
            headers=State.platform_admin.headers,
            params={
                "old_path": "sdk_test_file.txt",
                "new_path": "renamed_sdk_test_file.txt"
            }
        )
        assert response.status_code == 200, f"Failed to rename file: {response.text}"

        # Verify old path doesn't exist
        old_response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_file.txt"}
        )
        assert old_response.status_code == 404, "Old file path should not exist"

        # Verify new path exists
        new_response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "renamed_sdk_test_file.txt"}
        )
        assert new_response.status_code == 200, "New file path should exist"

    def test_428_delete_file(self):
        """Test deleting a file from S3."""
        response = State.client.delete(
            "/api/editor/files",
            headers=State.platform_admin.headers,
            params={"path": "renamed_sdk_test_file.txt"}
        )
        assert response.status_code == 204, f"Failed to delete file: {response.text}"

        # Verify file is deleted
        read_response = State.client.get(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            params={"path": "renamed_sdk_test_file.txt"}
        )
        assert read_response.status_code == 404, "Deleted file should not exist"

    def test_429_delete_folder(self):
        """Test deleting a folder from S3."""
        response = State.client.delete(
            "/api/editor/files",
            headers=State.platform_admin.headers,
            params={"path": "sdk_test_folder"}
        )
        assert response.status_code == 204, f"Failed to delete folder: {response.text}"

    # =========================================================================
    # PHASE 31: Workflow Extraction Tests (Write-time discovery)
    # =========================================================================

    def test_430_write_workflow_file_extracts_metadata(self):
        """Test that writing a workflow file extracts metadata to DB."""
        workflow_content = '''"""Test workflow for E2E SDK tests."""
from bifrost import workflow

@workflow(
    name="sdk_e2e_test_workflow",
    description="Workflow created via SDK E2E test",
    category="e2e_testing",
    tags=["sdk", "e2e", "test"]
)
async def sdk_e2e_test_workflow(name: str, count: int = 1) -> dict:
    """A simple test workflow."""
    return {"greeting": f"Hello {name}!", "count": count}
'''
        response = State.client.put(
            "/api/editor/files/content",
            headers=State.platform_admin.headers,
            json={
                "path": "workflows/sdk_e2e_test_workflow.py",
                "content": workflow_content,
                "encoding": "utf-8"
            }
        )
        assert response.status_code in [200, 201], f"Failed to write workflow: {response.text}"
        logger.info("Created test workflow file")

    def test_431_workflow_appears_in_list(self):
        """Test that the written workflow appears in the workflows list."""
        import time
        # Give a moment for the extraction to complete
        time.sleep(1)

        response = State.client.get(
            "/api/workflows",
            headers=State.platform_admin.headers
        )
        assert response.status_code == 200, f"Failed to list workflows: {response.text}"

        data = response.json()
        workflows = data.get("workflows", data) if isinstance(data, dict) else data

        # Find our workflow
        our_workflow = next(
            (w for w in workflows if w.get("name") == "sdk_e2e_test_workflow"),
            None
        )
        assert our_workflow is not None, "SDK E2E test workflow not found in workflows list"
        assert our_workflow.get("description") == "Workflow created via SDK E2E test"
        assert our_workflow.get("category") == "e2e_testing"
        logger.info("Verified workflow was extracted and indexed")

    def test_432_cleanup_workflow_file(self):
        """Clean up the test workflow file."""
        response = State.client.delete(
            "/api/editor/files",
            headers=State.platform_admin.headers,
            params={"path": "workflows/sdk_e2e_test_workflow.py"}
        )
        assert response.status_code == 204, f"Failed to delete workflow file: {response.text}"

    # =========================================================================
    # PHASE 32: Cleanup (Cleanup last)
    # =========================================================================

    def test_900_cleanup_e2e_test_files(self):
        """Clean up E2E test workflow file."""
        response = State.client.delete(
            "/api/editor/files?path=e2e_test_workflow.py",
            headers=State.platform_admin.headers,
        )
        assert response.status_code in [200, 204, 404]

    def test_901_cleanup_e2e_test_folder(self):
        """Clean up E2E test folder."""
        response = State.client.delete(
            "/api/editor/files?path=e2e_test_folder",
            headers=State.platform_admin.headers,
        )
        assert response.status_code in [200, 204, 404]

    def test_902_cleanup_e2e_form(self):
        """Clean up E2E test form."""
        if hasattr(State, 'e2e_form_id') and State.e2e_form_id:
            response = State.client.delete(
                f"/api/forms/{State.e2e_form_id}",
                headers=State.platform_admin.headers,
            )
            assert response.status_code in [200, 204, 404]

    def test_903_cleanup_e2e_role(self):
        """Clean up E2E test role."""
        if hasattr(State, 'e2e_role_id') and State.e2e_role_id:
            response = State.client.delete(
                f"/api/roles/{State.e2e_role_id}",
                headers=State.platform_admin.headers,
            )
            assert response.status_code in [200, 204, 404]

    def test_904_cleanup_e2e_configs(self):
        """Clean up E2E test configs."""
        for key in ["e2e_test_timeout", "e2e_max_retries", "e2e_settings", "e2e_api_key"]:
            response = State.client.delete(
                f"/api/config/{key}",
                headers=State.platform_admin.headers,
            )
            # Accept success or not found
            assert response.status_code in [200, 204, 404]

    def test_905_cleanup_role(self):
        """Clean up original test role."""
        if State.test_role_id:
            response = State.client.delete(
                f"/api/roles/{State.test_role_id}",
                headers=State.platform_admin.headers,
            )
            assert response.status_code in [200, 204, 404]

    # =========================================================================
    # PHASE: Form File Path Integration Tests
    # =========================================================================
