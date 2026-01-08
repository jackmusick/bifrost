"""
Worker process entry point for isolated execution.

This module runs in a separate process and:
1. Reads execution context from Redis
2. Runs the workflow/script
3. Writes logs to Redis Stream (already handled by engine)
4. Writes result to Redis (including resource metrics)
5. Exits cleanly (or gets killed on timeout)

The worker imports minimal dependencies to keep memory footprint low.

IMPORTANT: The virtual import hook is installed at module load time
(before any workspace imports can occur) to enable loading Python
modules from Redis cache instead of the filesystem.
"""

from __future__ import annotations

import asyncio
import json
import logging
import resource
import signal
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Install virtual import hook IMMEDIATELY at module load time.
# This must happen before any workspace imports (e.g., from shared import ...)
# The hook intercepts imports and loads modules from Redis cache.
from src.services.execution.virtual_import import install_virtual_import_hook

install_virtual_import_hook()

logger = logging.getLogger(__name__)


@dataclass
class ResourceMetrics:
    """Resource usage metrics captured during execution."""
    # Memory metrics (bytes)
    peak_memory_bytes: int  # Maximum RSS during execution
    # CPU metrics (seconds)
    cpu_user_seconds: float  # User-mode CPU time
    cpu_system_seconds: float  # Kernel-mode CPU time
    cpu_total_seconds: float  # Total CPU time (user + system)


