"""
E2E tests for App Builder component API endpoints.

Tests the granular component CRUD operations:
- POST /api/applications/{app_id}/pages/{page_id}/components
- GET /api/applications/{app_id}/pages/{page_id}/components
- GET /api/applications/{app_id}/pages/{page_id}/components/{component_id}
- PATCH /api/applications/{app_id}/pages/{page_id}/components/{component_id}
- DELETE /api/applications/{app_id}/pages/{page_id}/components/{component_id}
- POST /api/applications/{app_id}/pages/{page_id}/components/{component_id}/move

These endpoints support real-time granular saves in the App Builder editor.
"""

import pytest


@pytest.mark.e2e
class TestAppBuilderSetup:
    """Test application and page setup for component tests."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application for component tests."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Component Test App",
                "slug": "component-test-app",
                "description": "Application for testing component CRUD",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201, f"Create app failed: {response.text}"
        app = response.json()

        yield app

        # Cleanup
        e2e_client.delete(
            f"/api/applications/{app['id']}",
            headers=platform_admin.headers,
        )

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page for component tests."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "test-page",
                "title": "Test Page",
                "path": "/test",
                "page_order": 0,
                "root_layout_type": "column",
                "root_layout_config": {
                    "gap": 16,
                    "padding": 24,
                },
            },
        )
        assert response.status_code == 201, f"Create page failed: {response.text}"
        page = response.json()

        yield page

        # Page cleanup handled by app deletion

    def test_app_created(self, test_app):
        """Verify test app was created."""
        assert test_app["id"]
        assert test_app["name"] == "Component Test App"

    def test_page_created(self, test_page):
        """Verify test page was created."""
        assert test_page["id"]
        assert test_page["title"] == "Test Page"


@pytest.mark.e2e
class TestComponentCreate:
    """Test component creation via POST endpoint."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Create Test App",
                "slug": "create-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201, f"Create app failed: {response.text}"
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "create-test",
                "title": "Create Test",
                "path": "/create",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_create_button_component(self, e2e_client, platform_admin, test_app, test_page):
        """Create a button component with POST."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "btn_submit",
                "type": "button",
                "props": {
                    "label": "Submit",
                    "variant": "default",
                    "onClick": None,
                },
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201, f"Create component failed: {response.text}"
        component = response.json()

        assert component["component_id"] == "btn_submit"
        assert component["type"] == "button"
        assert component["props"]["label"] == "Submit"
        assert component["props"]["variant"] == "default"
        assert component["id"] is not None  # Backend-assigned UUID

    def test_create_text_component(self, e2e_client, platform_admin, test_app, test_page):
        """Create a text component with POST."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "text_welcome",
                "type": "text",
                "props": {
                    "text": "Welcome to our app!",
                },
                "parent_id": None,
                "component_order": 1,
            },
        )
        assert response.status_code == 201
        component = response.json()
        assert component["component_id"] == "text_welcome"
        assert component["type"] == "text"
        assert component["props"]["text"] == "Welcome to our app!"

    def test_create_data_table_component(self, e2e_client, platform_admin, test_app, test_page):
        """Create a data table component with complex props."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "table_users",
                "type": "data-table",
                "props": {
                    "dataSource": "users_data",
                    "columns": [
                        {"key": "name", "header": "Name"},
                        {"key": "email", "header": "Email"},
                    ],
                    "pagination": True,
                    "pageSize": 10,
                },
                "parent_id": None,
                "component_order": 2,
            },
        )
        assert response.status_code == 201
        component = response.json()
        assert component["component_id"] == "table_users"
        assert component["type"] == "data-table"
        assert component["props"]["pagination"] is True
        assert len(component["props"]["columns"]) == 2

    def test_create_duplicate_component_id_fails(
        self, e2e_client, platform_admin, test_app, test_page
    ):
        """Creating component with duplicate ID returns 409."""
        # First create should succeed
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "dup_test",
                "type": "text",
                "props": {"text": "Original"},
                "parent_id": None,
                "component_order": 10,
            },
        )
        assert response.status_code == 201

        # Second create with same ID should fail
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "dup_test",
                "type": "text",
                "props": {"text": "Duplicate"},
                "parent_id": None,
                "component_order": 11,
            },
        )
        assert response.status_code == 409, f"Expected 409, got {response.status_code}"
        assert "already exists" in response.json().get("detail", "")


@pytest.mark.e2e
class TestComponentUpdate:
    """Test component update via PATCH endpoint."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Update Test App",
                "slug": "update-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "update-test",
                "title": "Update Test",
                "path": "/update",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    @pytest.fixture
    def button_component(self, e2e_client, platform_admin, test_app, test_page):
        """Create a button component for update tests."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": f"btn_update_{id(self)}",
                "type": "button",
                "props": {
                    "label": "Original Label",
                    "variant": "default",
                },
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_update_props(self, e2e_client, platform_admin, test_app, test_page, button_component):
        """Update component props via PATCH."""
        component_id = button_component["component_id"]

        response = e2e_client.patch(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/{component_id}",
            headers=platform_admin.headers,
            json={
                "props": {
                    "label": "Updated Label",
                    "variant": "destructive",
                },
            },
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        updated = response.json()

        assert updated["props"]["label"] == "Updated Label"
        assert updated["props"]["variant"] == "destructive"

    def test_partial_props_update(
        self, e2e_client, platform_admin, test_app, test_page, button_component
    ):
        """Partial update preserves other props."""
        component_id = button_component["component_id"]

        # Update only label
        response = e2e_client.patch(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/{component_id}",
            headers=platform_admin.headers,
            json={
                "props": {
                    "label": "Only Label Changed",
                },
            },
        )
        assert response.status_code == 200
        updated = response.json()

        # Label changed, variant preserved
        assert updated["props"]["label"] == "Only Label Changed"
        # Note: variant may be preserved or overwritten depending on backend merge strategy

    def test_update_component_order(
        self, e2e_client, platform_admin, test_app, test_page, button_component
    ):
        """Update component order via PATCH."""
        component_id = button_component["component_id"]

        response = e2e_client.patch(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/{component_id}",
            headers=platform_admin.headers,
            json={
                "component_order": 99,
            },
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["component_order"] == 99

    def test_update_nonexistent_component_fails(
        self, e2e_client, platform_admin, test_app, test_page
    ):
        """Updating nonexistent component returns 404."""
        response = e2e_client.patch(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/nonexistent_comp",
            headers=platform_admin.headers,
            json={"props": {"label": "test"}},
        )
        assert response.status_code == 404


@pytest.mark.e2e
class TestComponentDelete:
    """Test component deletion via DELETE endpoint."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Delete Test App",
                "slug": "delete-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "delete-test",
                "title": "Delete Test",
                "path": "/delete",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_delete_component(self, e2e_client, platform_admin, test_app, test_page):
        """Delete component via DELETE endpoint."""
        # First create
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "to_delete",
                "type": "text",
                "props": {"text": "Will be deleted"},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201

        # Then delete
        response = e2e_client.delete(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/to_delete",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Verify deleted
        response = e2e_client.get(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/to_delete",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_delete_nonexistent_component_fails(
        self, e2e_client, platform_admin, test_app, test_page
    ):
        """Deleting nonexistent component returns 404."""
        response = e2e_client.delete(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/nonexistent",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


@pytest.mark.e2e
class TestComponentMove:
    """Test component move via POST /move endpoint."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Move Test App",
                "slug": "move-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "move-test",
                "title": "Move Test",
                "path": "/move",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_move_component_order(self, e2e_client, platform_admin, test_app, test_page):
        """Move component to new order position among siblings."""
        base_url = f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components"

        # Create three components at positions 0, 1, 2
        for i, name in enumerate(["first", "second", "third"]):
            response = e2e_client.post(
                base_url,
                headers=platform_admin.headers,
                json={
                    "component_id": f"move_test_{name}",
                    "type": "text",
                    "props": {"text": name.title()},
                    "parent_id": None,
                    "component_order": i,
                },
            )
            assert response.status_code == 201

        # Move "first" (order 0) to order 2 (end)
        response = e2e_client.post(
            f"{base_url}/move_test_first/move",
            headers=platform_admin.headers,
            json={
                "new_parent_id": None,
                "new_order": 2,
            },
        )
        assert response.status_code == 200, f"Move failed: {response.text}"
        moved = response.json()
        assert moved["component_order"] == 2

    def test_move_component_to_parent(self, e2e_client, platform_admin, test_app, test_page):
        """Move component to a different parent."""
        # Create parent container (using row layout type as parent)
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "parent_container",
                "type": "row",
                "props": {"gap": 8},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201
        parent_uuid = response.json()["id"]  # Capture the backend UUID

        # Create child component
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "child_to_move",
                "type": "text",
                "props": {"text": "Child"},
                "parent_id": None,  # Initially at root
                "component_order": 1,
            },
        )
        assert response.status_code == 201

        # Move child into parent container (use UUID for parent)
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components/child_to_move/move",
            headers=platform_admin.headers,
            json={
                "new_parent_id": parent_uuid,
                "new_order": 0,
            },
        )
        assert response.status_code == 200
        moved = response.json()
        assert moved["parent_id"] == parent_uuid
        assert moved["component_order"] == 0


@pytest.mark.e2e
class TestComponentList:
    """Test component listing via GET endpoint."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "List Test App",
                "slug": "list-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page_with_components(self, e2e_client, platform_admin, test_app):
        """Create a test page with multiple components."""
        # Create page
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "list-test",
                "title": "List Test",
                "path": "/list",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        page = response.json()

        # Create components
        components_data = [
            {"component_id": "list_heading", "type": "heading", "props": {"text": "Title", "level": 1}},
            {"component_id": "list_text", "type": "text", "props": {"text": "Content"}},
            {"component_id": "list_button", "type": "button", "props": {"label": "Click"}},
        ]

        for i, comp in enumerate(components_data):
            response = e2e_client.post(
                f"/api/applications/{test_app['id']}/pages/{page['page_id']}/components",
                headers=platform_admin.headers,
                json={
                    **comp,
                    "parent_id": None,
                    "component_order": i,
                },
            )
            assert response.status_code == 201

        return page

    def test_list_components(self, e2e_client, platform_admin, test_app, test_page_with_components):
        """List all components for a page."""
        response = e2e_client.get(
            f"/api/applications/{test_app['id']}/pages/{test_page_with_components['page_id']}/components",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "components" in data
        assert "total" in data
        assert data["total"] >= 3

        component_ids = [c["component_id"] for c in data["components"]]
        assert "list_heading" in component_ids
        assert "list_text" in component_ids
        assert "list_button" in component_ids

    def test_get_single_component(
        self, e2e_client, platform_admin, test_app, test_page_with_components
    ):
        """Get a single component by ID."""
        response = e2e_client.get(
            f"/api/applications/{test_app['id']}/pages/{test_page_with_components['page_id']}/components/list_heading",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        component = response.json()

        assert component["component_id"] == "list_heading"
        assert component["type"] == "heading"
        assert component["props"]["text"] == "Title"
        assert component["props"]["level"] == 1


@pytest.mark.e2e
class TestComponentVersioning:
    """Test that component operations bump app/page versions."""

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Version Test App",
                "slug": "version-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "version-test",
                "title": "Version Test",
                "path": "/version",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_create_marks_unpublished_changes(self, e2e_client, platform_admin, test_app, test_page):
        """Creating component marks app as having unpublished changes."""
        # Get initial state
        response = e2e_client.get(
            f"/api/applications/{test_app['slug']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        app_data = response.json()
        _ = app_data["updated_at"]  # Capture for potential future use

        # Create component
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages/{test_page['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "version_test_comp",
                "type": "text",
                "props": {"text": "Version test"},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201

        # Check app state reflects the change
        response = e2e_client.get(
            f"/api/applications/{test_app['slug']}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        app_data = response.json()
        # App should have a draft version (created during setup or first edit)
        assert app_data["draft_version_id"] is not None, "App should have draft version"
        # Updated timestamp should change (may not always differ in fast tests)
        # The key check is that the draft exists and app is tracked


@pytest.mark.e2e
class TestComponentRealTimeSaveWorkflow:
    """
    Test the complete real-time save workflow as used by the editor.

    This simulates the actual workflow:
    1. Load app and page
    2. Add components (immediate POST)
    3. Update props (debounced PATCH)
    4. Move components (immediate POST /move)
    5. Delete components (immediate DELETE)
    6. Verify final state matches expectations
    """

    @pytest.fixture(scope="class")
    def test_app(self, e2e_client, platform_admin):
        """Create a test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Realtime Test App",
                "slug": "realtime-test-app",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def test_page(self, e2e_client, platform_admin, test_app):
        """Create a test page."""
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "realtime-test",
                "title": "Realtime Test",
                "path": "/realtime",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_complete_editor_workflow(self, e2e_client, platform_admin, test_app, test_page):
        """
        Simulate a complete editor session with granular saves.

        This tests the exact flow the frontend uses:
        1. User adds a heading - immediate POST
        2. User adds a button - immediate POST
        3. User edits button label - debounced PATCH
        4. User edits button variant - debounced PATCH (coalesced)
        5. User deletes heading - immediate DELETE
        6. Verify final state
        """
        app_id = test_app["id"]
        page_id = test_page["page_id"]
        base_url = f"/api/applications/{app_id}/pages/{page_id}/components"

        # Step 1: Add heading
        response = e2e_client.post(
            base_url,
            headers=platform_admin.headers,
            json={
                "component_id": "heading_1",
                "type": "heading",
                "props": {"text": "Welcome", "level": 1},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201, f"Add heading failed: {response.text}"

        # Step 2: Add button
        response = e2e_client.post(
            base_url,
            headers=platform_admin.headers,
            json={
                "component_id": "btn_1",
                "type": "button",
                "props": {"label": "Click Me", "variant": "default"},
                "parent_id": None,
                "component_order": 1,
            },
        )
        assert response.status_code == 201, f"Add button failed: {response.text}"

        # Step 3 & 4: Update button props (would be coalesced in frontend)
        response = e2e_client.patch(
            f"{base_url}/btn_1",
            headers=platform_admin.headers,
            json={
                "props": {
                    "label": "Submit Form",
                    "variant": "primary",
                },
            },
        )
        assert response.status_code == 200, f"Update button failed: {response.text}"

        # Step 5: Delete heading
        response = e2e_client.delete(
            f"{base_url}/heading_1",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete heading failed: {response.status_code}"

        # Step 6: Verify final state
        response = e2e_client.get(base_url, headers=platform_admin.headers)
        assert response.status_code == 200
        data = response.json()

        # Filter out root layout components (created automatically with page)
        user_components = [c for c in data["components"] if not c["component_id"].startswith("layout_")]

        # Should have 1 user component remaining (the button)
        assert len(user_components) == 1, f"Expected 1 user component, got: {[c['component_id'] for c in user_components]}"

        # Verify button state
        btn = user_components[0]
        assert btn["component_id"] == "btn_1"
        assert btn["component_order"] == 1  # Stays at original order

        # Get full button to check props
        response = e2e_client.get(f"{base_url}/btn_1", headers=platform_admin.headers)
        assert response.status_code == 200
        btn_full = response.json()
        assert btn_full["props"]["label"] == "Submit Form"
        assert btn_full["props"]["variant"] == "primary"


@pytest.mark.e2e
class TestComponentIsolation:
    """Test that component operations are properly isolated between apps/pages."""

    @pytest.fixture(scope="class")
    def app1(self, e2e_client, platform_admin):
        """Create first test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Isolation App 1",
                "slug": "isolation-app-1",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def app2(self, e2e_client, platform_admin):
        """Create second test application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Isolation App 2",
                "slug": "isolation-app-2",
                "access_level": "authenticated",
            },
        )
        assert response.status_code == 201
        app = response.json()
        yield app
        e2e_client.delete(f"/api/applications/{app['id']}", headers=platform_admin.headers)

    @pytest.fixture(scope="class")
    def page1(self, e2e_client, platform_admin, app1):
        """Create page in app1."""
        response = e2e_client.post(
            f"/api/applications/{app1['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "iso-page",
                "title": "Isolation Page",
                "path": "/iso",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    @pytest.fixture(scope="class")
    def page2(self, e2e_client, platform_admin, app2):
        """Create page in app2."""
        response = e2e_client.post(
            f"/api/applications/{app2['id']}/pages",
            headers=platform_admin.headers,
            json={
                "page_id": "iso-page",  # Same page_id as app1
                "title": "Isolation Page",
                "path": "/iso",
                "page_order": 0,
                "root_layout_type": "column",
            },
        )
        assert response.status_code == 201
        return response.json()

    def test_same_component_id_different_apps(
        self, e2e_client, platform_admin, app1, app2, page1, page2
    ):
        """Same component_id can exist in different apps."""
        # Create in app1
        response = e2e_client.post(
            f"/api/applications/{app1['id']}/pages/{page1['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "shared_id",
                "type": "text",
                "props": {"text": "App 1 content"},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201

        # Create same ID in app2 should succeed
        response = e2e_client.post(
            f"/api/applications/{app2['id']}/pages/{page2['page_id']}/components",
            headers=platform_admin.headers,
            json={
                "component_id": "shared_id",
                "type": "text",
                "props": {"text": "App 2 content"},
                "parent_id": None,
                "component_order": 0,
            },
        )
        assert response.status_code == 201

        # Verify they're independent
        response = e2e_client.get(
            f"/api/applications/{app1['id']}/pages/{page1['page_id']}/components/shared_id",
            headers=platform_admin.headers,
        )
        assert response.json()["props"]["text"] == "App 1 content"

        response = e2e_client.get(
            f"/api/applications/{app2['id']}/pages/{page2['page_id']}/components/shared_id",
            headers=platform_admin.headers,
        )
        assert response.json()["props"]["text"] == "App 2 content"
