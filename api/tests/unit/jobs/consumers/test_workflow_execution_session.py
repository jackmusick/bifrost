"""Tests for WorkflowExecutionConsumer session management.

Validates that the consumer uses short-lived sessions (no persistent session).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConsumerSessionLifecycle:
    """Test that consumer no longer holds a persistent DB session."""

    @pytest.mark.asyncio
    async def test_start_does_not_create_persistent_session(self):
        """Consumer.start() should NOT create a persistent DB session."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._pool = AsyncMock()
            consumer._pool.start = AsyncMock()
            consumer._pool_started = False

            with patch.object(
                WorkflowExecutionConsumer.__bases__[0], "start", AsyncMock()
            ):
                await consumer.start()

            # No _db_session attribute should exist
            assert not hasattr(consumer, "_db_session")

    @pytest.mark.asyncio
    async def test_stop_does_not_close_session(self):
        """Consumer.stop() should not try to close a persistent session."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._pool = AsyncMock()
            consumer._pool.stop = AsyncMock()
            consumer._pool_started = True

            with patch.object(
                WorkflowExecutionConsumer.__bases__[0], "stop", AsyncMock()
            ):
                # Should complete without error
                await consumer.stop()

    @pytest.mark.asyncio
    async def test_no_get_db_session_method(self):
        """Consumer should not have _get_db_session() method (removed)."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        assert not hasattr(WorkflowExecutionConsumer, "_get_db_session")


class TestConsumerStartupOrder:
    """Pool must be fully started before RabbitMQ begins delivering messages.

    Regression test for a production incident where two worker pods leaked
    ~800 MB each: the consumer was accepting messages from RabbitMQ before
    ProcessPoolManager.start() had finished initializing its template
    process, and a now-removed spawn fallback created ghost worker
    processes that were never reaped.
    """

    @pytest.mark.asyncio
    async def test_pool_starts_before_rabbitmq_consumer(self):
        """Consumer.start() must call pool.start() before super().start().

        super().start() (BaseConsumer) is what calls queue.consume() and
        begins message delivery. If pool.start() hasn't completed by the
        time that happens, messages can be routed to a not-yet-ready pool.
        """
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        call_order: list[str] = []

        async def mock_pool_start() -> None:
            call_order.append("pool")

        async def mock_super_start(self) -> None:  # type: ignore[no-untyped-def]
            call_order.append("rabbitmq")

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._pool = MagicMock()
            consumer._pool.start = mock_pool_start
            consumer._pool_started = False

            with patch.object(
                WorkflowExecutionConsumer.__bases__[0], "start", mock_super_start
            ):
                await consumer.start()

        assert call_order == ["pool", "rabbitmq"], (
            f"Pool must start before RabbitMQ consumer; got {call_order}"
        )
        assert consumer._pool_started is True
