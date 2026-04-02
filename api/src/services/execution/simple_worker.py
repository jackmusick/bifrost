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

Persistence: The ProcessPoolManager calls install_requirements() once at pool
startup. It reads requirements.txt via get_requirements_sync() (Redis → S3
fallback), then pip installs. Since all child processes share the same
filesystem, this single install is sufficient.
See api/src/core/requirements_cache.py for the full persistence flow.
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import resource
import signal
import sys
from datetime import datetime, timezone
from multiprocessing import Queue
from queue import Empty
from typing import Any

logger = logging.getLogger(__name__)


def install_requirements() -> None:
    """
    Install packages from requirements.txt.

    Called once at pool startup to ensure user-installed packages persist
    across container restarts. Reads requirements via get_requirements_sync()
    which handles Redis → S3 fallback automatically.

    Since all child processes share the same filesystem as the parent,
    installing once in the parent process is sufficient.

    This function never raises — failures are logged and execution continues.
    """
    import subprocess
    import tempfile

    from src.core.requirements_cache import get_requirements_sync

    content = get_requirements_sync()
    if not content:
        logger.info("[pool] No requirements.txt found")
        return

    # Write to temp file and install
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        logger.info("[pool] Installing packages from requirements.txt")

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", temp_path, "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            pkg_count = len([line for line in content.strip().split("\n") if line.strip()])
            logger.info(f"[pool] Installed {pkg_count} packages from requirements.txt")
        else:
            logger.warning(f"[pool] pip install failed: {result.stderr or result.stdout}")

    except subprocess.TimeoutExpired:
        logger.warning("[pool] pip install timed out after 5 minutes")

    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        except Exception as e:
            logger.warning(f"[pool] Failed to install requirements: {e}")
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

    # Install virtual import hook (after default finders so filesystem is checked first)
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

            # Clean up per-execution state to prevent memory leaks
            try:
                from bifrost._logging import clear_sequence_counter
                clear_sequence_counter(execution_id)
            except Exception:
                pass

            # Force GC to reclaim circular refs (exception chains, async closures)
            # before measuring RSS — otherwise dead objects inflate the reading
            gc.collect()

            # Report current RSS (not peak) so the pool can recycle bloated processes
            process_rss = _get_process_rss()
            result["process_rss_bytes"] = process_rss
            # Also inject into metrics dict for DB persistence
            if isinstance(result.get("metrics"), dict):
                result["metrics"]["process_rss_bytes"] = process_rss

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
    Clear workspace modules from sys.modules only if their content changed.

    Called before each execution. For each workspace module already loaded,
    checks the content hash against Redis. If unchanged, the module stays
    in sys.modules and the next `import` is a no-op. If changed (or if the
    hash check fails), the module is evicted so it gets re-fetched.

    This avoids re-exec'ing large unchanged modules on every execution.
    """
    from src.services.execution.virtual_import import VirtualModuleLoader, NamespacePackageLoader
    from src.core.module_cache_sync import get_module_index_sync, get_module_sync

    # Build set of known workspace module names from the Redis module index.
    module_index = get_module_index_sync()
    workspace_names: set[str] = set()
    # Also build a map from module name -> file path for hash checking
    name_to_path: dict[str, str] = {}
    for path in module_index:
        mod_name = path.replace("/", ".").removesuffix(".py").removesuffix(".__init__")
        parts = mod_name.split(".")
        for i in range(1, len(parts) + 1):
            prefix = ".".join(parts[:i])
            workspace_names.add(prefix)
        # Map the full module name to its file path
        name_to_path[mod_name] = path

    # Find workspace modules currently loaded
    workspace_modules = [
        (name, module) for name, module in sys.modules.items()
        if module is not None and (
            (hasattr(module, '__loader__') and isinstance(
                module.__loader__, (VirtualModuleLoader, NamespacePackageLoader)
            ))
            or name in workspace_names
        )
    ]

    # Check each module's hash — only clear if content changed
    modules_to_clear: list[str] = []
    modules_kept = 0

    for name, module in workspace_modules:
        cached_hash = getattr(module, '__content_hash__', None)

        if not cached_hash:
            # No hash stored — could be a namespace package or exec_from_db module.
            # Namespace packages are kept if any child modules are kept (decided later).
            # For now, check if this is a namespace package (has __path__ but no __file__).
            if isinstance(getattr(module, '__loader__', None), NamespacePackageLoader):
                # Defer — we'll keep it if any children survive
                continue
            # exec_from_db module with no hash — always clear
            modules_to_clear.append(name)
            continue

        # Look up current hash in Redis
        file_path = name_to_path.get(name)
        if not file_path:
            # Can't map to a file path — clear to be safe
            modules_to_clear.append(name)
            continue

        cached = get_module_sync(file_path)
        if not cached:
            # Module removed from cache — clear
            modules_to_clear.append(name)
            continue

        if cached.get("hash") != cached_hash:
            # Content changed — clear
            modules_to_clear.append(name)
        else:
            # Unchanged — keep it
            modules_kept += 1

    # If ANY workspace module changed, clear ALL workspace modules.
    # Reason: kept modules may hold stale references to cleared modules
    # via `from X import Y` bindings captured at import time.
    if modules_to_clear:
        modules_to_clear = [name for name, _ in workspace_modules]
        modules_kept = 0

    # Clear namespace packages only if ALL their children were cleared
    cleared_set = set(modules_to_clear)
    for name, module in workspace_modules:
        if not isinstance(getattr(module, '__loader__', None), NamespacePackageLoader):
            continue
        # Check if any child module survived (not in cleared_set and still in sys.modules)
        prefix = name + "."
        has_surviving_child = any(
            n.startswith(prefix) and n not in cleared_set
            for n in sys.modules
        )
        if not has_surviving_child:
            modules_to_clear.append(name)

    for name in modules_to_clear:
        if name in sys.modules:
            del sys.modules[name]

    if modules_to_clear or modules_kept:
        logger.debug(
            f"Workspace modules: cleared={len(modules_to_clear)} kept={modules_kept}"
            + (f" (cleared: {modules_to_clear})" if modules_to_clear else "")
        )


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
    start_time = datetime.now(timezone.utc)

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
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

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
            "execution_context": result.get("execution_context"),
            "worker_id": worker_id,
        }

    except Exception as e:
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
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


def _get_process_rss() -> int:
    """Get current process RSS in bytes (not peak).

    Reads VmRSS from /proc/self/status on Linux/Docker.
    Falls back to 0 if unavailable (e.g., macOS dev).
    """
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024  # kB to bytes
    except (OSError, ValueError):
        pass
    return 0


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
