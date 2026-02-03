"""Tests for WorkflowExecutionConsumer persistent DB session."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConsumerSessionLifecycle:
    """Test persistent DB session management."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create mock session factory."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = mock_session
        return factory, mock_session

    @pytest.mark.asyncio
    async def test_start_creates_db_session(self, mock_session_factory):
        """Consumer.start() should create persistent DB session."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        factory, mock_session = mock_session_factory

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._pool = AsyncMock()
            consumer._pool.start = AsyncMock()
            consumer._pool_started = False
            consumer._session_factory = factory
            consumer._db_session = None

            # Mock parent start
            with patch.object(
                WorkflowExecutionConsumer.__bases__[0], "start", AsyncMock()
            ):
                await consumer.start()

            assert consumer._db_session is not None
            factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_closes_db_session(self, mock_session_factory):
        """Consumer.stop() should close persistent DB session."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        factory, mock_session = mock_session_factory

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._pool = AsyncMock()
            consumer._pool.stop = AsyncMock()
            consumer._pool_started = True
            consumer._db_session = mock_session

            # Mock parent stop
            with patch.object(
                WorkflowExecutionConsumer.__bases__[0], "stop", AsyncMock()
            ):
                await consumer.stop()

            mock_session.close.assert_called_once()
            assert consumer._db_session is None


class TestConsumerSessionReconnection:
    """Test session health check and reconnection."""

    @pytest.mark.asyncio
    async def test_get_db_session_returns_healthy_session(self):
        """_get_db_session() returns existing session when healthy."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_session
            consumer._session_factory = MagicMock()

            result = await consumer._get_db_session()

            assert result is mock_session
            mock_session.execute.assert_called_once()  # Health check ran

    @pytest.mark.asyncio
    async def test_get_db_session_reconnects_on_stale(self):
        """_get_db_session() reconnects when session is stale."""
        from sqlalchemy.exc import DBAPIError
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        stale_session = AsyncMock()
        stale_session.execute = AsyncMock(side_effect=DBAPIError("connection closed", None, None))
        stale_session.close = AsyncMock()

        fresh_session = AsyncMock()
        fresh_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = fresh_session

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = stale_session
            consumer._session_factory = factory

            result = await consumer._get_db_session()

            assert result is fresh_session
            stale_session.close.assert_called_once()
            factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_db_session_creates_when_none(self):
        """_get_db_session() creates session when None."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        new_session = AsyncMock()
        new_session.execute = AsyncMock(return_value=MagicMock())

        factory = MagicMock()
        factory.return_value = new_session

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = None
            consumer._session_factory = factory

            result = await consumer._get_db_session()

            assert result is new_session
            factory.assert_called_once()


class TestSyncModuleCache:
    """Test module cache sync logic."""

    @pytest.mark.asyncio
    async def test_sync_adds_missing_modules(self):
        """_sync_module_cache() should add modules missing from Redis."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - empty cache
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.exists = AsyncMock(return_value=False)

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            # Mock the module caching function
            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    mock_set.assert_called_once_with(
                        path="modules/test.py",
                        content="# test module",
                        content_hash="abc123",
                    )

    @pytest.mark.asyncio
    async def test_sync_skips_cached_modules(self):
        """_sync_module_cache() should not re-cache existing modules."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - module already cached
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"bifrost:module:modules/test.py"})
        mock_redis.exists = AsyncMock(return_value=True)  # Key exists

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_handles_expired_keys(self):
        """_sync_module_cache() should re-cache modules with expired content keys."""
        from src.jobs.consumers.workflow_execution import WorkflowExecutionConsumer

        org_id = "ORG:test-org-id"

        # Mock DB modules
        mock_module = MagicMock()
        mock_module.path = "modules/test.py"
        mock_module.content = "# test module"
        mock_module.content_hash = "abc123"

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_module]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        # Mock Redis - key in index but content expired
        mock_redis = AsyncMock()
        mock_redis.smembers = AsyncMock(return_value={b"bifrost:module:modules/test.py"})
        mock_redis.exists = AsyncMock(return_value=False)  # Content expired!

        with patch.object(WorkflowExecutionConsumer, "__init__", lambda self: None):
            consumer = WorkflowExecutionConsumer()
            consumer._db_session = mock_db_session
            consumer._get_db_session = AsyncMock(return_value=mock_db_session)

            with patch("src.jobs.consumers.workflow_execution.set_module", new_callable=AsyncMock) as mock_set:
                with patch("src.jobs.consumers.workflow_execution.get_redis_client") as mock_get_redis:
                    mock_redis_client = MagicMock()
                    mock_redis_client._get_redis = AsyncMock(return_value=mock_redis)
                    mock_get_redis.return_value = mock_redis_client
                    consumer._redis_client = mock_redis_client

                    await consumer._sync_module_cache(org_id)

                    # Should re-cache because content key expired
                    mock_set.assert_called_once()
