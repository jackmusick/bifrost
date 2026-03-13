"""
Unit tests for package install consumer.

Tests the consumer that pip installs packages on the worker,
recycles processes, and updates the package list in Redis.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.jobs.consumers.package_install import PackageInstallConsumer


class TestProcessMessage:
    """Tests for process_message method."""

    @pytest.fixture
    def consumer(self) -> PackageInstallConsumer:
        return PackageInstallConsumer()

    @pytest.mark.asyncio
    async def test_specific_package_update_recycles(self, consumer: PackageInstallConsumer):
        """Test that updating a package (is_update=True) triggers recycle."""
        with (
            patch.object(
                consumer, "_pip_install", new_callable=AsyncMock, return_value=True
            ) as mock_pip,
            patch.object(consumer, "_mark_workers_for_recycle") as mock_recycle,
            patch.object(
                consumer, "_update_pool_packages", new_callable=AsyncMock
            ) as mock_update,
            patch.object(consumer, "_send_log", new_callable=AsyncMock),
            patch.object(consumer, "_send_complete", new_callable=AsyncMock),
        ):
            await consumer.process_message({
                "type": "recycle_workers",
                "package": "requests",
                "version": "2.31.0",
                "is_update": True,
            })

            mock_pip.assert_called_once_with("requests", "2.31.0")
            mock_recycle.assert_called_once()
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_package_skips_recycle(self, consumer: PackageInstallConsumer):
        """Test that a new package (is_update=False) skips recycle."""
        with (
            patch.object(
                consumer, "_pip_install", new_callable=AsyncMock, return_value=True
            ) as mock_pip,
            patch.object(consumer, "_mark_workers_for_recycle") as mock_recycle,
            patch.object(
                consumer, "_update_pool_packages", new_callable=AsyncMock
            ) as mock_update,
            patch.object(consumer, "_send_log", new_callable=AsyncMock),
            patch.object(consumer, "_send_complete", new_callable=AsyncMock),
        ):
            await consumer.process_message({
                "type": "recycle_workers",
                "package": "new-package",
                "version": "1.0.0",
                "is_update": False,
            })

            mock_pip.assert_called_once_with("new-package", "1.0.0")
            mock_recycle.assert_not_called()
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_is_update_defaults_to_recycle(self, consumer: PackageInstallConsumer):
        """Test that missing is_update defaults to True (safe default)."""
        with (
            patch.object(
                consumer, "_pip_install", new_callable=AsyncMock, return_value=True
            ),
            patch.object(consumer, "_mark_workers_for_recycle") as mock_recycle,
            patch.object(
                consumer, "_update_pool_packages", new_callable=AsyncMock
            ),
            patch.object(consumer, "_send_log", new_callable=AsyncMock),
            patch.object(consumer, "_send_complete", new_callable=AsyncMock),
        ):
            await consumer.process_message({
                "type": "recycle_workers",
                "package": "requests",
                "version": "2.31.0",
            })

            mock_recycle.assert_called_once()

    @pytest.mark.asyncio
    async def test_requirements_install(self, consumer: PackageInstallConsumer):
        """Test that no package triggers requirements.txt install + recycle."""
        with (
            patch.object(
                consumer, "_pip_install_requirements", new_callable=AsyncMock, return_value=True
            ) as mock_pip_req,
            patch.object(consumer, "_mark_workers_for_recycle") as mock_recycle,
            patch.object(
                consumer, "_update_pool_packages", new_callable=AsyncMock
            ) as mock_update,
            patch.object(consumer, "_send_log", new_callable=AsyncMock),
            patch.object(consumer, "_send_complete", new_callable=AsyncMock),
        ):
            await consumer.process_message({
                "type": "recycle_workers",
                "package": None,
                "is_update": True,
            })

            mock_pip_req.assert_called_once()
            mock_recycle.assert_called_once()
            mock_update.assert_called_once()


class TestMarkWorkersForRecycle:
    """Tests for _mark_workers_for_recycle method."""

    @pytest.fixture
    def consumer(self) -> PackageInstallConsumer:
        return PackageInstallConsumer()

    def test_marks_pool_for_recycle(self, consumer: PackageInstallConsumer):
        """Test that worker processes are marked for recycling."""
        mock_pool = MagicMock()
        mock_pool._started = True
        mock_pool.mark_for_recycle.return_value = (3, [])

        with patch(
            "src.services.execution.process_pool.get_process_pool",
            return_value=mock_pool,
        ):
            consumer._mark_workers_for_recycle()

            mock_pool.mark_for_recycle.assert_called_once()

    def test_skips_when_pool_not_started(self, consumer: PackageInstallConsumer):
        """Test that recycle is skipped when pool is not started."""
        mock_pool = MagicMock()
        mock_pool._started = False

        with patch(
            "src.services.execution.process_pool.get_process_pool",
            return_value=mock_pool,
        ):
            consumer._mark_workers_for_recycle()

            mock_pool.mark_for_recycle.assert_not_called()

    def test_handles_pool_error_gracefully(self, consumer: PackageInstallConsumer):
        """Test that pool errors are handled gracefully."""
        with patch(
            "src.services.execution.process_pool.get_process_pool",
            side_effect=RuntimeError("Pool not initialized"),
        ):
            # Should not raise
            consumer._mark_workers_for_recycle()


class TestUpdatePoolPackages:
    """Tests for _update_pool_packages method."""

    @pytest.fixture
    def consumer(self) -> PackageInstallConsumer:
        return PackageInstallConsumer()

    @pytest.mark.asyncio
    async def test_updates_packages(self, consumer: PackageInstallConsumer):
        """Test that pool packages are updated in Redis."""
        mock_pool = MagicMock()
        mock_pool._started = True
        mock_pool.update_packages = AsyncMock()

        with patch(
            "src.services.execution.process_pool.get_process_pool",
            return_value=mock_pool,
        ):
            await consumer._update_pool_packages()

            mock_pool.update_packages.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_error_gracefully(self, consumer: PackageInstallConsumer):
        """Test that errors are handled gracefully."""
        with patch(
            "src.services.execution.process_pool.get_process_pool",
            side_effect=RuntimeError("Pool not initialized"),
        ):
            # Should not raise
            await consumer._update_pool_packages()
