"""
Simple Worker Process for Execution Isolation.

This module provides a straightforward worker process that runs executions
one at a time in a simple loop. It's designed to be spawned by ProcessPoolManager
and communicate via multiprocessing queues.

Key features:
- Simple loop: wait for execution_id -> execute -> return result
- Graceful SIGTERM handling (complete current work or exit)
- Reuses existing engine.execute() for actual execution
- Context is read from Redis, result is returned via queue

Each worker process handles one execution at a time, providing clean
isolation between executions.

IMPORTANT: Workers are long-lived processes. Workspace modules (workflows,
data providers) are loaded from Redis via the virtual import hook and cleared
from sys.modules before each execution to pick up code changes. For package
installs, the ProcessPoolManager recycles worker processes so fresh Python
interpreters can see newly installed packages.

Persistence: On startup, workers call _install_requirements_from_cache_sync()
to install packages from the cached requirements.txt in Redis. This ensures
packages persist across container restarts. See api/src/core/requirements_cache.py
for the full persistence flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import resource
import signal
import sys
from datetime import datetime
from multiprocessing import Queue
from queue import Empty
from typing import Any

logger = logging.getLogger(__name__)


def _install_requirements_from_cache_sync(worker_id: str) -> None:
    """
    Install packages from cached requirements.txt.

    Called at worker startup to ensure packages persist across container restarts.
    Uses synchronous Redis client since we're not in async context yet.

    This function never raises - failures are logged and worker continues.
    This allows the worker to still function even if Redis is unavailable
    or if the cached requirements are invalid.

    Retry behavior:
    - 3 attempts for Redis connection errors
    - 1 second delay between retries
    - All other errors fail immediately (no retry)

    Args:
        worker_id: Worker identifier for logging
    """
    import subprocess
    import tempfile
    import time

    import redis

    # Get Redis URL from environment (check both BIFROST_REDIS_URL and REDIS_URL)
    redis_url = os.environ.get("BIFROST_REDIS_URL") or os.environ.get("REDIS_URL", "redis://localhost:6379")

    # Retry logic for Redis connection
    max_retries = 3
    retry_delay = 1.0

    for attempt in range(max_retries):
        try:
            # Connect to Redis (sync client)
            client = redis.from_url(redis_url, decode_responses=True, socket_timeout=5.0)

            # Fetch cached requirements
            data: str | None = client.get("bifrost:requirements:content")  # type: ignore[assignment]
            client.close()

            if not data:
                logger.info(f"[{worker_id}] No cached requirements.txt found")
                return

            cached: dict[str, Any] = json.loads(data)
            content = cached.get("content", "")

            if not content.strip():
                logger.info(f"[{worker_id}] Cached requirements.txt is empty")
                return

            # Write to temp file and install
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(content)
                temp_path = f.name

            try:
                logger.info(f"[{worker_id}] Installing packages from cached requirements.txt")

                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", temp_path, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )

                if result.returncode == 0:
                    # Count packages
                    pkg_count = len([line for line in content.strip().split("\n") if line.strip()])
                    logger.info(f"[{worker_id}] Installed {pkg_count} packages from requirements.txt")
                else:
                    logger.warning(
                        f"[{worker_id}] pip install failed: {result.stderr or result.stdout}"
                    )
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

            return  # Success, exit retry loop

        except redis.ConnectionError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"[{worker_id}] Redis connection failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.warning(
                    f"[{worker_id}] Redis unavailable after {max_retries} attempts, "
                    "skipping requirements install"
                )

        except json.JSONDecodeError as e:
            logger.warning(f"[{worker_id}] Invalid JSON in cached requirements: {e}")
            return

        except subprocess.TimeoutExpired:
            logger.warning(f"[{worker_id}] pip install timed out after 5 minutes")
            return

        except Exception as e:
            logger.warning(f"[{worker_id}] Failed to install requirements: {e}")
            return


def run_worker_process(
    work_queue: Queue,
    result_queue: Queue,
    worker_id: str,
) -> None:
    """
    Entry point for worker process.

    Simple loop: wait for execution_id -> execute -> return result.
    Designed to be the target of multiprocessing.Process().

    Args:
        work_queue: Queue to receive execution_ids from ProcessPoolManager
        result_queue: Queue to send results back to ProcessPoolManager
        worker_id: Unique identifier for this worker (for logging)
    """
    # Configure logging for this worker process
    logging.basicConfig(
        level=logging.INFO,
        format=f"[{worker_id}] %(levelname)s - %(message)s"
    )

    # Ensure user site-packages is in sys.path
    # When pip installs packages as a non-root user, they go to ~/.local/lib/pythonX.Y/site-packages.
    # Python's site.py only adds this path if the directory exists at interpreter startup.
    # If packages are installed AFTER the parent process started (creating the directory),
    # spawned subprocesses won't have it in sys.path even though they're fresh interpreters
    # (multiprocessing.spawn copies sys.path from the parent).
    import site
    user_site = site.getusersitepackages()
    if site.ENABLE_USER_SITE and os.path.exists(user_site) and user_site not in sys.path:
        sys.path.insert(0, user_site)
        logger.info(f"Added user site-packages to sys.path: {user_site}")

    # Install packages from cached requirements.txt
    # This ensures packages persist across container restarts
    _install_requirements_from_cache_sync(worker_id)

    # Install virtual import hook FIRST (before any workspace imports)
    from src.services.execution.virtual_import import install_virtual_import_hook
    install_virtual_import_hook()

    # Setup signal handler for graceful shutdown
    shutdown_requested = False

    def handle_sigterm(signum: int, frame: Any) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info(f"Worker {worker_id} received SIGTERM, will exit after current work")

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    logger.info(f"Worker {worker_id} started (PID={os.getpid()})")

    execution_id: str | None = None

    while not shutdown_requested:
        try:
            # Block waiting for work (with timeout to check shutdown flag)
            try:
                execution_id = work_queue.get(timeout=1.0)
            except Empty:
                continue

            if execution_id is None:
                continue

            logger.info(f"Worker {worker_id} processing execution: {execution_id[:8]}...")

            # Clear workspace modules so we pick up any code changes from Redis
            _clear_workspace_modules()

            # Execute and return result
            result = _execute_sync(execution_id, worker_id)
            result_queue.put(result)

            logger.info(
                f"Worker {worker_id} completed execution: {execution_id[:8]}... "
                f"success={result.get('success', False)}"
            )

            # Reset for next iteration
            execution_id = None

        except KeyboardInterrupt:
            logger.info(f"Worker {worker_id} interrupted")
            break
        except Exception as e:
            logger.exception(f"Worker {worker_id} error: {e}")
            # Try to report error if we have an execution_id
            if execution_id is not None:
                try:
                    result_queue.put({
                        "execution_id": execution_id,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "duration_ms": 0,
                        "worker_id": worker_id,
                    })
                except Exception:
                    pass  # Best effort
                execution_id = None

    logger.info(f"Worker {worker_id} exiting")


def _clear_workspace_modules() -> None:
    """
    Clear workspace modules from sys.modules.

    Called before each execution to ensure any code changes from Redis
    are picked up. The virtual import hook will re-fetch from Redis
    on the next import.

    We identify workspace modules by checking if their __loader__ is
    our VirtualModuleLoader class.
    """
    from src.services.execution.virtual_import import VirtualModuleLoader

    # Find all modules loaded by our virtual import system
    modules_to_clear = [
        name for name, module in sys.modules.items()
        if (
            module is not None
            and hasattr(module, '__loader__')
            and isinstance(module.__loader__, VirtualModuleLoader)
        )
    ]

    # Remove them from sys.modules so they'll be re-imported
    for name in modules_to_clear:
        del sys.modules[name]

    if modules_to_clear:
        logger.debug(f"Cleared {len(modules_to_clear)} workspace modules: {modules_to_clear}")


def _execute_sync(execution_id: str, worker_id: str) -> dict[str, Any]:
    """
    Synchronous wrapper that runs async execution.

    Creates a new event loop for this execution via asyncio.run().
    This ensures clean isolation between executions.

    Args:
        execution_id: Unique execution identifier
        worker_id: Worker identifier (for logging/tracking)

    Returns:
        Result dict with success, result, error, duration_ms, etc.
    """
    try:
        result = asyncio.run(_execute_async(execution_id, worker_id))
        return result
    except Exception as e:
        logger.exception(f"Execution {execution_id} failed: {e}")
        return {
            "execution_id": execution_id,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "duration_ms": 0,
            "worker_id": worker_id,
        }


async def _execute_async(execution_id: str, worker_id: str) -> dict[str, Any]:
    """
    Read context from Redis, execute workflow, return result.

    This is the core async execution logic. It:
    1. Reads execution context from Redis
    2. Builds an ExecutionRequest
    3. Calls the existing execute() engine
    4. Formats and returns the result

    Args:
        execution_id: Unique execution identifier
        worker_id: Worker identifier (for logging/tracking)

    Returns:
        Result dict with execution outcome
    """
    start_time = datetime.utcnow()

    # 1. Read context from Redis
    context = await _read_context_from_redis(execution_id)
    if context is None:
        return {
            "execution_id": execution_id,
            "success": False,
            "error": "Execution context not found in Redis",
            "error_type": "ContextNotFound",
            "duration_ms": 0,
            "worker_id": worker_id,
        }

    # 2. Run the execution using existing worker logic
    # This reuses the shared _run_execution() from worker.py
    try:
        from src.services.execution.worker import _run_execution

        result = await _run_execution(execution_id, context)

        # Calculate duration
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        # Determine success from result
        status = result.get("status", "Failed")
        success = status in ("Success", "CompletedWithErrors")

        # Capture resource metrics
        metrics = _capture_resource_metrics()

        return {
            "execution_id": execution_id,
            "success": success,
            "status": status,
            "result": result.get("result"),
            "error": result.get("error_message"),
            "error_type": result.get("error_type"),
            "duration_ms": result.get("duration_ms", duration_ms),
            "logs": result.get("logs", []),
            "variables": result.get("variables"),
            "integration_calls": result.get("integration_calls", []),
            "roi": result.get("roi"),
            "metrics": result.get("metrics") or metrics,
            "cached": result.get("cached", False),
            "cache_expires_at": result.get("cache_expires_at"),
            "worker_id": worker_id,
        }

    except Exception as e:
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        logger.exception(f"Execution {execution_id} failed in engine: {e}")
        return {
            "execution_id": execution_id,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "duration_ms": duration_ms,
            "worker_id": worker_id,
        }


async def _read_context_from_redis(execution_id: str) -> dict[str, Any] | None:
    """
    Read execution context from Redis.

    Args:
        execution_id: Unique execution identifier

    Returns:
        Context dict or None if not found
    """
    import redis.asyncio as redis
    from src.config import get_settings

    settings = get_settings()

    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=5.0,
    )

    try:
        key = f"bifrost:exec:{execution_id}:context"
        data = await redis_client.get(key)

        if data is None:
            logger.warning(f"Context not found in Redis: {execution_id}")
            return None

        return json.loads(data)
    except Exception as e:
        logger.error(f"Failed to read context from Redis: {e}")
        return None
    finally:
        await redis_client.aclose()


def _capture_resource_metrics() -> dict[str, Any]:
    """
    Capture resource usage for diagnostics.

    Returns:
        Dict with peak memory, CPU time, etc.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)

    # ru_maxrss is in KB on Linux, bytes on macOS
    if sys.platform == 'darwin':
        peak_memory_bytes = usage.ru_maxrss  # Already in bytes on macOS
    else:
        peak_memory_bytes = usage.ru_maxrss * 1024  # KB to bytes on Linux

    return {
        "peak_memory_bytes": peak_memory_bytes,
        "cpu_user_seconds": round(usage.ru_utime, 4),
        "cpu_system_seconds": round(usage.ru_stime, 4),
        "cpu_total_seconds": round(usage.ru_utime + usage.ru_stime, 4),
    }
