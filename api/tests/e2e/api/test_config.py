"""
E2E tests for configuration management.

Tests CRUD operations for different config types (string, int, bool, json, secret).
"""

import pytest


@pytest.mark.e2e
class TestConfigCRUD:
    """Test configuration CRUD operations."""

    def test_set_global_config_string(self, e2e_client, platform_admin):
        """Platform admin creates STRING config in GLOBAL scope."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
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

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_test_timeout",
            headers=platform_admin.headers,
        )

    def test_set_int_config(self, e2e_client, platform_admin):
        """Platform admin creates INT config."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_max_retries",
                "value": "5",
                "type": "int",
                "description": "Max retries setting",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_max_retries",
            headers=platform_admin.headers,
        )

    def test_set_bool_config(self, e2e_client, platform_admin):
        """Platform admin creates BOOL config."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_feature_flag",
                "value": "true",
                "type": "bool",
                "description": "Feature flag",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_feature_flag",
            headers=platform_admin.headers,
        )

    def test_set_json_config(self, e2e_client, platform_admin):
        """Platform admin creates JSON config."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_settings",
                "value": '{"enabled": true, "level": 3}',
                "type": "json",
                "description": "JSON settings",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_settings",
            headers=platform_admin.headers,
        )

    def test_set_secret_config(self, e2e_client, platform_admin):
        """Platform admin creates SECRET config (encrypted)."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_api_key",
                "value": "secret-api-key-12345",
                "type": "secret",
                "description": "Test API key",
            },
        )
        assert response.status_code == 201, f"Create secret failed: {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_api_key",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestConfigSecurity:
    """Test configuration security features."""

    def test_list_config_masks_secrets(self, e2e_client, platform_admin):
        """Listing configs shows [SECRET] for encrypted values."""
        # Create a secret first
        e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_test_secret",
                "value": "super-secret-value",
                "type": "secret",
                "description": "Test secret",
            },
        )

        # List configs and verify masking
        response = e2e_client.get(
            "/api/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"List config failed: {response.text}"
        configs = response.json()

        # Find the secret config
        secret_config = next((c for c in configs if c["key"] == "e2e_test_secret"), None)
        assert secret_config is not None, "Secret config not found"
        assert secret_config["value"] == "[SECRET]", "Secret should be masked"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_test_secret",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestConfigAccess:
    """Test configuration access control."""

    def test_org_user_cannot_manage_config(self, e2e_client, org1_user):
        """Org user cannot create config (403)."""
        response = e2e_client.post(
            "/api/config",
            headers=org1_user.headers,
            json={
                "key": "hacker_config",
                "value": "evil",
                "type": "string",
            },
        )
        assert response.status_code == 403, \
            f"Org user should not create config: {response.status_code}"

    def test_config_list_requires_auth(self, e2e_client):
        """Config listing requires authentication."""
        response = e2e_client.get("/api/config")
        assert response.status_code == 401

    def test_delete_config(self, e2e_client, platform_admin):
        """Platform admin can delete config."""
        # Create config to delete
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_delete_test",
                "value": "to_be_deleted",
                "type": "string",
                "description": "Config to delete",
            },
        )
        assert response.status_code == 201, f"Create config failed: {response.text}"

        # Delete the config
        response = e2e_client.delete(
            "/api/config/e2e_delete_test",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204, f"Delete config failed: {response.status_code}"

        # Verify it's gone
        response = e2e_client.get(
            "/api/config",
            headers=platform_admin.headers,
        )
        configs = response.json()
        deleted_config = next((c for c in configs if c["key"] == "e2e_delete_test"), None)
        assert deleted_config is None, "Config should be deleted"

    def test_org_user_cannot_modify_config(self, e2e_client, platform_admin, org1_user):
        """Org user cannot PUT/update config (403 or 405 if PUT not supported)."""
        # Admin creates a config
        e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_modify_test",
                "value": "original",
                "type": "string",
            },
        )

        # Org user tries to update it
        response = e2e_client.put(
            "/api/config/e2e_modify_test",
            headers=org1_user.headers,
            json={"value": "hacked"},
        )
        # 403 = forbidden, 404 = route doesn't exist (PUT not implemented), 405 = method not allowed
        assert response.status_code in [403, 404, 405], \
            f"Org user should not modify config: {response.status_code}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_modify_test",
            headers=platform_admin.headers,
        )

    def test_org_user_cannot_delete_config(self, e2e_client, platform_admin, org1_user):
        """Org user cannot DELETE config (403)."""
        # Admin creates a config
        e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            json={
                "key": "e2e_nodelete_test",
                "value": "protected",
                "type": "string",
            },
        )

        # Org user tries to delete it
        response = e2e_client.delete(
            "/api/config/e2e_nodelete_test",
            headers=org1_user.headers,
        )
        assert response.status_code == 403, \
            f"Org user should not delete config: {response.status_code}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_nodelete_test",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestConfigScoping:
    """Test configuration scoping (global vs org-scoped)."""

    def test_config_with_org_scope(self, e2e_client, platform_admin, org1):
        """Platform admin can create org-scoped config."""
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            params={"scope": org1["id"]},
            json={
                "key": "e2e_org_config",
                "value": "org-specific-value",
                "type": "string",
                "description": "Org-scoped config",
            },
        )
        assert response.status_code == 201, \
            f"Create org config failed: {response.status_code} - {response.text}"

        # Cleanup
        e2e_client.delete(
            "/api/config/e2e_org_config",
            headers=platform_admin.headers,
        )


@pytest.mark.e2e
class TestConfigScopeFiltering:
    """Test config scope filtering works correctly."""

    @pytest.fixture
    def scoped_configs(self, e2e_client, platform_admin, org1, org2):
        """Create configs in different scopes for testing."""
        configs = {}

        # Create global config (no organization_id / scope=global)
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            params={"scope": "global"},
            json={
                "key": "scope_test_global",
                "value": "global-value",
                "type": "string",
                "description": "Global config for scope testing",
            },
        )
        assert response.status_code == 201, f"Failed to create global config: {response.text}"
        configs["global"] = response.json()

        # Create org1 config
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            params={"scope": org1["id"]},
            json={
                "key": "scope_test_org1",
                "value": "org1-value",
                "type": "string",
                "description": "Org1 config for scope testing",
            },
        )
        assert response.status_code == 201, f"Failed to create org1 config: {response.text}"
        configs["org1"] = response.json()

        # Create org2 config
        response = e2e_client.post(
            "/api/config",
            headers=platform_admin.headers,
            params={"scope": org2["id"]},
            json={
                "key": "scope_test_org2",
                "value": "org2-value",
                "type": "string",
                "description": "Org2 config for scope testing",
            },
        )
        assert response.status_code == 201, f"Failed to create org2 config: {response.text}"
        configs["org2"] = response.json()

        yield configs

        # Cleanup
        for key in ["scope_test_global", "scope_test_org1", "scope_test_org2"]:
            try:
                e2e_client.delete(
                    f"/api/config/{key}",
                    headers=platform_admin.headers,
                )
            except Exception:
                pass

    def test_platform_admin_no_scope_sees_all(
        self, e2e_client, platform_admin, scoped_configs
    ):
        """Platform admin with no scope sees ALL configs."""
        response = e2e_client.get(
            "/api/config",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        config_keys = [c["key"] for c in response.json()]

        assert scoped_configs["global"]["key"] in config_keys, "Should see global config"
        assert scoped_configs["org1"]["key"] in config_keys, "Should see org1 config"
        assert scoped_configs["org2"]["key"] in config_keys, "Should see org2 config"

    def test_platform_admin_scope_global_sees_only_global(
        self, e2e_client, platform_admin, scoped_configs
    ):
        """Platform admin with scope=global sees ONLY global configs."""
        response = e2e_client.get(
            "/api/config",
            params={"scope": "global"},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        config_keys = [c["key"] for c in response.json()]

        assert scoped_configs["global"]["key"] in config_keys, "Should see global config"
        assert scoped_configs["org1"]["key"] not in config_keys, "Should NOT see org1 config"
        assert scoped_configs["org2"]["key"] not in config_keys, "Should NOT see org2 config"

    def test_platform_admin_scope_org_sees_only_that_org(
        self, e2e_client, platform_admin, org1, scoped_configs
    ):
        """Platform admin with scope={org1} sees ONLY org1 configs (NOT global)."""
        response = e2e_client.get(
            "/api/config",
            params={"scope": org1["id"]},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        config_keys = [c["key"] for c in response.json()]

        # KEY ASSERTION: Global should NOT be included when filtering by org
        assert scoped_configs["global"]["key"] not in config_keys, "Should NOT see global config"
        assert scoped_configs["org1"]["key"] in config_keys, "Should see org1 config"
        assert scoped_configs["org2"]["key"] not in config_keys, "Should NOT see org2 config"
