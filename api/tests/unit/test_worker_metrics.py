"""Tests for worker metrics persistence and heartbeat enhancement."""

from unittest.mock import patch
from datetime import datetime, timezone

import pytest


class TestHeartbeatCgroupData:
    """Tests for cgroup memory data in heartbeat payload."""

    def test_heartbeat_includes_cgroup_memory(self):
        """Heartbeat should include memory_current_bytes and memory_max_bytes."""
        from src.services.execution.process_pool import ProcessPoolManager

        pool = ProcessPoolManager.__new__(ProcessPoolManager)
        pool.worker_id = "test-worker"
        pool.processes = {}
        pool.min_workers = 0
        pool.max_workers = 10
        pool._started_at = datetime.now(timezone.utc)
        pool._requirements_installed = 0
        pool._requirements_total = 0
        pool.heartbeat_interval_seconds = 10

        with patch(
            "src.services.execution.process_pool.get_cgroup_memory",
            return_value=(4_000_000_000, 8_000_000_000),
        ):
            heartbeat = pool._build_heartbeat()

        assert heartbeat["memory_current_bytes"] == 4_000_000_000
        assert heartbeat["memory_max_bytes"] == 8_000_000_000

    def test_heartbeat_cgroup_unavailable(self):
        """When cgroup is unavailable, heartbeat should have -1 values."""
        from src.services.execution.process_pool import ProcessPoolManager

        pool = ProcessPoolManager.__new__(ProcessPoolManager)
        pool.worker_id = "test-worker"
        pool.processes = {}
        pool.min_workers = 0
        pool.max_workers = 10
        pool._started_at = datetime.now(timezone.utc)
        pool._requirements_installed = 0
        pool._requirements_total = 0
        pool.heartbeat_interval_seconds = 10

        with patch(
            "src.services.execution.process_pool.get_cgroup_memory",
            return_value=(-1, -1),
        ):
            heartbeat = pool._build_heartbeat()

        assert heartbeat["memory_current_bytes"] == -1
        assert heartbeat["memory_max_bytes"] == -1
