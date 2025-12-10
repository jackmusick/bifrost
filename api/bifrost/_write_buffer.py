"""
Write buffer for Bifrost SDK.

Buffers SDK write operations to Redis during workflow execution.
Changes are flushed to Postgres after execution completes.

Pattern:
    1. SDK write (config.set, roles.create, etc.) calls buffer method
    2. Buffer writes change record to Redis Hash
    3. After execution, flush_pending_changes() applies all changes to Postgres
    4. Redis Hash is cleared on success
"""

from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import redis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ContextVar to hold the write buffer for the current execution
_write_buffer: ContextVar["WriteBuffer | None"] = ContextVar(
    "bifrost_write_buffer",
    default=None,
)


def get_write_buffer() -> "WriteBuffer":
    """
    Get the write buffer for the current execution.

    Returns:
        WriteBuffer: The write buffer instance

    Raises:
        RuntimeError: If no write buffer is set
    """
    buffer = _write_buffer.get()
    if buffer is None:
        raise RuntimeError(
            "No write buffer found. "
            "The bifrost SDK write operations can only be used within workflow executions."
        )
    return buffer


def set_write_buffer(buffer: "WriteBuffer") -> None:
    """Set the write buffer for the current execution."""
    _write_buffer.set(buffer)


def clear_write_buffer() -> None:
    """Clear the write buffer for the current execution."""
    _write_buffer.set(None)


# =============================================================================
# Change Record
# =============================================================================


@dataclass
class ChangeRecord:
    """
    Record of a single change made during execution.

    Stored in Redis and used to apply changes to Postgres after execution.
    """

    entity_type: str  # "config" | "role" | "organization" | "user_role" | "form_role"
    operation: str  # "create" | "update" | "delete"
    entity_id: str | None  # For existing entities
    entity_key: str  # Unique key within entity type (e.g., config key, role ID)
    org_id: str | None  # Organization scope
    data: dict[str, Any]  # Full entity data for create, partial for update
    timestamp: str  # ISO timestamp
    user_id: str  # Who made the change
    sequence: int  # Order within execution


# =============================================================================
# Write Buffer
# =============================================================================


