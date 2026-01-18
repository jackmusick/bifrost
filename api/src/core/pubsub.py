"""
WebSocket PubSub Infrastructure

Provides real-time updates for:
- Execution status changes
- Log streaming
- System notifications

Uses Redis pub/sub for scalability across multiple API instances.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import UUID

import redis.asyncio as redis
from fastapi import WebSocket

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ConnectionManager:
    """
    Manages WebSocket connections and Redis pub/sub subscriptions.

    Channels:
    - execution:{execution_id} - Execution status updates and logs
    - user:{user_id} - User-specific notifications
    - system - System-wide broadcasts
    """

    # Active WebSocket connections per channel
    connections: dict[str, set[WebSocket]] = field(default_factory=dict)
    # Redis pub/sub connection
    _redis: redis.Redis | None = None
    _pubsub: redis.client.PubSub | None = None
    _listener_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket, channels: list[str]) -> None:
        """
        Accept WebSocket connection and subscribe to channels.

        Args:
            websocket: FastAPI WebSocket connection
            channels: List of channels to subscribe to
        """
        await websocket.accept()

        # Ensure Redis listener is running for cross-container messages
        # This fixes a race condition where the scheduler publishes progress
        # before the API's Redis listener is started
        if not self._redis:
            await self._init_redis()

        for channel in channels:
            if channel not in self.connections:
                self.connections[channel] = set()
            self.connections[channel].add(websocket)
            logger.debug(f"WebSocket connected to channel: {channel}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket from all channels."""
        for channel, sockets in list(self.connections.items()):
            sockets.discard(websocket)
            if not sockets:
                del self.connections[channel]
        logger.debug("WebSocket disconnected")

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        """
        Broadcast message to all connections on a channel.
        Publishes to Redis for cross-instance delivery (including this instance).

        Args:
            channel: Channel name
            message: Message payload
        """
        # Publish to Redis - the Redis listener will deliver to local connections
        # This avoids double-delivery (once here, once from Redis listener)
        published = await self._publish_to_redis(channel, message)

        # Only send locally if Redis is unavailable (fallback mode)
        if not published:
            await self._send_local(channel, message)

    async def _send_local(self, channel: str, message: dict[str, Any]) -> None:
        """Send message to local WebSocket connections."""
        if channel not in self.connections:
            return

        dead_connections = set()
        message_json = json.dumps(message)

        for websocket in self.connections[channel]:
            try:
                await websocket.send_text(message_json)
            except Exception:
                dead_connections.add(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)

    async def _publish_to_redis(self, channel: str, message: dict[str, Any]) -> bool:
        """
        Publish message to Redis pub/sub.

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not self._redis:
            await self._init_redis()

        if self._redis:
            try:
                await self._redis.publish(
                    f"bifrost:{channel}",
                    json.dumps(message)
                )
                return True
            except Exception as e:
                logger.warning(f"Failed to publish to Redis: {e}")
                return False
        return False

    async def _init_redis(self) -> None:
        """Initialize Redis connection and start listener."""
        settings = get_settings()
        try:
            self._redis = redis.from_url(settings.redis_url)
            pubsub = self._redis.pubsub()
            self._pubsub = pubsub

            # Subscribe to all bifrost channels
            await pubsub.psubscribe("bifrost:*")

            # Start listener task
            self._listener_task = asyncio.create_task(self._redis_listener())
            logger.info("Redis pub/sub initialized")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self._redis = None

    async def _redis_listener(self) -> None:
        """Listen for messages from Redis and forward to local connections."""
        if not self._pubsub:
            return

        try:
            while True:
                # Use get_message with timeout instead of blocking listen()
                # This allows the task to check for cancellation periodically
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.5  # Check for cancellation every 500ms
                )
                if message and message["type"] == "pmessage":
                    channel = message["channel"].decode().replace("bifrost:", "")
                    data = json.loads(message["data"])
                    await self._send_local(channel, data)
        except asyncio.CancelledError:
            logger.debug("Redis listener cancelled")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")

    async def close(self) -> None:
        """Clean up connections."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()


# Global connection manager instance
manager = ConnectionManager()


# Convenience functions for common pubsub operations

