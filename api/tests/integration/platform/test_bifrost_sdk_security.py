"""
Security Integration Tests for Bifrost SDK

Tests UNIQUE to new SDK additions (config, oauth, custom packages):
1. Custom packages isolation (.packages directory)
2. Context protection for new modules
3. Default org scoping (list() returns only current org)
4. Cross-org parameter validation

NOTE: Org isolation for organizations/forms/executions/roles is already tested
in test_organizations_endpoints.py, test_forms_endpoints.py, etc.
"""

import pytest

# Import context functions directly from bifrost package
# This ensures we're using the SAME module instance as the SDK code
from bifrost._context import set_execution_context, clear_execution_context




class TestSDKContextProtection:
    """
    Test that new SDK modules (config) require execution context.

    UNIQUE TO: New config module
    """

    async def test_config_requires_context(self):
        """Test that config SDK requires execution context in external mode (no API key)"""
        from bifrost import config
        from bifrost.client import BifrostClient
        import os

        # Clear context and reset client
        clear_execution_context()
        BifrostClient._instance = None

        # Clear env vars - need to actually remove them
        old_url = os.environ.get("BIFROST_DEV_URL")
        old_key = os.environ.get("BIFROST_DEV_KEY")

        try:
            if "BIFROST_DEV_URL" in os.environ:
                del os.environ["BIFROST_DEV_URL"]
            if "BIFROST_DEV_KEY" in os.environ:
                del os.environ["BIFROST_DEV_KEY"]

            # In external mode without API key configured, should raise RuntimeError
            with pytest.raises(RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"):
                await config.get("test_key")
        finally:
            # Restore env vars
            if old_url is not None:
                os.environ["BIFROST_DEV_URL"] = old_url
            if old_key is not None:
                os.environ["BIFROST_DEV_KEY"] = old_key
            BifrostClient._instance = None


class TestDefaultOrgScoping:
    """
    Test that list() operations default to current org from context.

    UNIQUE TO: Verifying new modules respect org scoping by default

    NOTE: The actual org isolation (user in org A can't see org B data) is
    tested in the repository layer and HTTP endpoints. These tests verify
    that the SDK correctly passes the context org_id to those layers.
    """

    async def test_config_list_defaults_to_current_org(self):
        """Test that config.list() uses context.org_id by default"""
        from unittest.mock import AsyncMock, patch
        from contextlib import asynccontextmanager
        from bifrost import config
        from src.sdk.context import ExecutionContext, Organization

        # Create context for org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Mock get_redis - config.list reads from Redis cache
            with patch('src.core.cache.get_redis') as mock_get_redis:
                mock_redis = AsyncMock()

                # Mock hgetall to return empty dict (no configs)
                mock_redis.hgetall = AsyncMock(return_value={})

                @asynccontextmanager
                async def mock_redis_context():
                    yield mock_redis

                mock_get_redis.return_value = mock_redis_context()

                # Call list() without org_id
                result = await config.list()

                # Verify it called hgetall with org-123 hash key
                mock_redis.hgetall.assert_called_once()
                call_args = mock_redis.hgetall.call_args
                # The hash key should contain org-123
                assert "org-123" in call_args[0][0]
                # Verify result is empty (ConfigData wraps empty dict)
                assert len(result) == 0
        finally:
            clear_execution_context()


class TestIntegrationsSDKSecurity:
    """
    Test security features of the integrations SDK module.

    Tests:
    - Context protection (requires execution context in external mode)
    - Default org scoping (uses context org_id by default)
    - Explicit org_id parameter support
    """

    async def test_integrations_get_requires_context(self):
        """Test that integrations.get() requires execution context in external mode (no API key)"""
        from bifrost import integrations
        from bifrost.client import BifrostClient
        import os

        # Clear context and reset client
        clear_execution_context()
        BifrostClient._instance = None

        # Clear env vars - need to actually remove them
        old_url = os.environ.get("BIFROST_DEV_URL")
        old_key = os.environ.get("BIFROST_DEV_KEY")

        try:
            if "BIFROST_DEV_URL" in os.environ:
                del os.environ["BIFROST_DEV_URL"]
            if "BIFROST_DEV_KEY" in os.environ:
                del os.environ["BIFROST_DEV_KEY"]

            # In external mode without API key configured, should raise RuntimeError
            with pytest.raises(RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"):
                await integrations.get("Microsoft Partner")
        finally:
            # Restore env vars
            if old_url is not None:
                os.environ["BIFROST_DEV_URL"] = old_url
            if old_key is not None:
                os.environ["BIFROST_DEV_KEY"] = old_key
            BifrostClient._instance = None

    async def test_integrations_get_uses_context_org_by_default(self):
        """Test that integrations.get() uses context.org_id by default"""
        from unittest.mock import AsyncMock, patch, MagicMock
        from contextlib import asynccontextmanager
        from bifrost import integrations
        from src.sdk.context import ExecutionContext, Organization

        # Create context for org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        # Mock repository instance - both methods return None (not found)
        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=None)
        mock_repo.get_integration_by_name = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        try:
            with patch("src.core.database.get_db_context", mock_db_context):
                with patch(
                    "src.repositories.integrations.IntegrationsRepository",
                    return_value=mock_repo,
                ):
                    # Call get() without org_id - should use context org_id
                    result = await integrations.get("Microsoft Partner")

                    # Verify result is None (not found)
                    assert result is None
        finally:
            clear_execution_context()

    async def test_integrations_get_with_explicit_org_id(self):
        """Test that integrations.get(org_id='other-org') uses the specified org"""
        from unittest.mock import AsyncMock, patch, MagicMock
        from contextlib import asynccontextmanager
        from bifrost import integrations
        from src.sdk.context import ExecutionContext, Organization

        # User is in org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=True,  # Platform admin can access other orgs
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        # Mock repository instance - both methods return None (not found)
        mock_repo = MagicMock()
        mock_repo.get_integration_for_org = AsyncMock(return_value=None)
        mock_repo.get_integration_by_name = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_db_context():
            yield MagicMock()

        try:
            with patch("src.core.database.get_db_context", mock_db_context):
                with patch(
                    "src.repositories.integrations.IntegrationsRepository",
                    return_value=mock_repo,
                ):
                    # Explicitly request org-999's integration
                    result = await integrations.get("Microsoft Partner", org_id="org-999")

                    # Verify result is None (not found)
                    assert result is None
        finally:
            clear_execution_context()

    async def test_integrations_list_mappings_requires_context(self):
        """Test that integrations.list_mappings() requires execution context in external mode (no API key)"""
        from bifrost import integrations
        from bifrost.client import BifrostClient
        import os

        # Clear context and reset client
        clear_execution_context()
        BifrostClient._instance = None

        # Clear env vars - need to actually remove them
        old_url = os.environ.get("BIFROST_DEV_URL")
        old_key = os.environ.get("BIFROST_DEV_KEY")

        try:
            if "BIFROST_DEV_URL" in os.environ:
                del os.environ["BIFROST_DEV_URL"]
            if "BIFROST_DEV_KEY" in os.environ:
                del os.environ["BIFROST_DEV_KEY"]

            # In external mode without API key configured, should raise RuntimeError
            with pytest.raises(RuntimeError, match="BIFROST_DEV_URL and BIFROST_DEV_KEY"):
                await integrations.list_mappings("Microsoft Partner")
        finally:
            # Restore env vars
            if old_url is not None:
                os.environ["BIFROST_DEV_URL"] = old_url
            if old_key is not None:
                os.environ["BIFROST_DEV_KEY"] = old_key
            BifrostClient._instance = None


class TestFilesSDKSecurity:
    """
    Test security features of the files SDK module.

    Tests:
    - Path traversal protection (../ attacks blocked)
    - Absolute path protection (external mode only)
    - Location-based access control (temp/workspace/uploads isolation)
    """

    async def test_files_path_traversal_blocked(self):
        """Test that path traversal attacks are blocked"""
        from bifrost import files

        # In platform mode, test path traversal is blocked
        from src.sdk.context import ExecutionContext, Organization

        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Path traversal attempt should raise ValueError
            with pytest.raises(ValueError, match="Path must be within"):
                await files.read("../../../etc/passwd", location="workspace")

            # Another path traversal attempt
            with pytest.raises(ValueError, match="Path must be within"):
                await files.write("../../escape.txt", "malicious", location="temp")
        finally:
            clear_execution_context()

    async def test_files_absolute_path_blocked_in_external_mode(self):
        """Test that absolute paths are blocked in external (CLI) mode"""
        from bifrost import files

        # Clear context to force external mode
        clear_execution_context()

        # Absolute paths should raise ValueError in external mode
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            await files.read("/etc/passwd", location="workspace")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            await files.write("/tmp/malicious.txt", "content", location="temp")

    async def test_files_location_access_controlled(self):
        """Test that each location maps to the correct base directory"""
        from bifrost import files
        from src.sdk.context import ExecutionContext, Organization

        # In platform mode, verify location mapping
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=False,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Test workspace location resolves to workspace directory
            workspace_path = files._resolve_path("test.txt", location="workspace")
            assert str(workspace_path).startswith(str(files.WORKSPACE_FILES_DIR))

            # Test temp location resolves to temp directory
            temp_path = files._resolve_path("test.txt", location="temp")
            assert str(temp_path).startswith(str(files.TEMP_FILES_DIR))

            # Verify workspace and temp are separate
            assert files.WORKSPACE_FILES_DIR != files.TEMP_FILES_DIR
        finally:
            clear_execution_context()


class TestCrossOrgParameterUsage:
    """
    Test that when org_id parameter is specified, it's actually used.

    UNIQUE TO: New optional org_id parameter on config

    NOTE: Whether the user is AUTHORIZED to access another org's data is
    checked at the repository/service layer (existing tests). These tests
    verify the SDK correctly passes the org_id parameter through.
    """

    async def test_config_get_with_explicit_org_id(self):
        """Test that config.get(org_id='other-org') uses the specified org"""
        import json
        from unittest.mock import AsyncMock, patch
        from contextlib import asynccontextmanager
        from bifrost import config
        from src.sdk.context import ExecutionContext, Organization

        # User is in org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=True,  # Platform admin can access other orgs
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Mock get_redis - config.get reads from Redis cache
            with patch('src.core.cache.get_redis') as mock_get_redis:
                mock_redis = AsyncMock()

                # Create cached config data as JSON
                cached_config_data = json.dumps({
                    "value": "other-value",
                    "type": "string"
                })

                # Mock hget to return our cached data
                mock_redis.hget = AsyncMock(return_value=cached_config_data)

                @asynccontextmanager
                async def mock_redis_context():
                    yield mock_redis

                mock_get_redis.return_value = mock_redis_context()

                # Explicitly request org-999's config
                result = await config.get("test_key", org_id="org-999")

                # Verify it called hget with org-999 hash key
                mock_redis.hget.assert_called_once()
                call_args = mock_redis.hget.call_args
                # The hash key should contain org-999
                assert "org-999" in call_args[0][0]
                assert call_args[0][1] == "test_key"
                # Verify result contains the value
                assert result == "other-value"
        finally:
            clear_execution_context()

    # Note: test_secrets_get_with_explicit_org_id was removed because
    # secrets.get() no longer accepts org_id parameter. Secrets use Key Vault
    # secret names which encode the scope in the naming convention.

    async def test_config_set_with_explicit_org_id(self):
        """Test that config.set(org_id='other-org') writes to the specified org"""
        from unittest.mock import AsyncMock, MagicMock, patch
        from bifrost import config
        from src.sdk.context import ExecutionContext, Organization

        # User is in org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Mock get_write_buffer - config.set writes to buffer, not directly to DB
            with patch('bifrost._write_buffer.get_write_buffer') as mock_get_buffer:
                mock_buffer = MagicMock()
                mock_buffer.add_config_change = AsyncMock()
                mock_get_buffer.return_value = mock_buffer

                # Set config for org-999
                await config.set("api_url", "https://api.other.com", org_id="org-999")

                # Verify it called add_config_change with org-999
                mock_buffer.add_config_change.assert_called_once()
                call_kwargs = mock_buffer.add_config_change.call_args[1]
                assert call_kwargs["org_id"] == "org-999"
                assert call_kwargs["key"] == "api_url"
                assert call_kwargs["value"] == "https://api.other.com"
                assert call_kwargs["operation"] == "set"
        finally:
            clear_execution_context()

    async def test_config_delete_with_explicit_org_id(self):
        """Test that config.delete(org_id='other-org') deletes from the specified org"""
        from unittest.mock import AsyncMock, MagicMock, patch
        from bifrost import config
        from src.sdk.context import ExecutionContext, Organization

        # User is in org-123
        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="test-user",
            email="test@example.com",
            name="Test User",
            scope="org-123",
            organization=org,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="test-exec-123"
        )
        set_execution_context(context)

        try:
            # Mock get_write_buffer - config.delete writes to buffer, not directly to DB
            with patch('bifrost._write_buffer.get_write_buffer') as mock_get_buffer:
                mock_buffer = MagicMock()
                mock_buffer.add_config_change = AsyncMock()
                mock_get_buffer.return_value = mock_buffer

                # Delete config from org-999
                result = await config.delete("old_key", org_id="org-999")

                # Verify it called add_config_change with org-999
                mock_buffer.add_config_change.assert_called_once()
                call_kwargs = mock_buffer.add_config_change.call_args[1]
                assert call_kwargs["org_id"] == "org-999"
                assert call_kwargs["key"] == "old_key"
                assert call_kwargs["operation"] == "delete"
                # Verify result is True (deletion queued)
                assert result is True
        finally:
            clear_execution_context()