class WriteBuffer:
    """
    Thread-safe write buffer for SDK operations.

    Buffers changes in Redis for later flush to Postgres.
    """

    def __init__(
        self,
        execution_id: str,
        org_id: str | None,
        user_id: str,
    ):
        self.execution_id = execution_id
        self.org_id = org_id
        self.user_id = user_id
        self._redis: redis.Redis | None = None
        self._sequence = 0
        self._lock = threading.Lock()
        self._pending_key = f"bifrost:pending:{execution_id}"

    def _get_redis(self) -> redis.Redis:
        """Get sync Redis connection (thread-safe)."""
        if self._redis is None:
            from src.config import get_settings

            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _next_sequence(self) -> int:
        """Get next sequence number (thread-safe)."""
        with self._lock:
            self._sequence += 1
            return self._sequence

    async def _async_buffer_change(self, change: ChangeRecord) -> None:
        """Buffer a change using async Redis (for async SDK methods)."""
        from src.core.cache import get_redis, TTL_PENDING

        async with get_redis() as r:
            field_name = f"changes:{change.entity_type}:{change.entity_key}"
            await r.hset(self._pending_key, field_name, json.dumps(asdict(change)))  # type: ignore[misc]
            await r.expire(self._pending_key, TTL_PENDING)  # type: ignore[misc]

    # =========================================================================
    # Config Operations
    # =========================================================================

    async def add_config_change(
        self,
        operation: str,
        key: str,
        value: Any = None,
        org_id: str | None = None,
        config_type: str = "string",
    ) -> None:
        """
        Buffer a config change.

        Args:
            operation: "set" or "delete"
            key: Config key
            value: Config value (for set operation)
            org_id: Organization ID (defaults to buffer's org_id)
            config_type: Config type (string, int, bool, json, secret)
        """
        change = ChangeRecord(
            entity_type="config",
            operation=operation,
            entity_id=None,
            entity_key=key,
            org_id=org_id or self.org_id,
            data={"value": value, "config_type": config_type} if value is not None else {},
            timestamp=datetime.utcnow().isoformat(),
            user_id=self.user_id,
            sequence=self._next_sequence(),
        )
        await self._async_buffer_change(change)

        # Also update the read cache for read-your-writes consistency
        await self._update_config_cache(key, value, config_type, org_id or self.org_id)

    async def _update_config_cache(
        self,
        key: str,
        value: Any,
        config_type: str,
        org_id: str | None,
    ) -> None:
        """Update the read cache after a write (read-your-writes consistency)."""
        from src.core.cache import config_hash_key, get_redis

        cache_value = {"value": value, "type": config_type}
        async with get_redis() as r:
            await r.hset(config_hash_key(org_id), key, json.dumps(cache_value))  # type: ignore[misc]

    # =========================================================================
    # Role Operations
    # =========================================================================

    async def add_role_change(
        self,
        operation: str,
        role_id: str | None,
        data: dict[str, Any],
        org_id: str | None = None,
    ) -> str:
        """
        Buffer a role change.

        Args:
            operation: "create", "update", or "delete"
            role_id: Role ID (None for create, will generate)
            data: Role data
            org_id: Organization ID

        Returns:
            str: Role ID (generated if create)
        """
        entity_key = role_id or str(uuid4())

        change = ChangeRecord(
            entity_type="role",
            operation=operation,
            entity_id=role_id,
            entity_key=entity_key,
            org_id=org_id or self.org_id,
            data=data,
            timestamp=datetime.utcnow().isoformat(),
            user_id=self.user_id,
            sequence=self._next_sequence(),
        )
        await self._async_buffer_change(change)

        # Update read cache
        if operation != "delete":
            await self._update_role_cache(entity_key, data, org_id or self.org_id)

        return entity_key

    async def _update_role_cache(
        self,
        role_id: str,
        data: dict[str, Any],
        org_id: str | None,
    ) -> None:
        """Update the read cache after a role write."""
        from src.core.cache import get_redis, roles_hash_key

        async with get_redis() as r:
            await r.hset(roles_hash_key(org_id), role_id, json.dumps(data))  # type: ignore[misc]

    async def add_role_users_change(
        self,
        role_id: str,
        user_ids: list[str],
        org_id: str | None = None,
    ) -> None:
        """Buffer a role-users assignment change."""
        change = ChangeRecord(
            entity_type="user_role",
            operation="assign",
            entity_id=role_id,
            entity_key=f"{role_id}:users",
            org_id=org_id or self.org_id,
            data={"user_ids": user_ids},
            timestamp=datetime.utcnow().isoformat(),
            user_id=self.user_id,
            sequence=self._next_sequence(),
        )
        await self._async_buffer_change(change)

    async def add_role_forms_change(
        self,
        role_id: str,
        form_ids: list[str],
        org_id: str | None = None,
    ) -> None:
        """Buffer a role-forms assignment change."""
        change = ChangeRecord(
            entity_type="form_role",
            operation="assign",
            entity_id=role_id,
            entity_key=f"{role_id}:forms",
            org_id=org_id or self.org_id,
            data={"form_ids": form_ids},
            timestamp=datetime.utcnow().isoformat(),
            user_id=self.user_id,
            sequence=self._next_sequence(),
        )
        await self._async_buffer_change(change)

    # =========================================================================
    # Organization Operations
    # =========================================================================

    async def add_org_change(
        self,
        operation: str,
        org_id: str | None,
        data: dict[str, Any],
    ) -> str:
        """
        Buffer an organization change.

        Args:
            operation: "create", "update", or "delete"
            org_id: Organization ID (None for create)
            data: Organization data

        Returns:
            str: Organization ID
        """
        entity_key = org_id or str(uuid4())

        change = ChangeRecord(
            entity_type="organization",
            operation=operation,
            entity_id=org_id,
            entity_key=entity_key,
            org_id=None,  # Orgs are global
            data=data,
            timestamp=datetime.utcnow().isoformat(),
            user_id=self.user_id,
            sequence=self._next_sequence(),
        )
        await self._async_buffer_change(change)

        # Update read cache
        if operation != "delete":
            await self._update_org_cache(entity_key, data)

        return entity_key

    async def _update_org_cache(self, org_id: str, data: dict[str, Any]) -> None:
        """Update the read cache after an org write."""
        from src.core.cache import get_redis, org_key

        async with get_redis() as r:
            await r.set(org_key(org_id), json.dumps(data))  # type: ignore[misc]

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_pending_count(self) -> int:
        """Get the number of pending changes."""
        from src.core.cache import get_redis

        async with get_redis() as r:
            return await r.hlen(self._pending_key)  # type: ignore[misc]

    async def has_pending_changes(self) -> bool:
        """Check if there are pending changes."""
        return await self.get_pending_count() > 0

    def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            self._redis.close()
            self._redis = None
