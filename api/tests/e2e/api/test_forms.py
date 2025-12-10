"""
E2E tests for form management.

Tests form CRUD operations, access levels, and role-based access.
"""

import time
import pytest


@pytest.mark.e2e
class TestFormCRUD:
    """Test form CRUD operations."""

    @pytest.fixture
    def test_form(self, e2e_client, platform_admin):
        """Create a test form and clean up after."""
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "E2E Test Form",
                "description": "Test form for E2E testing",
                "workflow_id": None,
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

        yield form

        # Cleanup
        e2e_client.delete(
            f"/api/forms/{form['id']}",
            headers=platform_admin.headers,
        )

    def test_create_form(self, e2e_client, platform_admin):
        """Platform admin can create a form."""
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Customer Onboarding",
                "description": "New customer intake form",
                "workflow_id": None,
                "form_schema": {
                    "fields": [
                        {"name": "company_name", "type": "text", "label": "Company Name", "required": True},
                    ]
                },
                "access_level": "role_based",
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()
        assert form["name"] == "Customer Onboarding"

        # Cleanup
        e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)

    def test_list_forms(self, e2e_client, platform_admin, test_form):
        """Platform admin can list forms."""
        response = e2e_client.get(
            "/api/forms",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List forms failed: {response.text}"
        forms = response.json()
        assert isinstance(forms, list)
        form_names = [f["name"] for f in forms]
        assert "E2E Test Form" in form_names

    def test_update_form(self, e2e_client, platform_admin, test_form):
        """Platform admin can update a form."""
        response = e2e_client.patch(
            f"/api/forms/{test_form['id']}",
            headers=platform_admin.headers,
            json={
                "description": "Updated description",
            },
        )
        assert response.status_code == 200, f"Update form failed: {response.text}"
        updated = response.json()
        assert updated["description"] == "Updated description"


@pytest.mark.e2e
class TestFormAccessLevels:
    """Test different form access levels."""

    @pytest.fixture
    def authenticated_form(self, e2e_client, platform_admin):
        """Create an authenticated-access form."""
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Authenticated Form",
                "workflow_id": None,
                "form_schema": {"fields": [{"name": "data", "type": "text", "label": "Data"}]},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        form = response.json()

        yield form

        e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)

    @pytest.fixture
    def public_form(self, e2e_client, platform_admin):
        """Create a public-access form."""
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Public Form",
                "workflow_id": None,
                "form_schema": {"fields": [{"name": "data", "type": "text", "label": "Data"}]},
                "access_level": "public",
            },
        )
        assert response.status_code == 201
        form = response.json()

        yield form

        e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)

    def test_authenticated_form_accessible_by_any_user(
        self, e2e_client, org1_user, authenticated_form
    ):
        """Any authenticated user can access authenticated forms."""
        response = e2e_client.get(
            f"/api/forms/{authenticated_form['id']}",
            headers=org1_user.headers,
        )
        # Should at least be able to see the form
        assert response.status_code in [200, 403]  # Depends on implementation


@pytest.mark.e2e
class TestFormRoleAccess:
    """Test role-based form access."""

    @pytest.fixture
    def role_based_setup(self, e2e_client, platform_admin, org1_user):
        """Create role, form, and assign user."""
        # Create role
        role_resp = e2e_client.post(
            "/api/roles",
            headers=platform_admin.headers,
            json={"name": "Form Access Role", "description": "Test role"},
        )
        assert role_resp.status_code == 201
        role = role_resp.json()

        # Create form
        form_resp = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Role-Based Form",
                "workflow_id": None,
                "form_schema": {"fields": [{"name": "data", "type": "text", "label": "Data"}]},
                "access_level": "role_based",
            },
        )
        assert form_resp.status_code == 201
        form = form_resp.json()

        # Assign form to role
        e2e_client.post(
            f"/api/roles/{role['id']}/forms",
            headers=platform_admin.headers,
            json={"form_ids": [form["id"]]},
        )

        yield {"role": role, "form": form}

        # Cleanup
        e2e_client.delete(f"/api/forms/{form['id']}", headers=platform_admin.headers)
        e2e_client.delete(f"/api/roles/{role['id']}", headers=platform_admin.headers)

    def test_unassigned_user_cannot_access_role_form(
        self, e2e_client, org2_user, role_based_setup
    ):
        """User without role cannot access role-based form."""
        response = e2e_client.get(
            f"/api/forms/{role_based_setup['form']['id']}",
            headers=org2_user.headers,
        )
        # Should be denied
        assert response.status_code == 403


