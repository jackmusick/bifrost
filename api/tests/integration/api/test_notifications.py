"""
Integration tests for Notifications API.

Tests notification endpoints with real Redis backend.
These tests require Redis to be running (via docker-compose.test.yml).
"""

import pytest
import pytest_asyncio
from uuid import uuid4

from src.services.notification_service import (
    NotificationService,
    NOTIFICATION_KEY_PREFIX,
    USER_NOTIFICATIONS_PREFIX,
    ADMIN_NOTIFICATIONS_KEY,
)
from src.core.locks import (
    DistributedLockService,
)
from src.models.contracts.notifications import (
    NotificationCategory,
    NotificationCreate,
    NotificationStatus,
    NotificationUpdate,
)


@pytest.fixture
def test_user_id():
    """Generate unique user ID for test isolation."""
    return f"test-user-{uuid4()}"


@pytest.fixture
def test_admin_user_id():
    """Generate unique admin user ID for test isolation."""
    return f"test-admin-{uuid4()}"


@pytest_asyncio.fixture
async def notification_service():
    """Create a notification service connected to test Redis."""
    service = NotificationService()
    yield service
    await service.close()


@pytest_asyncio.fixture
async def lock_service():
    """Create a lock service connected to test Redis."""
    service = DistributedLockService()
    yield service
    await service.close()


@pytest_asyncio.fixture
async def redis_client():
    """Create a Redis client for test cleanup."""
    import os
    import redis.asyncio as async_redis
    redis_url = os.getenv("BIFROST_REDIS_URL", "redis://redis:6379/0")
    client = async_redis.from_url(redis_url, decode_responses=True)
    yield client
    await client.aclose()


class TestNotificationServiceIntegration:
    """Integration tests for NotificationService with real Redis."""

    async def test_create_and_get_notification(
        self, notification_service, test_user_id, redis_client
    ):
        """Test creating and retrieving a notification."""
        request = NotificationCreate(
            category=NotificationCategory.GITHUB_SETUP,
            title="Test Notification",
            description="Integration test notification",
        )

        # Create notification
        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
        )

        assert notification.id is not None
        assert notification.title == "Test Notification"
        assert notification.status == NotificationStatus.PENDING

        # Retrieve notification
        retrieved = await notification_service.get_notification(notification.id)

        assert retrieved is not None
        assert retrieved.id == notification.id
        assert retrieved.title == notification.title

        # Cleanup
        await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{notification.id}")
        await redis_client.srem(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}", notification.id)

    async def test_update_notification_status(
        self, notification_service, test_user_id, redis_client
    ):
        """Test updating notification status through lifecycle."""
        request = NotificationCreate(
            category=NotificationCategory.FILE_UPLOAD,
            title="File Upload",
            description="Starting upload...",
            percent=0.0,
        )

        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
        )

        # Update to running with progress
        update = NotificationUpdate(
            status=NotificationStatus.RUNNING,
            description="Uploading file 1 of 3...",
            percent=33.0,
        )
        updated = await notification_service.update_notification(notification.id, update)

        assert updated is not None
        assert updated.status == NotificationStatus.RUNNING
        assert updated.percent == 33.0

        # Update to completed
        update = NotificationUpdate(
            status=NotificationStatus.COMPLETED,
            description="Upload complete!",
            percent=100.0,
            result={"files_uploaded": 3},
        )
        updated = await notification_service.update_notification(notification.id, update)

        assert updated.status == NotificationStatus.COMPLETED
        assert updated.result == {"files_uploaded": 3}

        # Cleanup
        await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{notification.id}")
        await redis_client.srem(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}", notification.id)

    async def test_update_notification_to_failed(
        self, notification_service, test_user_id, redis_client
    ):
        """Test updating notification to failed state."""
        request = NotificationCreate(
            category=NotificationCategory.GITHUB_SETUP,
            title="GitHub Setup",
        )

        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
        )

        update = NotificationUpdate(
            status=NotificationStatus.FAILED,
            error="Connection refused: Could not reach GitHub API",
        )
        updated = await notification_service.update_notification(notification.id, update)

        assert updated.status == NotificationStatus.FAILED
        assert "Connection refused" in updated.error

        # Cleanup
        await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{notification.id}")
        await redis_client.srem(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}", notification.id)

    async def test_get_user_notifications(
        self, notification_service, test_user_id, redis_client
    ):
        """Test retrieving all notifications for a user."""
        # Create multiple notifications
        notification_ids = []
        for i in range(3):
            request = NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title=f"Test Notification {i}",
            )
            notification = await notification_service.create_notification(
                user_id=test_user_id,
                request=request,
            )
            notification_ids.append(notification.id)

        # Get all notifications
        notifications = await notification_service.get_user_notifications(test_user_id)

        assert len(notifications) >= 3  # May include other test notifications
        titles = [n.title for n in notifications]
        assert "Test Notification 0" in titles
        assert "Test Notification 1" in titles
        assert "Test Notification 2" in titles

        # Cleanup
        for nid in notification_ids:
            await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{nid}")
        await redis_client.delete(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}")

    async def test_dismiss_notification(
        self, notification_service, test_user_id, redis_client
    ):
        """Test dismissing a notification."""
        request = NotificationCreate(
            category=NotificationCategory.SYSTEM,
            title="Dismissable Notification",
        )

        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
        )

        # Dismiss notification
        result = await notification_service.dismiss_notification(
            notification_id=notification.id,
            user_id=test_user_id,
        )

        assert result is True

        # Verify it's gone
        retrieved = await notification_service.get_notification(notification.id)
        assert retrieved is None

    async def test_dismiss_notification_wrong_user(
        self, notification_service, test_user_id, redis_client
    ):
        """Test that users cannot dismiss other users' notifications."""
        request = NotificationCreate(
            category=NotificationCategory.SYSTEM,
            title="Protected Notification",
        )

        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
        )

        # Try to dismiss with different user
        result = await notification_service.dismiss_notification(
            notification_id=notification.id,
            user_id="different-user",
        )

        assert result is False

        # Verify it still exists
        retrieved = await notification_service.get_notification(notification.id)
        assert retrieved is not None

        # Cleanup
        await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{notification.id}")
        await redis_client.srem(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}", notification.id)

    async def test_admin_notifications(
        self, notification_service, test_user_id, test_admin_user_id, redis_client
    ):
        """Test admin notification visibility."""
        # Create a notification visible to admins
        request = NotificationCreate(
            category=NotificationCategory.SYSTEM,
            title="Admin Notification",
        )

        notification = await notification_service.create_notification(
            user_id=test_user_id,
            request=request,
            for_admins=True,
        )

        # Admin should see it with include_admin=True
        admin_notifications = await notification_service.get_user_notifications(
            test_admin_user_id,
            include_admin=True,
        )

        admin_notif_ids = [n.id for n in admin_notifications]
        assert notification.id in admin_notif_ids

        # Cleanup
        await redis_client.delete(f"{NOTIFICATION_KEY_PREFIX}{notification.id}")
        await redis_client.srem(f"{USER_NOTIFICATIONS_PREFIX}{test_user_id}", notification.id)
        await redis_client.srem(ADMIN_NOTIFICATIONS_KEY, notification.id)


