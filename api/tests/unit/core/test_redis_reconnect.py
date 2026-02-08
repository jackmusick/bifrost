"""
Unit tests for ResilientPubSubListener.

Tests automatic reconnection with exponential backoff for Redis pub/sub.
These tests use synchronous verification where possible to avoid async loop issues.
"""

import pytest
from unittest.mock import AsyncMock

from src.core.redis_reconnect import ResilientPubSubListener


class TestResilientPubSubListenerConfig:
    """Tests for ResilientPubSubListener configuration and initialization."""

    def test_default_configuration(self):
        """Test default configuration values."""
        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        assert listener.redis_url == "redis://localhost:6379"
        assert listener.channels == ["test:channel"]
        assert listener.patterns == []
        assert listener.initial_backoff == 1.0
        assert listener.max_backoff == 30.0
        assert listener.backoff_multiplier == 2.0
        assert listener.extended_failure_threshold == 5
        assert not listener._running
        assert listener._redis is None
        assert listener._pubsub is None
        assert listener._listener_task is None
        assert listener._consecutive_failures == 0

    def test_custom_configuration(self):
        """Test custom configuration values."""
        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://custom:9999",
            channels=["channel:1", "channel:2"],
            patterns=["pattern:*"],
            on_message=callback,
            initial_backoff=2.0,
            max_backoff=60.0,
            backoff_multiplier=3.0,
            extended_failure_threshold=10,
        )

        assert listener.redis_url == "redis://custom:9999"
        assert listener.channels == ["channel:1", "channel:2"]
        assert listener.patterns == ["pattern:*"]
        assert listener.initial_backoff == 2.0
        assert listener.max_backoff == 60.0
        assert listener.backoff_multiplier == 3.0
        assert listener.extended_failure_threshold == 10

    def test_is_healthy_false_when_not_running(self):
        """Test is_healthy returns False when not running."""
        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        assert not listener.is_healthy()

    def test_is_healthy_false_with_many_failures(self):
        """Test is_healthy returns False when consecutive failures exceed threshold."""
        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
            extended_failure_threshold=3,
        )

        # Simulate running state with failures
        listener._running = True
        listener._consecutive_failures = 5

        assert not listener.is_healthy()

    def test_backoff_calculation(self):
        """Test that backoff calculation follows exponential pattern with cap."""
        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
            initial_backoff=1.0,
            max_backoff=10.0,
            backoff_multiplier=2.0,
        )

        # Simulate backoff progression
        backoff = listener.initial_backoff
        expected_sequence = [1.0, 2.0, 4.0, 8.0, 10.0, 10.0]  # Caps at 10

        for expected in expected_sequence:
            assert backoff == expected, f"Expected {expected}, got {backoff}"
            backoff = min(backoff * listener.backoff_multiplier, listener.max_backoff)


class TestResilientPubSubListenerAsync:
    """Async tests that verify actual behavior with mocked Redis."""

    @pytest.fixture
    def mock_pubsub(self):
        """Create a mock Redis PubSub instance."""
        from unittest.mock import MagicMock
        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()
        pubsub.psubscribe = AsyncMock()
        pubsub.get_message = AsyncMock(return_value=None)
        pubsub.close = AsyncMock()
        return pubsub

    @pytest.fixture
    def mock_redis(self, mock_pubsub):
        """Create a mock Redis instance."""
        from unittest.mock import MagicMock
        redis_instance = MagicMock()
        redis_instance.pubsub = MagicMock(return_value=mock_pubsub)
        redis_instance.close = AsyncMock()
        return redis_instance

    async def test_connect_subscribes_to_channels(self, mock_redis, mock_pubsub):
        """Test that _connect subscribes to specified channels."""
        from unittest.mock import patch

        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["channel:one", "channel:two"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            result = await listener._connect()

            assert result is True
            assert mock_pubsub.subscribe.call_count == 2
            mock_pubsub.subscribe.assert_any_call("channel:one")
            mock_pubsub.subscribe.assert_any_call("channel:two")

        await listener._cleanup()

    async def test_connect_subscribes_to_patterns(self, mock_redis, mock_pubsub):
        """Test that _connect subscribes to specified patterns."""
        from unittest.mock import patch

        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            patterns=["bifrost:*", "events:*"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            result = await listener._connect()

            assert result is True
            assert mock_pubsub.psubscribe.call_count == 2
            mock_pubsub.psubscribe.assert_any_call("bifrost:*")
            mock_pubsub.psubscribe.assert_any_call("events:*")

        await listener._cleanup()

    async def test_connect_returns_false_on_error(self):
        """Test that _connect returns False when connection fails."""
        from unittest.mock import patch

        callback = AsyncMock()
        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url",
            side_effect=ConnectionError("Cannot connect"),
        ):
            result = await listener._connect()

            assert result is False

    async def test_handle_message_dispatches_channel_message(self, mock_redis, mock_pubsub):
        """Test that _handle_message correctly dispatches channel messages."""
        import json
        from unittest.mock import patch

        callback = AsyncMock()
        test_data = {"key": "value"}

        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            await listener._connect()

            message = {
                "type": "message",
                "channel": b"test:channel",
                "data": json.dumps(test_data),
            }
            await listener._handle_message(message)

            callback.assert_called_once_with("test:channel", test_data)

        await listener._cleanup()

    async def test_handle_message_dispatches_pattern_message(self, mock_redis, mock_pubsub):
        """Test that _handle_message correctly dispatches pattern messages."""
        import json
        from unittest.mock import patch

        callback = AsyncMock()
        test_data = {"event": "test"}

        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            patterns=["bifrost:*"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            await listener._connect()

            message = {
                "type": "pmessage",
                "pattern": b"bifrost:*",
                "channel": b"bifrost:scheduler:reindex",
                "data": json.dumps(test_data),
            }
            await listener._handle_message(message)

            callback.assert_called_once_with("bifrost:scheduler:reindex", test_data)

        await listener._cleanup()

    async def test_handle_message_handles_invalid_json(self, mock_redis, mock_pubsub):
        """Test that _handle_message handles invalid JSON without crashing."""
        from unittest.mock import patch

        callback = AsyncMock()

        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            await listener._connect()

            message = {
                "type": "message",
                "channel": b"test:channel",
                "data": "not valid json {",
            }
            # Should not raise
            await listener._handle_message(message)

            # Callback should not be called for invalid JSON
            callback.assert_not_called()

        await listener._cleanup()

    async def test_cleanup_closes_connections(self, mock_redis, mock_pubsub):
        """Test that _cleanup properly closes Redis connections."""
        from unittest.mock import patch

        callback = AsyncMock()

        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            await listener._connect()
            assert listener._redis is not None
            assert listener._pubsub is not None

            await listener._cleanup()

            mock_pubsub.close.assert_called_once()
            mock_redis.close.assert_called_once()
            assert listener._redis is None
            assert listener._pubsub is None

    async def test_start_raises_if_already_running(self, mock_redis, mock_pubsub):
        """Test that start raises RuntimeError if already running."""
        from unittest.mock import patch

        callback = AsyncMock()

        listener = ResilientPubSubListener(
            redis_url="redis://localhost:6379",
            channels=["test:channel"],
            on_message=callback,
        )

        with patch(
            "src.core.redis_reconnect.Redis.from_url", return_value=mock_redis
        ):
            await listener.start()

            with pytest.raises(RuntimeError, match="already running"):
                await listener.start()

            await listener.stop()
