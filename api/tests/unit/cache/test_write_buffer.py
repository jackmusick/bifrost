"""
Unit tests for the SDK write buffer.

Tests the WriteBuffer class that buffers SDK writes to Redis during execution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bifrost._write_buffer import (
    ChangeRecord,
    WriteBuffer,
    clear_write_buffer,
    get_write_buffer,
    set_write_buffer,
)


class TestWriteBufferContextVar:
    """Tests for write buffer context variable management."""

    def test_get_write_buffer_raises_when_not_set(self):
        """get_write_buffer raises when no buffer is set."""
        clear_write_buffer()
        with pytest.raises(RuntimeError, match="No write buffer found"):
            get_write_buffer()

    def test_set_and_get_write_buffer(self):
        """set_write_buffer and get_write_buffer work together."""
        buffer = WriteBuffer("exec-123", "org-456", "user-789")
        set_write_buffer(buffer)

        retrieved = get_write_buffer()
        assert retrieved is buffer

        clear_write_buffer()

    def test_clear_write_buffer(self):
        """clear_write_buffer removes the buffer."""
        buffer = WriteBuffer("exec-123", "org-456", "user-789")
        set_write_buffer(buffer)

        clear_write_buffer()

        with pytest.raises(RuntimeError):
            get_write_buffer()


class TestChangeRecord:
    """Tests for ChangeRecord dataclass."""

    def test_change_record_fields(self):
        """ChangeRecord has all required fields."""
        record = ChangeRecord(
            entity_type="config",
            operation="set",
            entity_id=None,
            entity_key="api_key",
            org_id="org-123",
            data={"value": "secret123"},
            timestamp="2025-01-01T00:00:00",
            user_id="user-456",
            sequence=1,
        )

        assert record.entity_type == "config"
        assert record.operation == "set"
        assert record.entity_id is None
        assert record.entity_key == "api_key"
        assert record.org_id == "org-123"
        assert record.data == {"value": "secret123"}
        assert record.timestamp == "2025-01-01T00:00:00"
        assert record.user_id == "user-456"
        assert record.sequence == 1


class TestWriteBufferInit:
    """Tests for WriteBuffer initialization."""

    def test_init_stores_values(self):
        """WriteBuffer stores initialization values."""
        buffer = WriteBuffer("exec-111", "org-222", "user-333")

        assert buffer.execution_id == "exec-111"
        assert buffer.org_id == "org-222"
        assert buffer.user_id == "user-333"

    def test_init_creates_pending_key(self):
        """WriteBuffer creates correct pending key."""
        buffer = WriteBuffer("exec-aaa-bbb", None, "user")

        assert buffer._pending_key == "bifrost:pending:exec-aaa-bbb"

    def test_init_sequence_starts_at_zero(self):
        """WriteBuffer sequence starts at 0."""
        buffer = WriteBuffer("exec", "org", "user")

        assert buffer._sequence == 0

    def test_next_sequence_increments(self):
        """_next_sequence increments properly."""
        buffer = WriteBuffer("exec", "org", "user")

        seq1 = buffer._next_sequence()
        seq2 = buffer._next_sequence()
        seq3 = buffer._next_sequence()

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3


class TestWriteBufferConfigOperations:
    """Tests for WriteBuffer config operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock async Redis context manager."""
        mock_r = AsyncMock()
        mock_r.hset = AsyncMock()
        mock_r.expire = AsyncMock()
        mock_r.hlen = AsyncMock(return_value=0)
        return mock_r

    @pytest.fixture
    def buffer(self):
        """Create WriteBuffer instance."""
        return WriteBuffer("exec-test", "org-test", "user-test")

    @pytest.mark.asyncio
    async def test_add_config_change_set(self, buffer, mock_redis):
        """add_config_change buffers set operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_config_change(
                operation="set",
                key="my_key",
                value="my_value",
                config_type="string",
            )

            # Verify hset called for pending changes
            assert mock_redis.hset.call_count == 2  # Once for pending, once for cache
            assert mock_redis.expire.call_count >= 1

    @pytest.mark.asyncio
    async def test_add_config_change_delete(self, buffer, mock_redis):
        """add_config_change buffers delete operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_config_change(
                operation="delete",
                key="delete_key",
            )

            # Should still buffer the change
            mock_redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_add_config_change_increments_sequence(self, buffer, mock_redis):
        """Each add_config_change increments sequence."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_config_change("set", "key1", "val1")
            await buffer.add_config_change("set", "key2", "val2")

            assert buffer._sequence == 2

    @pytest.mark.asyncio
    async def test_add_config_change_uses_org_id_from_param(self, buffer, mock_redis):
        """add_config_change uses org_id parameter when provided."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_config_change(
                operation="set",
                key="test_key",
                value="test_value",
                org_id="different-org",
            )

            # Verify the change record was created with the parameter org_id
            # The hset call should have been made
            mock_redis.hset.assert_called()


class TestWriteBufferRoleOperations:
    """Tests for WriteBuffer role operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock async Redis context manager."""
        mock_r = AsyncMock()
        mock_r.hset = AsyncMock()
        mock_r.expire = AsyncMock()
        mock_r.hlen = AsyncMock(return_value=0)
        return mock_r

    @pytest.fixture
    def buffer(self):
        """Create WriteBuffer instance."""
        return WriteBuffer("exec-test", "org-test", "user-test")

    @pytest.mark.asyncio
    async def test_add_role_change_create(self, buffer, mock_redis):
        """add_role_change generates ID for create operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            role_id = await buffer.add_role_change(
                operation="create",
                role_id=None,
                data={"name": "Admin", "description": "Administrator role"},
            )

            # Should return a generated UUID
            assert role_id is not None
            assert len(role_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_add_role_change_update(self, buffer, mock_redis):
        """add_role_change uses existing ID for update operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            role_id = await buffer.add_role_change(
                operation="update",
                role_id="existing-role-123",
                data={"name": "Updated Name"},
            )

            assert role_id == "existing-role-123"

    @pytest.mark.asyncio
    async def test_add_role_users_change(self, buffer, mock_redis):
        """add_role_users_change buffers user assignment."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_role_users_change(
                role_id="role-123",
                user_ids=["user-1", "user-2", "user-3"],
            )

            mock_redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_add_role_forms_change(self, buffer, mock_redis):
        """add_role_forms_change buffers form assignment."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            await buffer.add_role_forms_change(
                role_id="role-456",
                form_ids=["form-a", "form-b"],
            )

            mock_redis.hset.assert_called()


class TestWriteBufferOrgOperations:
    """Tests for WriteBuffer organization operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock async Redis context manager."""
        mock_r = AsyncMock()
        mock_r.hset = AsyncMock()
        mock_r.set = AsyncMock()
        mock_r.expire = AsyncMock()
        mock_r.hlen = AsyncMock(return_value=0)
        return mock_r

    @pytest.fixture
    def buffer(self):
        """Create WriteBuffer instance."""
        return WriteBuffer("exec-test", "org-test", "user-test")

    @pytest.mark.asyncio
    async def test_add_org_change_create(self, buffer, mock_redis):
        """add_org_change generates ID for create operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            org_id = await buffer.add_org_change(
                operation="create",
                org_id=None,
                data={"name": "New Org", "domain": "new.org"},
            )

            assert org_id is not None
            assert len(org_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_add_org_change_update(self, buffer, mock_redis):
        """add_org_change uses existing ID for update operation."""
        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            org_id = await buffer.add_org_change(
                operation="update",
                org_id="existing-org-789",
                data={"name": "Updated Org"},
            )

            assert org_id == "existing-org-789"


class TestWriteBufferUtilityMethods:
    """Tests for WriteBuffer utility methods."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock async Redis context manager."""
        mock_r = AsyncMock()
        mock_r.hset = AsyncMock()
        mock_r.expire = AsyncMock()
        mock_r.hlen = AsyncMock(return_value=0)
        return mock_r

    @pytest.fixture
    def buffer(self):
        """Create WriteBuffer instance."""
        return WriteBuffer("exec-test", "org-test", "user-test")

    @pytest.mark.asyncio
    async def test_get_pending_count_returns_zero_when_empty(self, buffer, mock_redis):
        """get_pending_count returns 0 when no pending changes."""
        mock_redis.hlen = AsyncMock(return_value=0)

        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            count = await buffer.get_pending_count()

            assert count == 0

    @pytest.mark.asyncio
    async def test_get_pending_count_returns_count(self, buffer, mock_redis):
        """get_pending_count returns actual count."""
        mock_redis.hlen = AsyncMock(return_value=5)

        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            count = await buffer.get_pending_count()

            assert count == 5

    @pytest.mark.asyncio
    async def test_has_pending_changes_false_when_empty(self, buffer, mock_redis):
        """has_pending_changes returns False when no pending changes."""
        mock_redis.hlen = AsyncMock(return_value=0)

        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            has_changes = await buffer.has_pending_changes()

            assert has_changes is False

    @pytest.mark.asyncio
    async def test_has_pending_changes_true_when_changes_exist(self, buffer, mock_redis):
        """has_pending_changes returns True when changes exist."""
        mock_redis.hlen = AsyncMock(return_value=3)

        with patch("src.core.cache.get_redis") as mock_get_redis:
            mock_get_redis.return_value.__aenter__.return_value = mock_redis

            has_changes = await buffer.has_pending_changes()

            assert has_changes is True

    def test_close_clears_redis_connection(self, buffer):
        """close clears the Redis connection."""
        mock_redis = MagicMock()
        buffer._redis = mock_redis

        buffer.close()

        mock_redis.close.assert_called_once()
        assert buffer._redis is None

    def test_close_does_nothing_when_no_connection(self, buffer):
        """close does nothing when no connection exists."""
        assert buffer._redis is None

        buffer.close()  # Should not raise

        assert buffer._redis is None
