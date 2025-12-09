"""
Process pool for isolated workflow execution.

Manages a pool of worker processes that execute workflows in isolation.
Provides:
- Timeout enforcement via SIGTERM/SIGKILL
- Cancellation via Redis flag + process termination
- Result collection via Redis
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import multiprocessing.context
import os
import signal
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Global pool instance
_pool: "ExecutionPool | None" = None


@dataclass
class ExecutionHandle:
    """Handle to a running execution in the pool."""
    execution_id: str
    process: multiprocessing.context.SpawnProcess
    start_time: datetime
    timeout_seconds: int


class ExecutionPool:
    """
    Process pool for isolated workflow execution.

    Usage:
        pool = ExecutionPool(pool_size=4)
        result = await pool.execute(
            execution_id="...",
            context_data={...},
            timeout_seconds=300,
        )
    """

    def __init__(
        self,
        pool_size: int = 4,
        graceful_shutdown_seconds: int = 3,
        cancel_check_interval_ms: int = 250,
    ):
        self.pool_size = pool_size
        self.graceful_shutdown_seconds = graceful_shutdown_seconds
        self.cancel_check_interval = cancel_check_interval_ms / 1000.0
        self._running: dict[str, ExecutionHandle] = {}
        self._redis: redis.Redis | None = None
        self._shutdown = False

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            from src.config import get_settings
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=5.0,
            )
        return self._redis

    async def _write_context(self, execution_id: str, context_data: dict[str, Any]):
        """Write execution context to Redis for worker to read."""
        r = await self._get_redis()
        key = f"bifrost:exec:{execution_id}:context"
        # 1 hour TTL - should be read quickly but safety margin
        await r.setex(key, 3600, json.dumps(context_data, default=str))

    async def _read_result(self, execution_id: str) -> dict[str, Any] | None:
        """Read execution result from Redis."""
        r = await self._get_redis()
        key = f"bifrost:exec:{execution_id}:result"
        data = await r.get(key)
        if data:
            return json.loads(data)
        return None

    async def _set_cancel_flag(self, execution_id: str):
        """Set cancellation flag in Redis."""
        r = await self._get_redis()
        key = f"bifrost:exec:{execution_id}:cancel"
        await r.setex(key, 3600, "1")

    async def _check_cancel_flag(self, execution_id: str) -> bool:
        """Check if cancellation was requested."""
        r = await self._get_redis()
        key = f"bifrost:exec:{execution_id}:cancel"
        return await r.exists(key) > 0

    async def _cleanup_redis_keys(self, execution_id: str):
        """Clean up Redis keys after execution."""
        r = await self._get_redis()
        keys = [
            f"bifrost:exec:{execution_id}:context",
            f"bifrost:exec:{execution_id}:result",
            f"bifrost:exec:{execution_id}:cancel",
        ]
        await r.delete(*keys)

    def _terminate_process(self, handle: ExecutionHandle, use_kill: bool = False):
        """Terminate or kill the worker process."""
        if handle.process.is_alive():
            pid = handle.process.pid
            if pid is not None:
                if use_kill:
                    logger.warning(f"Sending SIGKILL to execution {handle.execution_id}")
                    os.kill(pid, signal.SIGKILL)
                else:
                    logger.info(f"Sending SIGTERM to execution {handle.execution_id}")
                    handle.process.terminate()

    async def _wait_for_memory(self, execution_id: str) -> None:
        """
        Wait until sufficient memory is available to start subprocess.

        Publishes status updates while waiting. Checks for cancellation
        between memory checks.

        Args:
            execution_id: Execution ID for status updates and cancellation checks

        Raises:
            asyncio.CancelledError: If cancelled while waiting for memory
        """
        from src.config import get_settings
        from src.core.pubsub import publish_execution_update
        from .memory_monitor import get_available_memory_mb, has_sufficient_memory

        settings = get_settings()
        threshold_mb = settings.memory_throttle_threshold_mb

        # Check if we need to wait
        if has_sufficient_memory(threshold_mb):
            return  # Proceed immediately

        logger.info(
            f"Execution {execution_id} waiting for memory "
            f"(available: {get_available_memory_mb()}MB, required: {threshold_mb}MB)"
        )

        # Wait loop with status updates
        while not has_sufficient_memory(threshold_mb):
            # Check for cancellation
            if await self._check_cancel_flag(execution_id):
                logger.info(f"Execution {execution_id} cancelled while waiting for memory")
                raise asyncio.CancelledError("Cancelled while waiting for memory")

            # Publish memory pressure status
            available_mb = get_available_memory_mb()
            await publish_execution_update(
                execution_id,
                "Pending",
                {
                    "waitReason": "memory_pressure",
                    "availableMemoryMb": available_mb,
                    "requiredMemoryMb": threshold_mb,
                }
            )

            # Wait before next check (use cancel_check_interval for consistency)
            await asyncio.sleep(self.cancel_check_interval)

        logger.info(f"Execution {execution_id} proceeding - memory now available")

    async def execute(
        self,
        execution_id: str,
        context_data: dict[str, Any],
        timeout_seconds: int = 300,
        on_cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a workflow in an isolated worker process.

        Args:
            execution_id: Unique execution ID
            context_data: Serializable context for the worker
            timeout_seconds: Maximum execution time
            on_cancel_check: Optional callback to check external cancellation

        Returns:
            Execution result dict

        Raises:
            TimeoutError: If execution exceeds timeout
            asyncio.CancelledError: If execution was cancelled
        """
        from .worker import run_in_worker

        # Write context to Redis for worker
        await self._write_context(execution_id, context_data)

        # Wait for sufficient memory before spawning subprocess
        await self._wait_for_memory(execution_id)

        start_time = datetime.utcnow()

        # Spawn worker process
        ctx = multiprocessing.get_context('spawn')
        process = ctx.Process(
            target=run_in_worker,
            args=(execution_id,),
            name=f"worker-{execution_id[:8]}"
        )
        process.start()

        handle = ExecutionHandle(
            execution_id=execution_id,
            process=process,
            start_time=start_time,
            timeout_seconds=timeout_seconds,
        )
        self._running[execution_id] = handle

        logger.info(f"Started worker process {process.pid} for execution {execution_id}")

        try:
            # Monitor loop
            while process.is_alive():
                # Check for external cancellation (e.g., from consumer checking DB)
                if on_cancel_check and on_cancel_check():
                    logger.info(f"External cancellation requested for {execution_id}")
                    await self._set_cancel_flag(execution_id)
                    self._terminate_process(handle)

                    # Wait for graceful shutdown
                    await asyncio.sleep(self.graceful_shutdown_seconds)

                    # Force kill if still alive
                    if process.is_alive():
                        self._terminate_process(handle, use_kill=True)
                        process.join(timeout=1)

                    raise asyncio.CancelledError("Execution cancelled by user")

                # Check for Redis cancel flag (set by API)
                if await self._check_cancel_flag(execution_id):
                    logger.info(f"Redis cancel flag set for {execution_id}")
                    self._terminate_process(handle)

                    await asyncio.sleep(self.graceful_shutdown_seconds)

                    if process.is_alive():
                        self._terminate_process(handle, use_kill=True)
                        process.join(timeout=1)

                    raise asyncio.CancelledError("Execution cancelled via API")

                # Check for timeout
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                if elapsed > timeout_seconds:
                    logger.warning(f"Execution {execution_id} exceeded timeout of {timeout_seconds}s")
                    self._terminate_process(handle)

                    await asyncio.sleep(self.graceful_shutdown_seconds)

                    if process.is_alive():
                        self._terminate_process(handle, use_kill=True)
                        process.join(timeout=1)

                    raise TimeoutError(f"Execution exceeded timeout of {timeout_seconds} seconds")

                # Wait before next check
                await asyncio.sleep(self.cancel_check_interval)

            # Process finished - get result from Redis
            process.join(timeout=1)
            result = await self._read_result(execution_id)

            if result is None:
                # Worker didn't write result - check exit code
                exit_code = process.exitcode
                if exit_code != 0:
                    return {
                        "status": "Failed",
                        "error_message": f"Worker process exited with code {exit_code}",
                        "error_type": "WorkerCrash",
                        "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    }
                else:
                    return {
                        "status": "Failed",
                        "error_message": "Worker completed but no result found",
                        "error_type": "NoResult",
                        "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    }

            return result

        finally:
            # Cleanup
            self._running.pop(execution_id, None)

            # Ensure process is terminated
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    pid = process.pid
                    if pid is not None:
                        os.kill(pid, signal.SIGKILL)

            # Clean up Redis keys
            try:
                await self._cleanup_redis_keys(execution_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup Redis keys for {execution_id}: {e}")

    async def cancel(self, execution_id: str):
        """
        Cancel a running execution.

        Sets the cancel flag and terminates the worker process.
        """
        await self._set_cancel_flag(execution_id)

        handle = self._running.get(execution_id)
        if handle:
            self._terminate_process(handle)
            # Give it time to shut down gracefully
            await asyncio.sleep(self.graceful_shutdown_seconds)
            if handle.process.is_alive():
                self._terminate_process(handle, use_kill=True)

    async def shutdown(self):
        """Shutdown the pool and terminate all workers."""
        self._shutdown = True

        # Terminate all running executions
        for execution_id, handle in list(self._running.items()):
            logger.info(f"Shutting down execution {execution_id}")
            self._terminate_process(handle)

        # Wait for graceful shutdown
        await asyncio.sleep(self.graceful_shutdown_seconds)

        # Force kill any remaining
        for execution_id, handle in list(self._running.items()):
            if handle.process.is_alive():
                self._terminate_process(handle, use_kill=True)

        # Close Redis
        if self._redis:
            await self._redis.aclose()
            self._redis = None


def get_execution_pool() -> ExecutionPool:
    """Get the global execution pool, creating if needed."""
    global _pool
    if _pool is None:
        from src.config import get_settings
        settings = get_settings()
        _pool = ExecutionPool(
            pool_size=settings.max_concurrency,
            graceful_shutdown_seconds=settings.graceful_shutdown_seconds,
            cancel_check_interval_ms=settings.cancel_check_interval_ms,
        )
    return _pool


async def shutdown_pool():
    """Shutdown the global execution pool."""
    global _pool
    if _pool:
        await _pool.shutdown()
        _pool = None
