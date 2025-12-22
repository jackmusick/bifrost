"""
Workspace Sync Service

Keeps local workspace in sync with S3 via Redis pub/sub.

Architecture:
- On startup: Download workspace from S3 to /tmp/bifrost/workspace
- On file changes: Receive pub/sub events and apply locally
- Execution: Uses local workspace (already synced)

This eliminates the need for shared NFS volumes while keeping
all containers in sync.
"""

import asyncio
import base64
import hashlib
import json
import logging
import shutil
from pathlib import Path

import redis.asyncio as redis

from src.config import get_settings
from src.core.workspace_cache import get_workspace_cache

logger = logging.getLogger(__name__)

# Local workspace path
WORKSPACE_PATH = Path("/tmp/bifrost/workspace")


class WorkspaceSyncService:
    """
    Manages local workspace synchronization via Redis pub/sub.

    Listens for file change events and applies them locally.
    """

    def __init__(self):
        self._redis: redis.Redis | None = None  # type: ignore[type-arg]
        self._pubsub: redis.client.PubSub | None = None  # type: ignore[type-arg]
        self._listener_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._running = False

    async def start(self) -> None:
        """
        Start the workspace sync service.

        1. Ensures workspace directory exists
        2. Downloads initial workspace from S3 (if configured)
        3. Starts listening for pub/sub events
        """
        settings = get_settings()

        # Ensure workspace directory exists
        WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace directory: {WORKSPACE_PATH}")

        # Download initial workspace from S3 if configured
        if settings.s3_configured:
            await self._download_initial_workspace()

        # Start pub/sub listener
        try:
            self._redis = redis.from_url(settings.redis_url)
            self._pubsub = self._redis.pubsub()
            if self._pubsub:
                await self._pubsub.subscribe("bifrost:workspace:sync")
                logger.info("Subscribed to Redis channel: bifrost:workspace:sync")
                self._running = True
                self._listener_task = asyncio.create_task(self._listen())
                logger.info("Workspace sync service started")
            else:
                logger.warning("Failed to create Redis pubsub connection")
        except Exception as e:
            logger.warning(f"Failed to start workspace sync: {e}", exc_info=True)

    async def stop(self) -> None:
        """Stop the workspace sync service."""
        self._running = False

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

        logger.info("Workspace sync service stopped")

    async def _download_initial_workspace(self) -> None:
        """Download workspace from S3 on startup and reindex."""
        from src.services.file_storage_service import FileStorageService
        from src.core.database import get_session_factory

        try:
            session_factory = get_session_factory()
            async with session_factory() as db:
                storage = FileStorageService(db)

                # Download all files from S3 to local workspace
                await storage.download_workspace(WORKSPACE_PATH)

                # Reindex workspace_files and reconcile orphaned workflows
                # inject_ids=False means detect only, don't modify files
                counts = await storage.reindex_workspace_files(WORKSPACE_PATH, inject_ids=False)

                await db.commit()
                logger.info(f"Downloaded and reindexed workspace from S3 to {WORKSPACE_PATH}")

                # Check if any files need ID injection and create notification
                files_needing_ids = counts.get("files_needing_ids", [])
                if isinstance(files_needing_ids, list) and len(files_needing_ids) > 0:
                    await self._create_maintenance_notification(db, files_needing_ids)

        except Exception as e:
            logger.warning(f"Failed to download workspace from S3: {e}")

    async def _create_maintenance_notification(
        self, db, files_needing_ids: list[str]
    ) -> None:
        """Create a notification for platform admins about files needing ID injection."""
        from src.services.notification_service import get_notification_service
        from src.models.contracts.notifications import (
            NotificationCreate,
            NotificationCategory,
            NotificationStatus,
        )

        try:
            notification_service = get_notification_service()

            # Check for existing notification to avoid duplicates
            # (Both API and Worker call workspace_sync.start())
            existing = await notification_service.find_admin_notification_by_title(
                title="Workspace Indexing Required",
                category=NotificationCategory.SYSTEM,
            )
            if existing:
                logger.debug("Maintenance notification already exists, skipping")
                return

            count = len(files_needing_ids)
            # Limit files shown in description to keep it readable
            preview_files = files_needing_ids[:3]
            remaining = count - len(preview_files)

            file_list = ", ".join(preview_files)
            if remaining > 0:
                file_list += f" (+{remaining} more)"

            # Create notification in awaiting_action state with action button
            # This shows no spinner and allows user to trigger reindex inline
            await notification_service.create_notification(
                user_id="system",
                request=NotificationCreate(
                    category=NotificationCategory.SYSTEM,
                    title="Workspace Indexing Required",
                    description=f"{count} workflow file(s) need indexing: {file_list}",
                    metadata={
                        "action": "run_maintenance",
                        "action_label": "Run Now",
                        "files": files_needing_ids,
                    },
                ),
                for_admins=True,
                initial_status=NotificationStatus.AWAITING_ACTION,
            )
            logger.info(f"Created maintenance notification for {count} files needing IDs")
        except Exception as e:
            logger.warning(f"Failed to create maintenance notification: {e}")

    async def _listen(self) -> None:
        """Listen for workspace sync events."""
        if not self._pubsub:
            return

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self._handle_event(data)
                    except json.JSONDecodeError:
                        logger.warning("Invalid workspace sync message")
                    except Exception as e:
                        logger.error(f"Error handling workspace sync event: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Workspace sync listener error: {e}")

    async def _handle_event(self, data: dict) -> None:
        """Handle a workspace sync event."""
        event_type = data.get("type")
        logger.info(f"Received workspace sync event: {event_type}")

        if event_type == "workspace_file_write":
            await self._handle_write(data)
        elif event_type == "workspace_file_delete":
            await self._handle_delete(data)
        elif event_type == "workspace_file_rename":
            await self._handle_rename(data)
        elif event_type == "workspace_folder_create":
            await self._handle_folder_create(data)
        elif event_type == "workspace_folder_delete":
            await self._handle_folder_delete(data)
        else:
            logger.warning(f"Unknown workspace sync event type: {event_type}")

    async def _handle_write(self, data: dict) -> None:
        """Handle file write event."""
        path = data.get("path")
        content_b64 = data.get("content")
        expected_hash = data.get("content_hash")

        # Check path exists - content can be empty string for empty files
        if not path or content_b64 is None:
            logger.warning(f"Missing path or content in write event: path={path}, has_content={content_b64 is not None}")
            return

        try:
            content = base64.b64decode(content_b64)

            # Verify hash
            actual_hash = hashlib.sha256(content).hexdigest()
            if expected_hash and actual_hash != expected_hash:
                logger.warning(f"Hash mismatch for {path}: expected={expected_hash}, actual={actual_hash}")
                return

            # Update Redis cache BEFORE writing locally
            # This ensures the watcher sees the correct hash and doesn't re-publish
            cache = get_workspace_cache()
            await cache.set_file_state(path, actual_hash, is_deleted=False)

            # Write to local workspace
            file_path = WORKSPACE_PATH / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

            logger.info(f"Synced file write: {path} ({len(content)} bytes)")

        except Exception as e:
            logger.error(f"Failed to sync file write {path}: {e}", exc_info=True)

    async def _handle_delete(self, data: dict) -> None:
        """Handle file delete event."""
        path = data.get("path")
        if not path:
            logger.warning("Missing path in delete event")
            return

        try:
            # Update Redis cache BEFORE deleting locally
            # This ensures the watcher sees the file as deleted and doesn't re-publish
            cache = get_workspace_cache()
            await cache.set_file_state(path, content_hash=None, is_deleted=True)

            file_path = WORKSPACE_PATH / path

            if file_path.is_dir():
                shutil.rmtree(file_path, ignore_errors=True)
                logger.info(f"Synced directory delete: {path}")
            elif file_path.exists():
                file_path.unlink()
                logger.info(f"Synced file delete: {path}")
            else:
                logger.info(f"File already deleted or not found: {path}")

        except Exception as e:
            logger.error(f"Failed to sync file delete {path}: {e}", exc_info=True)

    async def _handle_rename(self, data: dict) -> None:
        """Handle file rename event."""
        old_path = data.get("old_path")
        new_path = data.get("new_path")

        if not old_path or not new_path:
            logger.warning(f"Missing path in rename event: old={old_path}, new={new_path}")
            return

        try:
            old_file = WORKSPACE_PATH / old_path
            new_file = WORKSPACE_PATH / new_path

            if old_file.exists():
                new_file.parent.mkdir(parents=True, exist_ok=True)
                old_file.rename(new_file)
                logger.info(f"Synced file rename: {old_path} -> {new_path}")
            else:
                logger.warning(f"Source file not found for rename: {old_path}")

        except Exception as e:
            logger.error(f"Failed to sync file rename {old_path} -> {new_path}: {e}", exc_info=True)

    async def _handle_folder_create(self, data: dict) -> None:
        """Handle folder create event."""
        path = data.get("path")
        if not path:
            logger.warning("Missing path in folder create event")
            return

        try:
            # Normalize to trailing slash for cache key
            normalized_path = path.rstrip("/") + "/"

            # Update Redis cache BEFORE creating locally
            # This ensures the watcher sees the folder as existing and doesn't re-publish
            cache = get_workspace_cache()
            await cache.set_file_state(normalized_path, content_hash=None, is_deleted=False)

            # Remove trailing slash for filesystem
            folder_path = WORKSPACE_PATH / path.rstrip("/")
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Synced folder create: {path}")

        except Exception as e:
            logger.error(f"Failed to sync folder create {path}: {e}", exc_info=True)

    async def _handle_folder_delete(self, data: dict) -> None:
        """Handle folder delete event."""
        path = data.get("path")
        if not path:
            logger.warning("Missing path in folder delete event")
            return

        try:
            # Normalize to trailing slash for cache key
            normalized_path = path.rstrip("/") + "/"

            # Update Redis cache BEFORE deleting locally
            # This ensures the watcher sees the folder as deleted and doesn't re-publish
            cache = get_workspace_cache()
            await cache.set_file_state(normalized_path, content_hash=None, is_deleted=True)

            # Remove trailing slash for filesystem
            folder_path = WORKSPACE_PATH / path.rstrip("/")

            if folder_path.exists() and folder_path.is_dir():
                shutil.rmtree(folder_path, ignore_errors=True)
                logger.info(f"Synced folder delete: {path}")
            else:
                logger.info(f"Folder already deleted or not found: {path}")

        except Exception as e:
            logger.error(f"Failed to sync folder delete {path}: {e}", exc_info=True)


# Global instance
workspace_sync = WorkspaceSyncService()


def get_local_workspace_path() -> Path:
    """Get the local workspace path."""
    return WORKSPACE_PATH


def get_file_from_workspace(relative_path: str) -> Path:
    """Get absolute path to a file in the local workspace."""
    return WORKSPACE_PATH / relative_path
