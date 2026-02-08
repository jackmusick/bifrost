"""
Unit tests for Distributed Lock Service.

Tests the Redis-based distributed locking for exclusive operations.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock


class TestLockInfo:
    """Tests for LockInfo dataclass."""

    def test_to_dict(self):
        """Test converting LockInfo to dict."""
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        expires = now + timedelta(seconds=300)

        lock_info = LockInfo(
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="file_upload",
            locked_at=now,
            expires_at=expires,
        )

        result = lock_info.to_dict()

        assert result["owner_user_id"] == "user-123"
        assert result["owner_email"] == "user@example.com"
        assert result["operation"] == "file_upload"
        assert result["locked_at"] == now.isoformat()
        assert result["expires_at"] == expires.isoformat()

    def test_from_dict(self):
        """Test creating LockInfo from dict."""
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        expires = now + timedelta(seconds=300)

        data = {
            "owner_user_id": "user-456",
            "owner_email": "another@example.com",
            "operation": "github_setup",
            "locked_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }

        lock_info = LockInfo.from_dict(data)

        assert lock_info.owner_user_id == "user-456"
        assert lock_info.owner_email == "another@example.com"
        assert lock_info.operation == "github_setup"
        assert lock_info.locked_at == now
        assert lock_info.expires_at == expires


class TestDistributedLockService:
    """Tests for DistributedLockService."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis instance."""
        redis = AsyncMock()
        redis.setnx = AsyncMock()
        redis.expire = AsyncMock()
        redis.get = AsyncMock()
        redis.delete = AsyncMock()
        redis.setex = AsyncMock()
        redis.aclose = AsyncMock()
        return redis

    @pytest.fixture
    def lock_service(self, mock_redis):
        """Create a lock service with mocked Redis."""
        from src.core.locks import DistributedLockService

        service = DistributedLockService()
        service._redis = mock_redis
        return service

    async def test_acquire_lock_success(self, lock_service, mock_redis):
        """Test successful lock acquisition."""
        mock_redis.setnx.return_value = True

        success, existing = await lock_service.acquire_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
            ttl_seconds=300,
        )

        assert success is True
        assert existing is None
        mock_redis.setnx.assert_called_once()
        mock_redis.expire.assert_called_once()

        # Verify the key contains correct prefix
        call_args = mock_redis.setnx.call_args
        assert call_args[0][0] == "bifrost:lock:test_lock"

    async def test_acquire_lock_already_held(self, lock_service, mock_redis):
        """Test lock acquisition when lock is already held."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        mock_redis.setnx.return_value = False

        # Set up existing lock info
        now = datetime.utcnow()
        existing_lock = LockInfo(
            owner_user_id="other-user",
            owner_email="other@example.com",
            operation="other_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(existing_lock.to_dict())

        success, existing = await lock_service.acquire_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
        )

        assert success is False
        assert existing is not None
        assert existing.owner_user_id == "other-user"
        assert existing.owner_email == "other@example.com"

    async def test_release_lock_success(self, lock_service, mock_redis):
        """Test successful lock release by owner."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())
        mock_redis.delete.return_value = 1

        result = await lock_service.release_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
        )

        assert result is True
        mock_redis.delete.assert_called_once_with("bifrost:lock:test_lock")

    async def test_release_lock_not_owner(self, lock_service, mock_redis):
        """Test lock release denied when not owner."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="other-user",
            owner_email="other@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())

        result = await lock_service.release_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
        )

        assert result is False
        mock_redis.delete.assert_not_called()

    async def test_release_lock_not_locked(self, lock_service, mock_redis):
        """Test lock release when lock doesn't exist."""
        mock_redis.get.return_value = None

        result = await lock_service.release_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
        )

        assert result is False

    async def test_extend_lock_success(self, lock_service, mock_redis):
        """Test successful lock extension by owner."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=100),  # About to expire
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())

        result = await lock_service.extend_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
            additional_seconds=300,
        )

        assert result is True
        mock_redis.setex.assert_called_once()

    async def test_extend_lock_not_owner(self, lock_service, mock_redis):
        """Test lock extension denied when not owner."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="other-user",
            owner_email="other@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())

        result = await lock_service.extend_lock(
            lock_name="test_lock",
            owner_user_id="user-123",
            additional_seconds=300,
        )

        assert result is False
        mock_redis.setex.assert_not_called()

    async def test_get_lock_info_exists(self, lock_service, mock_redis):
        """Test getting info for existing lock."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())

        result = await lock_service.get_lock_info("test_lock")

        assert result is not None
        assert result.owner_user_id == "user-123"
        assert result.owner_email == "user@example.com"

    async def test_get_lock_info_not_exists(self, lock_service, mock_redis):
        """Test getting info for non-existent lock."""
        mock_redis.get.return_value = None

        result = await lock_service.get_lock_info("test_lock")

        assert result is None

    async def test_is_locked_true(self, lock_service, mock_redis):
        """Test is_locked returns True when locked."""
        from datetime import datetime, timedelta
        from src.core.locks import LockInfo

        now = datetime.utcnow()
        lock_info = LockInfo(
            owner_user_id="user-123",
            owner_email="user@example.com",
            operation="test_operation",
            locked_at=now,
            expires_at=now + timedelta(seconds=300),
        )
        mock_redis.get.return_value = json.dumps(lock_info.to_dict())

        result = await lock_service.is_locked("test_lock")

        assert result is True

    async def test_is_locked_false(self, lock_service, mock_redis):
        """Test is_locked returns False when not locked."""
        mock_redis.get.return_value = None

        result = await lock_service.is_locked("test_lock")

        assert result is False

    async def test_force_release_lock_success(self, lock_service, mock_redis):
        """Test force release of lock."""
        mock_redis.delete.return_value = 1

        result = await lock_service.force_release_lock("test_lock")

        assert result is True
        mock_redis.delete.assert_called_once_with("bifrost:lock:test_lock")

    async def test_force_release_lock_not_exists(self, lock_service, mock_redis):
        """Test force release when lock doesn't exist."""
        mock_redis.delete.return_value = 0

        result = await lock_service.force_release_lock("test_lock")

        assert result is False

    async def test_close(self, lock_service, mock_redis):
        """Test closing Redis connection."""
        await lock_service.close()

        mock_redis.aclose.assert_called_once()
        assert lock_service._redis is None


class TestLockServiceSingleton:
    """Tests for lock service singleton functions."""

    def test_get_lock_service_returns_singleton(self):
        """Test that get_lock_service returns same instance."""
        import src.core.locks as module

        # Reset singleton
        module._lock_service = None

        from src.core.locks import get_lock_service

        service1 = get_lock_service()
        service2 = get_lock_service()

        assert service1 is service2

        # Cleanup
        module._lock_service = None

    async def test_close_lock_service(self):
        """Test closing singleton lock service."""
        import src.core.locks as module

        # Reset singleton
        module._lock_service = None

        from src.core.locks import get_lock_service, close_lock_service

        get_lock_service()  # Creates singleton
        assert module._lock_service is not None

        await close_lock_service()
        assert module._lock_service is None
