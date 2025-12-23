"""
Unit tests for Bifrost Organizations SDK module.

Tests platform mode (inside workflows) operations.
Organizations module is admin-only and does not support external mode.
Uses mocked dependencies for fast, isolated testing.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def admin_context(test_org_id):
    """Create platform admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="admin-user",
        email="admin@example.com",
        name="Admin User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=True,
        is_function_key=False,
        execution_id="admin-exec-456",
    )


@pytest.fixture
def non_admin_context(test_org_id):
    """Create non-admin execution context."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="regular-user",
        email="user@example.com",
        name="Regular User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="user-exec-789",
    )


class TestOrganizationsPlatformMode:
    """Test organizations SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_list_returns_organizations_from_cache(self, admin_context):
        """Test that organizations.list() returns organizations from Redis cache."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org1_id = str(uuid4())
        org2_id = str(uuid4())

        # Mock Redis cache with organization data
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=[org1_id, org2_id])

        org1_data = {
            "id": org1_id,
            "name": "Organization Alpha",
            "domain": "alpha.com",
            "is_active": True,
            "created_by": "system",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        org2_data = {
            "id": org2_id,
            "name": "Organization Beta",
            "domain": "beta.com",
            "is_active": True,
            "created_by": "system",
            "created_at": "2025-01-02T00:00:00",
            "updated_at": "2025-01-02T00:00:00",
        }

        # Mock get() to return org data
        mock_redis.get = AsyncMock(
            side_effect=[json.dumps(org1_data), json.dumps(org2_data)]
        )

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.list()

        assert len(result) == 2
        # Verify sorting by name
        assert result[0].name == "Organization Alpha"
        assert result[1].name == "Organization Beta"
        assert result[0].id == org1_id
        assert result[1].id == org2_id
        assert result[0].domain == "alpha.com"
        assert result[1].domain == "beta.com"

    @pytest.mark.asyncio
    async def test_list_filters_inactive_organizations(self, admin_context):
        """Test that organizations.list() filters out inactive organizations."""
        from bifrost import organizations

        set_execution_context(admin_context)

        active_org_id = str(uuid4())
        inactive_org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=[active_org_id, inactive_org_id])

        active_org_data = {
            "id": active_org_id,
            "name": "Active Org",
            "is_active": True,
        }
        inactive_org_data = {
            "id": inactive_org_id,
            "name": "Inactive Org",
            "is_active": False,
        }

        mock_redis.get = AsyncMock(
            side_effect=[json.dumps(active_org_data), json.dumps(inactive_org_data)]
        )

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.list()

        # Should only return active organization
        assert len(result) == 1
        assert result[0].id == active_org_id
        assert result[0].name == "Active Org"

    @pytest.mark.asyncio
    async def test_list_returns_empty_when_no_organizations(self, admin_context):
        """Test that organizations.list() returns empty list when no orgs exist."""
        from bifrost import organizations

        set_execution_context(admin_context)

        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=[])

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_requires_admin_privileges(self, non_admin_context):
        """Test that organizations.list() requires admin privileges."""
        from bifrost import organizations

        set_execution_context(non_admin_context)

        with pytest.raises(PermissionError, match="not a platform admin"):
            await organizations.list()

    @pytest.mark.asyncio
    async def test_list_skips_invalid_json_in_cache(self, admin_context):
        """Test that organizations.list() skips organizations with invalid JSON."""
        from bifrost import organizations

        set_execution_context(admin_context)

        valid_org_id = str(uuid4())
        invalid_org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=[valid_org_id, invalid_org_id])

        valid_org_data = {
            "id": valid_org_id,
            "name": "Valid Org",
            "is_active": True,
        }

        # First call returns valid JSON, second returns invalid
        mock_redis.get = AsyncMock(
            side_effect=[json.dumps(valid_org_data), "invalid-json{"]
        )

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.list()

        # Should only return valid organization
        assert len(result) == 1
        assert result[0].id == valid_org_id

    @pytest.mark.asyncio
    async def test_get_returns_organization_data(self, admin_context):
        """Test that organizations.get() returns organization from Redis cache."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())
        org_data = {
            "id": org_id,
            "name": "Test Organization",
            "domain": "test.com",
            "is_active": True,
            "created_by": "admin-123",
            "created_at": "2025-01-15T10:00:00",
            "updated_at": "2025-01-20T15:30:00",
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(org_data))

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.get(org_id)

        assert result.id == org_id
        assert result.name == "Test Organization"
        assert result.domain == "test.com"
        assert result.is_active is True
        assert result.created_by == "admin-123"

    @pytest.mark.asyncio
    async def test_get_raises_when_organization_not_found(self, admin_context):
        """Test that organizations.get() raises ValueError when org not found."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with pytest.raises(ValueError, match="Organization not found"):
                await organizations.get(org_id)

    @pytest.mark.asyncio
    async def test_get_raises_when_invalid_json(self, admin_context):
        """Test that organizations.get() raises ValueError on invalid JSON."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value="invalid-json{")

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with pytest.raises(ValueError, match="Invalid organization data"):
                await organizations.get(org_id)

    @pytest.mark.asyncio
    async def test_get_works_for_non_admin_users(self, non_admin_context, test_org_id):
        """Test that organizations.get() works for non-admin users (read-only)."""
        from bifrost import organizations

        set_execution_context(non_admin_context)

        org_data = {
            "id": test_org_id,
            "name": "Regular Org",
            "is_active": True,
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(org_data))

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            result = await organizations.get(test_org_id)

        assert result.name == "Regular Org"

    @pytest.mark.asyncio
    async def test_create_queues_to_write_buffer(self, admin_context):
        """Test that organizations.create() queues change to write buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        new_org_id = str(uuid4())

        # Mock write buffer
        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock(return_value=new_org_id)

        with patch("bifrost.organizations.get_write_buffer", return_value=mock_buffer):
            result = await organizations.create(
                name="New Organization", domain="neworg.com", is_active=True
            )

        # Verify write buffer was called
        mock_buffer.add_org_change.assert_called_once_with(
            operation="create",
            org_id=None,
            data={
                "name": "New Organization",
                "domain": "neworg.com",
                "is_active": True,
            },
        )

        # Verify returned schema
        assert result.id == new_org_id
        assert result.name == "New Organization"
        assert result.domain == "neworg.com"
        assert result.is_active is True
        assert result.created_by == admin_context.user_id

    @pytest.mark.asyncio
    async def test_create_with_optional_domain(self, admin_context):
        """Test that organizations.create() works with optional domain."""
        from bifrost import organizations

        set_execution_context(admin_context)

        new_org_id = str(uuid4())

        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock(return_value=new_org_id)

        with patch("bifrost.organizations.get_write_buffer", return_value=mock_buffer):
            result = await organizations.create(name="Domain-less Org")

        # Verify data sent to buffer
        call_args = mock_buffer.add_org_change.call_args
        assert call_args[1]["data"]["name"] == "Domain-less Org"
        assert call_args[1]["data"]["domain"] is None
        assert call_args[1]["data"]["is_active"] is True

        assert result.domain is None

    @pytest.mark.asyncio
    async def test_create_requires_admin_privileges(self, non_admin_context):
        """Test that organizations.create() requires admin privileges."""
        from bifrost import organizations

        set_execution_context(non_admin_context)

        with pytest.raises(PermissionError, match="not a platform admin"):
            await organizations.create(name="Should Fail")

    @pytest.mark.asyncio
    async def test_update_queues_to_write_buffer(self, admin_context):
        """Test that organizations.update() queues change to write buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())
        existing_data = {
            "id": org_id,
            "name": "Old Name",
            "domain": "old.com",
            "is_active": True,
            "created_by": "system",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(existing_data))

        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock()

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with patch(
                "bifrost.organizations.get_write_buffer", return_value=mock_buffer
            ):
                result = await organizations.update(
                    org_id, name="New Name", domain="new.com"
                )

        # Verify write buffer was called
        mock_buffer.add_org_change.assert_called_once_with(
            operation="update",
            org_id=org_id,
            data={"name": "New Name", "domain": "new.com", "is_active": True},
        )

        # Verify returned schema
        assert result.id == org_id
        assert result.name == "New Name"
        assert result.domain == "new.com"

    @pytest.mark.asyncio
    async def test_update_with_partial_fields(self, admin_context):
        """Test that organizations.update() supports partial updates."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())
        existing_data = {
            "id": org_id,
            "name": "Existing Name",
            "domain": "existing.com",
            "is_active": True,
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(existing_data))

        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock()

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with patch(
                "bifrost.organizations.get_write_buffer", return_value=mock_buffer
            ):
                # Only update name
                result = await organizations.update(org_id, name="Updated Name")

        # Verify unchanged fields are preserved
        call_args = mock_buffer.add_org_change.call_args
        assert call_args[1]["data"]["name"] == "Updated Name"
        assert call_args[1]["data"]["domain"] == "existing.com"
        assert call_args[1]["data"]["is_active"] is True

        assert result.name == "Updated Name"
        assert result.domain == "existing.com"

    @pytest.mark.asyncio
    async def test_update_can_deactivate_organization(self, admin_context):
        """Test that organizations.update() can set is_active to False."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())
        existing_data = {
            "id": org_id,
            "name": "Active Org",
            "is_active": True,
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(existing_data))

        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock()

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with patch(
                "bifrost.organizations.get_write_buffer", return_value=mock_buffer
            ):
                result = await organizations.update(org_id, is_active=False)

        assert result.is_active is False

        call_args = mock_buffer.add_org_change.call_args
        assert call_args[1]["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_raises_when_organization_not_found(self, admin_context):
        """Test that organizations.update() raises ValueError when org not found."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with pytest.raises(ValueError, match="Organization not found"):
                await organizations.update(org_id, name="Should Fail")

    @pytest.mark.asyncio
    async def test_update_requires_admin_privileges(self, non_admin_context):
        """Test that organizations.update() requires admin privileges."""
        from bifrost import organizations

        set_execution_context(non_admin_context)

        with pytest.raises(PermissionError, match="not a platform admin"):
            await organizations.update(str(uuid4()), name="Should Fail")

    @pytest.mark.asyncio
    async def test_delete_queues_to_write_buffer(self, admin_context):
        """Test that organizations.delete() queues change to write buffer."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())
        existing_data = {
            "id": org_id,
            "name": "To Delete",
            "is_active": True,
        }

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(existing_data))

        mock_buffer = MagicMock()
        mock_buffer.add_org_change = AsyncMock()

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with patch(
                "bifrost.organizations.get_write_buffer", return_value=mock_buffer
            ):
                result = await organizations.delete(org_id)

        # Verify write buffer was called
        mock_buffer.add_org_change.assert_called_once_with(
            operation="delete",
            org_id=org_id,
            data={},
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_raises_when_organization_not_found(self, admin_context):
        """Test that organizations.delete() raises ValueError when org not found."""
        from bifrost import organizations

        set_execution_context(admin_context)

        org_id = str(uuid4())

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        @asynccontextmanager
        async def mock_get_redis():
            yield mock_redis

        with patch("bifrost.organizations.get_redis", mock_get_redis):
            with pytest.raises(ValueError, match="Organization not found"):
                await organizations.delete(org_id)

    @pytest.mark.asyncio
    async def test_delete_requires_admin_privileges(self, non_admin_context):
        """Test that organizations.delete() requires admin privileges."""
        from bifrost import organizations

        set_execution_context(non_admin_context)

        with pytest.raises(PermissionError, match="not a platform admin"):
            await organizations.delete(str(uuid4()))

    @pytest.mark.asyncio
    async def test_requires_execution_context(self):
        """Test that organizations methods require execution context."""
        from bifrost import organizations

        clear_execution_context()

        with pytest.raises(RuntimeError, match="No execution context"):
            await organizations.get(str(uuid4()))

        with pytest.raises(RuntimeError, match="No execution context"):
            await organizations.list()

        with pytest.raises(RuntimeError, match="No execution context"):
            await organizations.create(name="Should Fail")

        with pytest.raises(RuntimeError, match="No execution context"):
            await organizations.update(str(uuid4()), name="Should Fail")

        with pytest.raises(RuntimeError, match="No execution context"):
            await organizations.delete(str(uuid4()))