class TestDistributedLockServiceIntegration:
    """Integration tests for DistributedLockService with real Redis."""

    async def test_acquire_and_release_lock(self, lock_service, test_user_id, redis_client):
        """Test basic lock acquisition and release."""
        lock_name = f"test-lock-{uuid4()}"

        # Acquire lock
        success, existing = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="test@example.com",
            operation="test_operation",
            ttl_seconds=60,
        )

        assert success is True
        assert existing is None

        # Verify lock exists
        lock_info = await lock_service.get_lock_info(lock_name)
        assert lock_info is not None
        assert lock_info.owner_user_id == test_user_id

        # Release lock
        released = await lock_service.release_lock(lock_name, test_user_id)
        assert released is True

        # Verify lock is gone
        lock_info = await lock_service.get_lock_info(lock_name)
        assert lock_info is None

    async def test_lock_contention(self, lock_service, test_user_id, redis_client):
        """Test that lock prevents concurrent acquisition."""
        lock_name = f"test-lock-{uuid4()}"
        other_user = f"other-user-{uuid4()}"

        # First user acquires lock
        success, _ = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="first@example.com",
            operation="first_operation",
        )
        assert success is True

        # Second user tries to acquire - should fail
        success, existing = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=other_user,
            owner_email="second@example.com",
            operation="second_operation",
        )
        assert success is False
        assert existing is not None
        assert existing.owner_user_id == test_user_id
        assert existing.owner_email == "first@example.com"

        # Cleanup
        await lock_service.release_lock(lock_name, test_user_id)

    async def test_lock_extension(self, lock_service, test_user_id, redis_client):
        """Test extending lock TTL."""
        lock_name = f"test-lock-{uuid4()}"

        # Acquire with short TTL
        success, _ = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="test@example.com",
            operation="test_operation",
            ttl_seconds=30,
        )
        assert success is True

        # Extend lock
        extended = await lock_service.extend_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            additional_seconds=300,
        )
        assert extended is True

        # Verify lock still exists with new expiration
        lock_info = await lock_service.get_lock_info(lock_name)
        assert lock_info is not None

        # Cleanup
        await lock_service.release_lock(lock_name, test_user_id)

    async def test_cannot_release_other_users_lock(
        self, lock_service, test_user_id, redis_client
    ):
        """Test that users cannot release locks they don't own."""
        lock_name = f"test-lock-{uuid4()}"
        other_user = f"other-user-{uuid4()}"

        # First user acquires lock
        success, _ = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="owner@example.com",
            operation="test_operation",
        )
        assert success is True

        # Other user tries to release - should fail
        released = await lock_service.release_lock(lock_name, other_user)
        assert released is False

        # Lock should still exist
        lock_info = await lock_service.get_lock_info(lock_name)
        assert lock_info is not None
        assert lock_info.owner_user_id == test_user_id

        # Cleanup
        await lock_service.release_lock(lock_name, test_user_id)

    async def test_force_release_lock(self, lock_service, test_user_id, redis_client):
        """Test force releasing a lock (admin operation)."""
        lock_name = f"test-lock-{uuid4()}"

        # Acquire lock
        success, _ = await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="test@example.com",
            operation="test_operation",
        )
        assert success is True

        # Force release (simulating admin action)
        released = await lock_service.force_release_lock(lock_name)
        assert released is True

        # Verify lock is gone
        lock_info = await lock_service.get_lock_info(lock_name)
        assert lock_info is None

    async def test_is_locked(self, lock_service, test_user_id, redis_client):
        """Test checking lock status."""
        lock_name = f"test-lock-{uuid4()}"

        # Should not be locked initially
        is_locked = await lock_service.is_locked(lock_name)
        assert is_locked is False

        # Acquire lock
        await lock_service.acquire_lock(
            lock_name=lock_name,
            owner_user_id=test_user_id,
            owner_email="test@example.com",
            operation="test_operation",
        )

        # Should be locked now
        is_locked = await lock_service.is_locked(lock_name)
        assert is_locked is True

        # Cleanup
        await lock_service.release_lock(lock_name, test_user_id)
