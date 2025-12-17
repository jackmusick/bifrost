"""
Workspace Filesystem Watcher

Monitors local workspace for changes and determines whether to publish
sync events to other containers.

Architecture:
- All containers run the watcher (API and workers)
- When a change is detected, check DB state to determine if we originated it
- If DB already reflects the change → we received it from pub/sub, don't publish
- If DB doesn't reflect the change → we originated it, sync to S3/DB AND publish

This ensures:
1. SDK writes (which bypass FileStorageService) get synced
2. API writes get synced (FileStorageService writes locally, watcher detects)
3. Pub/sub received changes don't get re-published (DB check prevents loops)
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import (  # type: ignore[import-untyped]
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
)
from watchdog.observers import Observer  # type: ignore[import-untyped]

from src.config import get_settings
from src.services.editor.file_filter import is_excluded_path

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Local workspace path (same as workspace_sync.py)
WORKSPACE_PATH = Path("/tmp/bifrost/workspace")

# Debounce delay in seconds (batch rapid changes)
DEBOUNCE_DELAY = 0.5

# Directories to ignore (in addition to file_filter exclusions)
IGNORED_DIRS = {".tmp", ".git"}


class WorkspaceWatcher:
    """
    Watches local workspace for filesystem changes and syncs to S3/DB.

    Uses watchdog for cross-platform filesystem monitoring.
    Implements debouncing to batch rapid changes (e.g., editor save-reload).
    """

    def __init__(self):
        self._observer: Observer | None = None
        self._event_handler: WorkspaceEventHandler | None = None
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._pending_changes: dict[str, str] = {}  # path -> event_type
        self._pending_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start the filesystem watcher."""
        settings = get_settings()

        if not settings.s3_configured:
            logger.info("S3 not configured, workspace watcher disabled")
            return

        # Ensure workspace directory exists
        WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)

        self._loop = asyncio.get_event_loop()
        self._running = True

        # Create event handler
        self._event_handler = WorkspaceEventHandler(self)

        # Create and start observer
        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(WORKSPACE_PATH),
            recursive=True,
        )
        self._observer.start()

        # Start the sync processing task
        self._sync_task = asyncio.create_task(self._process_pending_changes())

        logger.info(f"Workspace watcher started, monitoring: {WORKSPACE_PATH}")

    async def stop(self) -> None:
        """Stop the filesystem watcher."""
        self._running = False

        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

        logger.info("Workspace watcher stopped")

    def queue_change(self, path: str, event_type: str) -> None:
        """
        Queue a filesystem change for processing.

        Called from the watchdog thread, schedules work on the async loop.
        """
        if self._loop and self._running:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._add_pending_change(path, event_type))
            )

    async def _add_pending_change(self, path: str, event_type: str) -> None:
        """Add a change to the pending queue (debouncing)."""
        async with self._pending_lock:
            # Delete supersedes modify
            if event_type == "deleted":
                self._pending_changes[path] = "deleted"
            elif path not in self._pending_changes:
                self._pending_changes[path] = event_type
            elif self._pending_changes[path] != "deleted":
                # Update existing non-delete to latest event type
                self._pending_changes[path] = event_type

    async def _process_pending_changes(self) -> None:
        """Process pending changes in batches with debouncing."""
        while self._running:
            try:
                await asyncio.sleep(DEBOUNCE_DELAY)

                # Get and clear pending changes
                async with self._pending_lock:
                    if not self._pending_changes:
                        continue
                    changes = self._pending_changes.copy()
                    self._pending_changes.clear()

                # Process each change
                for path, event_type in changes.items():
                    try:
                        await self._sync_change(path, event_type)
                    except Exception as e:
                        logger.error(f"Error syncing {event_type} for {path}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in change processor: {e}")

    async def _sync_change(self, path: str, event_type: str) -> None:
        """
        Sync a single change to S3/DB with deduplication.

        Checks DB hash before syncing to avoid re-publishing events
        we just received from pub/sub.
        """
        from src.core.database import get_session_factory

        session_factory = get_session_factory()

        async with session_factory() as db:
            if event_type == "deleted":
                await self._handle_delete(db, path)
            elif event_type in ("created", "modified"):
                await self._handle_write(db, path)
            elif event_type == "folder_created":
                await self._handle_folder_create(db, path)
            elif event_type == "folder_deleted":
                await self._handle_folder_delete(db, path)

            await db.commit()

    async def _handle_write(self, db, path: str) -> None:
        """
        Handle file write - check DB to determine if we should publish.

        Logic:
        - If DB hash matches local hash → change came from pub/sub, skip
        - If DB hash differs → we originated this change, sync AND publish
        """
        from sqlalchemy import select
        from src.models import WorkspaceFile
        from src.services.file_storage_service import FileStorageService
        from src.core.pubsub import publish_workspace_file_write

        local_file = WORKSPACE_PATH / path
        if not local_file.exists() or not local_file.is_file():
            return

        # Read local content and compute hash
        try:
            content = local_file.read_bytes()
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return

        local_hash = hashlib.sha256(content).hexdigest()

        # Check DB for existing hash
        stmt = select(WorkspaceFile.content_hash).where(
            WorkspaceFile.path == path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        db_hash = result.scalar_one_or_none()

        if db_hash == local_hash:
            # Hash matches - this change came from pub/sub, we're not the originator
            logger.debug(f"Watcher: skipping {path} (DB hash matches, not originator)")
            return

        # Hash differs or file is new - we originated this change
        logger.info(f"Watcher: originating file write {path} ({len(content)} bytes)")

        # Sync to S3/DB
        storage = FileStorageService(db)
        await storage.write_file(path, content, updated_by="watcher")

        # Publish to Redis so other containers sync
        try:
            await publish_workspace_file_write(path, content, local_hash)
        except Exception as e:
            logger.warning(f"Failed to publish workspace write event: {e}")

    async def _handle_delete(self, db, path: str) -> None:
        """
        Handle file delete - check DB to determine if we should publish.

        Logic:
        - If DB shows file already deleted → change came from pub/sub, skip
        - If DB shows file exists → we originated this change, sync AND publish
        """
        from sqlalchemy import select
        from src.models import WorkspaceFile
        from src.services.file_storage_service import FileStorageService
        from src.core.pubsub import publish_workspace_file_delete

        # Check if file exists in DB and is not already deleted
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()

        if not file_record:
            # Not in DB or already deleted - we're not the originator
            logger.debug(f"Watcher: skipping delete {path} (already deleted in DB)")
            return

        # File exists in DB - we originated this delete
        logger.info(f"Watcher: originating file delete {path}")

        # Sync to S3/DB
        storage = FileStorageService(db)
        if path.endswith("/"):
            await storage.delete_folder(path)
        else:
            await storage.delete_file(path)

        # Publish to Redis so other containers sync
        try:
            await publish_workspace_file_delete(path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace delete event: {e}")

    async def _handle_folder_create(self, db, path: str) -> None:
        """
        Handle folder creation - check DB to determine if we should publish.

        Logic:
        - If DB shows folder exists → change came from pub/sub, skip
        - If DB shows no folder → we originated this change, sync AND publish
        """
        from sqlalchemy import select
        from src.models import WorkspaceFile
        from src.services.file_storage_service import FileStorageService
        from src.core.pubsub import publish_workspace_folder_create

        folder_path = path.rstrip("/") + "/"

        # Check if folder already exists in DB
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == folder_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        folder_record = result.scalar_one_or_none()

        if folder_record:
            # Folder already in DB - we're not the originator
            logger.debug(f"Watcher: skipping folder create {path} (already in DB)")
            return

        # Folder not in DB - we originated this create
        logger.info(f"Watcher: originating folder create {path}")

        # Sync to DB
        storage = FileStorageService(db)
        await storage.create_folder(path, updated_by="watcher")

        # Publish to Redis so other containers sync
        try:
            await publish_workspace_folder_create(folder_path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace folder create event: {e}")

    async def _handle_folder_delete(self, db, path: str) -> None:
        """
        Handle folder deletion - check DB to determine if we should publish.

        Logic:
        - If DB shows folder already deleted → change came from pub/sub, skip
        - If DB shows folder exists → we originated this change, sync AND publish
        """
        from sqlalchemy import select
        from src.models import WorkspaceFile
        from src.services.file_storage_service import FileStorageService
        from src.core.pubsub import publish_workspace_folder_delete

        folder_path = path.rstrip("/") + "/"

        # Check if folder exists in DB and is not already deleted
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == folder_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        folder_record = result.scalar_one_or_none()

        if not folder_record:
            # Folder not in DB or already deleted - we're not the originator
            logger.debug(f"Watcher: skipping folder delete {path} (already deleted in DB)")
            return

        # Folder exists in DB - we originated this delete
        logger.info(f"Watcher: originating folder delete {path}")

        # Sync to S3/DB
        storage = FileStorageService(db)
        await storage.delete_folder(path)

        # Publish to Redis so other containers sync
        try:
            await publish_workspace_folder_delete(folder_path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace folder delete event: {e}")


class WorkspaceEventHandler(FileSystemEventHandler):
    """
    Watchdog event handler for workspace filesystem changes.

    Filters out excluded paths and queues changes for async processing.
    """

    def __init__(self, watcher: WorkspaceWatcher):
        super().__init__()
        self.watcher = watcher

    def _get_relative_path(self, absolute_path: str) -> str | None:
        """Convert absolute path to workspace-relative path."""
        try:
            return str(Path(absolute_path).relative_to(WORKSPACE_PATH))
        except ValueError:
            return None

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored."""
        # Check against ignored directories
        parts = Path(path).parts
        for part in parts:
            if part in IGNORED_DIRS:
                return True

        # Check against file filter
        if is_excluded_path(path):
            return True

        return False

    def on_created(self, event: "FileSystemEvent") -> None:
        """Handle file/folder creation."""
        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or self._should_ignore(rel_path):
            return

        if isinstance(event, DirCreatedEvent):
            self.watcher.queue_change(rel_path, "folder_created")
        elif isinstance(event, FileCreatedEvent):
            self.watcher.queue_change(rel_path, "created")

    def on_modified(self, event: "FileSystemEvent") -> None:
        """Handle file modification."""
        if isinstance(event, DirCreatedEvent):
            # Ignore directory modifications
            return

        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or self._should_ignore(rel_path):
            return

        if isinstance(event, FileModifiedEvent):
            self.watcher.queue_change(rel_path, "modified")

    def on_deleted(self, event: "FileSystemEvent") -> None:
        """Handle file/folder deletion."""
        rel_path = self._get_relative_path(event.src_path)
        if not rel_path or self._should_ignore(rel_path):
            return

        if isinstance(event, DirDeletedEvent):
            self.watcher.queue_change(rel_path, "folder_deleted")
        elif isinstance(event, FileDeletedEvent):
            self.watcher.queue_change(rel_path, "deleted")

    def on_moved(self, event: "FileSystemEvent") -> None:
        """Handle file/folder move/rename."""
        if not isinstance(event, (FileMovedEvent, DirMovedEvent)):
            return

        src_rel = self._get_relative_path(event.src_path)
        dst_rel = self._get_relative_path(event.dest_path)

        # Handle as delete + create for simplicity
        # (proper rename handling would need more complex logic)
        if src_rel and not self._should_ignore(src_rel):
            if isinstance(event, DirMovedEvent):
                self.watcher.queue_change(src_rel, "folder_deleted")
            else:
                self.watcher.queue_change(src_rel, "deleted")

        if dst_rel and not self._should_ignore(dst_rel):
            if isinstance(event, DirMovedEvent):
                self.watcher.queue_change(dst_rel, "folder_created")
            else:
                self.watcher.queue_change(dst_rel, "created")


# Global instance
workspace_watcher = WorkspaceWatcher()
