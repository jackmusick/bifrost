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
from typing import Any
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
            async for message in self._pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"].decode().replace("bifrost:", "")
                    data = json.loads(message["data"])
                    await self._send_local(channel, data)
        except asyncio.CancelledError:
            pass
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


def publish_to_redis_sync(channel: str, message: dict[str, Any]) -> None:
    """
    Publish to Redis using sync client.

    This avoids event loop affinity issues when publishing from
    worker threads. Uses a thread-local connection for efficiency.

    Args:
        channel: Channel name (without bifrost: prefix)
        message: Message payload
    """
    import threading
    import redis as redis_sync  # Sync redis client

    # Thread-local storage for Redis connections
    if not hasattr(publish_to_redis_sync, '_local'):
        publish_to_redis_sync._local = threading.local()

    local = publish_to_redis_sync._local

    # Get or create connection for this thread
    if not hasattr(local, 'redis') or local.redis is None:
        settings = get_settings()
        local.redis = redis_sync.from_url(settings.redis_url)

    try:
        local.redis.publish(f"bifrost:{channel}", json.dumps(message))
    except Exception as e:
        logger.warning(f"Failed to publish to Redis (sync): {e}")
        # Reset connection on error
        local.redis = None


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


def publish_execution_log_sync(
    execution_id: str | UUID,
    level: str,
    message: str,
    data: dict[str, Any] | None = None
) -> None:
    """
    Publish execution log entry (sync version for worker threads).

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
    publish_to_redis_sync(f"execution:{execution_id}", log_entry)


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
# Workspace File Sync Pub/Sub
# =============================================================================
# These functions enable containers to stay in sync without shared NFS volumes.
# When a file is written/deleted/renamed, all containers are notified to apply
# the same change to their local /tmp workspace.


async def publish_workspace_file_write(
    path: str,
    content: bytes,
    content_hash: str,
) -> None:
    """
    Publish workspace file write event.

    All containers listening will write this content to their local workspace.

    Args:
        path: File path relative to workspace root
        content: File content bytes (base64 encoded for transport)
        content_hash: SHA-256 hash for verification
    """
    import base64

    message = {
        "type": "workspace_file_write",
        "path": path,
        "content": base64.b64encode(content).decode("utf-8"),
        "content_hash": content_hash,
    }
    logger.info(f"Publishing workspace file write: {path}")
    await manager._publish_to_redis("workspace:sync", message)


async def publish_workspace_file_delete(path: str) -> None:
    """
    Publish workspace file delete event.

    All containers listening will delete this file from their local workspace.

    Args:
        path: File path relative to workspace root
    """
    message = {
        "type": "workspace_file_delete",
        "path": path,
    }
    await manager._publish_to_redis("workspace:sync", message)


async def publish_workspace_file_rename(old_path: str, new_path: str) -> None:
    """
    Publish workspace file rename event.

    All containers listening will rename this file in their local workspace.

    Args:
        old_path: Original file path
        new_path: New file path
    """
    message = {
        "type": "workspace_file_rename",
        "old_path": old_path,
        "new_path": new_path,
    }
    await manager._publish_to_redis("workspace:sync", message)


async def publish_workspace_folder_create(path: str) -> None:
    """
    Publish workspace folder create event.

    All containers listening will create this folder in their local workspace.

    Args:
        path: Folder path relative to workspace root (with trailing slash)
    """
    message = {
        "type": "workspace_folder_create",
        "path": path,
    }
    await manager._publish_to_redis("workspace:sync", message)


async def publish_workspace_folder_delete(path: str) -> None:
    """
    Publish workspace folder delete event.

    All containers listening will delete this folder from their local workspace.

    Args:
        path: Folder path relative to workspace root (with trailing slash)
    """
    message = {
        "type": "workspace_folder_delete",
        "path": path,
    }
    await manager._publish_to_redis("workspace:sync", message)


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


def publish_workspace_file_write_sync(
    path: str,
    content: bytes,
    content_hash: str,
) -> None:
    """
    Publish workspace file write event (sync version for non-async contexts).

    Args:
        path: File path relative to workspace root
        content: File content bytes
        content_hash: SHA-256 hash for verification
    """
    import base64

    message = {
        "type": "workspace_file_write",
        "path": path,
        "content": base64.b64encode(content).decode("utf-8"),
        "content_hash": content_hash,
    }
    publish_to_redis_sync("workspace:sync", message)


def publish_workspace_file_delete_sync(path: str) -> None:
    """
    Publish workspace file delete event (sync version).

    Args:
        path: File path relative to workspace root
    """
    message = {
        "type": "workspace_file_delete",
        "path": path,
    }
    publish_to_redis_sync("workspace:sync", message)
