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
