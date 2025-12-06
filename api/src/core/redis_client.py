"""
Redis Client for Execution Management

Provides:
1. Pending execution storage (API writes, Worker reads)
2. Sync execution results via BLPOP/RPUSH pattern
3. Cancellation flag management

Execution Flow:
1. API writes pending execution to Redis
2. API publishes to RabbitMQ
3. Worker reads pending execution from Redis
4. Worker writes to PostgreSQL and executes
5. For sync: Worker pushes result, API's BLPOP returns
"""

import json
import logging
from datetime import datetime
from typing import Any, Awaitable, TypedDict, cast

import redis.asyncio as redis

from src.config import get_settings

logger = logging.getLogger(__name__)

# Redis key prefixes
RESULT_KEY_PREFIX = "bifrost:result:"
PENDING_KEY_PREFIX = "bifrost:exec:"
PENDING_KEY_SUFFIX = ":pending"

# Default timeout for sync execution (5 minutes)
DEFAULT_TIMEOUT_SECONDS = 300

# Result TTL for auto-cleanup (60 seconds after push)
RESULT_TTL_SECONDS = 60

# Pending execution TTL (1 hour safety for orphaned entries)
PENDING_EXECUTION_TTL_SECONDS = 3600


class PendingExecution(TypedDict):
    """Schema for pending execution data stored in Redis."""
    execution_id: str
    workflow_name: str
    parameters: dict[str, Any]
    org_id: str | None
    user_id: str
    user_name: str
    user_email: str
    form_id: str | None
    created_at: str  # ISO format
    cancelled: bool


