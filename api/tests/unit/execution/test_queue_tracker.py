"""
Unit tests for queue_tracker module.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.execution.queue_tracker import (
    add_to_queue,
    remove_from_queue,
    get_queue_position,
    get_queue_depth,
    get_all_queue_positions,
    publish_all_queue_positions,
    cleanup_stale_entries,
    QUEUE_KEY,
)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_get_redis(mock_redis):
    """Patch _get_redis to return our mock."""
    with patch(
        "src.services.execution.queue_tracker._get_redis",
        return_value=mock_redis
    ) as patched:
        yield patched


class TestAddToQueue:
    """Tests for add_to_queue function."""

    @pytest.mark.asyncio
    async def test_adds_execution_to_sorted_set(self, mock_get_redis, mock_redis):
        """Should add execution to Redis sorted set with timestamp."""
        mock_redis.zadd = AsyncMock()
        mock_redis.zrank = AsyncMock(return_value=0)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ):
            with patch("time.time", return_value=1000.0):
                position = await add_to_queue("exec-123")

        mock_redis.zadd.assert_called_once_with(
            QUEUE_KEY,
            {"exec-123": 1000.0}
        )
        assert position == 1  # 0-based rank + 1

    @pytest.mark.asyncio
    async def test_returns_correct_position(self, mock_get_redis, mock_redis):
        """Should return 1-based queue position."""
        mock_redis.zadd = AsyncMock()
        mock_redis.zrank = AsyncMock(return_value=4)  # 5th position (0-indexed)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ):
            position = await add_to_queue("exec-456")

        assert position == 5

    @pytest.mark.asyncio
    async def test_publishes_queue_positions_after_add(self, mock_get_redis, mock_redis):
        """Should publish position updates to all queued executions."""
        mock_redis.zadd = AsyncMock()
        mock_redis.zrank = AsyncMock(return_value=0)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ) as mock_publish:
            await add_to_queue("exec-789")

        mock_publish.assert_called_once()


class TestRemoveFromQueue:
    """Tests for remove_from_queue function."""

    @pytest.mark.asyncio
    async def test_removes_execution_from_sorted_set(self, mock_get_redis, mock_redis):
        """Should remove execution from Redis sorted set."""
        mock_redis.zrem = AsyncMock(return_value=1)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ):
            await remove_from_queue("exec-123")

        mock_redis.zrem.assert_called_once_with(QUEUE_KEY, "exec-123")

    @pytest.mark.asyncio
    async def test_publishes_positions_when_entry_removed(self, mock_get_redis, mock_redis):
        """Should publish position updates when entry is actually removed."""
        mock_redis.zrem = AsyncMock(return_value=1)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ) as mock_publish:
            await remove_from_queue("exec-123")

        mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_publish_when_entry_not_found(self, mock_get_redis, mock_redis):
        """Should not publish updates when entry wasn't in queue."""
        mock_redis.zrem = AsyncMock(return_value=0)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ) as mock_publish:
            await remove_from_queue("exec-nonexistent")

        mock_publish.assert_not_called()


class TestGetQueuePosition:
    """Tests for get_queue_position function."""

    @pytest.mark.asyncio
    async def test_returns_1_based_position(self, mock_get_redis, mock_redis):
        """Should convert 0-based rank to 1-based position."""
        mock_redis.zrank = AsyncMock(return_value=2)

        position = await get_queue_position("exec-123")

        assert position == 3

    @pytest.mark.asyncio
    async def test_returns_none_when_not_in_queue(self, mock_get_redis, mock_redis):
        """Should return None when execution is not in queue."""
        mock_redis.zrank = AsyncMock(return_value=None)

        position = await get_queue_position("exec-nonexistent")

        assert position is None


class TestGetQueueDepth:
    """Tests for get_queue_depth function."""

    @pytest.mark.asyncio
    async def test_returns_queue_size(self, mock_get_redis, mock_redis):
        """Should return cardinality of sorted set."""
        mock_redis.zcard = AsyncMock(return_value=5)

        depth = await get_queue_depth()

        assert depth == 5
        mock_redis.zcard.assert_called_once_with(QUEUE_KEY)


class TestGetAllQueuePositions:
    """Tests for get_all_queue_positions function."""

    @pytest.mark.asyncio
    async def test_returns_all_positions_in_order(self, mock_get_redis, mock_redis):
        """Should return all executions with 1-based positions."""
        mock_redis.zrange = AsyncMock(return_value=["exec-1", "exec-2", "exec-3"])

        positions = await get_all_queue_positions()

        assert positions == [
            ("exec-1", 1),
            ("exec-2", 2),
            ("exec-3", 3),
        ]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_queue_empty(self, mock_get_redis, mock_redis):
        """Should return empty list when no executions queued."""
        mock_redis.zrange = AsyncMock(return_value=[])

        positions = await get_all_queue_positions()

        assert positions == []


class TestPublishAllQueuePositions:
    """Tests for publish_all_queue_positions function."""

    @pytest.mark.asyncio
    async def test_publishes_update_for_each_queued_execution(self, mock_get_redis, mock_redis):
        """Should publish position update to each execution."""
        mock_redis.zrange = AsyncMock(return_value=["exec-1", "exec-2"])

        with patch(
            "src.core.pubsub.publish_execution_update",
            new_callable=AsyncMock
        ) as mock_publish:
            await publish_all_queue_positions()

        assert mock_publish.call_count == 2
        mock_publish.assert_any_call(
            "exec-1",
            "Pending",
            {"queuePosition": 1, "waitReason": "queued"}
        )
        mock_publish.assert_any_call(
            "exec-2",
            "Pending",
            {"queuePosition": 2, "waitReason": "queued"}
        )

    @pytest.mark.asyncio
    async def test_continues_on_individual_publish_failure(self, mock_get_redis, mock_redis):
        """Should continue publishing even if one fails."""
        mock_redis.zrange = AsyncMock(return_value=["exec-1", "exec-2", "exec-3"])

        publish_mock = AsyncMock()
        publish_mock.side_effect = [
            None,
            Exception("Publish failed"),
            None,
        ]

        with patch(
            "src.core.pubsub.publish_execution_update",
            publish_mock
        ):
            # Should not raise
            await publish_all_queue_positions()

        # All three should be attempted
        assert publish_mock.call_count == 3


class TestCleanupStaleEntries:
    """Tests for cleanup_stale_entries function."""

    @pytest.mark.asyncio
    async def test_removes_entries_older_than_max_age(self, mock_get_redis, mock_redis):
        """Should remove entries with timestamp older than cutoff."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=2)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ):
            with patch("time.time", return_value=1000.0):
                removed = await cleanup_stale_entries(max_age_seconds=600)

        # Cutoff should be 1000 - 600 = 400
        mock_redis.zremrangebyscore.assert_called_once_with(
            QUEUE_KEY,
            "-inf",
            400.0
        )
        assert removed == 2

    @pytest.mark.asyncio
    async def test_publishes_positions_when_entries_removed(self, mock_get_redis, mock_redis):
        """Should publish position updates when entries are cleaned."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=1)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ) as mock_publish:
            await cleanup_stale_entries()

        mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_publish_when_no_entries_removed(self, mock_get_redis, mock_redis):
        """Should not publish when no entries cleaned."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)

        with patch(
            "src.services.execution.queue_tracker.publish_all_queue_positions",
            new_callable=AsyncMock
        ) as mock_publish:
            await cleanup_stale_entries()

        mock_publish.assert_not_called()