def _get_resource_usage() -> tuple[int, float, float]:
    """Get current resource usage from the OS.

    Returns:
        Tuple of (max_rss_bytes, user_cpu_seconds, system_cpu_seconds)
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # ru_maxrss is in KB on Linux, bytes on macOS
    # Normalize to bytes
    if sys.platform == 'darwin':
        max_rss_bytes = usage.ru_maxrss  # Already in bytes on macOS
    else:
        max_rss_bytes = usage.ru_maxrss * 1024  # KB to bytes on Linux

    return max_rss_bytes, usage.ru_utime, usage.ru_stime


def _capture_metrics(start_rss: int, start_utime: float, start_stime: float) -> ResourceMetrics:
    """Capture resource metrics since execution started.

    Args:
        start_rss: RSS at start (for reference, we use peak which is cumulative)
        start_utime: User CPU time at start
        start_stime: System CPU time at start

    Returns:
        ResourceMetrics with delta values
    """
    end_rss, end_utime, end_stime = _get_resource_usage()

    cpu_user = end_utime - start_utime
    cpu_system = end_stime - start_stime

    return ResourceMetrics(
        peak_memory_bytes=end_rss,  # Peak is cumulative from process start
        cpu_user_seconds=round(cpu_user, 4),
        cpu_system_seconds=round(cpu_system, 4),
        cpu_total_seconds=round(cpu_user + cpu_system, 4),
    )


def _setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    def handle_sigterm(signum, frame):
        logger.info("Worker received SIGTERM, initiating graceful shutdown")
        # Raise SystemExit to trigger cleanup
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)


async def _read_execution_context(redis_client, execution_id: str) -> dict[str, Any] | None:
    """Read execution context from Redis."""
    key = f"bifrost:exec:{execution_id}:context"
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def _write_execution_result(redis_client, execution_id: str, result: dict[str, Any]):
    """Write execution result to Redis."""
    key = f"bifrost:exec:{execution_id}:result"
    # Set with 1 hour TTL (parent should read quickly, but safety margin)
    await redis_client.setex(key, 3600, json.dumps(result, default=str))


async def _run_execution(execution_id: str, context_data: dict[str, Any]) -> dict[str, Any]:
    """
    Run the actual execution.

    This is the core execution logic, isolated in the worker process.
    """
    from src.sdk.context import Caller, Organization
    from src.services.execution.engine import ExecutionRequest, execute
    from src.models.enums import ExecutionStatus
    from src.core.security import authenticate_engine

    # Ensure engine has valid credentials for SDK calls
    # This creates/refreshes a superuser token in ~/.bifrost/credentials.json
    # so that SDK calls (files.read, etc.) work identically to CLI mode
    authenticate_engine()

    start_time = datetime.utcnow()

    # Capture starting resource usage
    start_rss, start_utime, start_stime = _get_resource_usage()

    try:
        # Reconstruct Organization
        org = None
        org_data = context_data.get("organization")
        if org_data:
            org = Organization(
                id=org_data["id"],
                name=org_data["name"],
                is_active=org_data.get("is_active", True)
            )

        # Reconstruct Caller
        caller_data = context_data["caller"]
        caller = Caller(
            user_id=caller_data["user_id"],
            email=caller_data["email"],
            name=caller_data["name"]
        )

        # Load executable function if not a script
        # All types (workflow, tool, data_provider) use the same unified loader
        workflow_func = None
        metadata = None
        is_script = bool(context_data.get("code"))

        if not is_script:
            from src.services.execution.module_loader import load_workflow_from_db

            name = context_data["name"]
            function_name = context_data.get("function_name")
            workflow_code = context_data.get("workflow_code")
            file_path = context_data.get("file_path")
            result = None

            # Platform entities (workflows, tools, data providers) are stored in database
            # The code is passed from the consumer which has DB access
            # No filesystem fallback - platform entities must have code in database
            if workflow_code and function_name and file_path:
                result = load_workflow_from_db(
                    code=workflow_code,
                    path=file_path,
                    function_name=function_name,
                )
            else:
                # Missing required fields for execution
                logger.error(
                    f"Missing required fields for workflow execution: "
                    f"workflow_code={bool(workflow_code)}, "
                    f"function_name={function_name}, "
                    f"file_path={file_path}"
                )

            if not result:
                metrics = _capture_metrics(start_rss, start_utime, start_stime)
                return {
                    "status": ExecutionStatus.FAILED.value,
                    "error_message": f"Executable '{name}' not found",
                    "error_type": "ExecutableNotFound",
                    "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    "result": None,
                    "logs": [],
                    "variables": None,
                    "metrics": {
                        "peak_memory_bytes": metrics.peak_memory_bytes,
                        "cpu_user_seconds": metrics.cpu_user_seconds,
                        "cpu_system_seconds": metrics.cpu_system_seconds,
                        "cpu_total_seconds": metrics.cpu_total_seconds,
                    },
                }
            workflow_func, metadata = result

        # Build execution request
        request = ExecutionRequest(
            execution_id=execution_id,
            caller=caller,
            organization=org,
            config=context_data.get("config", {}),
            func=workflow_func,
            code=context_data.get("code"),
            name=context_data.get("name"),
            tags=context_data.get("tags", []),
            timeout_seconds=context_data.get("timeout_seconds", 1800),
            cache_ttl_seconds=context_data.get("cache_ttl_seconds", 300),
            parameters=context_data.get("parameters", {}),
            startup=context_data.get("startup"),  # Launch workflow results
            roi=context_data.get("roi"),  # ROI initialization
            transient=context_data.get("transient", False),
            no_cache=context_data.get("no_cache", False),
            is_platform_admin=context_data.get("is_platform_admin", False),
            broadcaster=None,  # Logs go to Redis Stream directly
        )

        # Execute
        exec_result = await execute(request)

        # Capture resource metrics after execution
        metrics = _capture_metrics(start_rss, start_utime, start_stime)

        # Convert result to dict for serialization
        return {
            "status": exec_result.status.value,
            "result": exec_result.result,
            "duration_ms": exec_result.duration_ms,
            "logs": exec_result.logs,
            "variables": exec_result.variables,
            "integration_calls": exec_result.integration_calls,
            "roi": exec_result.roi,
            "error_message": exec_result.error_message,
            "error_type": exec_result.error_type,
            "cached": exec_result.cached,
            "cache_expires_at": exec_result.cache_expires_at,
            "metrics": {
                "peak_memory_bytes": metrics.peak_memory_bytes,
                "cpu_user_seconds": metrics.cpu_user_seconds,
                "cpu_system_seconds": metrics.cpu_system_seconds,
                "cpu_total_seconds": metrics.cpu_total_seconds,
            },
        }

    except Exception as e:
        import traceback
        logger.exception(f"Worker execution failed: {e}")

        # Still capture metrics even on failure
        metrics = _capture_metrics(start_rss, start_utime, start_stime)

        return {
            "status": ExecutionStatus.FAILED.value,
            "error_message": str(e),
            "error_type": type(e).__name__,
            "duration_ms": int((datetime.utcnow() - start_time).total_seconds() * 1000),
            "result": None,
            "logs": [],
            "variables": None,
            "traceback": traceback.format_exc(),
            "metrics": {
                "peak_memory_bytes": metrics.peak_memory_bytes,
                "cpu_user_seconds": metrics.cpu_user_seconds,
                "cpu_system_seconds": metrics.cpu_system_seconds,
                "cpu_total_seconds": metrics.cpu_total_seconds,
            },
        }


async def worker_main(execution_id: str):
    """
    Main entry point for worker process.

    Called by the pool manager when spawning a new worker.
    """
    import redis.asyncio as redis
    from src.config import get_settings

    settings = get_settings()

    # Set up signal handlers
    _setup_signal_handlers()

    logger.info(f"Worker starting for execution: {execution_id}")

    # Note: No workspace directory needed - modules are loaded from Redis via virtual imports
    # The virtual import hook is installed below before any workspace imports

    # Connect to Redis
    redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=5.0,
    )

    try:
        # Read context from Redis
        context_data = await _read_execution_context(redis_client, execution_id)
        if not context_data:
            logger.error(f"No context found for execution: {execution_id}")
            await _write_execution_result(redis_client, execution_id, {
                "status": "Failed",
                "error_message": "Execution context not found in Redis",
                "error_type": "ContextNotFound",
                "duration_ms": 0,
                "metrics": None,
            })
            return

        # Run the execution
        result = await _run_execution(execution_id, context_data)

        # Write result to Redis
        await _write_execution_result(redis_client, execution_id, result)

        # Log metrics
        metrics = result.get("metrics")
        if metrics:
            logger.info(
                f"Worker completed execution: {execution_id}, "
                f"status: {result.get('status')}, "
                f"memory: {metrics['peak_memory_bytes'] / 1024 / 1024:.1f}MB, "
                f"cpu: {metrics['cpu_total_seconds']:.3f}s"
            )
        else:
            logger.info(f"Worker completed execution: {execution_id}, status: {result.get('status')}")

    except Exception as e:
        logger.exception(f"Worker failed for execution {execution_id}: {e}")
        try:
            await _write_execution_result(redis_client, execution_id, {
                "status": "Failed",
                "error_message": str(e),
                "error_type": type(e).__name__,
                "duration_ms": 0,
                "metrics": None,
            })
        except Exception:
            pass  # Best effort
    finally:
        await redis_client.aclose()


def run_in_worker(execution_id: str):
    """
    Synchronous entry point for multiprocessing.

    This is called when the process is spawned.
    """
    # Configure logging for worker process
    logging.basicConfig(
        level=logging.INFO,
        format=f"[Worker:{execution_id[:8]}] %(levelname)s - %(message)s"
    )

    # Run the async worker
    asyncio.run(worker_main(execution_id))