async def publish_execution_update(
    execution_id: str | UUID,
    status: str,
    data: dict[str, Any] | None = None
) -> None:
    """
    Publish execution status update.

    Args:
        execution_id: Execution ID
        status: New status (Pending, Running, Success, Failed, etc.)
        data: Additional data (result, error, logs, etc.)
    """
    message = {
        "type": "execution_update",
        "executionId": str(execution_id),
        "status": status,
        **(data or {})
    }
    await manager.broadcast(f"execution:{execution_id}", message)


async def publish_execution_log(
    execution_id: str | UUID,
    level: str,
    message: str,
    data: dict[str, Any] | None = None
) -> None:
    """
    Publish execution log entry (async version).

    Args:
        execution_id: Execution ID
        level: Log level (debug, info, warning, error)
        message: Log message
        data: Additional log data
    """
    log_entry = {
        "type": "execution_log",
        "executionId": str(execution_id),
        "level": level,
        "message": message,
        "data": data
    }
    await manager.broadcast(f"execution:{execution_id}", log_entry)


async def publish_history_update(
    execution_id: str | UUID,
    status: str,
    executed_by: str | UUID,
    executed_by_name: str,
    workflow_name: str,
    org_id: str | UUID | None = None,
    started_at: Any = None,
    completed_at: Any = None,
    duration_ms: int | None = None,
) -> None:
    """
    Publish execution update to history channels.

    Broadcasts to:
    - history:user:{executed_by} - for the user who ran the execution
    - history:GLOBAL - for platform admins watching all executions

    Args:
        execution_id: Execution ID
        status: Execution status (Pending, Running, Success, Failed, etc.)
        executed_by: User ID who ran the execution
        executed_by_name: Display name of the user
        workflow_name: Name of the workflow
        org_id: Organization ID (if org-scoped)
        started_at: When the execution started
        completed_at: When the execution completed
        duration_ms: Execution duration in milliseconds
    """
    from datetime import datetime

    message = {
        "type": "history_update",
        "execution_id": str(execution_id),
        "workflow_name": workflow_name,
        "status": status,
        "executed_by": str(executed_by),
        "executed_by_name": executed_by_name,
        "org_id": str(org_id) if org_id else None,
        "started_at": started_at.isoformat() if isinstance(started_at, datetime) else started_at,
        "completed_at": completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at,
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Always publish to user's channel and global admin channel
    await manager.broadcast(f"history:user:{executed_by}", message)
    await manager.broadcast("history:GLOBAL", message)


async def publish_user_notification(
    user_id: str | UUID,
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None
) -> None:
    """
    Publish user notification.

    Args:
        user_id: User ID
        notification_type: Type (info, success, warning, error)
        title: Notification title
        message: Notification message
        data: Additional data
    """
    notification = {
        "type": "notification",
        "notificationType": notification_type,
        "title": title,
        "message": message,
        **(data or {})
    }
    await manager.broadcast(f"user:{user_id}", notification)


async def publish_system_event(
    event_type: str,
    data: dict[str, Any]
) -> None:
    """
    Publish system-wide event.

    Args:
        event_type: Event type
        data: Event data
    """
    event = {
        "type": "system_event",
        "eventType": event_type,
        **data
    }
    await manager.broadcast("system", event)


# =============================================================================
# Local Runner Pub/Sub (CLI<->Web Communication)
# =============================================================================


async def publish_local_runner_state_update(
    user_id: str | UUID,
    state: dict[str, Any] | None,
) -> None:
    """
    Publish local runner state update.

    Notifies the web UI when CLI registers workflows or state changes.

    Args:
        user_id: User ID
        state: Current local runner state (None if no active session)
    """
    message = {
        "type": "local_runner_state_update",
        "state": state,
    }
    await manager.broadcast(f"local-runner:{user_id}", message)


# Alias for backwards compatibility
publish_devrun_state_update = publish_local_runner_state_update


async def publish_cli_session_update(
    user_id: str | UUID,
    session_id: str,
    state: dict[str, Any] | None,
) -> None:
    """
    Publish CLI session state update.

    Notifies the web UI when CLI session state changes.

    Args:
        user_id: User ID
        session_id: CLI session ID
        state: Current CLI session state (None if session deleted)
    """
    message = {
        "type": "cli_session_update",
        "session_id": session_id,
        "state": state,
    }
    # Broadcast to both session-specific and user-level channels
    await manager.broadcast(f"cli-session:{session_id}", message)
    await manager.broadcast(f"cli-sessions:{user_id}", message)


# =============================================================================
# Reindex Pub/Sub (API -> Scheduler Communication)
# =============================================================================


async def publish_reindex_request(
    job_id: str,
    user_id: str,
) -> None:
    """
    Request a reindex operation from the scheduler.

    The scheduler listens on `bifrost:scheduler:reindex` and executes
    the reindex, publishing progress to `reindex:{job_id}`.

    Args:
        job_id: Unique job ID for tracking
        user_id: User who initiated the reindex
    """
    message = {
        "type": "reindex_request",
        "job_id": job_id,
        "user_id": user_id,
    }
    await manager._publish_to_redis("scheduler:reindex", message)


async def publish_reindex_progress(
    job_id: str,
    phase: str,
    current: int,
    total: int,
    current_file: str | None = None,
) -> None:
    """
    Publish reindex progress update.

    Args:
        job_id: Unique job ID
        phase: Current phase (downloading, validating_workflows, etc.)
        current: Current item number
        total: Total items to process
        current_file: Currently processing file path
    """
    message = {
        "type": "progress",
        "jobId": job_id,
        "phase": phase,
        "current": current,
        "total": total,
        "current_file": current_file,
    }
    await manager.broadcast(f"reindex:{job_id}", message)


async def publish_reindex_completed(
    job_id: str,
    counts: dict,
    warnings: list[str],
    errors: list[dict],
) -> None:
    """
    Publish reindex completion.

    Args:
        job_id: Unique job ID
        counts: Summary counts from reindex
        warnings: List of warning messages
        errors: List of ReindexError dicts
    """
    message = {
        "type": "completed",
        "jobId": job_id,
        "counts": counts,
        "warnings": warnings,
        "errors": errors,
    }
    await manager.broadcast(f"reindex:{job_id}", message)


async def publish_reindex_failed(
    job_id: str,
    error: str,
) -> None:
    """
    Publish reindex failure.

    Args:
        job_id: Unique job ID
        error: Error message
    """
    message = {
        "type": "failed",
        "jobId": job_id,
        "error": error,
    }
    await manager.broadcast(f"reindex:{job_id}", message)


# =============================================================================
# App Builder Pub/Sub
# =============================================================================
# These functions enable real-time updates for App Builder applications.
# - Draft mode viewers see changes instantly when MCP/editor makes modifications
# - Published app users see a "New Version Available" indicator when republished


async def publish_app_draft_update(
    app_id: str,
    user_id: str,
    user_name: str,
    entity_type: str,  # 'page' | 'component' | 'app'
    entity_id: str,
    page_id: str | None = None,
) -> None:
    """
    Broadcast draft changes to app:draft:{app_id} channel.

    Notifies draft mode viewers when pages, components, or app settings
    are modified by MCP tools or the visual editor.

    Args:
        app_id: Application ID
        user_id: User who made the change
        user_name: Display name of the user
        entity_type: Type of entity changed ('page', 'component', 'app')
        entity_id: ID of the changed entity
        page_id: Page ID (for component changes)
    """
    from datetime import datetime, timezone

    channel = f"app:draft:{app_id}"
    message = {
        "type": "app_draft_update",
        "appId": app_id,
        "entityType": entity_type,
        "entityId": entity_id,
        "pageId": page_id,
        "userId": user_id,
        "userName": user_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(channel, message)


async def publish_app_code_file_update(
    app_id: str,
    user_id: str,
    user_name: str,
    path: str,
    source: str | None = None,
    compiled: str | None = None,
    action: str = "update",  # 'create', 'update', 'delete'
) -> None:
    """
    Broadcast code file changes with full content to app:draft:{app_id} channel.

    This specialized function includes the file content, enabling
    real-time preview updates without additional API calls.

    Args:
        app_id: Application ID
        user_id: User who made the change
        user_name: Display name of the user
        path: File path (e.g., 'pages/index', 'components/Button')
        source: Source code content (None for delete)
        compiled: Compiled JS content (None for delete or if not compiled)
        action: Type of change ('create', 'update', 'delete')
    """
    from datetime import datetime, timezone

    channel = f"app:draft:{app_id}"
    message = {
        "type": "app_code_file_update",
        "appId": app_id,
        "action": action,
        "path": path,
        "source": source,
        "compiled": compiled,
        "userId": user_id,
        "userName": user_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(channel, message)


async def publish_app_published(
    app_id: str,
    user_id: str,
    user_name: str,
    new_version_id: str,
) -> None:
    """
    Broadcast publish event to app:live:{app_id} channel.

    Notifies live app viewers that a new version has been published,
    allowing them to see a "New Version Available" indicator.

    Args:
        app_id: Application ID
        user_id: User who published the app
        user_name: Display name of the user
        new_version_id: ID of the newly published version
    """
    from datetime import datetime, timezone

    channel = f"app:live:{app_id}"
    message = {
        "type": "app_published",
        "appId": app_id,
        "newVersionId": new_version_id,
        "userId": user_id,
        "userName": user_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast(channel, message)


# =============================================================================
# Git Sync Pub/Sub (API -> Scheduler Communication)
# =============================================================================


async def publish_git_sync_request(
    job_id: str,
    org_id: str,
    user_id: str,
    user_email: str,
    conflict_resolutions: Mapping[str, str],
    confirm_orphans: bool,
    confirm_unresolved_refs: bool = False,
) -> None:
    """
    Request a git sync operation from the scheduler.

    The scheduler listens on `bifrost:scheduler:git-sync` and executes
    the sync, publishing progress to `git:{job_id}`.

    Args:
        job_id: Unique job ID for tracking
        org_id: Organization ID to sync
        user_id: User who initiated the sync
        user_email: Email of the user (for git commit author)
        conflict_resolutions: Dict mapping file paths to resolution strategy
        confirm_orphans: Whether to proceed with orphan cleanup
        confirm_unresolved_refs: Whether to proceed despite unresolved refs
    """
    message = {
        "type": "git_sync_request",
        "jobId": job_id,
        "orgId": org_id,
        "userId": user_id,
        "userEmail": user_email,
        "conflictResolutions": conflict_resolutions,
        "confirmOrphans": confirm_orphans,
        "confirmUnresolvedRefs": confirm_unresolved_refs,
    }
    await manager._publish_to_redis("scheduler:git-sync", message)


async def publish_git_sync_progress(
    job_id: str,
    phase: str,
    current: int,
    total: int,
    path: str | None = None,
) -> None:
    """
    Publish git sync progress update.

    Broadcasts to git:{job_id} channel for real-time UI updates.

    Args:
        job_id: Unique job ID
        phase: Current phase (pulling, analyzing, pushing, etc.)
        current: Current item number
        total: Total items to process
        path: Current file path being processed
    """
    message = {
        "type": "git_progress",
        "jobId": job_id,
        "phase": phase,
        "current": current,
        "total": total,
        "path": path,
    }
    await manager.broadcast(f"git:{job_id}", message)


async def publish_git_sync_log(
    job_id: str,
    level: str,
    message: str,
) -> None:
    """
    Publish git sync log message.

    Broadcasts to git:{job_id} channel for real-time log streaming.

    Args:
        job_id: Unique job ID
        level: Log level (debug, info, warning, error)
        message: Log message text
    """
    log_message = {
        "type": "git_log",
        "jobId": job_id,
        "level": level,
        "message": message,
    }
    await manager.broadcast(f"git:{job_id}", log_message)


async def publish_git_sync_completed(
    job_id: str,
    status: str,
    message: str,
    **kwargs: Any,
) -> None:
    """
    Publish git sync completion.

    Broadcasts to git:{job_id} channel to notify the UI that sync is complete.
    Also stores the result in Redis for HTTP polling (5-minute TTL).

    Args:
        job_id: Unique job ID
        status: Completion status (success, failed, conflict, orphans_detected)
        message: Human-readable completion message
        **kwargs: Additional data (conflicts, orphans, counts, etc.)
    """
    import json

    completion_message = {
        "type": "git_complete",
        "jobId": job_id,
        "status": status,
        "message": message,
        **kwargs,
    }
    await manager.broadcast(f"git:{job_id}", completion_message)

    # Store result in Redis for HTTP polling (used by E2E tests and fallback)
    try:
        from src.core.redis_client import get_redis_client

        redis_client = get_redis_client()
        if redis_client:
            result_key = f"bifrost:job:{job_id}"
            # Store job result with 5-minute TTL
            await redis_client.setex(
                result_key,
                300,  # 5 minutes TTL
                json.dumps(completion_message),
            )
            logger.info(f"Stored job result in Redis: {result_key} status={status}")
        else:
            logger.warning(f"Redis client is None, cannot store job result for {job_id}")
    except Exception as e:
        logger.warning(f"Failed to store job result in Redis: {e}")


# =============================================================================
# Worker Monitoring Pub/Sub
# =============================================================================
# These functions enable real-time monitoring of worker processes.
# - Heartbeats: Periodic updates with process state, memory, executions
# - Events: Lifecycle events (online, offline, state changes)


async def publish_worker_heartbeat(heartbeat: dict[str, Any]) -> None:
    """
    Publish worker heartbeat to platform_workers channel and store in Redis.

    Contains detailed state about worker processes and their executions.
    Published every heartbeat interval (default 10s).

    The heartbeat is both:
    1. Broadcast to WebSocket subscribers for real-time updates
    2. Stored in Redis for API queries (with TTL)

    Args:
        heartbeat: Dict with worker_id, timestamp, processes, queue info
    """
    # Broadcast to WebSocket subscribers
    await manager.broadcast("platform_workers", heartbeat)

    # Store in Redis for API queries
    worker_id = heartbeat.get("worker_id")
    if worker_id:
        try:
            from src.core.redis_client import get_redis_client

            redis_client = get_redis_client()
            heartbeat_key = f"bifrost:pool:{worker_id}:heartbeat"
            # Store with TTL slightly longer than heartbeat interval
            await redis_client.setex(heartbeat_key, 60, json.dumps(heartbeat))
        except Exception as e:
            logger.warning(f"Failed to store heartbeat in Redis: {e}")


async def publish_worker_event(event: dict[str, Any]) -> None:
    """
    Publish worker lifecycle event to platform_workers channel.

    Events include:
    - worker_online: Worker registered and ready
    - worker_offline: Worker shutting down gracefully
    - process_state_changed: Worker process state changed
    - execution_stuck: Execution marked as stuck

    Args:
        event: Dict with type, worker_id, and event-specific data
    """
    await manager.broadcast("platform_workers", event)


async def publish_pool_config_changed(
    worker_id: str,
    old_min: int,
    old_max: int,
    new_min: int,
    new_max: int,
) -> None:
    """
    Publish pool configuration change event to platform_workers channel.

    Sent when min/max workers are updated via API or command.

    Args:
        worker_id: Worker/pool ID that was reconfigured
        old_min: Previous minimum workers
        old_max: Previous maximum workers
        new_min: New minimum workers
        new_max: New maximum workers
    """
    from datetime import datetime, timezone

    message = {
        "type": "pool_config_changed",
        "worker_id": worker_id,
        "old_min": old_min,
        "old_max": old_max,
        "new_min": new_min,
        "new_max": new_max,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast("platform_workers", message)


async def publish_pool_scaling(
    worker_id: str,
    action: str,
    processes_affected: int,
) -> None:
    """
    Publish pool scaling event to platform_workers channel.

    Sent when the pool scales up or down, or when processes are recycled.

    Args:
        worker_id: Worker/pool ID that is scaling
        action: Scaling action ('scale_up', 'scale_down', 'recycle_all')
        processes_affected: Number of processes affected by this action
    """
    from datetime import datetime, timezone

    message = {
        "type": "pool_scaling",
        "worker_id": worker_id,
        "action": action,
        "processes_affected": processes_affected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast("platform_workers", message)


async def publish_pool_progress(
    worker_id: str,
    action: str,
    current: int,
    total: int,
    message: str,
) -> None:
    """
    Publish real-time pool operation progress to platform_workers channel.

    Provides granular progress updates during pool operations like:
    - Scaling up: "Spawning process 3 of 4..."
    - Scaling down: "Terminating process 2 of 3..."
    - Recycling: "Recycling process 1 of 5..."

    Args:
        worker_id: Worker/pool ID performing the operation
        action: Operation type ('scale_up', 'scale_down', 'recycle_all')
        current: Current process number (1-indexed)
        total: Total processes to be affected
        message: Human-readable progress message
    """
    from datetime import datetime, timezone

    payload = {
        "type": "pool_progress",
        "worker_id": worker_id,
        "action": action,
        "current": current,
        "total": total,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast("platform_workers", payload)