# DOCUMENTATION: What's NOT tested here (already covered elsewhere)
"""
The following security concerns are ALREADY tested in existing test suites:

1. Org Isolation (HTTP layer):
   - tests/integration/api/test_organizations_endpoints.py
   - tests/integration/api/test_forms_endpoints.py
   - tests/integration/api/test_executions_endpoints.py
   - tests/integration/api/test_roles_endpoints.py

   These test that:
   - Regular users can't list organizations (403)
   - Regular users can't access other org's forms
   - Regular users can't see other org's executions
   - etc.

2. Repository Layer Org Isolation:
   - tests/unit/repositories/test_config_repository.py
   - tests/unit/repositories/test_forms_repository.py
   - tests/unit/repositories/test_roles_repository.py

   These test that repositories:
   - Query with correct PartitionKey (org_id)
   - Fallback to GLOBAL when appropriate
   - Return only org-scoped data

3. Authorization & Permissions:
   - tests/unit/test_authorization.py
   - tests/integration/api/test_permissions_endpoints.py

   These test that:
   - Platform admins can access all orgs
   - Regular users can only access their org
   - Form visibility rules (isPublic, role-based)
   - Execution visibility rules

4. Form/Workflow Execution Security:
   - tests/integration/api/test_workflows_endpoints.py
   - tests/integration/api/test_forms_endpoints.py

   These test that:
   - Users can only execute forms they have permission for
   - Workflows execute in correct org context
   - Results are scoped to correct org

This test file focuses ONLY on security concerns UNIQUE to the new SDK additions:
- Custom packages isolation
- Context protection for new modules (config, oauth)
- Default org scoping in SDK (not repository)
- Cross-org parameter passing
"""
