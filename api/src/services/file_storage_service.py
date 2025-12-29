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

from sqlalchemy import delete, select, update
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
class WorkflowIdConflictInfo:
    """Info about a workflow that would lose its ID on overwrite."""

    name: str  # Workflow display name from decorator
    function_name: str  # Python function name
    existing_id: str  # UUID from database
    file_path: str


@dataclass
class FileDiagnosticInfo:
    """A file-specific issue detected during save/indexing."""

    severity: str  # "error", "warning", "info"
    message: str
    line: int | None = None
    column: int | None = None
    source: str = "bifrost"  # e.g., "syntax", "indexing", "sdk"


@dataclass
class WriteResult:
    """Result of a file write operation."""

    file_record: WorkspaceFile
    final_content: bytes
    content_modified: bool  # True if server modified content (e.g., injected IDs)
    needs_indexing: bool = False  # True if file has decorators that need ID injection
    workflow_id_conflicts: list[WorkflowIdConflictInfo] | None = None  # Workflows that would lose IDs
    diagnostics: list[FileDiagnosticInfo] | None = None  # File issues detected during save


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
        force_ids: dict[str, str] | None = None,
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
            force_ids: Map of function_name -> ID to inject (for reusing existing IDs
                       when user chooses "Use Existing IDs" for workflow conflicts)

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
        (
            final_content,
            content_modified,
            needs_indexing,
            workflow_id_conflicts,
            diagnostics,
        ) = await self._extract_metadata(
            path, content, skip_id_injection=not index, force_ids=force_ids
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

        # Scan Python files for missing SDK references (config.get, integrations.get)
        # and create platform admin notifications if issues are found
        if path.endswith(".py"):
            try:
                await self._scan_for_sdk_issues(path, final_content)
            except Exception as e:
                logger.warning(f"Failed to scan for SDK issues in {path}: {e}")

        # Create or clear system notification based on diagnostic errors
        # This ensures visibility when files are written from any source (editor, git sync, MCP)
        has_errors = diagnostics and any(d.severity == "error" for d in diagnostics)
        if has_errors:
            try:
                await self._create_diagnostic_notification(path, diagnostics)
            except Exception as e:
                logger.warning(f"Failed to create diagnostic notification for {path}: {e}")
        else:
            # Clear any existing diagnostic notification for this file
            try:
                await self._clear_diagnostic_notification(path)
            except Exception as e:
                logger.warning(f"Failed to clear diagnostic notification for {path}: {e}")

        logger.info(f"File written: {path} ({size_bytes} bytes) by {updated_by}")
        return WriteResult(
            file_record=file_record,
            final_content=final_content,
            content_modified=content_modified,
            needs_indexing=needs_indexing,
            workflow_id_conflicts=workflow_id_conflicts,
            diagnostics=diagnostics if diagnostics else None,
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

    def detect_files_needing_ids(self, workspace_path: Path) -> list[str]:
        """
        Scan workspace for Python files with decorators missing IDs.

        This is a lightweight read-only operation that can run safely
        from multiple processes without database writes.

        Args:
            workspace_path: Path to workspace directory

        Returns:
            List of relative file paths that need ID injection
        """
        from src.services.decorator_property_service import DecoratorPropertyService
        from src.services.editor.file_filter import is_excluded_path

        files_needing_ids: list[str] = []
        decorator_service = DecoratorPropertyService()

        for file_path in workspace_path.rglob("*.py"):
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(workspace_path))
            if is_excluded_path(rel_path):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                inject_result = decorator_service.inject_ids_if_missing(content)

                if inject_result.modified:
                    files_needing_ids.append(rel_path)
            except Exception as e:
                logger.warning(f"Failed to check {rel_path} for missing IDs: {e}")

        return files_needing_ids

    async def _extract_metadata(
        self,
        path: str,
        content: bytes,
        skip_id_injection: bool = False,
        force_ids: dict[str, str] | None = None,
    ) -> tuple[bytes, bool, bool, list[WorkflowIdConflictInfo] | None, list[FileDiagnosticInfo]]:
        """
        Extract workflow/form/agent metadata from file content.

        Called at write time to keep registry in sync.

        Args:
            path: Relative file path
            content: File content bytes
            skip_id_injection: If True, don't inject IDs into decorators (detect only)
            force_ids: Map of function_name -> ID to inject (for reusing existing IDs)

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics) where:
            - final_content: The content after any modifications (e.g., ID injection)
            - content_modified: True if the content was modified by the server
            - needs_indexing: True if IDs are needed but skip_id_injection was True
            - conflicts: List of workflows that would lose their IDs (if any)
            - diagnostics: List of file issues detected during indexing
        """
        try:
            if path.endswith(".py"):
                return await self._index_python_file(
                    path, content, skip_id_injection, force_ids
                )
            elif path.endswith(".form.json"):
                await self._index_form(path, content)
            elif path.endswith(".agent.json"):
                await self._index_agent(path, content)
        except Exception as e:
            # Log but don't fail the write
            logger.warning(f"Failed to extract metadata from {path}: {e}")

        return content, False, False, None, []

    async def _index_python_file(
        self,
        path: str,
        content: bytes,
        skip_id_injection: bool = False,
        force_ids: dict[str, str] | None = None,
    ) -> tuple[bytes, bool, bool, list[WorkflowIdConflictInfo] | None, list[FileDiagnosticInfo]]:
        """
        Extract and index workflows/providers from Python file.

        Uses AST-based parsing to extract metadata from @workflow and
        @data_provider decorators without importing the module.
        Also updates workspace_files.is_workflow/is_data_provider flags.

        Automatically injects stable UUIDs into decorators that don't have them
        (unless skip_id_injection is True, in which case it just detects).

        Args:
            path: File path
            content: File content
            skip_id_injection: If True, don't inject IDs, just detect
            force_ids: Map of function_name -> ID to inject (for reusing existing IDs)

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics) where:
            - final_content: The content after any modifications (e.g., ID injection)
            - content_modified: True if IDs were injected into decorators
            - needs_indexing: True if IDs are needed but skip_id_injection was True
            - conflicts: List of workflows that would lose their IDs (if any)
            - diagnostics: List of file issues detected during indexing
        """
        from src.models import Workflow, DataProvider

        content_str = content.decode("utf-8", errors="replace")
        final_content = content
        content_modified = False
        needs_indexing = False
        workflow_id_conflicts: list[WorkflowIdConflictInfo] | None = None
        diagnostics: list[FileDiagnosticInfo] = []

        # Check if decorators need IDs
        try:
            from src.services.decorator_property_service import DecoratorPropertyService

            decorator_service = DecoratorPropertyService()

            # First, read existing decorators to find ones without IDs
            existing_decorators = decorator_service.read_decorators(content_str)
            decorators_without_ids = [
                d for d in existing_decorators
                if d.decorator_type == "workflow" and "id" not in d.properties
            ]

            # Check if any of these would overwrite existing workflows in DB
            if decorators_without_ids and not force_ids:
                conflicts = []
                for dec in decorators_without_ids:
                    # Query DB for existing workflow at this location
                    stmt = select(Workflow).where(
                        Workflow.file_path == path,
                        Workflow.function_name == dec.function_name
                    )
                    result = await self.db.execute(stmt)
                    existing_workflow = result.scalar_one_or_none()

                    if existing_workflow:
                        # This workflow already has an ID in DB but new file doesn't have it
                        conflicts.append(WorkflowIdConflictInfo(
                            name=dec.properties.get("name", dec.function_name),
                            function_name=dec.function_name,
                            existing_id=str(existing_workflow.id),
                            file_path=path,
                        ))

                if conflicts:
                    # Return conflicts without injecting IDs
                    # Let the client decide whether to use existing IDs
                    workflow_id_conflicts = conflicts
                    logger.info(
                        f"File {path} has {len(conflicts)} workflows that would lose their IDs"
                    )
                    # Don't inject new IDs, just proceed with indexing without ID injection
                    needs_indexing = True

            # If force_ids provided, inject those specific IDs
            if force_ids:
                inject_result = decorator_service.inject_specific_ids(content_str, force_ids)
                if inject_result.modified:
                    logger.info(f"Injecting specific IDs into decorators in {path}: {inject_result.changes}")
                    modified_content = inject_result.new_content.encode("utf-8")
                    await self._write_file_for_id_injection(path, modified_content)
                    content_str = inject_result.new_content
                    final_content = modified_content
                    content_modified = True
            # Otherwise, if no conflicts, inject new IDs as usual
            elif not workflow_id_conflicts:
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
            diagnostics.append(FileDiagnosticInfo(
                severity="error",
                message=f"Syntax error: {e.msg}" if e.msg else str(e),
                line=e.lineno,
                column=e.offset,
                source="syntax",
            ))
            return final_content, content_modified, needs_indexing, workflow_id_conflicts, diagnostics

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

                    # Extract workflow id from decorator - required for upsert
                    workflow_id_str = kwargs.get("id")
                    if not workflow_id_str:
                        logger.warning(f"Workflow in {path} has no id - skipping indexing")
                        diagnostics.append(FileDiagnosticInfo(
                            severity="warning",
                            message=f"Workflow '{kwargs.get('name') or node.name}' has no id - skipping indexing. Save the file to inject an ID.",
                            line=node.lineno,
                            source="indexing",
                        ))
                        continue

                    # Convert string UUID to UUID object
                    from uuid import UUID as UUID_type
                    try:
                        workflow_uuid = UUID_type(workflow_id_str)
                    except ValueError:
                        logger.warning(f"Invalid workflow id '{workflow_id_str}' in {path} - skipping indexing")
                        diagnostics.append(FileDiagnosticInfo(
                            severity="error",
                            message=f"Invalid workflow id '{workflow_id_str}' - must be a valid UUID",
                            line=node.lineno,
                            source="indexing",
                        ))
                        continue

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
                    # Apply same logic as decorator: endpoints default to sync, others to async
                    execution_mode = kwargs.get("execution_mode")
                    if execution_mode is None:
                        execution_mode = "sync" if endpoint_enabled else "async"
                    is_tool = kwargs.get("is_tool", False)
                    tool_description = kwargs.get("tool_description")
                    time_saved = kwargs.get("time_saved", 0)
                    value = kwargs.get("value", 0.0)

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    # function_name is the actual Python function name (unique per file)
                    # workflow_name is the display name from decorator (can have duplicates)
                    function_name = node.name

                    # Use workflow ID as the conflict key for upsert
                    # This ensures we update the correct workflow even if file_path or function_name changes
                    stmt = insert(Workflow).values(
                        id=workflow_uuid,
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
                        time_saved=time_saved,
                        value=value,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.id],
                        set_={
                            "name": workflow_name,
                            "function_name": function_name,
                            "file_path": path,
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
                            "time_saved": time_saved,
                            "value": value,
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

                    # Update Redis caches for this workflow
                    try:
                        from src.core.redis_client import get_redis_client
                        redis_client = get_redis_client()

                        # Invalidate endpoint workflow cache (keyed by name)
                        await redis_client.invalidate_endpoint_workflow_cache(workflow_name)
                        logger.debug(f"Invalidated endpoint cache for workflow: {workflow_name}")

                        # Upsert workflow metadata cache (keyed by ID)
                        await redis_client.set_workflow_metadata_cache(
                            workflow_id=str(workflow_uuid),
                            name=workflow_name,
                            file_path=path,
                            timeout_seconds=kwargs.get("timeout_seconds", 1800),
                            time_saved=time_saved,
                            value=value,
                            execution_mode=execution_mode,
                        )
                        logger.debug(f"Upserted workflow metadata cache: {workflow_name}")
                    except Exception as e:
                        logger.warning(f"Failed to update caches for workflow {workflow_name}: {e}")

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

        return final_content, content_modified, needs_indexing, workflow_id_conflicts, diagnostics

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

    async def _resolve_workflow_name_to_id(self, workflow_name: str) -> str | None:
        """
        Resolve a workflow name to its UUID.

        Used for legacy form files that use linked_workflow (name) instead of workflow_id (UUID).

        Args:
            workflow_name: The workflow name to resolve

        Returns:
            The workflow UUID as a string, or None if not found
        """
        from src.models import Workflow

        result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.name == workflow_name,
                Workflow.is_active == True,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None

    async def _index_form(self, path: str, content: bytes) -> None:
        """
        Parse and index form from .form.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Updates form definition (name, description, workflow_id, form_schema, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT on primary key (id) to update existing forms.
        """
        import json
        from uuid import UUID, uuid4
        from src.models import Form, FormField as FormFieldORM

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
                form_id = uuid4()  # Generate new ID if invalid
        else:
            form_id = uuid4()  # Generate new ID for files without one

        now = datetime.utcnow()

        # Get workflow_id - prefer explicit workflow_id, fall back to linked_workflow (name lookup)
        workflow_id = form_data.get("workflow_id")
        if not workflow_id:
            linked_workflow = form_data.get("linked_workflow")
            if linked_workflow:
                # Legacy format - resolve workflow name to UUID
                workflow_id = await self._resolve_workflow_name_to_id(linked_workflow)
                if workflow_id:
                    logger.info(f"Resolved legacy linked_workflow '{linked_workflow}' to workflow_id '{workflow_id}'")
                else:
                    logger.warning(f"Could not resolve linked_workflow '{linked_workflow}' to workflow ID for form {path}")

        # Same fallback for launch_workflow_id
        launch_workflow_id = form_data.get("launch_workflow_id")
        if not launch_workflow_id:
            launch_workflow_name = form_data.get("launch_workflow")
            if launch_workflow_name:
                launch_workflow_id = await self._resolve_workflow_name_to_id(launch_workflow_name)

        # Upsert form - updates definition but NOT organization_id or access_level
        # These env-specific fields are only set via the API, not from file sync
        stmt = insert(Form).values(
            id=form_id,
            name=name,
            description=form_data.get("description"),
            workflow_id=workflow_id,
            launch_workflow_id=launch_workflow_id,
            default_launch_params=form_data.get("default_launch_params"),
            allowed_query_params=form_data.get("allowed_query_params"),
            file_path=path,
            is_active=form_data.get("is_active", True),
            last_seen_at=now,
            created_by="file_sync",
        ).on_conflict_do_update(
            index_elements=[Form.id],
            set_={
                # Update definition fields from file
                "name": name,
                "description": form_data.get("description"),
                "workflow_id": workflow_id,
                "launch_workflow_id": launch_workflow_id,
                "default_launch_params": form_data.get("default_launch_params"),
                "allowed_query_params": form_data.get("allowed_query_params"),
                "file_path": path,
                "is_active": form_data.get("is_active", True),
                "last_seen_at": now,
                "updated_at": now,
                # NOTE: organization_id and access_level are NOT updated
                # These are preserved from the database (env-specific)
            },
        )
        await self.db.execute(stmt)

        # Sync form_schema (fields) if present
        form_schema = form_data.get("form_schema")
        if form_schema and isinstance(form_schema, dict):
            fields_data = form_schema.get("fields", [])
            if isinstance(fields_data, list):
                # Delete existing fields
                await self.db.execute(
                    delete(FormFieldORM).where(FormFieldORM.form_id == form_id)
                )

                # Create new fields from schema
                for position, field in enumerate(fields_data):
                    if not isinstance(field, dict) or not field.get("name"):
                        continue

                    field_orm = FormFieldORM(
                        form_id=form_id,
                        name=field.get("name"),
                        label=field.get("label"),
                        type=field.get("type", "text"),
                        required=field.get("required", False),
                        position=position,
                        placeholder=field.get("placeholder"),
                        help_text=field.get("help_text"),
                        default_value=field.get("default_value"),
                        options=field.get("options"),
                        data_provider_id=field.get("data_provider_id"),
                        data_provider_inputs=field.get("data_provider_inputs"),
                        visibility_expression=field.get("visibility_expression"),
                        validation=field.get("validation"),
                        allowed_types=field.get("allowed_types"),
                        multiple=field.get("multiple"),
                        max_size_mb=field.get("max_size_mb"),
                        content=field.get("content"),
                    )
                    self.db.add(field_orm)

        logger.debug(f"Indexed form: {name} from {path}")

    async def _index_agent(self, path: str, content: bytes) -> None:
        """
        Parse and index agent from .agent.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Updates agent definition (name, description, system_prompt, tools, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT to update existing agents.
        """
        import json
        from uuid import UUID, uuid4
        from src.models.orm import Agent, AgentTool, AgentDelegation

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
                agent_id = uuid4()  # Generate new ID if invalid
        else:
            agent_id = uuid4()  # Generate new ID for files without one

        # Parse channels
        channels = agent_data.get("channels", ["chat"])
        if not isinstance(channels, list):
            channels = ["chat"]

        # Get knowledge_sources (JSONB field)
        knowledge_sources = agent_data.get("knowledge_sources", [])
        if not isinstance(knowledge_sources, list):
            knowledge_sources = []

        now = datetime.utcnow()

        # Upsert agent - updates definition but NOT organization_id or access_level
        # These env-specific fields are only set via the API, not from file sync
        stmt = insert(Agent).values(
            id=agent_id,
            name=name,
            description=agent_data.get("description"),
            system_prompt=system_prompt,
            channels=channels,
            knowledge_sources=knowledge_sources,
            is_active=agent_data.get("is_active", True),
            file_path=path,
            created_by="file_sync",
        ).on_conflict_do_update(
            index_elements=[Agent.id],
            set_={
                # Update definition fields from file
                "name": name,
                "description": agent_data.get("description"),
                "system_prompt": system_prompt,
                "channels": channels,
                "knowledge_sources": knowledge_sources,
                "file_path": path,
                "is_active": agent_data.get("is_active", True),
                "updated_at": now,
                # NOTE: organization_id and access_level are NOT updated
                # These are preserved from the database (env-specific)
            },
        )
        await self.db.execute(stmt)

        # Sync tool associations (tool_ids in JSON are workflow IDs)
        tool_ids = agent_data.get("tool_ids", [])
        if isinstance(tool_ids, list):
            # Delete existing tool associations
            await self.db.execute(
                delete(AgentTool).where(AgentTool.agent_id == agent_id)
            )
            # Create new tool associations
            for tool_id_str in tool_ids:
                try:
                    workflow_id = UUID(tool_id_str)
                    self.db.add(AgentTool(agent_id=agent_id, workflow_id=workflow_id))
                except ValueError:
                    logger.warning(f"Invalid tool_id in agent {name}: {tool_id_str}")

        # Sync delegated agent associations
        delegated_agent_ids = agent_data.get("delegated_agent_ids", [])
        if isinstance(delegated_agent_ids, list):
            # Delete existing delegations
            await self.db.execute(
                delete(AgentDelegation).where(AgentDelegation.parent_agent_id == agent_id)
            )
            # Create new delegations
            for child_id_str in delegated_agent_ids:
                try:
                    child_agent_id = UUID(child_id_str)
                    self.db.add(AgentDelegation(parent_agent_id=agent_id, child_agent_id=child_agent_id))
                except ValueError:
                    logger.warning(f"Invalid delegated_agent_id in agent {name}: {child_id_str}")

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

            # Invalidate endpoint workflow cache for this workflow
            try:
                from src.core.redis_client import get_redis_client
                redis_client = get_redis_client()
                await redis_client.invalidate_endpoint_workflow_cache(workflow.name)
                logger.debug(f"Invalidated endpoint cache for deleted workflow: {workflow.name}")
            except Exception as e:
                logger.warning(f"Failed to invalidate endpoint cache for {workflow.name}: {e}")

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

    async def _scan_for_sdk_issues(self, path: str, content: bytes) -> None:
        """
        Scan a Python file for missing SDK references and create notifications.

        Detects config.get("key") and integrations.get("name") calls where
        the key/name doesn't exist in the database. Creates platform admin
        notifications with links to the file and line number.

        Args:
            path: Relative file path
            content: File content as bytes
        """
        from pathlib import Path
        from src.services.sdk_reference_scanner import SDKReferenceScanner
        from src.services.notification_service import get_notification_service
        from src.models.contracts.notifications import (
            NotificationCreate,
            NotificationCategory,
            NotificationStatus,
        )

        try:
            content_str = content.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to decode content for SDK scan: {e}")
            return

        scanner = SDKReferenceScanner(self.db)
        issues = await scanner.scan_file(path, content_str)

        if not issues:
            # Clear any existing notification since issues are resolved
            await self._clear_sdk_issues_notification(path)
            return

        # Create platform admin notification
        service = get_notification_service()

        # Check for existing notification to avoid duplicates
        file_name = Path(path).name
        title = f"Missing SDK References: {file_name}"

        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            logger.debug(f"SDK notification already exists for {path}")
            return

        # Build description with first few issues
        issue_keys = [i.key for i in issues[:3]]
        description = f"{len(issues)} missing: {', '.join(issue_keys)}"
        if len(issues) > 3:
            description += "..."

        await service.create_notification(
            user_id="system",
            request=NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title=title,
                description=description,
                metadata={
                    "action": "view_file",
                    "file_path": path,
                    "line_number": issues[0].line_number,
                    "issues": [
                        {
                            "type": i.issue_type,
                            "key": i.key,
                            "line": i.line_number,
                        }
                        for i in issues
                    ],
                },
            ),
            for_admins=True,
            initial_status=NotificationStatus.AWAITING_ACTION,
        )

        logger.info(f"Created SDK issues notification for {path}: {len(issues)} issues")

    async def _clear_sdk_issues_notification(self, path: str) -> None:
        """
        Clear SDK issues notification for a file when issues are resolved.

        Called when a file is saved without SDK reference issues to remove
        any existing notification that was created for previous issues.

        Args:
            path: Relative file path
        """
        from pathlib import Path
        from src.services.notification_service import get_notification_service
        from src.models.contracts.notifications import NotificationCategory

        service = get_notification_service()

        # Match the title format used in _scan_for_sdk_issues
        file_name = Path(path).name
        title = f"Missing SDK References: {file_name}"

        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            await service.dismiss_notification(existing.id, user_id="system")
            logger.info(f"Cleared SDK issues notification for {path}")

    async def _create_diagnostic_notification(
        self, path: str, diagnostics: list[FileDiagnosticInfo]
    ) -> None:
        """
        Create a system notification for file diagnostics that contain errors.

        Called after file writes to ensure visibility when files have issues,
        regardless of the source (editor, git sync, MCP).

        Args:
            path: Relative file path
            diagnostics: List of file diagnostics
        """
        from pathlib import Path
        from src.services.notification_service import get_notification_service
        from src.models.contracts.notifications import (
            NotificationCreate,
            NotificationCategory,
            NotificationStatus,
        )

        errors = [d for d in diagnostics if d.severity == "error"]
        if not errors:
            return

        service = get_notification_service()

        # Build title from file name
        file_name = Path(path).name
        title = f"File issues: {file_name}"

        # Check for existing notification to avoid duplicates
        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            logger.debug(f"Diagnostic notification already exists for {path}")
            return

        # Build description from first few errors
        error_msgs = [e.message for e in errors[:3]]
        description = "; ".join(error_msgs)
        if len(errors) > 3:
            description += f"... (+{len(errors) - 3} more)"

        await service.create_notification(
            user_id="system",
            request=NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title=title,
                description=description,
                metadata={
                    "action": "view_file",
                    "file_path": path,
                    "line_number": errors[0].line if errors[0].line else 1,
                    "diagnostics": [
                        {
                            "severity": d.severity,
                            "message": d.message,
                            "line": d.line,
                            "column": d.column,
                            "source": d.source,
                        }
                        for d in diagnostics
                    ],
                },
            ),
            for_admins=True,
            initial_status=NotificationStatus.AWAITING_ACTION,
        )

        logger.info(f"Created diagnostic notification for {path}: {len(errors)} errors")

    async def _clear_diagnostic_notification(self, path: str) -> None:
        """
        Clear diagnostic notification for a file when issues are fixed.

        Called when a file is saved without errors to remove any existing
        diagnostic notification that was created for previous errors.

        Args:
            path: Relative file path
        """
        from pathlib import Path
        from src.services.notification_service import get_notification_service
        from src.models.contracts.notifications import NotificationCategory

        service = get_notification_service()

        # Match the title format used in _create_diagnostic_notification
        file_name = Path(path).name
        title = f"File issues: {file_name}"

        existing = await service.find_admin_notification_by_title(
            title=title,
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            await service.dismiss_notification(existing.id, user_id="system")
            logger.info(f"Cleared diagnostic notification for {path}")

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

    # =========================================================================
    # Raw S3 operations (no workspace indexing)
    # Used for temp and uploads locations
    # =========================================================================

    async def write_raw_to_s3(self, path: str, content: bytes) -> None:
        """
        Write content directly to S3 without workspace indexing.

        Used for temp files and uploads that don't need tracking.

        Args:
            path: S3 key (e.g., _tmp/myfile.txt, uploads/form-id/file.pdf)
            content: File content as bytes
        """
        async with self._get_s3_client() as s3:
            await s3.put_object(
                Bucket=self.settings.s3_bucket,
                Key=path,
                Body=content,
                ContentType=self._guess_content_type(path),
            )

    async def delete_raw_from_s3(self, path: str) -> None:
        """
        Delete a file directly from S3 without workspace indexing.

        Used for temp files and uploads that don't need tracking.

        Args:
            path: S3 key (e.g., _tmp/myfile.txt, uploads/form-id/file.pdf)
        """
        async with self._get_s3_client() as s3:
            await s3.delete_object(
                Bucket=self.settings.s3_bucket,
                Key=path,
            )

    async def list_raw_s3(self, prefix: str) -> list[str]:
        """
        List objects directly from S3 by prefix.

        Used for temp files and uploads that don't need tracking.

        Args:
            prefix: S3 key prefix (e.g., _tmp/, uploads/form-id/)

        Returns:
            List of S3 keys under the prefix
        """
        # Ensure prefix ends with / for directory listing
        if prefix and not prefix.endswith("/"):
            prefix = prefix + "/"

        keys: list[str] = []
        async with self._get_s3_client() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.settings.s3_bucket,
                Prefix=prefix,
            ):
                for obj in page.get("Contents", []):
                    key = obj.get("Key")
                    if key:
                        # Return path relative to prefix
                        rel_path = key[len(prefix):] if key.startswith(prefix) else key
                        if rel_path:
                            keys.append(rel_path)
        return keys

    async def file_exists(self, path: str) -> bool:
        """
        Check if a file exists in S3.

        Args:
            path: S3 key

        Returns:
            True if file exists, False otherwise
        """
        async with self._get_s3_client() as s3:
            try:
                await s3.head_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                )
                return True
            except s3.exceptions.ClientError:
                return False


def get_file_storage_service(db: AsyncSession) -> FileStorageService:
    """Factory function for FileStorageService."""
    return FileStorageService(db)
