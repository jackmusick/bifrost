"""
Folder Operations Service for File Storage.

Handles folder creation, deletion, listing, and bulk operations.
"""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.models.orm.file_index import FileIndex
from src.services.repo_storage import REPO_PREFIX

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    """Lightweight file/folder entry for listings (replaces WorkspaceFile)."""

    path: str
    content_hash: str = ""
    size_bytes: int = 0
    content_type: str = "text/plain"
    is_deleted: bool = False
    entity_type: str | None = None
    entity_id: str | None = None
    updated_at: datetime | None = None


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
    ) -> FileEntry:
        """
        Create a folder marker in file_index.

        Folders are represented by paths ending with '/'.

        Args:
            path: Folder path (will be normalized to end with '/')
            updated_by: User who created the folder

        Returns:
            FileEntry for the folder
        """
        folder_path = path.rstrip("/") + "/"
        now = datetime.now(timezone.utc)

        # Insert folder marker in file_index
        stmt = insert(FileIndex).values(
            path=folder_path,
            content=None,
            content_hash="",
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[FileIndex.path],
            set_={"updated_at": now},
        )
        await self.db.execute(stmt)

        logger.info(f"Folder created: {folder_path} by {updated_by}")
        return FileEntry(path=folder_path, content_type="inode/directory", updated_at=now)

    async def delete_folder(self, path: str) -> None:
        """
        Delete a folder and all its contents.

        Args:
            path: Folder path (with or without trailing slash)
        """
        folder_path = path.rstrip("/") + "/"

        # Find all files under this path
        stmt = select(FileIndex.path).where(
            FileIndex.path.startswith(folder_path),
        )
        result = await self.db.execute(stmt)
        child_paths = [row[0] for row in result.fetchall()]

        # Delete children from S3 _repo/ and clean up metadata
        async with self._s3_client.get_client() as s3:
            for child_path in child_paths:
                if child_path.endswith("/"):
                    continue

                # Delete from S3 _repo/ prefix for all files
                s3_key = f"{REPO_PREFIX}{child_path}"
                try:
                    await s3.delete_object(
                        Bucket=self.settings.s3_bucket,
                        Key=s3_key,
                    )
                except Exception as e:
                    logger.warning(f"Failed to delete S3 object {child_path}: {e}")

                await self._remove_metadata(child_path)

        # Delete all entries from file_index
        del_stmt = delete(FileIndex).where(
            FileIndex.path.startswith(folder_path),
        )
        await self.db.execute(del_stmt)

        logger.info(f"Folder deleted: {folder_path}")

    async def list_files(
        self,
        directory: str = "",
        include_deleted: bool = False,
        recursive: bool = False,
    ) -> list[FileEntry]:
        """
        List files and folders in a directory.

        Queries file_index for code files and synthesizes folder entries.

        Args:
            directory: Directory path (empty for root)
            include_deleted: Ignored (file_index has no soft delete)
            recursive: If True, return all files under directory

        Returns:
            List of FileEntry records (files and folders)
        """
        from src.services.editor.file_filter import is_excluded_path

        prefix = directory.rstrip("/") + "/" if directory else ""

        # Query file_index for all files under this prefix
        stmt = select(FileIndex).order_by(FileIndex.path)
        if prefix:
            stmt = stmt.where(FileIndex.path.startswith(prefix))

        result = await self.db.execute(stmt)
        all_entries = list(result.scalars().all())

        # Convert to FileEntry
        all_files = [
            FileEntry(
                path=fi.path,
                content_hash=fi.content_hash or "",
                size_bytes=len(fi.content.encode("utf-8")) if fi.content else 0,
                content_type="inode/directory" if fi.path.endswith("/") else "text/plain",
                updated_at=fi.updated_at,
            )
            for fi in all_entries
        ]

        if recursive:
            return [
                f for f in all_files
                if not is_excluded_path(f.path) and not f.path.endswith("/")
            ]

        # Synthesize direct children
        direct_children: dict[str, FileEntry] = {}
        seen_folders: set[str] = set()

        for file in all_files:
            if is_excluded_path(file.path):
                continue

            relative_path = file.path[len(prefix):] if prefix else file.path
            if not relative_path:
                continue

            slash_idx = relative_path.find("/")

            if slash_idx == -1:
                direct_children[file.path] = file
            elif slash_idx == len(relative_path) - 1:
                folder_name = relative_path.rstrip("/")
                direct_children[file.path] = file
                seen_folders.add(folder_name)
            else:
                folder_name = relative_path[:slash_idx]
                folder_path = f"{prefix}{folder_name}/"

                if folder_name not in seen_folders:
                    seen_folders.add(folder_name)
                    if folder_path not in direct_children:
                        direct_children[folder_path] = FileEntry(
                            path=folder_path,
                            content_type="inode/directory",
                        )

        return sorted(direct_children.values(), key=lambda f: f.path)

    async def list_all_files(
        self,
        include_deleted: bool = False,
    ) -> list[FileEntry]:
        """
        List all files in workspace.

        Args:
            include_deleted: Ignored (file_index has no soft delete)

        Returns:
            List of FileEntry records
        """
        stmt = select(FileIndex).order_by(FileIndex.path)
        result = await self.db.execute(stmt)
        return [
            FileEntry(
                path=fi.path,
                content_hash=fi.content_hash or "",
                size_bytes=len(fi.content.encode("utf-8")) if fi.content else 0,
                updated_at=fi.updated_at,
            )
            for fi in result.scalars()
        ]

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
    ) -> int:
        """
        Upload all files from local directory to workspace.

        Used for git sync operations.

        Args:
            local_path: Local directory to upload from
            updated_by: User who made the change

        Returns:
            Number of files uploaded
        """
        count = 0

        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                # Skip git metadata
                if ".git" in file_path.parts:
                    continue

                rel_path = str(file_path.relative_to(local_path))
                content = file_path.read_bytes()

                await self._write_file(rel_path, content, updated_by)
                count += 1

        logger.info(f"Uploaded {count} files from {local_path}")
        return count
