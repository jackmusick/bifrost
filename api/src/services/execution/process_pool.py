"""
Process Pool Manager for Execution Isolation.

This module provides a pool of long-lived worker processes that can handle
concurrent executions. Unlike the one-process-per-execution model, this
approach reuses processes for multiple executions, improving efficiency.

Key features:
- Dynamic scaling between min_workers and max_workers
- Automatic timeout handling with graceful shutdown (SIGTERM -> SIGKILL)
- Crash detection and process replacement
- Heartbeat publishing for UI visibility
- Manual process recycling via API

Architecture:
    ProcessPoolManager (runs in consumer process)
        |
        +-- min_workers to max_workers processes
        +-- Each process: work_queue (in) + result_queue (out)
        +-- Monitor loop checks health and timeouts
        +-- Result loop collects execution results
        +-- Heartbeat loop publishes status to Redis/WebSocket
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import signal
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from multiprocessing import Queue as MPQueue
from queue import Empty
from typing import Any, Awaitable, Callable

import psutil
import redis.asyncio as redis

from src.config import get_settings
from src.services.execution.simple_worker import run_worker_process as simple_run_worker_process

logger = logging.getLogger(__name__)


def _get_installed_packages() -> list[dict[str, str]]:
    """
    Get list of installed packages via pip list.

    Returns a list of dicts with 'name' and 'version' keys.
    Used to populate the packages field in Redis pool registration.
    """
    try:
        result = subprocess.run(
            ["pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"Failed to get installed packages: {e}")
    return []


class ProcessState(Enum):
    """
    State of a worker process in the pool.

    States:
    - IDLE: Ready to accept work
    - BUSY: Currently executing
    - KILLED: Process was terminated (pending removal)
    """

    IDLE = "idle"
    BUSY = "busy"
    KILLED = "killed"


@dataclass
class ExecutionInfo:
    """
    Information about a currently running execution.

    Attributes:
        execution_id: Unique identifier for the execution
        started_at: When the execution started
        timeout_seconds: Execution timeout in seconds
    """

    execution_id: str
    started_at: datetime
    timeout_seconds: int

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since execution started."""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    @property
    def is_timed_out(self) -> bool:
        """Check if execution has exceeded its timeout."""
        return self.elapsed_seconds > self.timeout_seconds


@dataclass
class ProcessHandle:
    """
    Represents a worker process managed by the pool.

    Attributes:
        id: Unique identifier for this process handle (e.g., "process-1")
        process: The multiprocessing.Process instance
        pid: Process ID (set after process.start())
        state: Current ProcessState
        work_queue: Queue for sending execution_ids to process
        result_queue: Queue for receiving results from process
        started_at: When the process was spawned
        current_execution: Info about current execution (if BUSY)
        executions_completed: Number of executions this process has completed
    """

    id: str
    process: Any  # multiprocessing.Process or SpawnProcess
    pid: int | None
    state: ProcessState
    work_queue: MPQueue  # type: ignore[type-arg]
    result_queue: MPQueue  # type: ignore[type-arg]
    started_at: datetime
    current_execution: ExecutionInfo | None = None
    executions_completed: int = 0
    pending_recycle: bool = False  # Mark for recycle after current execution

    @property
    def is_alive(self) -> bool:
        """Check if the process is still running."""
        return self.process.is_alive()

    @property
    def uptime_seconds(self) -> float:
        """Seconds since process was started."""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


# Type alias for result callback
ResultCallback = Callable[[dict[str, Any]], Awaitable[None]]


