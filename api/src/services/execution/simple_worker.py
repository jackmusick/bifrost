"""
Execution helpers for forked worker processes.

This module provides the helpers that forked children (spawned by
TemplateProcess via os.fork) use to run an execution:

- install_requirements(): called once at pool startup to pip-install
  user requirements. All forked children inherit the resulting
  filesystem, so installing once in the parent is sufficient.
- _clear_workspace_modules(): called before each execution so workflow
  code changes are picked up from Redis.
- _execute_sync() / _execute_async(): run a single execution given an
  execution_id (context is read from Redis, result is returned).
- _get_process_rss() / _get_pss_bytes() / _capture_resource_metrics():
  per-process memory/resource reporting used by the pool for recycling
  bloated children.

All callers live in template_process.py (fork path) and process_pool.py
(install_requirements at pool startup). There is no longer a
multiprocessing.spawn code path — forked children are created by
template_process.fork() and communicate via pipe-backed send/recv queues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import resource
import sys
from datetime import datetime, timezone
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
    except Exception as e:
        logger.warning(f"[pool] Failed to install requirements: {e}")
    finally:
        try:
            os.unlink(temp_path)
        except OSError as e:
            # Temp file may already be gone — best-effort cleanup
            logger.debug(f"[pool] could not remove temp requirements file {temp_path}: {e}")


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

        # Capture baseline PSS before execution so we can measure the delta
        baseline_pss = _get_pss_bytes()

        result = await _run_execution(execution_id, context)

        # Calculate duration
        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        # Determine success from result
        status = result.get("status", "Failed")
        success = status in ("Success", "CompletedWithErrors")

        # Capture resource metrics (use worker's metrics if available, else local)
        metrics = result.get("metrics") or _capture_resource_metrics()

        # Overwrite peak_memory_bytes with PSS delta — the memory uniquely
        # attributable to this execution, excluding shared parent pages.
        end_pss = _get_pss_bytes()
        if baseline_pss > 0 and end_pss > 0:
            metrics["peak_memory_bytes"] = max(0, end_pss - baseline_pss)

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
            "metrics": metrics,
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


def _get_pss_bytes() -> int:
    """Get current PSS (Proportional Set Size) in bytes.

    PSS divides shared pages proportionally among all processes sharing them
    and counts private pages fully — giving the true unique memory footprint.
    Reads from /proc/self/smaps_rollup on Linux/Docker.
    Falls back to 0 if unavailable.
    """
    try:
        with open("/proc/self/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) * 1024  # kB to bytes
    except (OSError, ValueError) as e:
        # /proc not available (macOS) or unexpected line format — caller treats 0 as unknown
        logger.debug(f"could not read smaps_rollup PSS: {e}")
    return 0


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
    except (OSError, ValueError) as e:
        # /proc not available (macOS) or unexpected line format — caller treats 0 as unknown
        logger.debug(f"could not read /proc/self/status VmRSS: {e}")
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
