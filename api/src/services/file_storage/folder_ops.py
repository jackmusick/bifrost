"""
Folder Operations Service for File Storage.

Handles folder creation, deletion, listing, and bulk operations.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.core.workspace_cache import get_workspace_cache
from src.models import WorkspaceFile
from src.models.enums import GitStatus

logger = logging.getLogger(__name__)


class FolderOperationsService:
    """Service for folder and bulk file operations."""

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        s3_client,
        remove_metadata_fn,
        write_file_fn,
    ):
        """
        Initialize folder operations service.

        Args:
            db: Database session
            settings: Application settings
            s3_client: S3 client context manager
            remove_metadata_fn: Function to remove file metadata
            write_file_fn: Function to write individual files
        """
        self.db = db
        self.settings = settings
        self._s3_client = s3_client
        self._remove_metadata = remove_metadata_fn
        self._write_file = write_file_fn

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

        # Create on local filesystem too (for tools that read files directly)
        try:
            from src.core.paths import WORKSPACE_PATH
            local_folder = WORKSPACE_PATH / path.rstrip("/")
            local_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create local folder: {e}")

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

        # Delete children from S3 (regular files only) and soft-delete in DB
        # Platform entities (entity_type is not None) have content in DB, not S3
        async with self._s3_client.get_client() as s3:
            for child in children:
                # Skip folder records (no S3 object)
                if child.path.endswith("/"):
                    continue

                # Only delete from S3 if not a platform entity
                if child.entity_type is None:
                    try:
                        await s3.delete_object(
                            Bucket=self.settings.s3_bucket,
                            Key=child.path,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to delete S3 object {child.path}: {e}")

                # Clean up metadata for all files (platform entities and regular)
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
            from src.core.paths import WORKSPACE_PATH
            local_folder = WORKSPACE_PATH / path.rstrip("/")
            if local_folder.exists():
                shutil.rmtree(local_folder)
        except Exception as e:
            logger.warning(f"Failed to delete local folder: {e}")

        logger.info(f"Folder deleted: {folder_path}")

    async def list_files(
        self,
        directory: str = "",
        include_deleted: bool = False,
        recursive: bool = False,
    ) -> list[WorkspaceFile]:
        """
        List files and folders in a directory.

        Works like S3 - synthesizes folders from file path prefixes.
        Returns both:
        - Files (actual records)
        - Folders (explicit records OR synthesized from nested file paths)

        Args:
            directory: Directory path (empty for root)
            include_deleted: Whether to include soft-deleted files
            recursive: If True, return all files under directory (not just direct children)

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

        # If recursive mode, return all files under this prefix (excluding folders)
        if recursive:
            return [
                f for f in all_files
                if not is_excluded_path(f.path) and not f.path.endswith("/")
            ]

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
        # Clear existing workspace to remove stale files
        if local_path.exists():
            shutil.rmtree(local_path)
        local_path.mkdir(parents=True, exist_ok=True)

        async with self._s3_client.get_client() as s3:
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

                write_result = await self._write_file(rel_path, content, updated_by)
                uploaded.append(write_result.file_record)

        logger.info(f"Uploaded {len(uploaded)} files from {local_path}")
        return uploaded
