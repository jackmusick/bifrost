"""
Unified log streaming for Bifrost SDK.

Writes execution logs to Redis Stream as the single source of truth.
Two consumers read from this stream:
1. PubSub forwarder - Publishes to WebSocket for real-time delivery
2. Log persistence worker - Batch inserts to Postgres

This replaces the previous dual-write pattern (sync Postgres + Redis PubSub)
which caused duplicate logs and event loop affinity issues.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

import redis as redis_sync

from src.core.cache.keys import execution_logs_stream_key

logger = logging.getLogger(__name__)

# Thread-local storage for Redis connections
_local = threading.local()


def _serialize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Ensure metadata is JSON-serializable by converting datetime to ISO strings.

    This prevents "Object of type datetime is not JSON serializable" errors
    when metadata contains datetime objects (e.g., from workflow code).
    """
    if metadata is None:
        return None

    def convert(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        return obj

    return convert(metadata)


def _get_sync_redis() -> redis_sync.Redis:
    """Get thread-local sync Redis connection."""
    if not hasattr(_local, "redis") or _local.redis is None:
        from src.config import get_settings

        settings = get_settings()
        _local.redis = redis_sync.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _local.redis


def append_log_to_stream(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> str | None:
    """
    Append a log entry to the execution's Redis Stream.

    This is the single source of truth for execution logs.
    Call this from workflow threads (sync context).

    Args:
        execution_id: Execution UUID
        level: Log level (INFO, WARNING, ERROR, DEBUG, CRITICAL)
        message: Log message text
        metadata: Optional JSON metadata
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Stream entry ID if successful, None on error
    """
    exec_id = str(execution_id)
    ts = timestamp or datetime.utcnow()
    stream_key = execution_logs_stream_key(exec_id)

    safe_metadata = _serialize_metadata(metadata)
    entry = {
        "execution_id": exec_id,
        "level": level.upper(),
        "message": message,
        "metadata": json.dumps(safe_metadata) if safe_metadata else "{}",
        "timestamp": ts.isoformat(),
    }

    try:
        r = _get_sync_redis()
        # XADD with automatic ID generation (*)
        # MAXLEN ~ 10000 keeps stream bounded (approximate trimming)
        entry_id: str = r.xadd(stream_key, entry, maxlen=10000)  # type: ignore[misc]
        return entry_id
    except Exception as e:
        logger.warning(f"Failed to append log to stream: {e}")
        # Reset connection on error
        _local.redis = None
        return None


def publish_log_to_pubsub(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> None:
    """
    Publish log entry directly to PubSub for immediate WebSocket delivery.

    This is called alongside append_log_to_stream for real-time streaming.
    The stream is the source of truth; PubSub is for immediate delivery.

    Args:
        execution_id: Execution UUID
        level: Log level
        message: Log message
        metadata: Optional metadata
        timestamp: Optional timestamp
    """
    exec_id = str(execution_id)
    ts = timestamp or datetime.utcnow()

    safe_metadata = _serialize_metadata(metadata)
    log_entry = {
        "type": "execution_log",
        "executionId": exec_id,
        "level": level.upper(),
        "message": message,
        "metadata": safe_metadata,
        "timestamp": ts.isoformat(),
    }

    try:
        r = _get_sync_redis()
        r.publish(f"bifrost:execution:{exec_id}", json.dumps(log_entry))
    except Exception as e:
        logger.warning(f"Failed to publish log to PubSub: {e}")
        _local.redis = None


def log_and_broadcast(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> str | None:
    """
    Write log to stream AND publish to PubSub in one call.

    This is the main entry point for logging from workflow threads.
    Replaces the old pattern of calling append_log_sync + broadcaster separately.

    Args:
        execution_id: Execution UUID
        level: Log level
        message: Log message
        metadata: Optional metadata
        timestamp: Optional timestamp

    Returns:
        Stream entry ID if successful, None on error
    """
    ts = timestamp or datetime.utcnow()

    # Write to stream (source of truth for persistence)
    entry_id = append_log_to_stream(
        execution_id=execution_id,
        level=level,
        message=message,
        metadata=metadata,
        timestamp=ts,
    )

    # Publish to PubSub (immediate WebSocket delivery)
    publish_log_to_pubsub(
        execution_id=execution_id,
        level=level,
        message=message,
        metadata=metadata,
        timestamp=ts,
    )

    return entry_id


# =============================================================================
# Async versions for use in async contexts (API routes, consumers)
# =============================================================================


async def append_log_to_stream_async(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> str | None:
    """
    Async version of append_log_to_stream.

    Use this in async contexts (API routes, background tasks).
    """
    from src.core.cache import get_redis

    exec_id = str(execution_id)
    ts = timestamp or datetime.utcnow()
    stream_key = execution_logs_stream_key(exec_id)

    safe_metadata = _serialize_metadata(metadata)
    entry = {
        "execution_id": exec_id,
        "level": level.upper(),
        "message": message,
        "metadata": json.dumps(safe_metadata) if safe_metadata else "{}",
        "timestamp": ts.isoformat(),
    }

    try:
        async with get_redis() as r:
            entry_id = await r.xadd(stream_key, entry, maxlen=10000)  # type: ignore[misc]
            return entry_id
    except Exception as e:
        logger.warning(f"Failed to append log to stream (async): {e}")
        return None


async def read_logs_from_stream(
    execution_id: str | UUID,
    start: str = "0",
    count: int = 100,
) -> list[dict[str, Any]]:
    """
    Read log entries from an execution's Redis Stream.

    Args:
        execution_id: Execution UUID
        start: Stream ID to start from (default: beginning)
        count: Maximum entries to read

    Returns:
        List of log entries with id, level, message, metadata, timestamp
    """
    from src.core.cache import get_redis

    exec_id = str(execution_id)
    stream_key = execution_logs_stream_key(exec_id)

    try:
        async with get_redis() as r:
            # XRANGE returns [(id, {field: value}), ...]
            entries = await r.xrange(stream_key, min=start, count=count)  # type: ignore[misc]

            logs = []
            for entry_id, data in entries:
                logs.append({
                    "id": entry_id,
                    "execution_id": data.get("execution_id"),
                    "level": data.get("level"),
                    "message": data.get("message"),
                    "metadata": json.loads(data.get("metadata", "{}")),
                    "timestamp": data.get("timestamp"),
                })
            return logs
    except Exception as e:
        logger.warning(f"Failed to read logs from stream: {e}")
        return []


async def publish_log_to_pubsub_async(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> None:
    """
    Async version of publish_log_to_pubsub.

    Publish log entry directly to PubSub for immediate WebSocket delivery.
    Use this in async contexts (API routes, background tasks).

    Args:
        execution_id: Execution UUID
        level: Log level
        message: Log message
        metadata: Optional metadata
        timestamp: Optional timestamp
    """
    from src.core.cache import get_redis

    exec_id = str(execution_id)
    ts = timestamp or datetime.utcnow()

    safe_metadata = _serialize_metadata(metadata)
    log_entry = {
        "type": "execution_log",
        "executionId": exec_id,
        "level": level.upper(),
        "message": message,
        "metadata": safe_metadata,
        "timestamp": ts.isoformat(),
    }

    try:
        async with get_redis() as r:
            await r.publish(f"bifrost:execution:{exec_id}", json.dumps(log_entry))
    except Exception as e:
        logger.warning(f"Failed to publish log to PubSub (async): {e}")


async def log_and_broadcast_async(
    execution_id: str | UUID,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> str | None:
    """
    Async version of log_and_broadcast.

    Write log to stream AND publish to PubSub in one call.
    Use this in async contexts (API routes) to match workflow engine behavior.

    Args:
        execution_id: Execution UUID
        level: Log level
        message: Log message
        metadata: Optional metadata
        timestamp: Optional timestamp

    Returns:
        Stream entry ID if successful, None on error
    """
    ts = timestamp or datetime.utcnow()

    # Write to stream (source of truth for persistence)
    entry_id = await append_log_to_stream_async(
        execution_id=execution_id,
        level=level,
        message=message,
        metadata=metadata,
        timestamp=ts,
    )

    # Publish to PubSub (immediate WebSocket delivery)
    await publish_log_to_pubsub_async(
        execution_id=execution_id,
        level=level,
        message=message,
        metadata=metadata,
        timestamp=ts,
    )

    return entry_id


def close_thread_redis() -> None:
    """Close the thread-local Redis connection. Call on thread cleanup."""
    if hasattr(_local, "redis") and _local.redis is not None:
        try:
            _local.redis.close()
        except Exception:
            pass
        _local.redis = None


# =============================================================================
# Log Persistence (flush from Redis Stream to Postgres)
# =============================================================================


async def flush_logs_to_postgres(
    execution_id: str | UUID,
    session: "AsyncSession | None" = None,
) -> int:
    """
    Flush all logs from Redis Stream to Postgres.

    Called at the end of execution to persist logs from the stream
    to the database. Uses batch inserts for efficiency.

    Args:
        execution_id: Execution UUID
        session: Optional database session. If provided, uses it and
                 caller is responsible for commit. If None, creates own session.

    Returns:
        Number of logs persisted
    """
    from src.models.orm import ExecutionLog

    exec_id = str(execution_id)
    exec_uuid = UUID(exec_id)
    stream_key = execution_logs_stream_key(exec_id)

    try:
        from src.core.cache import get_redis

        async with get_redis() as r:
            # Read all entries from stream
            entries = await r.xrange(stream_key, min="-", max="+")  # type: ignore[misc]

            if not entries:
                return 0

            # Parse entries - enumerate to preserve insertion order
            logs_to_insert = []
            for seq, (entry_id, data) in enumerate(entries):
                try:
                    # Parse timestamp and strip timezone (DB uses TIMESTAMP WITHOUT TIME ZONE)
                    ts_str = data.get("timestamp", datetime.utcnow().isoformat())
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)

                    log_entry = ExecutionLog(
                        execution_id=exec_uuid,
                        level=data.get("level", "INFO"),
                        message=data.get("message", ""),
                        log_metadata=json.loads(data.get("metadata", "{}")),
                        timestamp=ts,
                        sequence=seq,
                    )
                    logs_to_insert.append(log_entry)
                except Exception as e:
                    logger.warning(f"Failed to parse log entry {entry_id}: {e}")
                    continue

            if not logs_to_insert:
                return 0

            # Batch insert to Postgres
            if session is not None:
                # Use provided session (caller manages commit)
                session.add_all(logs_to_insert)
            else:
                # Create own session
                from src.core.database import get_session_factory

                session_factory = get_session_factory()
                async with session_factory() as db:
                    db.add_all(logs_to_insert)
                    await db.commit()

            # Clear the stream after successful persistence
            await r.delete(stream_key)

            logger.debug(f"Flushed {len(logs_to_insert)} logs to Postgres for {exec_id}")
            return len(logs_to_insert)

    except Exception as e:
        logger.error(f"Failed to flush logs to Postgres: {e}")
        return 0
