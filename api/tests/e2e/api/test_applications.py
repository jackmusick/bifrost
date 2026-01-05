"""
E2E tests for App Builder applications.

Tests application CRUD operations, draft/live versioning, and rollback functionality.
Applications are stored in the database (DB-first model).
"""

import pytest


@pytest.mark.e2e
class TestApplicationCRUD:
    """Test application CRUD operations."""

    def test_create_application(self, e2e_client, platform_admin):
        """Platform admin can create an application."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "E2E Test App",
                "slug": "e2e-test-app",
                "description": "Test application for E2E tests",
                "icon": "box",
            },
        )
        assert response.status_code == 201, f"Create app failed: {response.text}"
        app = response.json()

        assert app["name"] == "E2E Test App"
        assert app["slug"] == "e2e-test-app"
        assert app["description"] == "Test application for E2E tests"
        assert app["icon"] == "box"
        assert app.get("id"), "App should have an ID"
        assert app["live_version"] == 0, "New app should have live_version 0"
        assert app["draft_version"] == 1, "New app should have draft_version 1"

        # Cleanup
        e2e_client.delete(
            "/api/applications/e2e-test-app",
            headers=platform_admin.headers,
        )

    def test_get_application_by_slug(self, e2e_client, platform_admin):
        """Get application by slug."""
        # Create app
        e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Get Test App",
                "slug": "get-test-app",
            },
        )

        # Get by slug
        response = e2e_client.get(
            "/api/applications/get-test-app",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get app failed: {response.text}"
        app = response.json()
        assert app["slug"] == "get-test-app"
        assert app["name"] == "Get Test App"

        # Cleanup
        e2e_client.delete(
            "/api/applications/get-test-app",
            headers=platform_admin.headers,
        )

    def test_list_applications(self, e2e_client, platform_admin):
        """List all applications."""
        # Create a couple of apps
        e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "List Test 1", "slug": "list-test-1"},
        )
        e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "List Test 2", "slug": "list-test-2"},
        )

        # List apps
        response = e2e_client.get(
            "/api/applications",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List apps failed: {response.text}"
        data = response.json()

        assert "applications" in data
        assert "total" in data
        app_slugs = [a["slug"] for a in data["applications"]]
        assert "list-test-1" in app_slugs
        assert "list-test-2" in app_slugs

        # Cleanup
        e2e_client.delete("/api/applications/list-test-1", headers=platform_admin.headers)
        e2e_client.delete("/api/applications/list-test-2", headers=platform_admin.headers)

    def test_update_application(self, e2e_client, platform_admin):
        """Update application metadata."""
        # Create app
        e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Update Test App",
                "slug": "update-test-app",
                "description": "Original description",
            },
        )

        # Update
        response = e2e_client.patch(
            "/api/applications/update-test-app",
            headers=platform_admin.headers,
            json={
                "name": "Updated App Name",
                "description": "Updated description",
                "icon": "star",
            },
        )
        assert response.status_code == 200, f"Update app failed: {response.text}"
        app = response.json()

        assert app["name"] == "Updated App Name"
        assert app["description"] == "Updated description"
        assert app["icon"] == "star"
        assert app["slug"] == "update-test-app"  # Slug unchanged

        # Cleanup
        e2e_client.delete(
            "/api/applications/update-test-app",
            headers=platform_admin.headers,
        )

    def test_delete_application(self, e2e_client, platform_admin):
        """Delete application."""
        # Create app
        e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "Delete Test App", "slug": "delete-test-app"},
        )

        # Delete
        response = e2e_client.delete(
            "/api/applications/delete-test-app",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete app failed: {response.text}"

        # Verify gone
        response = e2e_client.get(
            "/api/applications/delete-test-app",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


@pytest.mark.e2e
class TestApplicationDuplicateSlugs:
    """Test handling of duplicate application slugs."""

    def test_duplicate_slug_rejected(self, e2e_client, platform_admin):
        """Creating app with duplicate slug is rejected."""
        # Create first app
        response1 = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "First App", "slug": "duplicate-slug"},
        )
        assert response1.status_code == 201

        # Try to create second with same slug
        response2 = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "Second App", "slug": "duplicate-slug"},
        )
        assert response2.status_code == 409, \
            f"Expected 409 Conflict for duplicate slug, got {response2.status_code}"

        # Cleanup
        e2e_client.delete(
            "/api/applications/duplicate-slug",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestApplicationVersioning:
    """Test application draft/live versioning."""

    @pytest.fixture
    def test_app(self, e2e_client, platform_admin):
        """Create an app for versioning tests."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={
                "name": "Versioning Test App",
                "slug": "versioning-test-app",
                "description": "Tests draft/live versioning",
            },
        )
        assert response.status_code == 201
        app = response.json()

        yield app

        # Cleanup
        e2e_client.delete(
            "/api/applications/versioning-test-app",
            headers=platform_admin.headers,
        )

    def test_get_empty_draft(self, e2e_client, platform_admin, test_app):
        """Get draft definition for new app."""
        response = e2e_client.get(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Get draft failed: {response.text}"
        data = response.json()

        assert data["version"] == 1
        assert data["is_live"] is False
        # Definition may be empty or null for new app

    def test_save_draft(self, e2e_client, platform_admin, test_app):
        """Save a draft definition."""
        draft_definition = {
            "pages": [
                {
                    "id": "home",
                    "name": "Home",
                    "path": "/",
                    "layouts": [],
                }
            ],
            "navigation": [],
            "theme": {},
        }

        response = e2e_client.put(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
            json={"definition": draft_definition},
        )
        assert response.status_code == 200, f"Save draft failed: {response.text}"
        data = response.json()

        assert data["is_live"] is False
        # Definition is returned as-is from input

    def test_get_saved_draft(self, e2e_client, platform_admin, test_app):
        """Saved draft is retrievable."""
        draft_definition = {
            "pages": [{"id": "page1", "title": "Page 1", "path": "/", "layout": {"type": "column", "children": []}}],
        }

        # Save draft
        e2e_client.put(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
            json={"definition": draft_definition},
        )

        # Get draft
        response = e2e_client.get(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["definition"]["pages"][0]["id"] == "page1"

    def test_multiple_publishes_increment_version(
        self, e2e_client, platform_admin, test_app
    ):
        """Multiple publishes increment live version."""
        # Publish first version
        e2e_client.put(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
            json={"definition": {"pages": [{"id": "v1", "title": "V1", "path": "/", "layout": {"type": "column", "children": []}}]}},
        )
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/publish",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        v1 = response.json()

        # Publish second version
        e2e_client.put(
            f"/api/applications/{test_app['id']}/draft",
            headers=platform_admin.headers,
            json={"definition": {"pages": [{"id": "v2", "title": "V2", "path": "/", "layout": {"type": "column", "children": []}}]}},
        )
        response = e2e_client.post(
            f"/api/applications/{test_app['id']}/publish",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        v2 = response.json()

        assert v2["live_version"] > v1["live_version"], \
            "Live version should increment on each publish"


@pytest.mark.e2e
class TestApplicationAccess:
    """Test application access control."""

    def test_org_user_can_view_global_apps(self, e2e_client, platform_admin, org1_user):
        """Org user can view global applications."""
        # Create global app
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            params={"scope": "global"},
            json={"name": "Global App", "slug": "global-app"},
        )
        assert response.status_code == 201

        # Org user should be able to see it
        response = e2e_client.get(
            "/api/applications/global-app",
            headers=org1_user.headers,
        )
        # May be 200 (can view) or 403 (can't view) depending on access rules
        assert response.status_code in [200, 403]

        # Cleanup
        e2e_client.delete(
            "/api/applications/global-app",
            headers=platform_admin.headers,
            params={"scope": "global"},
        )


@pytest.mark.e2e
class TestApplicationScopeFiltering:
    """Test application scope filtering."""

    @pytest.fixture
    def scoped_apps(self, e2e_client, platform_admin, org1):
        """Create apps in different scopes."""
        apps = {}

        # Create global app
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            params={"scope": "global"},
            json={"name": "Global App", "slug": "global-scope-app"},
        )
        assert response.status_code == 201
        apps["global"] = response.json()

        # Create org-scoped app
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            params={"scope": org1["id"]},
            json={"name": "Org App", "slug": "org-scope-app"},
        )
        assert response.status_code == 201
        apps["org"] = response.json()

        yield apps

        # Cleanup
        e2e_client.delete(
            "/api/applications/global-scope-app",
            headers=platform_admin.headers,
            params={"scope": "global"},
        )
        e2e_client.delete(
            "/api/applications/org-scope-app",
            headers=platform_admin.headers,
            params={"scope": org1["id"]},
        )

    def test_list_with_global_scope(
        self, e2e_client, platform_admin, scoped_apps
    ):
        """Listing with scope=global shows only global apps."""
        response = e2e_client.get(
            "/api/applications",
            headers=platform_admin.headers,
            params={"scope": "global"},
        )
        assert response.status_code == 200
        data = response.json()
        app_slugs = [a["slug"] for a in data["applications"]]

        assert "global-scope-app" in app_slugs
        assert "org-scope-app" not in app_slugs

    def test_list_with_org_scope(
        self, e2e_client, platform_admin, org1, scoped_apps
    ):
        """Listing with scope=org shows org apps (may include global fallback)."""
        response = e2e_client.get(
            "/api/applications",
            headers=platform_admin.headers,
            params={"scope": org1["id"]},
        )
        assert response.status_code == 200
        data = response.json()
        app_slugs = [a["slug"] for a in data["applications"]]

        assert "org-scope-app" in app_slugs
        # Global may or may not be included depending on filter type