class RedisClient:
    """
    Redis client wrapper for execution management.

    Provides:
    - Pending execution: set/get/delete/cancel pending executions
    - Sync results: push_result/wait_for_result via BLPOP
    - Cancellation: set_cancel_flag for running executions
    """

    def __init__(self):
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    # =========================================================================
    # Pending Execution Methods (API writes, Worker reads)
    # =========================================================================

    async def set_pending_execution(
        self,
        execution_id: str,
        workflow_name: str,
        parameters: dict[str, Any],
        org_id: str | None,
        user_id: str,
        user_name: str,
        user_email: str,
        form_id: str | None = None,
    ) -> None:
        """
        Store pending execution in Redis.

        Called by API before publishing to RabbitMQ.
        Worker will read this data when it picks up the job.

        Args:
            execution_id: Unique execution ID (UUID)
            workflow_name: Name of workflow to execute
            parameters: Workflow input parameters
            org_id: Organization ID (None for GLOBAL scope)
            user_id: User ID who initiated execution
            user_name: Display name of user
            user_email: Email of user
            form_id: Optional form ID if triggered by form
        """
        redis_client = await self._get_redis()
        key = f"{PENDING_KEY_PREFIX}{execution_id}{PENDING_KEY_SUFFIX}"

        data: PendingExecution = {
            "execution_id": execution_id,
            "workflow_name": workflow_name,
            "parameters": parameters,
            "org_id": org_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "form_id": form_id,
            "created_at": datetime.utcnow().isoformat(),
            "cancelled": False,
        }

        try:
            await redis_client.setex(
                key,
                PENDING_EXECUTION_TTL_SECONDS,
                json.dumps(data),
            )
            logger.debug(f"Stored pending execution: {key}")
        except Exception as e:
            logger.error(f"Failed to store pending execution: {e}")
            raise

    async def get_pending_execution(
        self,
        execution_id: str,
    ) -> PendingExecution | None:
        """
        Get pending execution data from Redis.

        Called by Worker when it picks up a job from RabbitMQ.

        Args:
            execution_id: Execution ID

        Returns:
            PendingExecution dict or None if not found
        """
        redis_client = await self._get_redis()
        key = f"{PENDING_KEY_PREFIX}{execution_id}{PENDING_KEY_SUFFIX}"

        try:
            data = await redis_client.get(key)
            if data is None:
                logger.warning(f"Pending execution not found: {execution_id}")
                return None
            return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get pending execution: {e}")
            raise

    async def delete_pending_execution(self, execution_id: str) -> None:
        """
        Delete pending execution from Redis.

        Called by Worker after writing to PostgreSQL.

        Args:
            execution_id: Execution ID
        """
        redis_client = await self._get_redis()
        key = f"{PENDING_KEY_PREFIX}{execution_id}{PENDING_KEY_SUFFIX}"

        try:
            await redis_client.delete(key)
            logger.debug(f"Deleted pending execution: {key}")
        except Exception as e:
            logger.error(f"Failed to delete pending execution: {e}")
            raise

    async def set_pending_cancelled(self, execution_id: str) -> bool:
        """
        Mark a pending execution as cancelled.

        Called by API when user cancels before worker picks up.
        Worker checks this flag before starting execution.

        Args:
            execution_id: Execution ID

        Returns:
            True if execution was found and marked cancelled, False if not found
        """
        redis_client = await self._get_redis()
        key = f"{PENDING_KEY_PREFIX}{execution_id}{PENDING_KEY_SUFFIX}"

        try:
            data = await redis_client.get(key)
            if data is None:
                return False

            pending = json.loads(data)
            pending["cancelled"] = True

            # Preserve remaining TTL
            ttl = await redis_client.ttl(key)
            if ttl > 0:
                await redis_client.setex(key, ttl, json.dumps(pending))
            else:
                await redis_client.setex(
                    key, PENDING_EXECUTION_TTL_SECONDS, json.dumps(pending)
                )

            logger.info(f"Marked pending execution as cancelled: {execution_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel pending execution: {e}")
            raise

    async def is_pending_cancelled(self, execution_id: str) -> bool:
        """
        Check if a pending execution is cancelled.

        Called by Worker before starting execution.

        Args:
            execution_id: Execution ID

        Returns:
            True if cancelled, False otherwise
        """
        pending = await self.get_pending_execution(execution_id)
        if pending is None:
            return False
        return pending.get("cancelled", False)

    # =========================================================================
    # Sync Execution Results (BLPOP/RPUSH pattern)
    # =========================================================================

    async def push_result(
        self,
        execution_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
        error_type: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """
        Push execution result to Redis for sync callers.

        Called by Worker after workflow execution completes.

        Args:
            execution_id: Execution ID
            status: Execution status (Success, Failed, etc.)
            result: Workflow result data
            error: Error message if failed
            error_type: Error type if failed
            duration_ms: Execution duration in milliseconds
        """
        redis_client = await self._get_redis()
        key = f"{RESULT_KEY_PREFIX}{execution_id}"

        payload = {
            "status": status,
            "result": result,
            "error": error,
            "error_type": error_type,
            "duration_ms": duration_ms,
        }

        try:
            # Push result to list
            # Cast needed: redis-py returns Union[Awaitable[int], int] but we're async
            await cast(Awaitable[int], redis_client.rpush(key, json.dumps(payload)))
            # Set TTL for auto-cleanup
            await cast(Awaitable[bool], redis_client.expire(key, RESULT_TTL_SECONDS))
            logger.debug(f"Pushed result to Redis: {key}")
        except Exception as e:
            logger.error(f"Failed to push result to Redis: {e}")
            raise

    async def wait_for_result(
        self,
        execution_id: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any] | None:
        """
        Wait for execution result from Redis.

        Called by API for sync execution requests.

        Args:
            execution_id: Execution ID
            timeout_seconds: Max time to wait (default: 300s)

        Returns:
            Result dict or None if timeout
        """
        redis_client = await self._get_redis()
        key = f"{RESULT_KEY_PREFIX}{execution_id}"

        try:
            # BLPOP blocks until value available or timeout
            # Cast needed: redis-py returns Union[Awaitable[list], list] but we're async
            result = await cast(
                Awaitable[list[str] | None],
                redis_client.blpop([key], timeout=timeout_seconds)
            )

            if result is None:
                logger.warning(f"Timeout waiting for result: {execution_id}")
                return None

            # result is tuple (key, value)
            _, value = result
            return json.loads(value)

        except Exception as e:
            logger.error(f"Error waiting for result: {e}")
            raise

    async def set_cancel_flag(self, execution_id: str) -> None:
        """
        Set the cancellation flag for an execution.

        The execution pool checks this flag periodically and will terminate
        the worker process when it's set.

        Args:
            execution_id: Execution ID to cancel
        """
        redis_client = await self._get_redis()
        key = f"bifrost:exec:{execution_id}:cancel"
        try:
            # Set flag with 1 hour TTL (should be cleaned up much sooner)
            await redis_client.setex(key, 3600, "1")
            logger.debug(f"Set cancel flag: {key}")
        except Exception as e:
            logger.error(f"Failed to set cancel flag: {e}")
            raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Singleton instance
_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    """Get singleton Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


async def close_redis_client() -> None:
    """Close Redis client."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
