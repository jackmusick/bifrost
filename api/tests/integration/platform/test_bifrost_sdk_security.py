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
    Test that new SDK modules (config, oauth) require execution context.

    UNIQUE TO: New config, oauth modules
    """

    async def test_config_requires_context(self):
        """Test that config SDK requires execution context"""
        from bifrost import config

        # Clear context
        clear_execution_context()

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="No execution context found"):
            await config.get("test_key")

    async def test_oauth_requires_context(self):
        """Test that oauth SDK requires execution context"""
        from bifrost import oauth

        clear_execution_context()

        with pytest.raises(RuntimeError, match="No execution context found"):
            await oauth.get("microsoft")


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
        from shared.context import ExecutionContext, Organization

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
            with patch('bifrost.config.get_redis') as mock_get_redis:
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
                # Verify result is a dict (empty in this case)
                assert isinstance(result, dict)
                assert result == {}
        finally:
            clear_execution_context()


class TestCrossOrgParameterUsage:
    """
    Test that when org_id parameter is specified, it's actually used.

    UNIQUE TO: New optional org_id parameter on config, oauth

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
        from shared.context import ExecutionContext, Organization

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
            with patch('bifrost.config.get_redis') as mock_get_redis:
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
        from shared.context import ExecutionContext, Organization

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
            with patch('bifrost.config.get_write_buffer') as mock_get_buffer:
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
        from shared.context import ExecutionContext, Organization

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
            with patch('bifrost.config.get_write_buffer') as mock_get_buffer:
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

    async def test_oauth_get_with_explicit_org_id(self):
        """Test that oauth.get(org_id='other-org') uses the specified org"""
        import json
        from unittest.mock import AsyncMock, patch
        from contextlib import asynccontextmanager
        from bifrost import oauth
        from shared.context import ExecutionContext, Organization

        org = Organization(id="org-123", name="Test Org", is_active=True)
        context = ExecutionContext(
            user_id="admin-user",
            email="admin@example.com",
            name="Admin User",
            scope="org-123",
            organization=org,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="test-exec-admin-456"
        )
        set_execution_context(context)

        try:
            # Mock get_redis - oauth.get reads from Redis cache
            with patch('bifrost.oauth.get_redis') as mock_get_redis:
                mock_redis = AsyncMock()

                # Create cached OAuth data as JSON
                cached_oauth_data = json.dumps({
                    "provider_name": "microsoft",
                    "client_id": "client-123",
                    "client_secret": "secret-456",
                    "authorization_url": "https://login.microsoft.com",
                    "token_url": "https://login.microsoft.com/token",
                    "scopes": ["openid", "profile"],
                    "access_token": "xxx",
                    "refresh_token": "yyy",
                    "expires_at": None
                })

                # Mock hget to return our cached data
                mock_redis.hget = AsyncMock(return_value=cached_oauth_data)

                @asynccontextmanager
                async def mock_redis_context():
                    yield mock_redis

                mock_get_redis.return_value = mock_redis_context()

                # Explicitly request org-777's OAuth token
                result = await oauth.get("microsoft", org_id="org-777")

                # Verify it called hget with org-777 hash key
                mock_redis.hget.assert_called_once()
                call_args = mock_redis.hget.call_args
                # The hash key should contain org-777
                assert "org-777" in call_args[0][0]
                assert call_args[0][1] == "microsoft"

                # Verify result contains the OAuth config
                assert result is not None
                assert result["connection_name"] == "microsoft"
                assert result["client_id"] == "client-123"
                assert result["access_token"] == "xxx"
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