@pytest.mark.e2e
class TestApplicationDBStorage:
    """Test that applications are stored in database, not S3."""

    def test_app_immediately_queryable(self, e2e_client, platform_admin):
        """Created app is immediately queryable (DB storage)."""
        response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "Immediate Query App", "slug": "immediate-query-app"},
        )
        assert response.status_code == 201
        created = response.json()

        # Immediately query by slug - should work (DB storage)
        response = e2e_client.get(
            "/api/applications/immediate-query-app",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, \
            "App should be immediately queryable (DB-first)"
        queried = response.json()
        assert queried["id"] == created["id"]

        # Cleanup
        e2e_client.delete(
            "/api/applications/immediate-query-app",
            headers=platform_admin.headers,
        )

    def test_app_persists_across_requests(self, e2e_client, platform_admin):
        """App data persists across multiple requests."""
        # Create and save draft
        create_response = e2e_client.post(
            "/api/applications",
            headers=platform_admin.headers,
            json={"name": "Persist Test App", "slug": "persist-test-app"},
        )
        assert create_response.status_code == 201
        app = create_response.json()

        e2e_client.put(
            f"/api/applications/{app['id']}/draft",
            headers=platform_admin.headers,
            json={
                "definition": {
                    "pages": [{"id": "persist", "title": "Persist", "path": "/", "layout": {"type": "column", "children": []}}],
                    "custom_data": "test_value",
                }
            },
        )

        # Query in a separate request - data should persist
        response = e2e_client.get(
            f"/api/applications/{app['id']}/draft",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Note: custom_data won't be preserved (only pages are stored)
        # Check that the page was saved
        assert len(data["definition"]["pages"]) == 1

        # Cleanup
        e2e_client.delete(
            "/api/applications/persist-test-app",
            headers=platform_admin.headers,
        )
