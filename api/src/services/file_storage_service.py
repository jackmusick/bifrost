"""
File Storage Service for S3-based workspace storage.

Handles workspace files with PostgreSQL indexing and workflow extraction.
Files are stored in S3, indexed in PostgreSQL for fast querying.

S3 storage is required - no filesystem fallback.
"""

import ast
import hashlib
import logging
import mimetypes
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.core.workspace_cache import get_workspace_cache
from src.models.enums import GitStatus
from src.models import WorkspaceFile

if TYPE_CHECKING:
    from src.models import Workflow

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    """Result of a file write operation."""

    file_record: WorkspaceFile
    final_content: bytes
    content_modified: bool  # True if server modified content (e.g., injected IDs)
    needs_indexing: bool = False  # True if file has decorators that need ID injection


class FileStorageService:
    """
    Storage service for workspace files.

    Provides a unified interface for file operations that:
    - Stores files in S3
    - Maintains PostgreSQL index for fast queries
    - Extracts workflow/form metadata at write time
    """

    def __init__(self, db: AsyncSession, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self._s3_client = None

    @asynccontextmanager
    async def _get_s3_client(self):
        """Get S3 client context manager."""
        if not self.settings.s3_configured:
            raise RuntimeError("S3 storage not configured")

        from aiobotocore.session import get_session

        session = get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        ) as client:
            yield client

    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def _guess_content_type(self, path: str) -> str:
        """Guess content type from file path."""
        content_type, _ = mimetypes.guess_type(path)
        return content_type or "application/octet-stream"

    async def generate_presigned_upload_url(
        self,
        path: str,
        content_type: str,
        expires_in: int = 600,
    ) -> str:
        """
        Generate a presigned PUT URL for direct S3 upload.

        Uses the files bucket (not workspace bucket) for form uploads.
        The files bucket is for runtime uploads that are not git-tracked.

        Args:
            path: Target path in S3 (e.g., "uploads/{form_id}/{uuid}/{filename}")
            content_type: MIME type of the file being uploaded
            expires_in: URL expiration time in seconds (default 10 minutes)

        Returns:
            Presigned PUT URL for direct browser upload
        """
        async with self._get_s3_client() as s3:
            url = await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.settings.s3_bucket,
                    "Key": path,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
        return url

    async def read_uploaded_file(self, path: str) -> bytes:
        """
        Read a file from the bucket (for uploaded files).

        Args:
            path: File path in the bucket (e.g., uploads/{form_id}/{uuid}/filename)

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        async with self._get_s3_client() as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                )
                return await response["Body"].read()
            except s3.exceptions.NoSuchKey:
                raise FileNotFoundError(f"File not found: {path}")

    async def read_file(self, path: str) -> tuple[bytes, WorkspaceFile | None]:
        """
        Read file content and metadata.

        Args:
            path: Relative path within workspace

        Returns:
            Tuple of (content bytes, WorkspaceFile record or None)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        # Get index record
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        file_record = result.scalar_one_or_none()

        async with self._get_s3_client() as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                )
                content = await response["Body"].read()
                return content, file_record
            except s3.exceptions.NoSuchKey:
                raise FileNotFoundError(f"File not found: {path}")

    async def write_file(
        self,
        path: str,
        content: bytes,
        updated_by: str = "system",
        index: bool = True,
    ) -> WriteResult:
        """
        Write file content to storage and update index.

        Also extracts workflow/form metadata at write time.

        Args:
            path: Relative path within workspace
            content: File content as bytes
            updated_by: User who made the change
            index: If True (default), inject IDs into decorators when needed.
                   If False, detect if IDs needed and return needs_indexing=True.

        Returns:
            WriteResult containing file record, final content, modification flag,
            and needs_indexing flag (True if IDs needed but index=False)

        Raises:
            ValueError: If path is excluded (system files, caches, etc.)
        """
        # Check if path is excluded (system files, caches, metadata, etc.)
        from src.services.editor.file_filter import is_excluded_path
        if is_excluded_path(path):
            raise ValueError(f"Path is excluded from workspace: {path}")

        content_hash = self._compute_hash(content)
        content_type = self._guess_content_type(path)
        size_bytes = len(content)

        # Write to S3
        async with self._get_s3_client() as s3:
            await s3.put_object(
                Bucket=self.settings.s3_bucket,
                Key=path,
                Body=content,
                ContentType=content_type,
            )

        # Upsert index record
        # Use UTC datetime without timezone info to match SQLAlchemy model defaults
        now = datetime.utcnow()
        stmt = insert(WorkspaceFile).values(
            path=path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            content_type=content_type,
            git_status=GitStatus.MODIFIED,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "content_hash": content_hash,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "git_status": GitStatus.MODIFIED,
                "is_deleted": False,
                "updated_at": now,
            },
        ).returning(WorkspaceFile)

        result = await self.db.execute(stmt)
        file_record = result.scalar_one()

        # Dual-write: Update Redis cache with same state as DB
        cache = get_workspace_cache()
        await cache.set_file_state(path, content_hash, is_deleted=False)

        # Extract metadata for workflows/forms (may inject IDs and modify content)
        # When index=False, skip ID injection and just detect if indexing is needed
        final_content, content_modified, needs_indexing = await self._extract_metadata(
            path, content, skip_id_injection=not index
        )

        # Publish to Redis pub/sub so other containers sync
        # This notifies workers and other API instances about the file change
        # Use final_content (with injected IDs if any) for sync
        try:
            from src.core.pubsub import publish_workspace_file_write
            publish_content = final_content if content_modified else content
            publish_hash = self._compute_hash(publish_content) if content_modified else content_hash
            await publish_workspace_file_write(path, publish_content, publish_hash)
        except Exception as e:
            logger.warning(f"Failed to publish workspace file write event: {e}")

        logger.info(f"File written: {path} ({size_bytes} bytes) by {updated_by}")
        return WriteResult(
            file_record=file_record,
            final_content=final_content,
            content_modified=content_modified,
            needs_indexing=needs_indexing,
        )

    async def _write_file_for_id_injection(
        self,
        path: str,
        content: bytes,
    ) -> None:
        """
        Internal method to write file content during ID injection.

        This is a simplified write that:
        - Updates S3 and the database index
        - Publishes to Redis for container sync
        - Does NOT call _extract_metadata to avoid infinite recursion
        - Does NOT trigger another ID injection cycle

        Args:
            path: Relative path within workspace
            content: File content as bytes (with IDs injected)
        """
        content_hash = self._compute_hash(content)
        content_type = self._guess_content_type(path)
        size_bytes = len(content)

        # Write to S3
        async with self._get_s3_client() as s3:
            await s3.put_object(
                Bucket=self.settings.s3_bucket,
                Key=path,
                Body=content,
                ContentType=content_type,
            )

        # Upsert index record
        now = datetime.utcnow()
        stmt = insert(WorkspaceFile).values(
            path=path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            content_type=content_type,
            git_status=GitStatus.MODIFIED,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "content_hash": content_hash,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "git_status": GitStatus.MODIFIED,
                "is_deleted": False,
                "updated_at": now,
            },
        )
        await self.db.execute(stmt)

        # Dual-write: Update Redis cache
        cache = get_workspace_cache()
        await cache.set_file_state(path, content_hash, is_deleted=False)

        # Publish to Redis pub/sub so other containers sync
        try:
            from src.core.pubsub import publish_workspace_file_write
            await publish_workspace_file_write(path, content, content_hash)
        except Exception as e:
            logger.warning(f"Failed to publish workspace file write event: {e}")

        logger.debug(f"ID injection write complete: {path} ({size_bytes} bytes)")

    async def delete_file(self, path: str) -> None:
        """
        Delete a file from storage.

        Args:
            path: Relative path within workspace
        """
        async with self._get_s3_client() as s3:
            await s3.delete_object(
                Bucket=self.settings.s3_bucket,
                Key=path,
            )

        # Soft delete in index
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.path == path,
        ).values(
            is_deleted=True,
            git_status=GitStatus.DELETED,
            updated_at=datetime.utcnow(),
        )
        await self.db.execute(stmt)

        # Dual-write: Update Redis cache to mark as deleted
        cache = get_workspace_cache()
        await cache.set_file_state(path, content_hash=None, is_deleted=True)

        # Clean up related metadata
        await self._remove_metadata(path)

        # Publish to Redis pub/sub so other containers sync
        try:
            from src.core.pubsub import publish_workspace_file_delete
            await publish_workspace_file_delete(path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace file delete event: {e}")

        logger.info(f"File deleted: {path}")

    async def create_folder(
        self,
        path: str,
        updated_by: str = "system",
    ) -> WorkspaceFile:
        """
        Create a folder record explicitly.

        Folders are represented by paths ending with '/'. This enables:
        - Reliable folder listing (no need to synthesize from file paths)
        - Explicit folder metadata (created_at, updated_by)
        - Simpler deletion (just delete the folder record + children)

        Args:
            path: Folder path (will be normalized to end with '/')
            updated_by: User who created the folder

        Returns:
            WorkspaceFile record for the folder
        """
        # Normalize to trailing slash
        folder_path = path.rstrip("/") + "/"

        now = datetime.utcnow()

        # Insert folder record - use on_conflict_do_nothing for silent indexing
        stmt = insert(WorkspaceFile).values(
            path=folder_path,
            content_hash="",  # Empty hash for folders
            size_bytes=0,
            content_type="inode/directory",  # MIME type for directories
            git_status=GitStatus.UNTRACKED,
            is_deleted=False,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "is_deleted": False,  # Reactivate if was deleted
                "updated_at": now,
            },
        ).returning(WorkspaceFile)

        result = await self.db.execute(stmt)
        folder_record = result.scalar_one()

        # Dual-write: Update Redis cache for folder (hash is None for folders)
        cache = get_workspace_cache()
        await cache.set_file_state(folder_path, content_hash=None, is_deleted=False)

        # Create on local filesystem too
        try:
            from src.core.workspace_sync import WORKSPACE_PATH
            local_folder = WORKSPACE_PATH / path.rstrip("/")
            local_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create local folder: {e}")

        # Publish to Redis pub/sub so other containers sync
        try:
            from src.core.pubsub import publish_workspace_folder_create
            await publish_workspace_folder_create(folder_path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace folder create event: {e}")

        logger.info(f"Folder created: {folder_path} by {updated_by}")
        return folder_record

    async def delete_folder(self, path: str) -> None:
        """
        Delete a folder and all its contents.

        Args:
            path: Folder path (with or without trailing slash)
        """
        folder_path = path.rstrip("/") + "/"

        # Find all files/folders under this path (recursive)
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path.startswith(folder_path),
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        children = result.scalars().all()

        # Delete children from S3 and soft-delete in DB
        async with self._get_s3_client() as s3:
            for child in children:
                # Skip folder records (no S3 object) but delete files
                if not child.path.endswith("/"):
                    try:
                        await s3.delete_object(
                            Bucket=self.settings.s3_bucket,
                            Key=child.path,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to delete S3 object {child.path}: {e}")

                # Clean up metadata for files
                if not child.path.endswith("/"):
                    await self._remove_metadata(child.path)

        # Soft delete all children and the folder itself
        now = datetime.utcnow()
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.path.startswith(folder_path),
        ).values(
            is_deleted=True,
            git_status=GitStatus.DELETED,
            updated_at=now,
        )
        await self.db.execute(stmt)

        # Also soft delete the folder record itself
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.path == folder_path,
        ).values(
            is_deleted=True,
            git_status=GitStatus.DELETED,
            updated_at=now,
        )
        await self.db.execute(stmt)

        # Dual-write: Update Redis cache to mark folder and children as deleted
        cache = get_workspace_cache()
        # Mark folder itself as deleted
        await cache.set_file_state(folder_path, content_hash=None, is_deleted=True)
        # Mark all children as deleted
        for child in children:
            await cache.set_file_state(child.path, content_hash=None, is_deleted=True)

        # Delete from local filesystem
        try:
            from src.core.workspace_sync import WORKSPACE_PATH
            import shutil
            local_folder = WORKSPACE_PATH / path.rstrip("/")
            if local_folder.exists():
                shutil.rmtree(local_folder)
        except Exception as e:
            logger.warning(f"Failed to delete local folder: {e}")

        # Publish to Redis pub/sub so other containers sync
        try:
            from src.core.pubsub import publish_workspace_folder_delete
            await publish_workspace_folder_delete(folder_path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace folder delete event: {e}")

        logger.info(f"Folder deleted: {folder_path}")

    async def list_files(
        self,
        directory: str = "",
        include_deleted: bool = False,
    ) -> list[WorkspaceFile]:
        """
        List files and folders in a directory (direct children only).

        Works like S3 - synthesizes folders from file path prefixes.
        Returns both:
        - Files (actual records)
        - Folders (explicit records OR synthesized from nested file paths)

        Args:
            directory: Directory path (empty for root)
            include_deleted: Whether to include soft-deleted files

        Returns:
            List of WorkspaceFile records (files and folders)
        """
        from src.services.editor.file_filter import is_excluded_path

        # Normalize directory path
        prefix = directory.rstrip("/") + "/" if directory else ""

        # Query all files under this prefix
        stmt = select(WorkspaceFile)

        if prefix:
            # Get all files that start with this prefix
            stmt = stmt.where(WorkspaceFile.path.startswith(prefix))

        if not include_deleted:
            stmt = stmt.where(WorkspaceFile.is_deleted == False)  # noqa: E712

        stmt = stmt.order_by(WorkspaceFile.path)

        result = await self.db.execute(stmt)
        all_files = list(result.scalars().all())

        # Synthesize direct children (like S3 ListObjectsV2 with delimiter)
        direct_children: dict[str, WorkspaceFile] = {}
        seen_folders: set[str] = set()

        for file in all_files:
            # Skip excluded paths
            if is_excluded_path(file.path):
                continue

            # Get the part after the prefix
            relative_path = file.path[len(prefix):] if prefix else file.path

            # Skip empty (shouldn't happen, but safety)
            if not relative_path:
                continue

            # Check if this is a direct child or nested
            slash_idx = relative_path.find("/")

            if slash_idx == -1:
                # Direct child file (no slash in relative path)
                direct_children[file.path] = file
            elif slash_idx == len(relative_path) - 1:
                # This is an explicit folder record (ends with /)
                folder_name = relative_path.rstrip("/")
                direct_children[file.path] = file
                seen_folders.add(folder_name)
            else:
                # Nested file - extract the immediate folder name
                folder_name = relative_path[:slash_idx]
                folder_path = f"{prefix}{folder_name}/"

                if folder_name not in seen_folders:
                    seen_folders.add(folder_name)
                    # Check if we already have an explicit folder record
                    if folder_path not in direct_children:
                        # Synthesize a folder record
                        direct_children[folder_path] = WorkspaceFile(
                            path=folder_path,
                            content_hash="",
                            size_bytes=0,
                            content_type="inode/directory",
                            git_status=GitStatus.UNTRACKED,
                            is_deleted=False,
                        )

        return sorted(direct_children.values(), key=lambda f: f.path)

    async def list_all_files(
        self,
        include_deleted: bool = False,
    ) -> list[WorkspaceFile]:
        """
        List all files in workspace.

        Args:
            include_deleted: Whether to include soft-deleted files

        Returns:
            List of WorkspaceFile records
        """
        stmt = select(WorkspaceFile)

        if not include_deleted:
            stmt = stmt.where(WorkspaceFile.is_deleted == False)  # noqa: E712

        stmt = stmt.order_by(WorkspaceFile.path)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def download_workspace(self, local_path: Path) -> None:
        """
        Download entire workspace to local directory.

        Clears existing content first to ensure clean state.
        Used by workers before execution.

        Args:
            local_path: Local directory to download to
        """
        import shutil

        # Clear existing workspace to remove stale files
        if local_path.exists():
            shutil.rmtree(local_path)
        local_path.mkdir(parents=True, exist_ok=True)

        async with self._get_s3_client() as s3:
            # List all objects in bucket
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.settings.s3_bucket):
                for obj in page.get("Contents", []):
                    key = obj.get("Key")
                    if not key:
                        continue
                    local_file = local_path / key

                    # Create parent directories
                    local_file.parent.mkdir(parents=True, exist_ok=True)

                    # Download file
                    response = await s3.get_object(
                        Bucket=self.settings.s3_bucket,
                        Key=key,
                    )
                    content = await response["Body"].read()
                    local_file.write_bytes(content)

        logger.info(f"Workspace downloaded to {local_path}")

    async def upload_from_directory(
        self,
        local_path: Path,
        updated_by: str = "system",
    ) -> list[WorkspaceFile]:
        """
        Upload all files from local directory to workspace.

        Used for git sync operations.

        Args:
            local_path: Local directory to upload from
            updated_by: User who made the change

        Returns:
            List of uploaded WorkspaceFile records
        """
        uploaded = []

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                # Skip git metadata
                if ".git" in file_path.parts:
                    continue

                rel_path = str(file_path.relative_to(local_path))
                content = file_path.read_bytes()

                write_result = await self.write_file(rel_path, content, updated_by)
                uploaded.append(write_result.file_record)

        logger.info(f"Uploaded {len(uploaded)} files from {local_path}")
        return uploaded

    async def sync_index_from_s3(self) -> int:
        """
        Sync index from S3 bucket contents.

        Used for initial setup or recovery. Scans S3 bucket and
        creates index entries for all files.

        Returns:
            Number of files indexed
        """
        if not self.settings.s3_configured:
            raise RuntimeError("S3 storage not configured")

        count = 0
        async with self._get_s3_client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.settings.s3_bucket):
                for obj in page.get("Contents", []):
                    key = obj.get("Key")
                    size = obj.get("Size", 0)
                    if not key:
                        continue

                    # Get content for hash
                    response = await s3.get_object(
                        Bucket=self.settings.s3_bucket,
                        Key=key,
                    )
                    content = await response["Body"].read()
                    content_hash = self._compute_hash(content)
                    content_type = self._guess_content_type(key)

                    # Upsert index
                    now = datetime.utcnow()
                    stmt = insert(WorkspaceFile).values(
                        path=key,
                        content_hash=content_hash,
                        size_bytes=size,
                        content_type=content_type,
                        git_status=GitStatus.UNTRACKED,
                        is_deleted=False,
                        created_at=now,
                        updated_at=now,
                    ).on_conflict_do_update(
                        index_elements=[WorkspaceFile.path],
                        set_={
                            "content_hash": content_hash,
                            "size_bytes": size,
                            "content_type": content_type,
                            "is_deleted": False,
                            "updated_at": now,
                        },
                    )
                    await self.db.execute(stmt)

                    # Extract metadata
                    await self._extract_metadata(key, content)
                    count += 1

        logger.info(f"Indexed {count} files from S3")
        return count

    async def reindex_workspace_files(
        self, local_path: Path, inject_ids: bool = False
    ) -> dict[str, int | list[str]]:
        """
        Reindex workspace_files table from local filesystem.

        Called after download_workspace() to ensure DB matches actual files.
        Also reconciles orphaned workflows/data_providers.

        Args:
            local_path: Local workspace directory (e.g., /tmp/bifrost/workspace)
            inject_ids: If True, inject IDs into decorators (for maintenance).
                       If False (default), only detect files needing IDs.

        Returns:
            Dict with counts: files_indexed, files_removed, workflows_deactivated,
            data_providers_deactivated, files_needing_ids (list of paths)
        """
        from src.models import Workflow, DataProvider
        from src.services.editor.file_filter import is_excluded_path

        counts: dict[str, int | list[str]] = {
            "files_indexed": 0,
            "files_removed": 0,
            "workflows_deactivated": 0,
            "data_providers_deactivated": 0,
            "files_needing_ids": [],  # Python files with decorators missing IDs
        }

        # 1. Collect all file paths from local filesystem
        existing_paths: set[str] = set()
        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                rel_path = str(file_path.relative_to(local_path))
                # Skip excluded paths (system files, caches, etc.)
                if not is_excluded_path(rel_path):
                    existing_paths.add(rel_path)

        # 2. Update workspace_files: mark missing files as deleted
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.is_deleted == False,  # noqa: E712
            ~WorkspaceFile.path.in_(existing_paths) if existing_paths else True,
            ~WorkspaceFile.path.endswith("/"),  # Skip folder records
        ).values(
            is_deleted=True,
            git_status=GitStatus.DELETED,
            updated_at=datetime.utcnow(),
        )
        result = await self.db.execute(stmt)
        counts["files_removed"] = result.rowcount if result.rowcount > 0 else 0

        # 3. For each existing file, ensure it's in workspace_files
        now = datetime.utcnow()
        cache = get_workspace_cache()

        for rel_path in existing_paths:
            file_path = local_path / rel_path
            try:
                content = file_path.read_bytes()
            except OSError as e:
                logger.warning(f"Failed to read {rel_path}: {e}")
                continue

            content_hash = self._compute_hash(content)
            content_type = self._guess_content_type(rel_path)
            size_bytes = len(content)

            # Upsert workspace_files record
            stmt = insert(WorkspaceFile).values(
                path=rel_path,
                content_hash=content_hash,
                size_bytes=size_bytes,
                content_type=content_type,
                git_status=GitStatus.SYNCED,
                is_deleted=False,
                created_at=now,
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=[WorkspaceFile.path],
                set_={
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                    "content_type": content_type,
                    "is_deleted": False,
                    "updated_at": now,
                },
            )
            await self.db.execute(stmt)

            # Update Redis cache so watcher has correct state
            await cache.set_file_state(rel_path, content_hash, is_deleted=False)

            # Extract metadata (workflows/data_providers)
            # Use inject_ids parameter to control whether to inject or just detect
            await self._extract_metadata(rel_path, content, skip_id_injection=not inject_ids)

            # Detect Python files with decorators missing IDs
            if rel_path.endswith(".py") and not inject_ids:
                try:
                    from src.services.decorator_property_service import DecoratorPropertyService

                    content_str = content.decode("utf-8", errors="replace")
                    decorator_service = DecoratorPropertyService()
                    inject_result = decorator_service.inject_ids_if_missing(content_str)

                    if inject_result.modified:
                        # This file has decorators without IDs
                        files_needing_ids = counts["files_needing_ids"]
                        if isinstance(files_needing_ids, list):
                            files_needing_ids.append(rel_path)
                except Exception as e:
                    logger.warning(f"Failed to check {rel_path} for missing IDs: {e}")

            counts["files_indexed"] += 1

        # 4. Clean up endpoints for orphaned endpoint-enabled workflows
        result = await self.db.execute(
            select(Workflow).where(
                Workflow.is_active == True,  # noqa: E712
                Workflow.endpoint_enabled == True,  # noqa: E712
                ~Workflow.file_path.in_(existing_paths) if existing_paths else True,
            )
        )
        orphaned_endpoint_workflows = result.scalars().all()

        for workflow in orphaned_endpoint_workflows:
            try:
                from src.services.openapi_endpoints import remove_workflow_endpoint
                from src.main import app

                remove_workflow_endpoint(app, workflow.name)
            except Exception as e:
                logger.warning(
                    f"Failed to remove endpoint for orphaned workflow {workflow.name}: {e}"
                )

        # 5. Mark orphaned workflows as inactive
        stmt = update(Workflow).where(
            Workflow.is_active == True,  # noqa: E712
            ~Workflow.file_path.in_(existing_paths) if existing_paths else True,
        ).values(is_active=False)
        result = await self.db.execute(stmt)
        counts["workflows_deactivated"] = result.rowcount if result.rowcount > 0 else 0

        # 6. Mark orphaned data providers as inactive
        stmt = update(DataProvider).where(
            DataProvider.is_active == True,  # noqa: E712
            ~DataProvider.file_path.in_(existing_paths) if existing_paths else True,
        ).values(is_active=False)
        result = await self.db.execute(stmt)
        counts["data_providers_deactivated"] = (
            result.rowcount if result.rowcount > 0 else 0
        )

        if any(counts.values()):
            logger.info(f"Reindexed workspace: {counts}")

        return counts

    async def _extract_metadata(
        self, path: str, content: bytes, skip_id_injection: bool = False
    ) -> tuple[bytes, bool, bool]:
        """
        Extract workflow/form/agent metadata from file content.

        Called at write time to keep registry in sync.

        Args:
            path: Relative file path
            content: File content bytes
            skip_id_injection: If True, don't inject IDs into decorators (detect only)

        Returns:
            Tuple of (final_content, content_modified, needs_indexing) where:
            - final_content: The content after any modifications (e.g., ID injection)
            - content_modified: True if the content was modified by the server
            - needs_indexing: True if IDs are needed but skip_id_injection was True
        """
        try:
            if path.endswith(".py"):
                return await self._index_python_file(path, content, skip_id_injection)
            elif path.endswith(".form.json"):
                await self._index_form(path, content)
            elif path.endswith(".agent.json"):
                await self._index_agent(path, content)
        except Exception as e:
            # Log but don't fail the write
            logger.warning(f"Failed to extract metadata from {path}: {e}")

        return content, False, False

    async def _index_python_file(
        self, path: str, content: bytes, skip_id_injection: bool = False
    ) -> tuple[bytes, bool, bool]:
        """
        Extract and index workflows/providers from Python file.

        Uses AST-based parsing to extract metadata from @workflow and
        @data_provider decorators without importing the module.
        Also updates workspace_files.is_workflow/is_data_provider flags.

        Automatically injects stable UUIDs into decorators that don't have them
        (unless skip_id_injection is True, in which case it just detects).

        Returns:
            Tuple of (final_content, content_modified, needs_indexing) where:
            - final_content: The content after any modifications (e.g., ID injection)
            - content_modified: True if IDs were injected into decorators
            - needs_indexing: True if IDs are needed but skip_id_injection was True
        """
        from src.models import Workflow, DataProvider

        content_str = content.decode("utf-8", errors="replace")
        final_content = content
        content_modified = False
        needs_indexing = False

        # Check if decorators need IDs
        try:
            from src.services.decorator_property_service import DecoratorPropertyService

            decorator_service = DecoratorPropertyService()
            inject_result = decorator_service.inject_ids_if_missing(content_str)

            if inject_result.modified:
                if skip_id_injection:
                    # Just detect - don't actually inject
                    needs_indexing = True
                    logger.debug(f"File {path} needs indexing (decorators without IDs)")
                else:
                    # Write back the modified content with IDs injected
                    logger.info(f"Injecting IDs into decorators in {path}: {inject_result.changes}")
                    modified_content = inject_result.new_content.encode("utf-8")

                    # Use internal write to avoid infinite recursion
                    await self._write_file_for_id_injection(path, modified_content)

                    # Continue indexing with the modified content
                    content_str = inject_result.new_content
                    final_content = modified_content
                    content_modified = True
        except Exception as e:
            # Log but don't fail indexing if ID injection/detection fails
            logger.warning(f"Failed to process IDs for {path}: {e}")

        try:
            tree = ast.parse(content_str, filename=path)
        except SyntaxError as e:
            logger.warning(f"Syntax error parsing {path}: {e}")
            return final_content, content_modified, needs_indexing

        now = datetime.utcnow()

        # Track what decorators we find to update workspace_files
        found_workflow = False
        found_data_provider = False

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if not decorator_info:
                    continue

                decorator_name, kwargs = decorator_info

                if decorator_name == "workflow":
                    found_workflow = True
                    # Get workflow name from decorator or function name
                    workflow_name = kwargs.get("name") or node.name
                    description = kwargs.get("description")

                    # If no description in decorator, try to get from docstring
                    if description is None:
                        docstring = ast.get_docstring(node)
                        if docstring:
                            description = docstring.strip().split("\n")[0].strip()

                    category = kwargs.get("category", "General")
                    tags = kwargs.get("tags", [])
                    schedule = kwargs.get("schedule")
                    endpoint_enabled = kwargs.get("endpoint_enabled", False)
                    allowed_methods = kwargs.get("allowed_methods", ["POST"])
                    execution_mode = kwargs.get("execution_mode", "sync")
                    is_tool = kwargs.get("is_tool", False)
                    tool_description = kwargs.get("tool_description")

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    # function_name is the actual Python function name (unique per file)
                    # workflow_name is the display name from decorator (can have duplicates)
                    function_name = node.name

                    stmt = insert(Workflow).values(
                        name=workflow_name,
                        function_name=function_name,
                        file_path=path,
                        description=description,
                        category=category,
                        parameters_schema=parameters_schema,
                        tags=tags,
                        schedule=schedule,
                        endpoint_enabled=endpoint_enabled,
                        allowed_methods=allowed_methods,
                        execution_mode=execution_mode,
                        is_tool=is_tool,
                        tool_description=tool_description,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.file_path, Workflow.function_name],
                        set_={
                            "name": workflow_name,
                            "description": description,
                            "category": category,
                            "parameters_schema": parameters_schema,
                            "tags": tags,
                            "schedule": schedule,
                            "endpoint_enabled": endpoint_enabled,
                            "allowed_methods": allowed_methods,
                            "execution_mode": execution_mode,
                            "is_tool": is_tool,
                            "tool_description": tool_description,
                            "is_active": True,
                            "last_seen_at": now,
                            "updated_at": now,
                        },
                    ).returning(Workflow)
                    result = await self.db.execute(stmt)
                    workflow = result.scalar_one()
                    logger.debug(f"Indexed workflow: {workflow_name} ({function_name}) from {path}")

                    # Refresh endpoint registration if endpoint_enabled
                    if endpoint_enabled:
                        await self._refresh_workflow_endpoint(workflow)

                elif decorator_name == "data_provider":
                    found_data_provider = True
                    # Get provider name from decorator (required)
                    provider_name = kwargs.get("name") or node.name
                    description = kwargs.get("description")

                    # function_name is the actual Python function name (unique per file)
                    # provider_name is the display name from decorator (can have duplicates)
                    function_name = node.name

                    stmt = insert(DataProvider).values(
                        name=provider_name,
                        function_name=function_name,
                        file_path=path,
                        description=description,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[DataProvider.file_path, DataProvider.function_name],
                        set_={
                            "name": provider_name,
                            "description": description,
                            "is_active": True,
                            "last_seen_at": now,
                            "updated_at": now,
                        },
                    )
                    await self.db.execute(stmt)
                    logger.debug(f"Indexed data provider: {provider_name} ({function_name}) from {path}")

        # Update workspace_files with detection results
        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            is_workflow=found_workflow,
            is_data_provider=found_data_provider,
        )
        await self.db.execute(stmt)

        return final_content, content_modified, needs_indexing

    def _parse_decorator(self, decorator: ast.AST) -> tuple[str, dict[str, Any]] | None:
        """
        Parse a decorator AST node to extract name and keyword arguments.

        Returns:
            Tuple of (decorator_name, kwargs_dict) or None if not a workflow/provider decorator
        """
        # Handle @workflow (no parentheses)
        if isinstance(decorator, ast.Name):
            if decorator.id in ("workflow", "data_provider"):
                return decorator.id, {}
            return None

        # Handle @workflow(...) (with parentheses)
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                decorator_name = decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                # Handle module.workflow (e.g., bifrost.workflow)
                decorator_name = decorator.func.attr
            else:
                return None

            if decorator_name not in ("workflow", "data_provider"):
                return None

            # Extract keyword arguments
            kwargs = {}
            for keyword in decorator.keywords:
                if keyword.arg:
                    value = self._ast_value_to_python(keyword.value)
                    if value is not None:
                        kwargs[keyword.arg] = value

            return decorator_name, kwargs

        return None

    def _ast_value_to_python(self, node: ast.AST) -> Any:
        """Convert an AST node to a Python value."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Str):  # Python 3.7 compatibility
            return node.s
        elif isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        elif isinstance(node, ast.NameConstant):  # Python 3.7 compatibility
            return node.value
        elif isinstance(node, ast.List):
            return [self._ast_value_to_python(elt) for elt in node.elts]
        elif isinstance(node, ast.Dict):
            return {
                self._ast_value_to_python(k): self._ast_value_to_python(v)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }
        elif isinstance(node, ast.Name):
            # Handle True, False, None
            if node.id == "True":
                return True
            elif node.id == "False":
                return False
            elif node.id == "None":
                return None
        return None

    def _extract_parameters_from_ast(
        self, func_node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[dict[str, Any]]:
        """
        Extract parameter metadata from function definition AST.

        Returns list of parameter dicts with: name, type, required, label, default_value
        """
        parameters: list[dict[str, Any]] = []
        args = func_node.args

        # Get defaults - they align with the end of the args list
        defaults = args.defaults
        num_defaults = len(defaults)
        num_args = len(args.args)

        for i, arg in enumerate(args.args):
            param_name = arg.arg

            # Skip 'self', 'cls', and context parameters
            if param_name in ("self", "cls", "context"):
                continue

            # Skip ExecutionContext parameter (by annotation)
            if arg.annotation:
                annotation_str = self._annotation_to_string(arg.annotation)
                if "ExecutionContext" in annotation_str:
                    continue

            # Determine if parameter has a default
            default_index = i - (num_args - num_defaults)
            has_default = default_index >= 0

            # Get default value
            default_value = None
            if has_default:
                default_node = defaults[default_index]
                default_value = self._ast_value_to_python(default_node)

            # Determine type from annotation
            ui_type = "string"
            is_optional = has_default
            options = None
            if arg.annotation:
                ui_type = self._annotation_to_ui_type(arg.annotation)
                is_optional = is_optional or self._is_optional_annotation(arg.annotation)
                options = self._extract_literal_options(arg.annotation)

            # Generate label from parameter name
            label = re.sub(r"([a-z])([A-Z])", r"\1 \2", param_name.replace("_", " ")).title()

            param_meta = {
                "name": param_name,
                "type": ui_type,
                "required": not is_optional,
                "label": label,
            }

            if default_value is not None:
                param_meta["default_value"] = default_value

            if options:
                param_meta["options"] = options

            parameters.append(param_meta)

        return parameters

    def _annotation_to_string(self, annotation: ast.AST) -> str:
        """Convert annotation AST to string representation."""
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Constant):
            return str(annotation.value)
        elif isinstance(annotation, ast.Subscript):
            return f"{self._annotation_to_string(annotation.value)}[...]"
        elif isinstance(annotation, ast.Attribute):
            return f"{self._annotation_to_string(annotation.value)}.{annotation.attr}"
        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # Python 3.10+ union syntax: str | None
            left = self._annotation_to_string(annotation.left)
            right = self._annotation_to_string(annotation.right)
            return f"{left} | {right}"
        return ""

    def _annotation_to_ui_type(self, annotation: ast.AST) -> str:
        """Convert annotation AST to UI type string."""
        type_mapping = {
            "str": "string",
            "int": "int",
            "float": "float",
            "bool": "bool",
            "list": "list",
            "dict": "json",
        }

        if isinstance(annotation, ast.Name):
            return type_mapping.get(annotation.id, "json")

        elif isinstance(annotation, ast.Subscript):
            # Handle list[str], dict[str, Any], Literal[...], etc.
            if isinstance(annotation.value, ast.Name):
                base_type = annotation.value.id
                if base_type == "list":
                    return "list"
                elif base_type == "dict":
                    return "json"
                elif base_type == "Optional":
                    # Optional[str] -> string
                    if isinstance(annotation.slice, ast.Name):
                        return type_mapping.get(annotation.slice.id, "string")
                    return "string"
                elif base_type == "Literal":
                    # Literal["a", "b"] -> infer type from values
                    return self._infer_literal_type(annotation.slice)

        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # str | None -> string
            left_type = self._annotation_to_ui_type(annotation.left)
            return left_type

        return "json"

    def _infer_literal_type(self, slice_node: ast.AST) -> str:
        """Infer UI type from Literal values."""
        # Get the first value from the Literal
        if isinstance(slice_node, ast.Tuple):
            # Literal["a", "b"] - multiple values
            if slice_node.elts:
                first_val = self._ast_value_to_python(slice_node.elts[0])
            else:
                return "string"
        else:
            # Literal["a"] - single value
            first_val = self._ast_value_to_python(slice_node)

        if first_val is None:
            return "string"
        if isinstance(first_val, str):
            return "string"
        if isinstance(first_val, bool):
            return "bool"
        if isinstance(first_val, int):
            return "int"
        if isinstance(first_val, float):
            return "float"
        return "string"

    def _extract_literal_options(self, annotation: ast.AST) -> list[dict[str, str]] | None:
        """Extract options from Literal type annotation."""
        if not isinstance(annotation, ast.Subscript):
            return None
        if not isinstance(annotation.value, ast.Name):
            return None
        if annotation.value.id != "Literal":
            return None

        # Get values from the Literal
        slice_node = annotation.slice
        values = []

        if isinstance(slice_node, ast.Tuple):
            # Literal["a", "b"] - multiple values
            for elt in slice_node.elts:
                val = self._ast_value_to_python(elt)
                if val is not None:
                    values.append({"label": str(val), "value": str(val)})
        else:
            # Literal["a"] - single value
            val = self._ast_value_to_python(slice_node)
            if val is not None:
                values.append({"label": str(val), "value": str(val)})

        return values if values else None

    def _is_optional_annotation(self, annotation: ast.AST) -> bool:
        """Check if annotation represents an optional type."""
        if isinstance(annotation, ast.Subscript):
            if isinstance(annotation.value, ast.Name):
                if annotation.value.id == "Optional":
                    return True

        elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            # Check for str | None pattern
            right_str = self._annotation_to_string(annotation.right)
            left_str = self._annotation_to_string(annotation.left)
            if right_str == "None" or left_str == "None":
                return True

        return False

    async def _index_form(self, path: str, content: bytes) -> None:
        """
        Parse and index form from .form.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Uses ON CONFLICT on primary key (id) to update existing forms.
        """
        import json
        from uuid import UUID
        from src.models import Form

        try:
            form_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in form file: {path}")
            return

        name = form_data.get("name")
        if not name:
            logger.warning(f"Form file missing name: {path}")
            return

        # Use ID from JSON if present (for API-created forms), otherwise generate new
        form_id_str = form_data.get("id")
        if form_id_str:
            try:
                form_id = UUID(form_id_str)
            except ValueError:
                logger.warning(f"Invalid form ID in {path}: {form_id_str}")
                form_id = None
        else:
            form_id = None

        now = datetime.utcnow()

        if form_id:
            # Form has an ID - use upsert on primary key
            # This handles dual-write from API (form already exists)
            stmt = insert(Form).values(
                id=form_id,
                name=name,
                description=form_data.get("description"),
                workflow_id=form_data.get("workflow_id"),
                default_launch_params=form_data.get("default_launch_params"),
                allowed_query_params=form_data.get("allowed_query_params"),
                file_path=path,
                is_active=True,
                last_seen_at=now,
                created_by="file_sync",
            ).on_conflict_do_update(
                index_elements=[Form.id],
                set_={
                    "file_path": path,
                    "is_active": True,
                    "last_seen_at": now,
                    "updated_at": now,
                },
            )
        else:
            # No ID - use upsert on file_path (for git sync / editor writes)
            stmt = insert(Form).values(
                name=name,
                description=form_data.get("description"),
                workflow_id=form_data.get("workflow_id"),
                default_launch_params=form_data.get("default_launch_params"),
                allowed_query_params=form_data.get("allowed_query_params"),
                file_path=path,
                is_active=True,
                last_seen_at=now,
                created_by="file_sync",
            ).on_conflict_do_update(
                index_elements=[Form.file_path],
                set_={
                    "name": name,
                    "description": form_data.get("description"),
                    "workflow_id": form_data.get("workflow_id"),
                    "default_launch_params": form_data.get("default_launch_params"),
                    "allowed_query_params": form_data.get("allowed_query_params"),
                    "is_active": True,
                    "last_seen_at": now,
                    "updated_at": now,
                },
            )
        await self.db.execute(stmt)

    async def _index_agent(self, path: str, content: bytes) -> None:
        """
        Parse and index agent from .agent.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise uses upsert on file_path (for files synced from git/editor).

        Uses ON CONFLICT to update existing agents.
        """
        import json
        from uuid import UUID
        from src.models.orm import Agent
        from src.models.enums import AgentAccessLevel

        try:
            agent_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in agent file: {path}")
            return

        name = agent_data.get("name")
        if not name:
            logger.warning(f"Agent file missing name: {path}")
            return

        system_prompt = agent_data.get("system_prompt")
        if not system_prompt:
            logger.warning(f"Agent file missing system_prompt: {path}")
            return

        # Use ID from JSON if present (for API-created agents), otherwise generate new
        agent_id_str = agent_data.get("id")
        if agent_id_str:
            try:
                agent_id = UUID(agent_id_str)
            except ValueError:
                logger.warning(f"Invalid agent ID in {path}: {agent_id_str}")
                agent_id = None
        else:
            agent_id = None

        # Parse access level
        access_level_str = agent_data.get("access_level", "role_based")
        try:
            access_level = AgentAccessLevel(access_level_str)
        except ValueError:
            access_level = AgentAccessLevel.ROLE_BASED

        # Parse channels
        channels = agent_data.get("channels", ["chat"])
        if not isinstance(channels, list):
            channels = ["chat"]

        now = datetime.utcnow()

        if agent_id:
            # Agent has an ID - use upsert on primary key
            stmt = insert(Agent).values(
                id=agent_id,
                name=name,
                description=agent_data.get("description"),
                system_prompt=system_prompt,
                channels=channels,
                access_level=access_level,
                is_active=True,
                file_path=path,
                created_by="file_sync",
            ).on_conflict_do_update(
                index_elements=[Agent.id],
                set_={
                    "name": name,
                    "description": agent_data.get("description"),
                    "system_prompt": system_prompt,
                    "channels": channels,
                    "access_level": access_level,
                    "file_path": path,
                    "is_active": True,
                    "updated_at": now,
                },
            )
        else:
            # No ID - use upsert on file_path
            stmt = insert(Agent).values(
                name=name,
                description=agent_data.get("description"),
                system_prompt=system_prompt,
                channels=channels,
                access_level=access_level,
                is_active=True,
                file_path=path,
                created_by="file_sync",
            ).on_conflict_do_update(
                index_elements=["file_path"],
                set_={
                    "name": name,
                    "description": agent_data.get("description"),
                    "system_prompt": system_prompt,
                    "channels": channels,
                    "access_level": access_level,
                    "is_active": True,
                    "updated_at": now,
                },
            )
        await self.db.execute(stmt)
        logger.debug(f"Indexed agent: {name} from {path}")

    async def _refresh_workflow_endpoint(self, workflow: "Workflow") -> None:
        """
        Refresh the dynamic endpoint registration for an endpoint-enabled workflow.

        This is called when a workflow with endpoint_enabled=True is indexed,
        allowing live updates to the OpenAPI spec without restarting the API.

        Args:
            workflow: The Workflow ORM model that was just indexed
        """
        try:
            from src.services.openapi_endpoints import refresh_workflow_endpoint
            from src.main import app

            refresh_workflow_endpoint(app, workflow)
            logger.info(f"Refreshed endpoint for workflow: {workflow.name}")
        except ImportError:
            # App not fully initialized yet (during startup)
            pass
        except Exception as e:
            # Log but don't fail the file write
            logger.warning(f"Failed to refresh endpoint for {workflow.name}: {e}")

    async def _remove_metadata(self, path: str) -> None:
        """Remove workflow/form/agent metadata when file is deleted."""
        from src.models import Workflow, DataProvider, Form
        from src.models.orm import Agent

        # Get workflows being removed (to clean up endpoints)
        result = await self.db.execute(
            select(Workflow).where(Workflow.file_path == path, Workflow.endpoint_enabled == True)  # noqa: E712
        )
        endpoint_workflows = result.scalars().all()

        # Remove endpoint registrations for deleted workflows
        for workflow in endpoint_workflows:
            try:
                from src.services.openapi_endpoints import remove_workflow_endpoint
                from src.main import app

                remove_workflow_endpoint(app, workflow.name)
            except Exception as e:
                logger.warning(f"Failed to remove endpoint for {workflow.name}: {e}")

        # Mark workflows from this file as inactive
        await self.db.execute(
            update(Workflow).where(Workflow.file_path == path).values(is_active=False)
        )

        # Mark data providers from this file as inactive
        await self.db.execute(
            update(DataProvider).where(DataProvider.file_path == path).values(is_active=False)
        )

        # Mark forms from this file as inactive
        await self.db.execute(
            update(Form).where(Form.file_path == path).values(is_active=False)
        )

        # Mark agents from this file as inactive
        await self.db.execute(
            update(Agent).where(Agent.file_path == path).values(is_active=False)
        )

    async def update_git_status(
        self,
        path: str,
        status: GitStatus,
        commit_hash: str | None = None,
    ) -> None:
        """
        Update git status for a file.

        Args:
            path: File path
            status: New git status
            commit_hash: Git commit hash (for synced files)
        """
        values = {
            "git_status": status,
            "updated_at": datetime.utcnow(),
        }
        if commit_hash:
            values["last_git_commit_hash"] = commit_hash

        stmt = update(WorkspaceFile).where(
            WorkspaceFile.path == path,
        ).values(**values)

        await self.db.execute(stmt)

    async def bulk_update_git_status(
        self,
        status: GitStatus,
        commit_hash: str | None = None,
        paths: list[str] | None = None,
    ) -> int:
        """
        Bulk update git status for files.

        Args:
            status: New git status
            commit_hash: Git commit hash
            paths: List of paths to update (all if None)

        Returns:
            Number of files updated
        """
        values = {
            "git_status": status,
            "updated_at": datetime.utcnow(),
        }
        if commit_hash:
            values["last_git_commit_hash"] = commit_hash

        stmt = update(WorkspaceFile).values(**values)

        if paths:
            stmt = stmt.where(WorkspaceFile.path.in_(paths))

        cursor = await self.db.execute(stmt)

        # rowcount may be -1 for some database drivers
        row_count = getattr(cursor, "rowcount", 0)
        return row_count if row_count >= 0 else 0


def get_file_storage_service(db: AsyncSession) -> FileStorageService:
    """Factory function for FileStorageService."""
    return FileStorageService(db)
