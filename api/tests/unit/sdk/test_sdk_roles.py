"""
Unit tests for Bifrost Roles SDK module.

Tests platform mode (inside workflows) only.
Uses mocked dependencies for fast, isolated testing.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from bifrost._context import set_execution_context, clear_execution_context


@pytest.fixture
def test_org_id():
    """Return a test organization ID."""
    return str(uuid4())


@pytest.fixture
def test_context(test_org_id):
    """Create execution context for platform mode testing."""
    from src.sdk.context import ExecutionContext, Organization

    org = Organization(id=test_org_id, name="Test Org", is_active=True)
    return ExecutionContext(
        user_id="test-user",
        email="test@example.com",
        name="Test User",
        scope=test_org_id,
        organization=org,
        is_platform_admin=False,
        is_function_key=False,
        execution_id="test-exec-123",
    )


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
def mock_redis():
    """Create mock Redis client."""
    mock = MagicMock()
    mock.hget = AsyncMock()
    mock.hgetall = AsyncMock()
    mock.hset = AsyncMock()
    mock.smembers = AsyncMock()
    return mock


@pytest.fixture
def mock_write_buffer():
    """Create mock write buffer."""
    mock = MagicMock()
    mock.add_role_change = AsyncMock()
    mock.add_role_users_change = AsyncMock()
    mock.add_role_forms_change = AsyncMock()
    return mock


class TestRolesPlatformMode:
    """Test roles SDK methods in platform mode (inside workflows)."""

    @pytest.fixture(autouse=True)
    def cleanup_context(self):
        """Ensure context is cleared after each test."""
        yield
        clear_execution_context()

    @pytest.mark.asyncio
    async def test_list_returns_roles_from_cache(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list() returns roles from Redis cache."""
        from bifrost import roles

        set_execution_context(test_context)

        # Mock Redis data
        role1_id = str(uuid4())
        role2_id = str(uuid4())

        role1_data = {
            "id": role1_id,
            "name": "Admin",
            "description": "Administrator role",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        role2_data = {
            "id": role2_id,
            "name": "User",
            "description": "Standard user role",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hgetall.return_value = {
            role1_id: json.dumps(role1_data),
            role2_id: json.dumps(role2_data),
        }

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list()

        assert len(result) == 2
        # Results should be sorted by name
        assert result[0].name == "Admin"
        assert result[1].name == "User"
        assert result[0].id == role1_id
        assert result[1].id == role2_id

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_roles(
        self, test_context, mock_redis
    ):
        """Test that roles.list() returns empty list when no roles exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hgetall.return_value = {}

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_uses_context_org_id(self, test_context, test_org_id, mock_redis):
        """Test that roles.list() uses context.org_id for cache key."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hgetall.return_value = {}

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await roles.list()

        # Verify hgetall was called with correct key
        call_args = mock_redis.hgetall.call_args
        assert call_args is not None
        # Should use roles_hash_key(org_id) - format: bifrost:org:{org_id}:roles
        key_str = str(call_args[0][0])
        assert ":roles" in key_str
        assert test_org_id in key_str

    @pytest.mark.asyncio
    async def test_list_skips_invalid_json_entries(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list() gracefully skips invalid JSON entries."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        valid_data = {
            "id": role_id,
            "name": "Valid Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hgetall.return_value = {
            role_id: json.dumps(valid_data),
            "bad-role": "invalid-json{",
        }

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list()

        # Should only return the valid role
        assert len(result) == 1
        assert result[0].name == "Valid Role"

    @pytest.mark.asyncio
    async def test_get_returns_role_data(self, test_context, test_org_id, mock_redis):
        """Test that roles.get() returns complete role data."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        now = datetime.utcnow()

        role_data = {
            "id": role_id,
            "name": "Customer Manager",
            "description": "Manages customer data",
            "is_active": True,
            "created_by": "admin-user",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(role_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.get(role_id)

        assert result.id == role_id
        assert result.name == "Customer Manager"
        assert result.description == "Manages customer data"
        assert result.is_active is True
        assert result.created_by == "admin-user"

    @pytest.mark.asyncio
    async def test_get_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.get() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.get("nonexistent-role-id")

    @pytest.mark.asyncio
    async def test_get_raises_when_invalid_json(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.get() raises ValueError for invalid JSON data."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = "invalid-json{"

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Invalid role data"):
                await roles.get("role-123")

    @pytest.mark.asyncio
    async def test_create_queues_to_write_buffer(
        self, test_context, test_org_id, mock_write_buffer
    ):
        """Test that roles.create() queues change to write buffer."""
        from bifrost import roles

        set_execution_context(test_context)

        new_role_id = str(uuid4())
        mock_write_buffer.add_role_change.return_value = new_role_id

        with patch("bifrost.roles.get_write_buffer", return_value=mock_write_buffer):
            result = await roles.create(
                name="New Role", description="Test role description"
            )

        # Verify buffer was called
        mock_write_buffer.add_role_change.assert_called_once()
        call_args = mock_write_buffer.add_role_change.call_args

        assert call_args[1]["operation"] == "create"
        assert call_args[1]["role_id"] is None
        assert call_args[1]["data"]["name"] == "New Role"
        assert call_args[1]["data"]["description"] == "Test role description"
        assert call_args[1]["org_id"] == test_org_id

        # Verify returned role schema
        assert result.id == new_role_id
        assert result.name == "New Role"
        assert result.description == "Test role description"
        assert result.is_active is True
        assert result.created_by == "test-user"

    @pytest.mark.asyncio
    async def test_create_with_global_scope(self, admin_context, mock_write_buffer):
        """Test that roles.create() handles global scope correctly."""
        from bifrost import roles
        from src.sdk.context import ExecutionContext, Organization

        # Context with GLOBAL scope
        org = Organization(id="GLOBAL", name="Global", is_active=True)
        global_context = ExecutionContext(
            user_id="admin-user",
            email="admin@example.com",
            name="Admin User",
            scope="GLOBAL",
            organization=org,
            is_platform_admin=True,
            is_function_key=False,
            execution_id="global-exec-123",
        )

        set_execution_context(global_context)

        new_role_id = str(uuid4())
        mock_write_buffer.add_role_change.return_value = new_role_id

        with patch("bifrost.roles.get_write_buffer", return_value=mock_write_buffer):
            await roles.create(name="Global Role")

        # Verify org_id is None for global scope
        call_args = mock_write_buffer.add_role_change.call_args
        assert call_args[1]["org_id"] is None

    @pytest.mark.asyncio
    async def test_update_queues_to_write_buffer(
        self, test_context, test_org_id, mock_redis, mock_write_buffer
    ):
        """Test that roles.update() queues change to write buffer."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())

        existing_data = {
            "id": role_id,
            "name": "Old Name",
            "description": "Old description",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with patch(
                "bifrost.roles.get_write_buffer", return_value=mock_write_buffer
            ):
                result = await roles.update(
                    role_id, name="New Name", description="New description"
                )

        # Verify buffer was called
        mock_write_buffer.add_role_change.assert_called_once()
        call_args = mock_write_buffer.add_role_change.call_args

        assert call_args[1]["operation"] == "update"
        assert call_args[1]["role_id"] == role_id
        assert call_args[1]["data"]["name"] == "New Name"
        assert call_args[1]["data"]["description"] == "New description"

        # Verify returned schema
        assert result.id == role_id
        assert result.name == "New Name"
        assert result.description == "New description"

    @pytest.mark.asyncio
    async def test_update_preserves_unmodified_fields(
        self, test_context, test_org_id, mock_redis, mock_write_buffer
    ):
        """Test that roles.update() preserves fields not being updated."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())

        existing_data = {
            "id": role_id,
            "name": "Existing Name",
            "description": "Existing description",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with patch(
                "bifrost.roles.get_write_buffer", return_value=mock_write_buffer
            ):
                # Only update description
                await roles.update(role_id, description="Updated description")

        # Verify name is preserved
        call_args = mock_write_buffer.add_role_change.call_args
        assert call_args[1]["data"]["name"] == "Existing Name"
        assert call_args[1]["data"]["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.update() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.update("nonexistent-role-id", name="New Name")

    @pytest.mark.asyncio
    async def test_delete_queues_to_write_buffer(
        self, test_context, test_org_id, mock_redis, mock_write_buffer
    ):
        """Test that roles.delete() queues change to write buffer."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())

        existing_data = {
            "id": role_id,
            "name": "Role to Delete",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with patch(
                "bifrost.roles.get_write_buffer", return_value=mock_write_buffer
            ):
                await roles.delete(role_id)

        # Verify buffer was called
        mock_write_buffer.add_role_change.assert_called_once()
        call_args = mock_write_buffer.add_role_change.call_args

        assert call_args[1]["operation"] == "delete"
        assert call_args[1]["role_id"] == role_id
        assert call_args[1]["data"] == {}

    @pytest.mark.asyncio
    async def test_delete_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.delete() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.delete("nonexistent-role-id")

    @pytest.mark.asyncio
    async def test_list_users_returns_user_ids(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_users() returns list of user IDs."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        user_ids = {"user-1", "user-2", "user-3"}

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)
        mock_redis.smembers.return_value = user_ids

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list_users(role_id)

        assert len(result) == 3
        assert set(result) == user_ids

    @pytest.mark.asyncio
    async def test_list_users_returns_empty_list_when_no_assignments(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_users() returns empty list when no users assigned."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)
        mock_redis.smembers.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list_users(role_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_users_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_users() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.list_users("nonexistent-role-id")

    @pytest.mark.asyncio
    async def test_list_forms_returns_form_ids(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_forms() returns list of form IDs."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        form_ids = {"form-1", "form-2"}

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)
        mock_redis.smembers.return_value = form_ids

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list_forms(role_id)

        assert len(result) == 2
        assert set(result) == form_ids

    @pytest.mark.asyncio
    async def test_list_forms_returns_empty_list_when_no_assignments(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_forms() returns empty list when no forms assigned."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)
        mock_redis.smembers.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            result = await roles.list_forms(role_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_forms_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.list_forms() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.list_forms("nonexistent-role-id")

    @pytest.mark.asyncio
    async def test_assign_users_queues_to_write_buffer(
        self, test_context, test_org_id, mock_redis, mock_write_buffer
    ):
        """Test that roles.assign_users() queues change to write buffer."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        user_ids = ["user-1", "user-2", "user-3"]

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with patch(
                "bifrost.roles.get_write_buffer", return_value=mock_write_buffer
            ):
                await roles.assign_users(role_id, user_ids)

        # Verify buffer was called
        mock_write_buffer.add_role_users_change.assert_called_once()
        call_args = mock_write_buffer.add_role_users_change.call_args

        assert call_args[1]["role_id"] == role_id
        assert call_args[1]["user_ids"] == user_ids
        assert call_args[1]["org_id"] == test_org_id

    @pytest.mark.asyncio
    async def test_assign_users_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.assign_users() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.assign_users("nonexistent-role-id", ["user-1"])

    @pytest.mark.asyncio
    async def test_assign_forms_queues_to_write_buffer(
        self, test_context, test_org_id, mock_redis, mock_write_buffer
    ):
        """Test that roles.assign_forms() queues change to write buffer."""
        from bifrost import roles

        set_execution_context(test_context)

        role_id = str(uuid4())
        form_ids = ["form-1", "form-2"]

        existing_data = {
            "id": role_id,
            "name": "Test Role",
            "description": "",
            "is_active": True,
            "created_by": "system",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_redis.hget.return_value = json.dumps(existing_data)

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with patch(
                "bifrost.roles.get_write_buffer", return_value=mock_write_buffer
            ):
                await roles.assign_forms(role_id, form_ids)

        # Verify buffer was called
        mock_write_buffer.add_role_forms_change.assert_called_once()
        call_args = mock_write_buffer.add_role_forms_change.call_args

        assert call_args[1]["role_id"] == role_id
        assert call_args[1]["form_ids"] == form_ids
        assert call_args[1]["org_id"] == test_org_id

    @pytest.mark.asyncio
    async def test_assign_forms_raises_when_role_not_found(
        self, test_context, test_org_id, mock_redis
    ):
        """Test that roles.assign_forms() raises ValueError when role doesn't exist."""
        from bifrost import roles

        set_execution_context(test_context)

        mock_redis.hget.return_value = None

        with patch("bifrost.roles.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            with pytest.raises(ValueError, match="Role not found"):
                await roles.assign_forms("nonexistent-role-id", ["form-1"])

    @pytest.mark.asyncio
    async def test_all_methods_require_platform_context(self):
        """Test that all roles methods require execution context."""
        from bifrost import roles

        clear_execution_context()

        # Test methods that should fail without context
        with pytest.raises(RuntimeError, match="execution context"):
            await roles.list()

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.get("role-123")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.create("Test Role")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.update("role-123", name="New Name")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.delete("role-123")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.list_users("role-123")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.list_forms("role-123")

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.assign_users("role-123", ["user-1"])

        with pytest.raises(RuntimeError, match="execution context"):
            await roles.assign_forms("role-123", ["form-1"])
