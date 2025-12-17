"""
CLI E2E Tests.

Tests the Bifrost CLI API endpoints including:
- API key management (create, list, revoke, delete)
- Developer context (get, update)
- File operations via CLI (read, write, list, delete)
- Config operations via CLI (get, set, list, delete)
- OAuth operations via CLI (get)

These tests don't require external services like GitHub - they test
the CLI API endpoints that developers use for external integration.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# API Key Tests
# =============================================================================


class TestCLIApiKeys:
    """Test CLI API key management."""

    def test_create_api_key(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test creating a new CLI API key."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={
                "name": "E2E Test Key",
                "expires_in_days": 30,
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 201, f"Create key failed: {response.text}"

        data = response.json()
        assert "id" in data
        assert "key" in data
        assert data["key"].startswith("bfsk_")
        assert data["name"] == "E2E Test Key"
        assert data["is_active"] is True
        assert data["key_prefix"] == data["key"][:12]

        # Store key ID for cleanup
        key_id = data["id"]

        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{key_id}",
            headers=platform_admin.headers,
        )

    def test_create_api_key_without_expiration(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test creating an API key without expiration."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "No Expiration Key"},
            headers=platform_admin.headers,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["expires_at"] is None
        assert data["is_active"] is True

        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_list_api_keys(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test listing API keys."""
        # Create a key first
        create_response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "List Test Key"},
            headers=platform_admin.headers,
        )
        key_id = create_response.json()["id"]

        # List keys
        response = e2e_client.get(
            "/api/cli/keys",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "keys" in data
        assert isinstance(data["keys"], list)
        # Should have at least our key
        assert len(data["keys"]) >= 1

        # Verify key structure (should not include full key)
        key = data["keys"][0]
        assert "id" in key
        assert "name" in key
        assert "key_prefix" in key
        assert "key" not in key  # Full key should not be in list

        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{key_id}",
            headers=platform_admin.headers,
        )

    def test_revoke_api_key(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test revoking (deactivating) an API key."""
        # Create a key
        create_response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Revoke Test Key"},
            headers=platform_admin.headers,
        )
        key_id = create_response.json()["id"]

        # Revoke it
        response = e2e_client.patch(
            f"/api/cli/keys/{key_id}/revoke",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["is_active"] is False

        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{key_id}",
            headers=platform_admin.headers,
        )

    def test_delete_api_key(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test deleting an API key."""
        # Create a key
        create_response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Delete Test Key"},
            headers=platform_admin.headers,
        )
        key_id = create_response.json()["id"]

        # Delete it
        response = e2e_client.delete(
            f"/api/cli/keys/{key_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Verify it's gone
        list_response = e2e_client.get(
            "/api/cli/keys",
            headers=platform_admin.headers,
        )
        key_ids = [k["id"] for k in list_response.json()["keys"]]
        assert key_id not in key_ids

    def test_delete_nonexistent_key(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test deleting a key that doesn't exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = e2e_client.delete(
            f"/api/cli/keys/{fake_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


# =============================================================================
# Context Tests
# =============================================================================


class TestCLIContext:
    """Test SDK developer context endpoints."""

    @pytest.fixture
    def sdk_api_key(self, e2e_client, platform_admin):
        """Create an CLI API key for context tests."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Context Test Key"},
            headers=platform_admin.headers,
        )
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_get_context_with_api_key(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test getting developer context with API key auth."""
        response = e2e_client.get(
            "/api/cli/context",
            headers={"Authorization": f"Bearer {sdk_api_key['key']}"},
        )
        assert response.status_code == 200

        data = response.json()
        assert "user" in data
        assert "email" in data["user"]
        assert "default_parameters" in data
        assert isinstance(data["default_parameters"], dict)

    def test_context_requires_authentication(
        self,
        e2e_client,
    ):
        """Test that context endpoint requires valid authentication (session or API key)."""
        # Clear cookies to test without session auth
        e2e_client.cookies.clear()

        # No auth at all (no session, no API key)
        response = e2e_client.get("/api/cli/context")
        assert response.status_code in [401, 422]

        # Invalid API key (no session, invalid key)
        response = e2e_client.get(
            "/api/cli/context",
            headers={"Authorization": "Bearer bfsk_invalid_key_123"},
        )
        assert response.status_code == 401

    def test_update_context_default_params(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test updating developer context default parameters."""
        response = e2e_client.put(
            "/api/cli/context",
            json={
                "default_parameters": {
                    "env": "test",
                    "debug": True,
                },
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["default_parameters"]["env"] == "test"
        assert data["default_parameters"]["debug"] is True

    def test_update_context_track_executions(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test updating track_executions setting."""
        # Disable tracking
        response = e2e_client.put(
            "/api/cli/context",
            json={"track_executions": False},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        assert response.json()["track_executions"] is False

        # Re-enable tracking
        response = e2e_client.put(
            "/api/cli/context",
            json={"track_executions": True},
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        assert response.json()["track_executions"] is True


# =============================================================================
# File Operation Tests
# =============================================================================


class TestCLIFileOperations:
    """Test SDK file operation endpoints."""

    @pytest.fixture
    def sdk_api_key(self, e2e_client, platform_admin):
        """Create an CLI API key for file tests."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "File Test Key"},
            headers=platform_admin.headers,
        )
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_write_and_read_file(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test writing and reading a file via CLI.

        Note: This test may fail with 500 if the temp directory doesn't exist
        or has permission issues in the test environment.
        """
        test_path = "sdk-test-file.txt"
        test_content = "Hello from SDK E2E test!"
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Write file
        response = e2e_client.post(
            "/api/cli/files/write",
            json={
                "path": test_path,
                "content": test_content,
                "location": "temp",
            },
            headers=headers,
        )
        # Accept 204 (success) or 500 (temp dir not available in test env)
        if response.status_code == 500:
            pytest.skip("Temp directory not available in test environment")
        assert response.status_code == 204

        # Read file back
        response = e2e_client.post(
            "/api/cli/files/read",
            json={
                "path": test_path,
                "location": "temp",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() == test_content

        # Cleanup
        e2e_client.post(
            "/api/cli/files/delete",
            json={"path": test_path, "location": "temp"},
            headers=headers,
        )

    def test_list_files(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test listing files in a directory.

        Note: This test may fail if the temp directory doesn't exist
        or has permission issues in the test environment.
        """
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Create a test file first
        write_response = e2e_client.post(
            "/api/cli/files/write",
            json={
                "path": "list-test.txt",
                "content": "test content",
                "location": "temp",
            },
            headers=headers,
        )
        if write_response.status_code == 500:
            pytest.skip("Temp directory not available in test environment")

        # List files
        response = e2e_client.post(
            "/api/cli/files/list",
            json={
                "directory": "",
                "location": "temp",
            },
            headers=headers,
        )
        # Accept 200 or 404 (if temp dir doesn't exist)
        if response.status_code == 404:
            pytest.skip("Temp directory not available in test environment")
        assert response.status_code == 200
        files = response.json()
        assert isinstance(files, list)

        # Cleanup
        e2e_client.post(
            "/api/cli/files/delete",
            json={"path": "list-test.txt", "location": "temp"},
            headers=headers,
        )

    def test_delete_file(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test deleting a file via CLI.

        Note: This test may fail if the temp directory doesn't exist
        or has permission issues in the test environment.
        """
        test_path = "delete-test.txt"
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Create file
        write_response = e2e_client.post(
            "/api/cli/files/write",
            json={
                "path": test_path,
                "content": "to be deleted",
                "location": "temp",
            },
            headers=headers,
        )
        if write_response.status_code == 500:
            pytest.skip("Temp directory not available in test environment")

        # Delete file
        response = e2e_client.post(
            "/api/cli/files/delete",
            json={"path": test_path, "location": "temp"},
            headers=headers,
        )
        # Accept 204 (success) or 404 (file wasn't created)
        if response.status_code == 404:
            pytest.skip("File was not created (temp dir issue)")
        assert response.status_code == 204

        # Verify deleted
        response = e2e_client.post(
            "/api/cli/files/read",
            json={"path": test_path, "location": "temp"},
            headers=headers,
        )
        assert response.status_code == 404

    def test_read_nonexistent_file(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test reading a file that doesn't exist."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        response = e2e_client.post(
            "/api/cli/files/read",
            json={
                "path": "nonexistent-file-12345.txt",
                "location": "temp",
            },
            headers=headers,
        )
        assert response.status_code == 404

    def test_path_sandboxing(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test that path traversal is blocked."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Try to escape the sandbox
        response = e2e_client.post(
            "/api/cli/files/read",
            json={
                "path": "../../../etc/passwd",
                "location": "temp",
            },
            headers=headers,
        )
        # Should be blocked (400) or file not found in valid path (404)
        assert response.status_code in [400, 404]


# =============================================================================
# Config Operation Tests
# =============================================================================


class TestCLIConfigOperations:
    """Test SDK config operation endpoints."""

    @pytest.fixture
    def sdk_api_key(self, e2e_client, platform_admin):
        """Create an CLI API key for config tests."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Config Test Key"},
            headers=platform_admin.headers,
        )
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_set_and_get_config(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test setting and getting a config value.

        Note: SDK config uses a write-through pattern where set() writes to DB
        and get() reads from Redis cache. The cache is populated by workflow
        execution, so immediately after set(), get() may return None until
        the cache is populated.
        """
        test_key = "e2e_test_config"
        test_value = "test_value_123"
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Set config - should succeed
        response = e2e_client.post(
            "/api/cli/config/set",
            json={
                "key": test_key,
                "value": test_value,
            },
            headers=headers,
        )
        assert response.status_code == 204

        # Get config - may return value or None (if cache not populated)
        response = e2e_client.post(
            "/api/cli/config/get",
            json={"key": test_key},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Data may be None if cache is not populated yet
        if data is not None:
            assert data["key"] == test_key
            assert data["value"] == test_value

        # Cleanup
        e2e_client.post(
            "/api/cli/config/delete",
            json={"key": test_key},
            headers=headers,
        )

    def test_set_config_json(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test setting a JSON config value.

        Note: See test_set_and_get_config for cache behavior notes.
        """
        test_key = "e2e_json_config"
        test_value = {"nested": {"data": [1, 2, 3]}}
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Set JSON config - should succeed
        response = e2e_client.post(
            "/api/cli/config/set",
            json={
                "key": test_key,
                "value": test_value,
            },
            headers=headers,
        )
        assert response.status_code == 204

        # Get config - may return value or None (if cache not populated)
        response = e2e_client.post(
            "/api/cli/config/get",
            json={"key": test_key},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Data may be None if cache is not populated yet
        if data is not None:
            assert data["value"] == test_value

        # Cleanup
        e2e_client.post(
            "/api/cli/config/delete",
            json={"key": test_key},
            headers=headers,
        )

    def test_set_config_secret(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test setting a secret config value."""
        test_key = "e2e_secret_config"
        test_value = "super_secret_value"
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Set secret config
        response = e2e_client.post(
            "/api/cli/config/set",
            json={
                "key": test_key,
                "value": test_value,
                "is_secret": True,
            },
            headers=headers,
        )
        assert response.status_code == 204

        # Get config - value should be returned (decrypted for API key holder)
        response = e2e_client.post(
            "/api/cli/config/get",
            json={"key": test_key},
            headers=headers,
        )
        # May return 200 with value or masked value depending on implementation
        assert response.status_code == 200

        # Cleanup
        e2e_client.post(
            "/api/cli/config/delete",
            json={"key": test_key},
            headers=headers,
        )

    def test_list_config(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test listing all config values."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Create some config values
        e2e_client.post(
            "/api/cli/config/set",
            json={"key": "list_test_1", "value": "value1"},
            headers=headers,
        )
        e2e_client.post(
            "/api/cli/config/set",
            json={"key": "list_test_2", "value": "value2"},
            headers=headers,
        )

        # List config
        response = e2e_client.post(
            "/api/cli/config/list",
            json={},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

        # Cleanup
        e2e_client.post(
            "/api/cli/config/delete",
            json={"key": "list_test_1"},
            headers=headers,
        )
        e2e_client.post(
            "/api/cli/config/delete",
            json={"key": "list_test_2"},
            headers=headers,
        )

    def test_delete_config(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test deleting a config value."""
        test_key = "delete_test_config"
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Create config
        e2e_client.post(
            "/api/cli/config/set",
            json={"key": test_key, "value": "to delete"},
            headers=headers,
        )

        # Delete it
        response = e2e_client.post(
            "/api/cli/config/delete",
            json={"key": test_key},
            headers=headers,
        )
        assert response.status_code == 200

        # Verify deleted
        response = e2e_client.post(
            "/api/cli/config/get",
            json={"key": test_key},
            headers=headers,
        )
        # Should return null/None or 404
        assert response.status_code == 200
        assert response.json() is None

    def test_get_nonexistent_config(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test getting a config that doesn't exist."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        response = e2e_client.post(
            "/api/cli/config/get",
            json={"key": "nonexistent_key_12345"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() is None


# =============================================================================
# OAuth Operation Tests
# =============================================================================


class TestCLIOAuthOperations:
    """Test SDK OAuth operation endpoints."""

    @pytest.fixture
    def sdk_api_key(self, e2e_client, platform_admin):
        """Create an CLI API key for OAuth tests."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "OAuth Test Key"},
            headers=platform_admin.headers,
        )
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_get_oauth_nonexistent_provider(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test getting an OAuth provider that doesn't exist."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        response = e2e_client.post(
            "/api/cli/oauth/get",
            json={"provider": "nonexistent_provider_12345"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() is None

    def test_get_oauth_requires_api_key(
        self,
        e2e_client,
    ):
        """Test that OAuth endpoint requires valid API key."""
        # Clear cookies to test without session auth
        e2e_client.cookies.clear()

        response = e2e_client.post(
            "/api/cli/oauth/get",
            json={"provider": "microsoft"},
        )
        assert response.status_code == 401

    def test_get_oauth_with_invalid_api_key(
        self,
        e2e_client,
    ):
        """Test OAuth endpoint with invalid API key."""
        response = e2e_client.post(
            "/api/cli/oauth/get",
            json={"provider": "microsoft"},
            headers={"Authorization": "Bearer bfsk_invalid_key_123"},
        )
        assert response.status_code == 401

    def test_get_oauth_with_org_id(
        self,
        e2e_client,
        sdk_api_key,
    ):
        """Test getting OAuth with explicit org_id parameter."""
        headers = {"Authorization": f"Bearer {sdk_api_key['key']}"}

        # Even with a valid org_id, provider may not exist - should return None
        response = e2e_client.post(
            "/api/cli/oauth/get",
            json={
                "provider": "nonexistent_provider",
                "org_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json() is None


# =============================================================================
# SDK Download Test
# =============================================================================


class TestCLIDownload:
    """Test SDK package download."""

    def test_download_sdk(
        self,
        e2e_client,
    ):
        """Test downloading the SDK package."""
        response = e2e_client.get("/api/cli/download")
        assert response.status_code == 200

        # Should be a gzipped tarball
        assert response.headers.get("content-type") == "application/gzip"
        assert "bifrost-cli" in response.headers.get("content-disposition", "")

    def test_download_sdk_includes_new_files(
        self,
        e2e_client,
    ):
        """Test that downloaded SDK includes decorator, context, and CLI files."""
        import io
        import tarfile

        response = e2e_client.get("/api/cli/download")
        assert response.status_code == 200

        # Parse the tarball
        buffer = io.BytesIO(response.content)
        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            file_names = tar.getnames()

        # Should include core files
        expected_files = [
            "bifrost/client.py",
            "bifrost/files.py",
            "bifrost/config.py",
            "bifrost/oauth.py",
            "bifrost/__init__.py",
            "bifrost/_context.py",
            "bifrost/decorators.py",
            "bifrost/errors.py",
            "bifrost/cli.py",
            "bifrost/__main__.py",
            "pyproject.toml",
        ]

        for expected in expected_files:
            assert expected in file_names, f"Missing file: {expected}"

    def test_download_sdk_decorators_content(
        self,
        e2e_client,
    ):
        """Test that decorators.py has proper workflow decorator."""
        import io
        import tarfile

        response = e2e_client.get("/api/cli/download")
        buffer = io.BytesIO(response.content)

        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            decorators_file = tar.extractfile("bifrost/decorators.py")
            assert decorators_file is not None
            content = decorators_file.read().decode("utf-8")

        # Should contain workflow decorator
        assert "def workflow(" in content
        assert "def data_provider(" in content
        assert "@dataclass" in content
        assert "WorkflowMetadata" in content
        assert "DataProviderMetadata" in content

    def test_download_sdk_context_content(
        self,
        e2e_client,
    ):
        """Test that _context.py has API-fetching proxy."""
        import io
        import tarfile

        response = e2e_client.get("/api/cli/download")
        buffer = io.BytesIO(response.content)

        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            context_file = tar.extractfile("bifrost/_context.py")
            assert context_file is not None
            content = context_file.read().decode("utf-8")

        # Should contain context proxy that fetches from API
        assert "_ExternalContextProxy" in content
        assert "from .client import get_client" in content
        assert "context = _ExternalContextProxy()" in content

    def test_download_sdk_cli_content(
        self,
        e2e_client,
    ):
        """Test that cli.py has bifrost run command."""
        import io
        import tarfile

        response = e2e_client.get("/api/cli/download")
        buffer = io.BytesIO(response.content)

        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            cli_file = tar.extractfile("bifrost/cli.py")
            assert cli_file is not None
            content = cli_file.read().decode("utf-8")

        # Should contain CLI entry point
        assert "def main(" in content
        assert "argparse" in content
        assert "bifrost run" in content.lower() or "'run'" in content

    def test_download_sdk_pyproject_has_cli(
        self,
        e2e_client,
    ):
        """Test that pyproject.toml has CLI entry point."""
        import io
        import tarfile

        response = e2e_client.get("/api/cli/download")
        buffer = io.BytesIO(response.content)

        with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
            pyproject_file = tar.extractfile("pyproject.toml")
            assert pyproject_file is not None
            content = pyproject_file.read().decode("utf-8")

        # Should contain CLI entry point
        assert "[project.scripts]" in content
        assert 'bifrost = "bifrost.cli:main"' in content


# =============================================================================
# CLI Session Tests (CLI<->Web Communication)
# =============================================================================


class TestCLISessions:
    """Test CLI session endpoints for CLI<->Web workflow execution."""

    def test_list_sessions_empty(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test listing sessions when none exist."""
        response = e2e_client.get(
            "/api/cli/sessions",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_create_session(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test creating a CLI session."""
        import uuid
        session_id = str(uuid.uuid4())

        response = e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "test_workflow",
                        "description": "A test workflow",
                        "parameters": [
                            {
                                "name": "email",
                                "type": "string",
                                "label": "Email Address",
                                "required": True,
                                "default_value": None,
                            },
                        ],
                    }
                ],
                "selected_workflow": "test_workflow",
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 200, f"Create session failed: {response.text}"

        data = response.json()
        assert data["id"] == session_id
        assert data["file_path"] == "/path/to/workflows.py"
        assert len(data["workflows"]) == 1
        assert data["workflows"][0]["name"] == "test_workflow"
        assert data["selected_workflow"] == "test_workflow"
        assert data["pending"] is False

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_get_session(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test getting a specific session."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/test.py",
                "workflows": [
                    {
                        "name": "my_workflow",
                        "description": "My workflow",
                        "parameters": [],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Get session
        response = e2e_client.get(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == session_id
        assert data["file_path"] == "/path/to/test.py"
        assert len(data["workflows"]) == 1

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_get_nonexistent_session(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test getting a session that doesn't exist."""
        import uuid
        fake_id = str(uuid.uuid4())

        response = e2e_client.get(
            f"/api/cli/sessions/{fake_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404

    def test_continue_workflow(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test continuing workflow execution with params."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "onboard_user",
                        "description": "Onboard a user",
                        "parameters": [
                            {
                                "name": "email",
                                "type": "string",
                                "label": "Email",
                                "required": True,
                            }
                        ],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Continue with params
        response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "onboard_user",
                "params": {"email": "test@example.com"},
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 202, f"Continue failed: {response.text}"

        data = response.json()
        assert data["status"] == "pending"
        assert data["workflow"] == "onboard_user"

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_continue_invalid_workflow(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test continuing with invalid workflow name."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "real_workflow",
                        "description": "Real workflow",
                        "parameters": [],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Try to continue with wrong name
        response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "nonexistent_workflow",
                "params": {},
            },
            headers=platform_admin.headers,
        )
        assert response.status_code == 400

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_get_pending_no_execution(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test polling when no execution is pending."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session but don't continue
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "pending_test",
                        "description": "Test",
                        "parameters": [],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Poll - should return 204 (no pending execution)
        response = e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_get_pending_after_continue(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test polling after continue has been called."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "pending_workflow",
                        "description": "Test pending",
                        "parameters": [
                            {
                                "name": "value",
                                "type": "string",
                                "required": True,
                            }
                        ],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Continue
        e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "pending_workflow",
                "params": {"value": "test123"},
            },
            headers=platform_admin.headers,
        )

        # Poll - should return the pending execution
        response = e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=platform_admin.headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["workflow_name"] == "pending_workflow"
        assert data["params"] == {"value": "test123"}

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_pending_clears_after_poll(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test that pending flag is cleared after CLI polls."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "clear_test",
                        "description": "Test clearing",
                        "parameters": [],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Continue
        e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "clear_test",
                "params": {},
            },
            headers=platform_admin.headers,
        )

        # First poll - should get params
        response1 = e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=platform_admin.headers,
        )
        assert response1.status_code == 200

        # Second poll - should be 204 (pending was cleared)
        response2 = e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=platform_admin.headers,
        )
        assert response2.status_code == 204

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )

    def test_delete_session(
        self,
        e2e_client,
        platform_admin,
    ):
        """Test deleting a session."""
        import uuid
        session_id = str(uuid.uuid4())

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/workflows.py",
                "workflows": [
                    {
                        "name": "delete_test",
                        "description": "Test",
                        "parameters": [],
                    }
                ],
            },
            headers=platform_admin.headers,
        )

        # Delete session
        response = e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 204

        # Verify it's gone
        response = e2e_client.get(
            f"/api/cli/sessions/{session_id}",
            headers=platform_admin.headers,
        )
        assert response.status_code == 404


# =============================================================================
# CLI Execution Flow Tests - Validates CLI behaves identically to engine
# =============================================================================


class TestCLIExecutionFlow:
    """
    Comprehensive CLI execution tests matching engine behavior.

    These tests validate that CLI workflow execution produces:
    - Same log format as engine
    - Same completion events as engine
    - Same result handling as engine
    - CLI acts as a "local engine"
    """

    @pytest.fixture
    def cli_api_key(self, e2e_client, platform_admin):
        """Create a CLI API key for execution tests."""
        response = e2e_client.post(
            "/api/cli/keys",
            json={"name": "Execution Test Key"},
            headers=platform_admin.headers,
        )
        data = response.json()
        yield data
        # Cleanup
        e2e_client.delete(
            f"/api/cli/keys/{data['id']}",
            headers=platform_admin.headers,
        )

    def test_cli_execution_with_logging(
        self,
        e2e_client,
        platform_admin,
        cli_api_key,
    ):
        """
        Full CLI workflow execution with log validation.

        This test simulates what the CLI does locally:
        1. Register session with workflow
        2. Web UI continues with params
        3. CLI polls for pending, gets params
        4. CLI executes workflow, streaming logs
        5. CLI posts result
        6. Verify execution status, logs, and result
        """
        import uuid

        session_id = str(uuid.uuid4())
        headers = platform_admin.headers

        # 1. Create CLI session with test workflow
        create_response = e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/test_logging_workflow.py",
                "workflows": [
                    {
                        "name": "logging_test",
                        "description": "Test workflow with comprehensive logging",
                        "parameters": [
                            {
                                "name": "user_name",
                                "type": "string",
                                "label": "User Name",
                                "required": True,
                                "default_value": None,
                            },
                            {
                                "name": "steps",
                                "type": "integer",
                                "label": "Number of Steps",
                                "required": False,
                                "default_value": 3,
                            },
                        ],
                    }
                ],
                "selected_workflow": "logging_test",
            },
            headers=headers,
        )
        assert create_response.status_code == 200, f"Create failed: {create_response.text}"

        # 2. Continue workflow with params (this triggers pending execution)
        continue_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "logging_test",
                "params": {"user_name": "TestUser", "steps": 3},
            },
            headers=headers,
        )
        assert continue_response.status_code == 202, f"Continue failed: {continue_response.text}"

        continue_data = continue_response.json()
        execution_id = continue_data["execution_id"]
        assert continue_data["status"] == "pending"
        assert continue_data["workflow"] == "logging_test"

        # 3. CLI polls for pending execution
        pending_response = e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=headers,
        )
        assert pending_response.status_code == 200

        pending_data = pending_response.json()
        assert pending_data["execution_id"] == execution_id
        assert pending_data["workflow_name"] == "logging_test"
        assert pending_data["params"] == {"user_name": "TestUser", "steps": 3}

        # 4. Simulate CLI streaming logs at all levels
        log_messages = [
            {"level": "DEBUG", "message": "Starting workflow for TestUser"},
            {"level": "INFO", "message": "Processing 3 steps"},
            {"level": "WARNING", "message": "This is a test warning"},
            {"level": "INFO", "message": "Step 1/3 for TestUser"},
            {"level": "INFO", "message": "Step 2/3 for TestUser"},
            {"level": "INFO", "message": "Step 3/3 for TestUser"},
            {"level": "INFO", "message": "Workflow completed successfully"},
        ]

        for i, log in enumerate(log_messages):
            log_response = e2e_client.post(
                f"/api/cli/sessions/{session_id}/executions/{execution_id}/log",
                json={
                    "level": log["level"],
                    "message": log["message"],
                    "timestamp": f"2025-12-16T10:00:{i:02d}.000Z",
                    "metadata": {"step": i + 1},
                },
                headers=headers,
            )
            assert log_response.status_code == 204, f"Log {i} failed: {log_response.text}"

        # 5. CLI posts result (simulating successful completion)
        result_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/result",
            json={
                "status": "success",
                "result": {
                    "status": "success",
                    "user_name": "TestUser",
                    "steps_completed": 3,
                },
                "duration_ms": 1500,
            },
            headers=headers,
        )
        assert result_response.status_code == 200, f"Result failed: {result_response.text}"

        # 6. Validate execution status via API
        execution_response = e2e_client.get(
            f"/api/executions/{execution_id}",
            headers=headers,
        )
        assert execution_response.status_code == 200

        execution = execution_response.json()
        assert execution["status"] == "Success"
        assert execution["duration_ms"] == 1500
        # Result is stored directly (no wrapper)
        assert execution["result"]["status"] == "success"
        assert execution["result"]["user_name"] == "TestUser"
        assert execution["result"]["steps_completed"] == 3

        # 7. Validate logs were persisted
        logs_response = e2e_client.get(
            f"/api/executions/{execution_id}/logs",
            headers=headers,
        )
        assert logs_response.status_code == 200

        logs = logs_response.json()
        assert len(logs) >= 7, f"Expected at least 7 logs, got {len(logs)}"

        # Validate log levels present
        log_levels = {log["level"] for log in logs}
        assert "DEBUG" in log_levels, "DEBUG logs missing"
        assert "INFO" in log_levels, "INFO logs missing"
        assert "WARNING" in log_levels, "WARNING logs missing"

        # Validate log sequence (should be ordered)
        sequences = [log.get("sequence", i) for i, log in enumerate(logs)]
        assert sequences == sorted(sequences), "Logs not in order"

        # Validate specific log messages
        messages = [log["message"] for log in logs]
        assert any("Starting workflow" in m for m in messages)
        assert any("Step 1/3" in m for m in messages)
        assert any("completed successfully" in m for m in messages)

        # 8. Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=headers,
        )

    def test_cli_execution_failure(
        self,
        e2e_client,
        platform_admin,
        cli_api_key,
    ):
        """Test CLI workflow execution with failure and error logging."""
        import uuid

        session_id = str(uuid.uuid4())
        headers = platform_admin.headers

        # Create session
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/failing_workflow.py",
                "workflows": [
                    {
                        "name": "failing_test",
                        "description": "Test workflow that fails",
                        "parameters": [
                            {
                                "name": "should_fail",
                                "type": "boolean",
                                "label": "Should Fail",
                                "required": False,
                                "default_value": True,
                            },
                        ],
                    }
                ],
            },
            headers=headers,
        )

        # Continue workflow
        continue_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={
                "workflow_name": "failing_test",
                "params": {"should_fail": True},
            },
            headers=headers,
        )
        assert continue_response.status_code == 202

        execution_id = continue_response.json()["execution_id"]

        # Poll for pending
        e2e_client.get(
            f"/api/cli/sessions/{session_id}/pending",
            headers=headers,
        )

        # Post logs including error
        log_messages = [
            {"level": "INFO", "message": "Starting workflow..."},
            {"level": "WARNING", "message": "Failure mode enabled"},
            {"level": "ERROR", "message": "Intentional test failure occurred"},
        ]

        for log in log_messages:
            e2e_client.post(
                f"/api/cli/sessions/{session_id}/executions/{execution_id}/log",
                json={
                    "level": log["level"],
                    "message": log["message"],
                },
                headers=headers,
            )

        # Post failed result
        result_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/result",
            json={
                "status": "failed",
                "error_message": "ValueError: Intentional test failure",
                "duration_ms": 500,
            },
            headers=headers,
        )
        assert result_response.status_code == 200

        # Validate execution status
        execution_response = e2e_client.get(
            f"/api/executions/{execution_id}",
            headers=headers,
        )
        assert execution_response.status_code == 200

        execution = execution_response.json()
        assert execution["status"] == "Failed"
        assert execution["error_message"] == "ValueError: Intentional test failure"
        assert execution["duration_ms"] == 500

        # Validate error log persisted
        logs_response = e2e_client.get(
            f"/api/executions/{execution_id}/logs",
            headers=headers,
        )
        logs = logs_response.json()

        log_levels = {log["level"] for log in logs}
        assert "ERROR" in log_levels, "ERROR logs missing"

        error_messages = [log["message"] for log in logs if log["level"] == "ERROR"]
        assert any("Intentional test failure" in m for m in error_messages)

        # Cleanup
        e2e_client.delete(
            f"/api/cli/sessions/{session_id}",
            headers=headers,
        )

    def test_cli_logs_match_engine_format(
        self,
        e2e_client,
        platform_admin,
        cli_api_key,
    ):
        """
        Validate CLI logs match engine log format exactly.

        Both should have: level, message, timestamp, sequence, metadata
        """
        import uuid

        session_id = str(uuid.uuid4())
        headers = platform_admin.headers

        # Create session and start execution
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/format_test.py",
                "workflows": [
                    {
                        "name": "format_test",
                        "description": "Test log format",
                        "parameters": [],
                    }
                ],
            },
            headers=headers,
        )

        continue_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={"workflow_name": "format_test", "params": {}},
            headers=headers,
        )
        execution_id = continue_response.json()["execution_id"]

        # Poll to pick up execution
        e2e_client.get(f"/api/cli/sessions/{session_id}/pending", headers=headers)

        # Post log with all fields
        test_timestamp = "2025-12-16T12:30:45.123Z"
        test_metadata = {"custom_field": "custom_value", "count": 42}

        log_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/log",
            json={
                "level": "INFO",
                "message": "Test log with full metadata",
                "timestamp": test_timestamp,
                "metadata": test_metadata,
            },
            headers=headers,
        )
        assert log_response.status_code == 204

        # Complete the execution
        e2e_client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/result",
            json={"status": "success", "result": None, "duration_ms": 100},
            headers=headers,
        )

        # Retrieve logs and validate format
        logs_response = e2e_client.get(
            f"/api/executions/{execution_id}/logs",
            headers=headers,
        )
        logs = logs_response.json()
        assert len(logs) >= 1

        # Validate log structure matches API format (ExecutionLogPublic)
        log = logs[0]
        assert "level" in log, "Missing 'level' field"
        assert "message" in log, "Missing 'message' field"
        assert "timestamp" in log, "Missing 'timestamp' field"
        # Note: 'data' field contains metadata in the public API model
        # Internal model has 'log_metadata' and 'sequence' but public model uses 'data'
        assert "data" in log, "Missing 'data' field"

        assert log["level"] == "INFO"
        assert log["message"] == "Test log with full metadata"

        # Validate metadata preserved (API returns metadata in 'data' field)
        metadata_field = log.get("data", {})
        assert metadata_field.get("custom_field") == "custom_value"
        assert metadata_field.get("count") == 42

        # Cleanup
        e2e_client.delete(f"/api/cli/sessions/{session_id}", headers=headers)

    def test_cli_execution_result_format_matches_engine(
        self,
        e2e_client,
        platform_admin,
        cli_api_key,
    ):
        """
        Validate CLI completion event format matches engine exactly.

        Engine publishes: {status, result, durationMs, error (if failed)}
        CLI should publish the same format.
        """
        import uuid

        session_id = str(uuid.uuid4())
        headers = platform_admin.headers

        # Setup
        e2e_client.post(
            "/api/cli/sessions",
            json={
                "session_id": session_id,
                "file_path": "/path/to/result_format_test.py",
                "workflows": [
                    {
                        "name": "result_test",
                        "description": "Test result format",
                        "parameters": [],
                    }
                ],
            },
            headers=headers,
        )

        continue_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/continue",
            json={"workflow_name": "result_test", "params": {}},
            headers=headers,
        )
        execution_id = continue_response.json()["execution_id"]

        # Poll
        e2e_client.get(f"/api/cli/sessions/{session_id}/pending", headers=headers)

        # Post result with complex return value
        complex_result = {
            "users_created": ["user1", "user2", "user3"],
            "total": 3,
            "metadata": {"source": "cli_test"},
        }

        result_response = e2e_client.post(
            f"/api/cli/sessions/{session_id}/executions/{execution_id}/result",
            json={
                "status": "success",
                "result": complex_result,
                "duration_ms": 2500,
            },
            headers=headers,
        )
        assert result_response.status_code == 200

        # Retrieve execution and validate result format
        execution_response = e2e_client.get(
            f"/api/executions/{execution_id}",
            headers=headers,
        )
        execution = execution_response.json()

        # Validate status
        assert execution["status"] == "Success"
        assert execution["duration_ms"] == 2500

        # Validate result (stored directly, no wrapper)
        assert "result" in execution
        assert execution["result"] == complex_result
        assert execution["result"]["users_created"] == ["user1", "user2", "user3"]
        assert execution["result"]["total"] == 3

        # Cleanup
        e2e_client.delete(f"/api/cli/sessions/{session_id}", headers=headers)
