"""
Coding Mode Session Management

Manages coding mode sessions via Redis for:
- Session tracking and resumption
- Activity timestamps for TTL
- User session association
"""

import json
import logging
from datetime import datetime
from typing import Any

from src.core.redis_client import RedisClient, get_redis_client
from src.models.enums import CodingModePermission

logger = logging.getLogger(__name__)

# Session TTL: 24 hours
SESSION_TTL_SECONDS = 24 * 60 * 60

# Redis key prefix
SESSION_KEY_PREFIX = "bifrost:coding_mode:session:"


class SessionManager:
    """
    Manages coding mode sessions in Redis.

    Sessions are stored with a 24-hour TTL that refreshes on activity.
    This allows users to resume coding sessions across page refreshes.
    """

    def __init__(self) -> None:
        self._redis: RedisClient | None = None

    def _get_redis(self) -> RedisClient:
        """Get Redis client instance."""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        permission_mode: CodingModePermission = CodingModePermission.EXECUTE,
    ) -> dict[str, Any]:
        """
        Create a new coding mode session.

        Args:
            session_id: Unique session identifier
            user_id: User who owns this session
            permission_mode: Permission mode for the session (plan or execute)

        Returns:
            Session data dict
        """
        redis = self._get_redis()
        now = datetime.utcnow()

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "permission_mode": permission_mode.value,
            "created_at": now.isoformat(),
            "last_activity": now.isoformat(),
        }

        key = f"{SESSION_KEY_PREFIX}{session_id}"
        await redis.setex(key, SESSION_TTL_SECONDS, json.dumps(session_data))

        logger.info(f"Created coding mode session: {session_id} for user {user_id}, mode={permission_mode.value}")
        return session_data

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Get session data by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session data dict or None if not found/expired
        """
        redis = self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session_id}"

        data = await redis.get(key)
        if not data:
            return None

        return json.loads(data)

    async def update_activity(self, session_id: str, user_id: str) -> None:
        """
        Update session activity timestamp and refresh TTL.

        Creates session if it doesn't exist.

        Args:
            session_id: Session identifier
            user_id: User ID for session creation if needed
        """
        redis = self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session_id}"

        # Get existing session or create new
        data = await redis.get(key)
        if data:
            session_data = json.loads(data)
            session_data["last_activity"] = datetime.utcnow().isoformat()
        else:
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "permission_mode": CodingModePermission.EXECUTE.value,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
            }

        # Update with refreshed TTL
        await redis.setex(key, SESSION_TTL_SECONDS, json.dumps(session_data))

    async def set_permission_mode(
        self, session_id: str, permission_mode: CodingModePermission
    ) -> bool:
        """
        Update the permission mode for an existing session.

        Args:
            session_id: Session identifier
            permission_mode: New permission mode (plan or execute)

        Returns:
            True if session was updated, False if not found
        """
        redis = self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session_id}"

        data = await redis.get(key)
        if not data:
            logger.warning(f"Cannot set permission mode: session {session_id} not found")
            return False

        session_data = json.loads(data)
        old_mode = session_data.get("permission_mode", CodingModePermission.EXECUTE.value)
        session_data["permission_mode"] = permission_mode.value
        session_data["last_activity"] = datetime.utcnow().isoformat()

        await redis.setex(key, SESSION_TTL_SECONDS, json.dumps(session_data))
        logger.info(f"Session {session_id} permission mode changed: {old_mode} -> {permission_mode.value}")
        return True

    async def get_permission_mode(self, session_id: str) -> CodingModePermission:
        """
        Get the permission mode for a session.

        Args:
            session_id: Session identifier

        Returns:
            Permission mode (defaults to EXECUTE if session not found)
        """
        session_data = await self.get_session(session_id)
        if not session_data:
            return CodingModePermission.EXECUTE

        mode_value = session_data.get("permission_mode", CodingModePermission.EXECUTE.value)
        try:
            return CodingModePermission(mode_value)
        except ValueError:
            logger.warning(f"Unknown permission mode '{mode_value}' in session {session_id}, defaulting to EXECUTE")
            return CodingModePermission.EXECUTE

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was deleted, False if not found
        """
        redis = self._get_redis()
        key = f"{SESSION_KEY_PREFIX}{session_id}"

        result = await redis.delete(key)
        if result:
            logger.info(f"Deleted coding mode session: {session_id}")
        return result > 0

    async def get_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """
        Get all sessions for a user.

        Note: This is an expensive operation (SCAN) - use sparingly.

        Args:
            user_id: User identifier

        Returns:
            List of session data dicts
        """
        redis = self._get_redis()
        sessions: list[dict[str, Any]] = []

        # Scan for all session keys
        cursor = 0
        pattern = f"{SESSION_KEY_PREFIX}*"

        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                data = await redis.get(key)
                if data:
                    session_data = json.loads(data)
                    if session_data.get("user_id") == user_id:
                        sessions.append(session_data)

            if cursor == 0:
                break

        return sessions

    async def cleanup_user_sessions(self, user_id: str) -> int:
        """
        Delete all sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions deleted
        """
        sessions = await self.get_user_sessions(user_id)
        count = 0

        for session in sessions:
            if await self.delete_session(session["session_id"]):
                count += 1

        if count:
            logger.info(f"Cleaned up {count} coding mode sessions for user {user_id}")

        return count