class ProcessPoolManager:
    """
    Manages a pool of worker processes for execution isolation.

    The ProcessPoolManager:
    1. Spawns min_workers processes on startup
    2. Scales up to max_workers under load
    3. Routes executions to IDLE processes
    4. Monitors for timeouts and crashes
    5. Publishes heartbeats for UI visibility

    Usage:
        pool = ProcessPoolManager(
            min_workers=2,
            max_workers=10,
            on_result=handle_result,
        )
        await pool.start()

        # Route execution
        await pool.route_execution(execution_id, context)

        # Shutdown
        await pool.stop()
    """

    def __init__(
        self,
        min_workers: int = 2,
        max_workers: int = 10,
        execution_timeout_seconds: int = 300,
        graceful_shutdown_seconds: int = 5,
        recycle_after_executions: int = 0,
        heartbeat_interval_seconds: int = 10,
        registration_ttl_seconds: int = 30,
        on_result: ResultCallback | None = None,
    ):
        """
        Initialize the process pool manager.

        Args:
            min_workers: Minimum number of worker processes to maintain
            max_workers: Maximum number of worker processes
            execution_timeout_seconds: Default execution timeout in seconds
            graceful_shutdown_seconds: Seconds to wait between SIGTERM and SIGKILL
            recycle_after_executions: Recycle process after N executions (0 = never)
            heartbeat_interval_seconds: Interval for heartbeat publications
            registration_ttl_seconds: TTL for worker registration in Redis
            on_result: Async callback for handling execution results
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.execution_timeout_seconds = execution_timeout_seconds
        self.graceful_shutdown_seconds = graceful_shutdown_seconds
        self.recycle_after_executions = recycle_after_executions
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.registration_ttl_seconds = registration_ttl_seconds
        self.on_result = on_result

        # Worker ID from HOSTNAME env var (Docker container name) or UUID
        self.worker_id = os.environ.get("HOSTNAME", str(uuid.uuid4()))

        # Process tracking
        self.processes: dict[str, ProcessHandle] = {}
        self._process_counter = 0

        # State
        self._shutdown = False
        self._started = False

        # Async tasks
        self._monitor_task: asyncio.Task[None] | None = None
        self._result_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._cancel_task: asyncio.Task[None] | None = None
        self._command_task: asyncio.Task[None] | None = None

        # Redis connection
        self._redis: redis.Redis | None = None  # type: ignore[type-arg]

        # Lock for idle process waiting
        self._idle_condition = asyncio.Condition()

    async def _get_redis(self) -> redis.Redis:  # type: ignore[type-arg]
        """Get or create Redis connection."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _spawn_process(self) -> ProcessHandle:
        """
        Spawn a new worker process.

        Creates queues for communication and starts the worker process.
        The new process is set to IDLE state.

        Returns:
            ProcessHandle instance for the new process
        """
        # Create communication queues
        ctx = multiprocessing.get_context("spawn")
        work_queue: MPQueue[str] = ctx.Queue()
        result_queue: MPQueue[dict[str, Any]] = ctx.Queue()

        # Generate process ID
        self._process_counter += 1
        process_id = f"process-{self._process_counter}"

        # Create process with target function
        # Use simple_worker's run_worker_process which has:
        # - Virtual import hook installation
        # - Workspace module clearing between executions
        process = ctx.Process(
            target=simple_run_worker_process,
            args=(work_queue, result_queue, process_id),
            name=process_id,
        )
        process.start()

        # Create handle
        handle = ProcessHandle(
            id=process_id,
            process=process,
            pid=process.pid,
            state=ProcessState.IDLE,
            work_queue=work_queue,
            result_queue=result_queue,
            started_at=datetime.now(timezone.utc),
            current_execution=None,
            executions_completed=0,
        )

        self.processes[process_id] = handle

        logger.info(
            f"Spawned worker process {process_id} with PID={process.pid}"
        )

        return handle

    async def start(self) -> None:
        """
        Start the pool manager and spawn initial workers.

        This method:
        1. Spawns min_workers processes
        2. Registers in Redis
        3. Starts background tasks (monitor, result, heartbeat loops)
        """
        if self._started:
            logger.warning("ProcessPoolManager already started")
            return

        logger.info(
            f"ProcessPoolManager starting with min_workers={self.min_workers}, "
            f"max_workers={self.max_workers}"
        )

        self._started = True
        self._shutdown = False

        # Spawn initial pool
        for _ in range(self.min_workers):
            self._spawn_process()

        # Register in Redis
        await self._register_worker()

        # Start background tasks
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(),
            name="pool-monitor"
        )
        self._result_task = asyncio.create_task(
            self._result_loop(),
            name="pool-results"
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name="pool-heartbeat"
        )
        self._cancel_task = asyncio.create_task(
            self._cancel_listener_loop(),
            name="pool-cancel-listener"
        )
        self._command_task = asyncio.create_task(
            self._command_listener_loop(),
            name="pool-command-listener"
        )

        logger.info(
            f"ProcessPoolManager started with {len(self.processes)} workers"
        )

        # Check for persisted configuration and apply if different
        await self._apply_persisted_config()

    async def _apply_persisted_config(self) -> None:
        """
        Check for persisted pool configuration and apply if different from current.

        This ensures config changes survive container restarts.
        Called after pool start to check system_configs table.
        """
        try:
            # Import here to avoid circular dependencies
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy.ext.asyncio import async_sessionmaker

            from src.config import get_settings
            from src.services.worker_pool_config_service import get_pool_config

            settings = get_settings()

            # Create a temporary session for config lookup
            engine = create_async_engine(settings.database_url)
            async_session = async_sessionmaker(engine, expire_on_commit=False)

            async with async_session() as session:
                config = await get_pool_config(session)

                # Check if persisted config differs from current
                if (config.min_workers != self.min_workers or
                        config.max_workers != self.max_workers):
                    logger.info(
                        f"Applying persisted config: min={config.min_workers}, "
                        f"max={config.max_workers} (current: min={self.min_workers}, "
                        f"max={self.max_workers})"
                    )

                    # Apply the persisted config
                    await self.resize(config.min_workers, config.max_workers)
                else:
                    logger.debug("Persisted config matches current settings")

            await engine.dispose()

        except Exception as e:
            # Don't fail startup if we can't load persisted config
            logger.warning(f"Failed to apply persisted config (using defaults): {e}")

    async def stop(self) -> None:
        """
        Gracefully stop the pool manager and all processes.

        This method:
        1. Sets shutdown flag
        2. Cancels background tasks
        3. Terminates all processes gracefully
        4. Unregisters from Redis
        """
        if self._shutdown:
            return

        logger.info("ProcessPoolManager stopping...")
        self._shutdown = True

        # Cancel background tasks
        tasks = [
            self._monitor_task,
            self._result_task,
            self._heartbeat_task,
            self._cancel_task,
            self._command_task,
        ]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Terminate all processes
        for handle in list(self.processes.values()):
            await self._terminate_process(handle)

        # Unregister from Redis
        await self._unregister_worker()

        # Close Redis connection
        if self._redis:
            await self._redis.aclose()
            self._redis = None

        self.processes.clear()
        self._started = False

        logger.info("ProcessPoolManager stopped")

    async def _terminate_process(self, handle: ProcessHandle) -> None:
        """
        Terminate a process gracefully (SIGTERM -> wait -> SIGKILL).

        Args:
            handle: ProcessHandle to terminate
        """
        if not handle.is_alive:
            return

        pid = handle.pid
        if pid is None:
            return

        logger.info(f"Terminating process {handle.id} (PID={pid})")

        # SIGTERM for graceful shutdown
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        # Wait for graceful shutdown
        await asyncio.sleep(self.graceful_shutdown_seconds)

        # SIGKILL if still alive
        if handle.process.is_alive():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            handle.process.join(timeout=1)

        handle.state = ProcessState.KILLED

    def _get_idle_process(self) -> ProcessHandle | None:
        """
        Get an IDLE process from the pool.

        Returns:
            ProcessHandle with IDLE state, or None if no idle processes
        """
        for handle in self.processes.values():
            # Skip processes that are pending recycle - they're about to be terminated
            if handle.pending_recycle:
                continue
            if handle.state == ProcessState.IDLE and handle.is_alive:
                return handle
        return None

    async def _wait_for_idle_process(self, timeout: float = 30.0) -> ProcessHandle | None:
        """
        Wait for an idle process to become available.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            ProcessHandle with IDLE state, or None if timeout
        """
        async with self._idle_condition:
            try:
                await asyncio.wait_for(
                    self._idle_condition.wait_for(lambda: self._get_idle_process() is not None),
                    timeout=timeout
                )
                return self._get_idle_process()
            except asyncio.TimeoutError:
                return None

    async def route_execution(
        self,
        execution_id: str,
        context: dict[str, Any],
    ) -> None:
        """
        Route an execution to an idle process.

        The context is written to Redis, and the execution_id is sent
        to the process via the work queue.

        Args:
            execution_id: Unique identifier for the execution
            context: Execution context data (written to Redis)
        """
        # Write context to Redis
        await self._write_context_to_redis(execution_id, context)

        # Find or create idle process
        idle = self._get_idle_process()
        if idle is None:
            # Scale up if possible
            if len(self.processes) < self.max_workers:
                idle = self._spawn_process()
            else:
                # Wait for a process to become idle
                idle = await self._wait_for_idle_process()
                if idle is None:
                    raise RuntimeError("No idle process available after timeout")

        # Get timeout from context or use default
        timeout = context.get("timeout_seconds", self.execution_timeout_seconds)

        # Assign work
        idle.state = ProcessState.BUSY
        idle.current_execution = ExecutionInfo(
            execution_id=execution_id,
            started_at=datetime.now(timezone.utc),
            timeout_seconds=timeout,
        )

        # Send to process
        idle.work_queue.put_nowait(execution_id)

        logger.info(
            f"Routed {execution_id[:8]}... to {idle.id} "
            f"(timeout={timeout}s)"
        )

    async def _write_context_to_redis(
        self,
        execution_id: str,
        context: dict[str, Any],
    ) -> None:
        """
        Write execution context to Redis for worker to read.

        Args:
            execution_id: Execution ID
            context: Context data to store
        """
        r = await self._get_redis()
        context_key = f"bifrost:exec:{execution_id}:context"
        await r.setex(context_key, 3600, json.dumps(context, default=str))

    async def _monitor_loop(self) -> None:
        """
        Monitor loop for health checks and timeout handling.

        Runs every 1 second to:
        1. Check for timed-out executions and kill processes
        2. Check for crashed processes and replace them
        3. Scale down excess idle processes
        """
        logger.info("Monitor loop started")

        while not self._shutdown:
            try:
                await self._check_timeouts()
                await self._check_process_health()
                await self._maybe_scale_down()
            except Exception as e:
                logger.exception(f"Monitor loop error: {e}")

            await asyncio.sleep(1.0)

        logger.info("Monitor loop stopped")

    async def _check_timeouts(self) -> None:
        """
        Check for timed-out executions and kill their processes.

        For each BUSY process, checks if the execution has exceeded
        its timeout. If so, kills the process and spawns a replacement.
        """
        for handle in list(self.processes.values()):
            if handle.state != ProcessState.BUSY:
                continue
            if handle.current_execution is None:
                continue

            exec_info = handle.current_execution
            elapsed = exec_info.elapsed_seconds

            if elapsed > exec_info.timeout_seconds:
                logger.warning(
                    f"Execution {exec_info.execution_id} timed out after "
                    f"{elapsed:.1f}s (timeout={exec_info.timeout_seconds}s)"
                )

                # Kill process
                await self._kill_process(handle)

                # Report timeout
                await self._report_timeout(exec_info)

                # Remove from pool
                del self.processes[handle.id]

                # Spawn replacement if below min_workers
                if len(self.processes) < self.min_workers:
                    self._spawn_process()

    async def _kill_process(self, handle: ProcessHandle) -> None:
        """
        Kill a process (SIGTERM -> wait -> SIGKILL).

        Args:
            handle: ProcessHandle to kill
        """
        pid = handle.pid
        if pid is None:
            return

        # SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        # Wait grace period
        await asyncio.sleep(self.graceful_shutdown_seconds)

        # SIGKILL if still alive
        if handle.process.is_alive():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            handle.process.join(timeout=1)

        handle.state = ProcessState.KILLED

    async def _report_timeout(self, exec_info: ExecutionInfo) -> None:
        """
        Report a timeout to the result callback.

        Args:
            exec_info: ExecutionInfo for the timed-out execution
        """
        if self.on_result:
            try:
                await self.on_result({
                    "type": "result",
                    "execution_id": exec_info.execution_id,
                    "success": False,
                    "error": f"Execution timed out after {exec_info.timeout_seconds}s",
                    "error_type": "TimeoutError",
                    "duration_ms": int(exec_info.elapsed_seconds * 1000),
                })
            except Exception as e:
                logger.exception(f"Error reporting timeout: {e}")

    async def _cancel_listener_loop(self) -> None:
        """
        Listen for cancellation requests via Redis pub/sub.

        Subscribes to the bifrost:cancel channel and handles cancellation
        requests by killing the process handling the target execution.
        """
        logger.info("Cancel listener loop started")

        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe("bifrost:cancel")

        while not self._shutdown:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    execution_id = data.get("execution_id")
                    if execution_id:
                        await self._handle_cancel_request(execution_id)
            except Exception as e:
                logger.error(f"Cancel listener error: {e}")
                await asyncio.sleep(1.0)

        await pubsub.unsubscribe("bifrost:cancel")
        await pubsub.aclose()

        logger.info("Cancel listener loop stopped")

    async def _command_listener_loop(self) -> None:
        """
        Listen for pool management commands via Redis pub/sub.

        Subscribes to bifrost:pool:{worker_id}:commands and handles:
        - recycle_process: Recycle a specific process by PID
        - recycle_all: Mark all processes for recycling
        - resize: Update min/max workers and scale accordingly
        """
        channel = f"bifrost:pool:{self.worker_id}:commands"
        logger.info(f"Command listener loop started on channel {channel}")

        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)

        while not self._shutdown:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    await self._handle_command(data)
            except Exception as e:
                logger.error(f"Command listener error: {e}")
                await asyncio.sleep(1.0)

        await pubsub.unsubscribe(channel)
        await pubsub.aclose()

        logger.info("Command listener loop stopped")

    async def _handle_command(self, command: dict[str, Any]) -> None:
        """
        Dispatch a pool management command to the appropriate handler.

        Args:
            command: Command dict with 'action' field and action-specific data
        """
        action = command.get("action")
        logger.info(f"Received command: {action}")

        if action == "recycle_process":
            await self._handle_recycle_process_command(command)
        elif action == "recycle_all":
            await self._handle_recycle_all_command(command)
        elif action == "resize":
            await self._handle_resize_command(command)
        else:
            logger.warning(f"Unknown command action: {action}")

    async def _handle_recycle_process_command(self, command: dict[str, Any]) -> None:
        """
        Handle recycle_process command - recycle a specific process by PID.

        Args:
            command: Command dict with 'pid' field
        """
        pid = command.get("pid")
        reason = command.get("reason", "API request")

        if pid is None:
            logger.warning("recycle_process command missing 'pid' field")
            return

        logger.info(f"Processing recycle_process command for PID={pid} (reason: {reason})")

        success = await self.recycle_process(pid=pid)
        if success:
            logger.info(f"Successfully recycled process PID={pid}")
        else:
            logger.warning(f"Failed to recycle process PID={pid} (not found or busy)")

    async def _handle_recycle_all_command(self, command: dict[str, Any]) -> None:
        """
        Handle recycle_all command - mark all processes for recycling.

        Idle processes are recycled immediately with progress updates.
        Busy processes are marked for recycling after their current execution.

        Args:
            command: Command dict with optional 'reason' field
        """
        reason = command.get("reason", "API request")
        logger.info(f"Processing recycle_all command (reason: {reason})")

        count, idle_handles = self.mark_for_recycle()
        logger.info(f"Marked {count} processes for recycling ({len(idle_handles)} idle)")

        # Publish initial scaling event for UI feedback
        if count > 0:
            try:
                from src.core.pubsub import publish_pool_scaling

                await publish_pool_scaling(
                    worker_id=self.worker_id,
                    action="recycle_all",
                    processes_affected=count,
                )
            except Exception as e:
                logger.warning(f"Failed to publish recycle_all event: {e}")

        # Recycle idle processes with progress updates
        for i, handle in enumerate(idle_handles):
            try:
                from src.core.pubsub import publish_pool_progress
                await publish_pool_progress(
                    worker_id=self.worker_id,
                    action="recycle_all",
                    current=i + 1,
                    total=count,
                    message=f"Recycling process {i + 1} of {count}...",
                )
            except Exception as e:
                logger.warning(f"Failed to publish progress: {e}")

            # Recycle this idle process
            await self._recycle_idle_process(handle)

    async def _handle_resize_command(self, command: dict[str, Any]) -> None:
        """
        Handle resize command - update min/max workers and scale pool.

        Args:
            command: Command dict with 'min_workers' and 'max_workers' fields
        """
        new_min = command.get("min_workers")
        new_max = command.get("max_workers")

        if new_min is None or new_max is None:
            logger.warning("resize command missing min_workers or max_workers")
            return

        logger.info(f"Processing resize command: min={new_min}, max={new_max}")

        try:
            result = await self.resize(new_min, new_max)
            logger.info(f"Resize complete: {result}")
        except ValueError as e:
            logger.error(f"Resize failed: {e}")

    async def _handle_cancel_request(self, execution_id: str) -> None:
        """
        Handle cancellation request for a running execution.

        Finds the process handling the execution and kills it.

        Args:
            execution_id: Execution ID to cancel
        """
        # Find process handling this execution
        for handle in list(self.processes.values()):
            if (
                handle.current_execution
                and handle.current_execution.execution_id == execution_id
            ):
                logger.info(f"Cancelling execution {execution_id[:8]}...")

                # Kill process (same as timeout)
                await self._kill_process(handle)

                # Report cancellation
                await self._report_cancellation(handle.current_execution)

                # Remove from pool and replace
                del self.processes[handle.id]
                if len(self.processes) < self.min_workers:
                    self._spawn_process()

                return

        logger.debug(
            f"Cancellation request for {execution_id[:8]}... - not found in pool"
        )

    async def _report_cancellation(self, exec_info: ExecutionInfo) -> None:
        """
        Report a cancellation to the result callback.

        Args:
            exec_info: ExecutionInfo for the cancelled execution
        """
        if self.on_result:
            try:
                await self.on_result({
                    "type": "result",
                    "execution_id": exec_info.execution_id,
                    "success": False,
                    "error": "Execution was cancelled",
                    "error_type": "CancelledError",
                    "duration_ms": int(exec_info.elapsed_seconds * 1000),
                })
            except Exception as e:
                logger.exception(f"Error reporting cancellation: {e}")

    async def _check_process_health(self) -> None:
        """
        Check for crashed processes and replace them.

        For each process that is not alive but not in KILLED state,
        marks it as crashed and spawns a replacement if needed.
        """
        to_remove: list[str] = []

        for process_id, handle in self.processes.items():
            if not handle.is_alive and handle.state != ProcessState.KILLED:
                logger.warning(
                    f"Process {process_id} crashed "
                    f"(exit_code={handle.process.exitcode})"
                )

                # Report crash if there was an execution in progress
                if handle.current_execution:
                    await self._report_crash(handle.current_execution)

                to_remove.append(process_id)

        # Remove crashed processes
        for process_id in to_remove:
            del self.processes[process_id]

        # Spawn replacements to maintain min_workers
        while len(self.processes) < self.min_workers:
            self._spawn_process()

    async def _report_crash(self, exec_info: ExecutionInfo) -> None:
        """
        Report a crash to the result callback.

        Args:
            exec_info: ExecutionInfo for the crashed execution
        """
        if self.on_result:
            try:
                await self.on_result({
                    "type": "result",
                    "execution_id": exec_info.execution_id,
                    "success": False,
                    "error": "Worker process crashed unexpectedly",
                    "error_type": "ProcessCrashError",
                    "duration_ms": int(exec_info.elapsed_seconds * 1000),
                })
            except Exception as e:
                logger.exception(f"Error reporting crash: {e}")

    async def _maybe_scale_down(self) -> None:
        """
        Remove excess idle processes if above min_workers.

        Removes the oldest idle processes first to maintain min_workers.
        """
        idle_processes = [
            p for p in self.processes.values()
            if p.state == ProcessState.IDLE and p.is_alive
        ]

        excess = len(self.processes) - self.min_workers
        if excess <= 0:
            return

        # Sort by age (oldest first)
        idle_processes.sort(key=lambda p: p.started_at)

        # Remove oldest idle processes up to excess count
        to_remove = idle_processes[:excess]

        if not to_remove:
            return

        # Publish scaling event
        try:
            from src.core.pubsub import publish_pool_scaling
            await publish_pool_scaling(
                worker_id=self.worker_id,
                action="scale_down",
                processes_affected=len(to_remove),
            )
        except Exception as e:
            logger.warning(f"Failed to publish scale_down event: {e}")

        for i, handle in enumerate(to_remove):
            # Publish progress
            try:
                from src.core.pubsub import publish_pool_progress
                await publish_pool_progress(
                    worker_id=self.worker_id,
                    action="scale_down",
                    current=i + 1,
                    total=len(to_remove),
                    message=f"Terminating process {i + 1} of {len(to_remove)}...",
                )
            except Exception as e:
                logger.warning(f"Failed to publish progress: {e}")

            logger.info(f"Scaling down: removing idle process {handle.id}")
            await self._terminate_process(handle)
            del self.processes[handle.id]

    async def _result_loop(self) -> None:
        """
        Collect results from all process result queues.

        Polls result queues from all processes (non-blocking) and
        handles completed executions.
        """
        logger.info("Result loop started")

        while not self._shutdown:
            try:
                for handle in list(self.processes.values()):
                    try:
                        result = handle.result_queue.get_nowait()
                        await self._handle_result(handle, result)
                    except Empty:
                        pass
                    except Exception as e:
                        logger.exception(f"Result loop error for {handle.id}: {e}")
            except Exception as e:
                logger.exception(f"Result loop error: {e}")

            await asyncio.sleep(0.1)

        logger.info("Result loop stopped")

    async def _handle_result(
        self,
        handle: ProcessHandle,
        result: dict[str, Any],
    ) -> None:
        """
        Handle a result from a worker process.

        Args:
            handle: ProcessHandle that produced the result
            result: Result data from the worker
        """
        # Clear current execution
        handle.current_execution = None
        handle.executions_completed += 1

        # Check if should recycle (pending flag or execution count threshold)
        if handle.pending_recycle:
            logger.info(f"Recycling process {handle.id} (pending recycle flag)")
            await self._recycle_process(handle)
            return

        if self.recycle_after_executions > 0:
            if handle.executions_completed >= self.recycle_after_executions:
                await self._recycle_process(handle)
                return

        # Return to IDLE state
        handle.state = ProcessState.IDLE

        # Notify any waiters that an idle process is available
        async with self._idle_condition:
            self._idle_condition.notify_all()

        # Forward result to callback
        if self.on_result:
            try:
                await self.on_result(result)
            except Exception as e:
                logger.exception(f"Error in result callback: {e}")

    async def _recycle_process(self, handle: ProcessHandle) -> None:
        """
        Recycle a process by terminating and spawning replacement.

        Args:
            handle: ProcessHandle to recycle
        """
        # Check if already removed (race condition with multiple recycle paths)
        if handle.id not in self.processes:
            return

        logger.info(
            f"Recycling process {handle.id} after "
            f"{handle.executions_completed} executions"
        )

        # Remove from processes dict FIRST to prevent routing to dying process
        # A new process will be spawned with a fresh work queue
        del self.processes[handle.id]

        # Spawn replacement immediately so we maintain worker count
        self._spawn_process()

        # Then terminate the old process (this includes grace period wait)
        await self._terminate_process(handle)

    async def recycle_process(self, pid: int | None = None) -> bool:
        """
        Manually recycle a process.

        If pid is provided, recycles that specific process.
        If pid is None, recycles any idle process.

        Args:
            pid: Process ID to recycle, or None for any idle

        Returns:
            True if recycle was triggered, False if not found
        """
        target: ProcessHandle | None = None

        if pid is not None:
            for p in self.processes.values():
                if p.pid == pid:
                    target = p
                    break
        else:
            # Find any idle process
            target = self._get_idle_process()

        if target is None:
            return False

        if target.state == ProcessState.BUSY:
            logger.warning(f"Cannot recycle busy process {target.id}")
            return False

        await self._terminate_process(target)
        # The process might have been removed by the monitor loop during the
        # graceful shutdown wait. Only delete if still present.
        if target.id in self.processes:
            del self.processes[target.id]
        self._spawn_process()

        return True

    async def resize(self, new_min: int, new_max: int) -> dict[str, Any]:
        """
        Dynamically resize the pool.

        Adjusts min_workers and max_workers, then scales the pool:
        - Scale up: spawn processes if current size < new_min
        - Scale down: mark excess idle processes for removal (preserve busy)

        Args:
            new_min: New minimum worker count (must be >= 2)
            new_max: New maximum worker count (must be >= new_min)

        Returns:
            Dict with old/new config and scaling actions taken

        Raises:
            ValueError: If new_min < 2 or new_min > new_max
        """
        # Validate bounds
        if new_min < 2:
            raise ValueError(f"min_workers must be >= 2, got {new_min}")
        if new_min > new_max:
            raise ValueError(
                f"min_workers ({new_min}) cannot be greater than max_workers ({new_max})"
            )

        old_min = self.min_workers
        old_max = self.max_workers
        current_size = len(self.processes)

        logger.info(
            f"Resizing pool: min {old_min}->{new_min}, max {old_max}->{new_max}, "
            f"current size: {current_size}"
        )

        # Update config
        self.min_workers = new_min
        self.max_workers = new_max

        processes_spawned = 0
        processes_marked_for_removal = 0

        # Scale up if needed
        if current_size < new_min:
            to_spawn = new_min - current_size
            logger.info(f"Scaling up: spawning {to_spawn} processes")

            # Publish initial scaling event
            try:
                from src.core.pubsub import publish_pool_scaling, publish_pool_progress
                await publish_pool_scaling(
                    worker_id=self.worker_id,
                    action="scale_up",
                    processes_affected=to_spawn,
                )
            except Exception as e:
                logger.warning(f"Failed to publish scale_up event: {e}")

            for i in range(to_spawn):
                # Publish progress before spawning
                try:
                    from src.core.pubsub import publish_pool_progress
                    await publish_pool_progress(
                        worker_id=self.worker_id,
                        action="scale_up",
                        current=i + 1,
                        total=to_spawn,
                        message=f"Spawning process {i + 1} of {to_spawn}...",
                    )
                except Exception as e:
                    logger.warning(f"Failed to publish progress: {e}")

                self._spawn_process()
                processes_spawned += 1

        # Scale down if needed (mark excess idle processes for termination)
        elif current_size > new_max:
            excess = current_size - new_max
            logger.info(f"Scaling down: marking {excess} idle processes for removal")

            # Find idle processes to remove (oldest first)
            idle_handles = [
                h for h in self.processes.values()
                if h.state == ProcessState.IDLE
            ]
            # Sort by started_at to remove oldest first
            idle_handles.sort(key=lambda h: h.started_at or datetime.min.replace(tzinfo=timezone.utc))

            to_remove = idle_handles[:excess]

            # Publish initial scaling event
            if to_remove:
                try:
                    from src.core.pubsub import publish_pool_scaling
                    await publish_pool_scaling(
                        worker_id=self.worker_id,
                        action="scale_down",
                        processes_affected=len(to_remove),
                    )
                except Exception as e:
                    logger.warning(f"Failed to publish scale_down event: {e}")

            for i, handle in enumerate(to_remove):
                # Publish progress before terminating
                try:
                    from src.core.pubsub import publish_pool_progress
                    await publish_pool_progress(
                        worker_id=self.worker_id,
                        action="scale_down",
                        current=i + 1,
                        total=len(to_remove),
                        message=f"Terminating process {i + 1} of {len(to_remove)}...",
                    )
                except Exception as e:
                    logger.warning(f"Failed to publish progress: {e}")

                # Mark for removal and terminate
                asyncio.create_task(self._scale_down_process(handle))
                processes_marked_for_removal += 1

        # Update Redis registration with new config
        await self._update_redis_config()

        # Publish config changed event
        try:
            from src.core.pubsub import publish_pool_config_changed
            await publish_pool_config_changed(
                worker_id=self.worker_id,
                old_min=old_min,
                old_max=old_max,
                new_min=new_min,
                new_max=new_max,
            )
        except Exception as e:
            logger.warning(f"Failed to publish config changed event: {e}")

        result = {
            "old_min": old_min,
            "old_max": old_max,
            "new_min": new_min,
            "new_max": new_max,
            "processes_spawned": processes_spawned,
            "processes_marked_for_removal": processes_marked_for_removal,
        }

        logger.info(f"Resize complete: {result}")
        return result

    async def _scale_down_process(self, handle: ProcessHandle) -> None:
        """
        Terminate a process as part of scale-down operation.

        Only terminates idle processes. If the process becomes busy
        before we can terminate it, skip it.

        Args:
            handle: ProcessHandle to terminate
        """
        if handle.state != ProcessState.IDLE:
            logger.debug(f"Skipping scale-down of {handle.id} - no longer idle")
            return

        if handle.id not in self.processes:
            return  # Already removed

        logger.info(f"Scale-down: terminating process {handle.id}")

        # Remove from processes dict
        del self.processes[handle.id]

        # Terminate the process
        await self._terminate_process(handle)

    async def _update_redis_config(self) -> None:
        """Update the Redis registration with current min/max workers."""
        try:
            r = await self._get_redis()
            redis_key = f"bifrost:pool:{self.worker_id}"
            await r.hset(  # type: ignore[misc]
                redis_key,
                mapping={
                    "min_workers": str(self.min_workers),
                    "max_workers": str(self.max_workers),
                }
            )
            logger.debug(
                f"Updated Redis config: min={self.min_workers}, max={self.max_workers}"
            )
        except Exception as e:
            logger.warning(f"Failed to update Redis config: {e}")

    def mark_for_recycle(self) -> tuple[int, list[ProcessHandle]]:
        """
        Mark all worker processes for recycling after their current execution.

        Called after package installation so workers pick up newly installed
        packages. Each process will be recycled (terminated + respawned) after
        completing its current execution. Returns list of idle processes to
        be recycled so caller can publish progress.

        Returns:
            Tuple of (total count, list of idle handles to recycle immediately)
        """
        idle_handles: list[ProcessHandle] = []
        marked_for_later = 0

        for handle in list(self.processes.values()):
            if handle.state == ProcessState.IDLE:
                # Idle process - mark for immediate recycle
                handle.pending_recycle = True
                idle_handles.append(handle)
            else:
                # Busy process - mark for recycle after current execution
                handle.pending_recycle = True
                marked_for_later += 1

        logger.info(
            f"Marked {len(self.processes)} processes for recycle "
            f"({len(idle_handles)} immediate, {marked_for_later} after execution)"
        )
        return len(self.processes), idle_handles

    async def _recycle_idle_process(self, handle: ProcessHandle) -> None:
        """Recycle an idle process immediately."""
        if handle.id not in self.processes:
            return  # Already removed
        if handle.state != ProcessState.IDLE:
            return  # No longer idle, will be recycled after execution

        logger.info(f"Recycling idle process {handle.id} (package install)")
        await self._recycle_process(handle)

    async def _heartbeat_loop(self) -> None:
        """
        Periodic heartbeat publishing loop.

        Refreshes Redis TTL and publishes heartbeat with pool state.
        """
        logger.info(
            f"Heartbeat loop started (interval={self.heartbeat_interval_seconds}s)"
        )

        while not self._shutdown:
            try:
                # Refresh registration
                await self._refresh_registration()

                # Build and publish heartbeat
                heartbeat = self._build_heartbeat()
                await self._publish_heartbeat(heartbeat)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(self.heartbeat_interval_seconds)

        logger.info("Heartbeat loop stopped")

    async def _register_worker(self) -> None:
        """
        Register worker in Redis with TTL.

        Creates a Redis hash with worker metadata and sets TTL.
        Includes list of installed packages for API visibility.
        """
        r = await self._get_redis()
        redis_key = f"bifrost:pool:{self.worker_id}"

        # Get installed packages for API visibility
        packages = _get_installed_packages()

        # Store pool metadata in Redis hash
        await r.hset(  # type: ignore[misc]
            redis_key,
            mapping={
                "started_at": datetime.now(timezone.utc).isoformat(),
                "status": "online",
                "hostname": os.environ.get("HOSTNAME", "unknown"),
                "min_workers": str(self.min_workers),
                "max_workers": str(self.max_workers),
                "packages": json.dumps(packages),
            }
        )
        await r.expire(redis_key, self.registration_ttl_seconds)

        logger.info(
            f"Registered pool {self.worker_id} in Redis "
            f"(TTL={self.registration_ttl_seconds}s, {len(packages)} packages)"
        )

    async def _refresh_registration(self) -> None:
        """Refresh the Redis registration TTL."""
        r = await self._get_redis()
        await r.expire(f"bifrost:pool:{self.worker_id}", self.registration_ttl_seconds)

    async def update_packages(self) -> None:
        """
        Update the packages field in Redis after a package installation.

        Called by the package install consumer after successfully installing a package.
        This ensures the /api/packages endpoint reflects newly installed packages.
        """
        if not self._started:
            logger.debug("Pool not started, skipping package update")
            return

        try:
            r = await self._get_redis()
            redis_key = f"bifrost:pool:{self.worker_id}"
            packages = _get_installed_packages()
            await r.hset(redis_key, "packages", json.dumps(packages))  # type: ignore[misc]
            logger.info(f"Updated packages in Redis: {len(packages)} packages")
        except Exception as e:
            logger.warning(f"Failed to update packages in Redis: {e}")

    async def _unregister_worker(self) -> None:
        """
        Unregister worker from Redis.

        Deletes the Redis key and publishes offline event.
        """
        try:
            r = await self._get_redis()
            await r.delete(f"bifrost:pool:{self.worker_id}")
            logger.info(f"Unregistered pool {self.worker_id} from Redis")

            # Publish offline event
            try:
                from src.core.pubsub import publish_worker_event

                await publish_worker_event({
                    "type": "worker_offline",
                    "worker_id": self.worker_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.warning(f"Failed to publish worker_offline event: {e}")

        except Exception as e:
            logger.error(f"Error unregistering worker: {e}")

    def _build_heartbeat(self) -> dict[str, Any]:
        """
        Build heartbeat payload with all process state.

        Returns:
            Dict with worker_id, timestamp, processes, and pool info
        """
        processes = []
        for p in self.processes.values():
            info: dict[str, Any] = {
                "pid": p.pid,
                "process_id": p.id,
                "state": p.state.value,
                "memory_mb": self._get_process_memory(p.pid),
                "uptime_seconds": p.uptime_seconds,
                "executions_completed": p.executions_completed,
                "pending_recycle": p.pending_recycle,
            }
            if p.current_execution:
                info["execution"] = {
                    "execution_id": p.current_execution.execution_id,
                    "started_at": p.current_execution.started_at.isoformat(),
                    "elapsed_seconds": p.current_execution.elapsed_seconds,
                }
            processes.append(info)

        idle_count = len([p for p in self.processes.values() if p.state == ProcessState.IDLE])
        busy_count = len([p for p in self.processes.values() if p.state == ProcessState.BUSY])

        return {
            "type": "worker_heartbeat",
            "worker_id": self.worker_id,
            "hostname": os.environ.get("HOSTNAME", "unknown"),
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processes": processes,
            "pool_size": len(self.processes),
            "idle_count": idle_count,
            "busy_count": busy_count,
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
        }

    def _get_process_memory(self, pid: int | None) -> float:
        """
        Get memory usage for a process in MB.

        Args:
            pid: Process ID to check

        Returns:
            Memory usage in MB, or 0 if not available
        """
        if pid is None:
            return 0.0
        try:
            process = psutil.Process(pid)
            return process.memory_info().rss / 1024 / 1024
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0

    async def _publish_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        """
        Publish heartbeat to WebSocket channel.

        Args:
            heartbeat: Heartbeat payload to publish
        """
        try:
            from src.core.pubsub import publish_worker_heartbeat

            await publish_worker_heartbeat(heartbeat)
        except Exception as e:
            logger.warning(f"Failed to publish heartbeat: {e}")

    def get_status(self) -> dict[str, Any]:
        """
        Get current pool status.

        Returns:
            Dict with pool state and process details
        """
        return {
            "started": self._started,
            "shutdown": self._shutdown,
            "worker_id": self.worker_id,
            "pool_size": len(self.processes),
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "processes": [
                {
                    "process_id": p.id,
                    "pid": p.pid,
                    "state": p.state.value,
                    "uptime_seconds": p.uptime_seconds,
                    "executions_completed": p.executions_completed,
                    "is_alive": p.is_alive,
                    "current_execution": p.current_execution.execution_id if p.current_execution else None,
                }
                for p in self.processes.values()
            ],
        }


# Global pool instance
_pool: ProcessPoolManager | None = None


def get_process_pool() -> ProcessPoolManager:
    """
    Get the global process pool instance, creating if needed.

    Uses settings for configuration.
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ProcessPoolManager(
            min_workers=settings.min_workers,
            max_workers=settings.max_workers,
            execution_timeout_seconds=settings.execution_timeout_seconds,
            graceful_shutdown_seconds=settings.graceful_shutdown_seconds,
            recycle_after_executions=settings.recycle_after_executions,
            heartbeat_interval_seconds=settings.worker_heartbeat_interval_seconds,
            registration_ttl_seconds=settings.worker_registration_ttl_seconds,
        )
    return _pool


async def shutdown_process_pool() -> None:
    """Shutdown the global process pool."""
    global _pool
    if _pool:
        await _pool.stop()
        _pool = None