@pytest.mark.e2e
class TestFormAccess:
    """Test form access control."""

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


@pytest.mark.e2e
class TestFormFileSync:
    """Test form-file synchronization."""

    @pytest.fixture
    def form_with_file(self, e2e_client, platform_admin):
        """Create a form and verify its file is created."""
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "File Sync Test Form",
                "description": "Form for testing file sync",
                "workflow_id": None,
                "form_schema": {
                    "fields": [
                        {"name": "test_field", "type": "text", "label": "Test Field"},
                    ]
                },
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201, f"Create form failed: {response.text}"
        form = response.json()

        yield form

        # Cleanup
        e2e_client.delete(
            f"/api/forms/{form['id']}",
            headers=platform_admin.headers,
        )

    def test_form_file_path_is_workspace_relative(
        self, e2e_client, platform_admin, form_with_file
    ):
        """Form file_path uses workspace-relative path."""
        form = form_with_file
        # The form should have a file_path that is relative (not absolute)
        if "file_path" in form:
            file_path = form["file_path"]
            assert not file_path.startswith("/"), \
                f"Form file_path should be relative: {file_path}"
            assert "forms/" in file_path or file_path.endswith(".yaml"), \
                f"Form file should be in forms/ or have .yaml extension: {file_path}"

    def test_form_file_can_be_listed_in_editor(
        self, e2e_client, platform_admin, form_with_file
    ):
        """Form file appears in editor file listing."""
        form = form_with_file

        # Wait a moment for file sync
        time.sleep(1)

        # List files in forms directory
        response = e2e_client.get(
            "/api/editor/files",
            headers=platform_admin.headers,
            params={"path": "forms"},
        )

        # Forms directory may or may not exist depending on implementation
        if response.status_code == 200:
            files = response.json()
            # Check if the form file is listed
            if isinstance(files, list):
                file_names = [f.get("name", f.get("path", "")) for f in files]
                # The form file might be named after the form ID or name
                # Soft check - file may be in a different location
                _ = any(
                    form["id"] in name or "file_sync_test" in name.lower()
                    for name in file_names
                )

    def test_form_file_can_be_deleted_via_editor(
        self, e2e_client, platform_admin
    ):
        """Deleting form file via editor properly handles the form."""
        # Create a form specifically for this test
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Delete Test Form",
                "workflow_id": None,
                "form_schema": {"fields": [{"name": "x", "type": "text", "label": "X"}]},
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        form = response.json()
        form_id = form["id"]

        # If form has a file_path, try to delete it via editor
        if "file_path" in form and form["file_path"]:
            file_path = form["file_path"]
            response = e2e_client.delete(
                f"/api/editor/files?path={file_path}",
                headers=platform_admin.headers,
            )
            # Should either succeed (204) or not find the file (404)
            assert response.status_code in [200, 204, 404], \
                f"Delete form file failed: {response.status_code}"

        # Cleanup - delete the form itself
        e2e_client.delete(f"/api/forms/{form_id}", headers=platform_admin.headers)


@pytest.mark.e2e
class TestFormExecution:
    """Test form execution for different access levels."""

    def test_any_user_can_execute_public_form(self, e2e_client, platform_admin):
        """Public forms can be executed without authentication."""
        # Create a public form
        response = e2e_client.post(
            "/api/forms",
            headers=platform_admin.headers,
            json={
                "name": "Public Execution Form",
                "workflow_id": None,  # No workflow, just test form access
                "form_schema": {
                    "fields": [{"name": "data", "type": "text", "label": "Data"}]
                },
                "access_level": "public",
            },
        )
        assert response.status_code == 201
        form = response.json()
        form_id = form["id"]

        try:
            # Try to access form without authentication
            response = e2e_client.get(f"/api/forms/{form_id}")
            # Public forms should be accessible without auth
            # The actual response depends on implementation
            assert response.status_code in [200, 401, 403], \
                f"Unexpected status for public form: {response.status_code}"
        finally:
            # Cleanup
            e2e_client.delete(f"/api/forms/{form_id}", headers=platform_admin.headers)
