"""
File Operations Service for File Storage.

Handles read, write, delete, and move operations for individual files.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import Settings
from src.models import Workflow, Form, Agent
from src.models.orm.applications import Application
from src.models.orm.file_index import FileIndex
from src.core.module_cache import set_module, invalidate_module
from src.services.repo_storage import REPO_PREFIX
from .models import WriteResult
from .utils import serialize_form_to_yaml, serialize_agent_to_yaml
from .entity_detector import detect_platform_entity_type

if TYPE_CHECKING:
    from .diagnostics import DiagnosticsService
    from .deactivation import DeactivationProtectionService

logger = logging.getLogger(__name__)


def compute_git_blob_sha(content: bytes) -> str:
    """
    Compute Git blob SHA (how Git identifies file content).

    Git blob SHA = SHA1("blob <size>\\0<content>")

    This is stored in github_sha to enable fast sync comparison
    without reading file content from S3.
    """
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content).hexdigest()


class FileOperationsService:
    """Service for individual file operations (read, write, delete, move)."""

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        s3_client,
        diagnostics: "DiagnosticsService",
        deactivation: "DeactivationProtectionService",
        file_hash_fn: Callable[[bytes], str],
        content_type_fn: Callable[[str], str],
        platform_entity_detector_fn: Callable[[str, bytes], str | None],
        extract_metadata_fn,
        remove_metadata_fn,
    ):
        """
        Initialize file operations service.

        Args:
            db: Database session
            settings: Application settings
            s3_client: S3 client context manager
            diagnostics: DiagnosticsService instance
            deactivation: DeactivationProtectionService instance
            file_hash_fn: Function to compute content hash
            content_type_fn: Function to guess content type
            platform_entity_detector_fn: Function to detect platform entity type
            extract_metadata_fn: Function to extract metadata
            remove_metadata_fn: Function to remove metadata
        """
        self.db = db
        self.settings = settings
        self._s3_client = s3_client
        self._diagnostics = diagnostics
        self._deactivation = deactivation
        self._compute_hash = file_hash_fn
        self._guess_content_type = content_type_fn
        self._detect_platform_entity_type = platform_entity_detector_fn
        self._extract_metadata = extract_metadata_fn
        self._remove_metadata = remove_metadata_fn

    async def read_file(self, path: str) -> tuple[bytes, None]:
        """
        Read file content.

        Routes reads by path convention:
        - forms/{uuid}.form.yaml -> serialize from forms table
        - agents/{uuid}.agent.yaml -> serialize from agents table
        - Everything else -> fetch from file_index, fallback to S3

        Args:
            path: Relative path within workspace

        Returns:
            Tuple of (content bytes, None)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        import re
        from uuid import UUID

        # Forms: forms/{uuid}.form.yaml
        form_match = re.match(r"forms/([a-f0-9-]+)\.form\.yaml$", path, re.IGNORECASE)
        if form_match:
            try:
                form_id = UUID(form_match.group(1))
            except ValueError:
                raise FileNotFoundError(f"Invalid form path: {path}")
            form_stmt = (
                select(Form)
                .options(selectinload(Form.fields))
                .where(Form.id == form_id)
            )
            form_result = await self.db.execute(form_stmt)
            form = form_result.scalar_one_or_none()
            if form is not None:
                return serialize_form_to_yaml(form), None
            raise FileNotFoundError(f"Form not found: {form_id}")

        # Agents: agents/{uuid}.agent.yaml
        agent_match = re.match(r"agents/([a-f0-9-]+)\.agent\.yaml$", path, re.IGNORECASE)
        if agent_match:
            try:
                agent_id = UUID(agent_match.group(1))
            except ValueError:
                raise FileNotFoundError(f"Invalid agent path: {path}")
            agent_stmt = select(Agent).where(Agent.id == agent_id)
            agent_result = await self.db.execute(agent_stmt)
            agent = agent_result.scalar_one_or_none()
            if agent is not None:
                return serialize_agent_to_yaml(agent), None
            raise FileNotFoundError(f"Agent not found: {agent_id}")

        # Everything else: Redis cache → S3 _repo/ (file_index is search-only)
        from src.core.module_cache import get_module
        cached = await get_module(path)
        if cached:
            return cached["content"].encode("utf-8"), None

        # Fallback to S3 _repo/ prefix
        s3_key = f"{REPO_PREFIX}{path}"
        async with self._s3_client.get_client() as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.settings.s3_bucket,
                    Key=s3_key,
                )
                content = await response["Body"].read()
                return content, None
            except s3.exceptions.NoSuchKey:
                raise FileNotFoundError(f"File not found: {path}")

    async def write_file(
        self,
        path: str,
        content: bytes,
        updated_by: str = "system",
        force_deactivation: bool = False,
        replacements: dict[str, str] | None = None,
    ) -> WriteResult:
        """
        Write file content to storage and update index.

        Also extracts workflow/form metadata at write time.
        For platform entities (workflows, forms, apps, agents), content is stored
        in the database. For regular files, content is stored in S3.

        Args:
            path: Relative path within workspace
            content: File content as bytes
            updated_by: User who made the change
            force_deactivation: Skip deactivation protection for Python files
            replacements: Map of workflow_id -> new_function_name for identity transfer

        Returns:
            WriteResult containing file record, final content, modification flag,
            diagnostics, and pending deactivations if any.

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

        # For Python files, use AST detection to cache the tree and decoded string.
        # The cached AST avoids re-parsing in _extract_metadata.
        cached_ast = None
        cached_content_str = None
        if path.endswith(".py"):
            from src.services.file_storage.entity_detector import (
                detect_python_entity_type_with_ast,
            )
            detection_result = detect_python_entity_type_with_ast(content)
            cached_ast = detection_result.ast_tree
            cached_content_str = detection_result.content_str

        # Write ALL files to S3 under _repo/ prefix — this is the durable store.
        # Platform entities also go to S3 so the Redis→S3 fallback works for workers.
        s3_key = f"{REPO_PREFIX}{path}"
        async with self._s3_client.get_client() as s3:
            await s3.put_object(
                Bucket=self.settings.s3_bucket,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )

        now = datetime.now(timezone.utc)

        # Write to file_index (the sole search index)
        content_str = cached_content_str or content.decode("utf-8", errors="replace")
        fi_stmt = insert(FileIndex).values(
            path=path,
            content=content_str,
            content_hash=content_hash,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[FileIndex.path],
            set_={
                "content": content_str,
                "content_hash": content_hash,
                "updated_at": now,
            },
        )
        await self.db.execute(fi_stmt)
        await self.db.flush()

        # Update module cache in Redis for immediate availability in virtual imports.
        # Both workflows and modules need caching — workers load code via Redis→S3.
        if path.endswith(".py"):
            await set_module(path, content_str, content_hash)

        # Extract metadata for workflows/forms/agents
        # Pass cached AST and content_str to avoid re-parsing large Python files
        (
            final_content,
            content_modified,
            needs_indexing,
            workflow_id_conflicts,
            diagnostics,
            pending_deactivations,
            available_replacements,
        ) = await self._extract_metadata(
            path, content, force_deactivation, replacements,
            cached_ast=cached_ast, cached_content_str=cached_content_str
        )

        # Release cached AST and content string to free memory
        del cached_ast
        del cached_content_str

        # If there are pending deactivations, return early (caller should raise 409)
        if pending_deactivations:
            return WriteResult(
                file_record=None,
                final_content=final_content,
                content_modified=content_modified,
                needs_indexing=needs_indexing,
                workflow_id_conflicts=workflow_id_conflicts,
                diagnostics=diagnostics if diagnostics else None,
                pending_deactivations=pending_deactivations,
                available_replacements=available_replacements,
            )

        # Scan Python files for missing SDK references
        if path.endswith(".py"):
            try:
                await self._diagnostics.scan_for_sdk_issues(path, final_content)
            except Exception as e:
                logger.warning(f"Failed to scan for SDK issues in {path}: {e}")

        # Create or clear system notification based on diagnostic errors
        has_errors = diagnostics and any(d.severity == "error" for d in diagnostics)
        if has_errors:
            try:
                await self._diagnostics.create_diagnostic_notification(path, diagnostics)
            except Exception as e:
                logger.warning(f"Failed to create diagnostic notification for {path}: {e}")
        else:
            try:
                await self._diagnostics.clear_diagnostic_notification(path)
            except Exception as e:
                logger.warning(f"Failed to clear diagnostic notification for {path}: {e}")

        logger.info(f"File written: {path} ({size_bytes} bytes) by {updated_by}")
        return WriteResult(
            file_record=None,
            final_content=final_content,
            content_modified=content_modified,
            needs_indexing=needs_indexing,
            workflow_id_conflicts=workflow_id_conflicts,
            diagnostics=diagnostics if diagnostics else None,
        )

    async def delete_file(self, path: str) -> None:
        """
        Delete a file from storage.

        Args:
            path: Relative path within workspace
        """
        # Detect entity type from path (used for module cache invalidation below)
        platform_entity_type = detect_platform_entity_type(path, b"")

        # Delete from S3 _repo/ prefix for all files
        s3_key = f"{REPO_PREFIX}{path}"
        async with self._s3_client.get_client() as s3:
            try:
                await s3.delete_object(
                    Bucket=self.settings.s3_bucket,
                    Key=s3_key,
                )
            except Exception:
                pass  # Ignore S3 errors for idempotency

        # Delete from file_index
        from sqlalchemy import delete
        del_stmt = delete(FileIndex).where(FileIndex.path == path)
        await self.db.execute(del_stmt)

        # Clean up related metadata (workflows, forms, agents)
        await self._remove_metadata(path)

        # Invalidate module cache
        if platform_entity_type == "module" or path.endswith(".py"):
            await invalidate_module(path)

        logger.info(f"File deleted: {path}")

    async def move_file(self, old_path: str, new_path: str) -> None:
        """
        Move/rename a file, preserving platform entity associations.

        Args:
            old_path: Current relative path within workspace
            new_path: New relative path within workspace

        Raises:
            FileNotFoundError: If old_path doesn't exist
            FileExistsError: If new_path already exists
        """
        now = datetime.now(timezone.utc)

        # Check old path exists in file_index
        fi_stmt = select(FileIndex).where(FileIndex.path == old_path)
        fi_result = await self.db.execute(fi_stmt)
        old_record = fi_result.scalar_one_or_none()
        if not old_record:
            raise FileNotFoundError(f"File not found: {old_path}")

        # Check new path doesn't exist
        fi_stmt2 = select(FileIndex).where(FileIndex.path == new_path)
        fi_result2 = await self.db.execute(fi_stmt2)
        if fi_result2.scalar_one_or_none():
            raise FileExistsError(f"File already exists: {new_path}")

        # Update entity table paths for Python files
        if old_path.endswith(".py"):
            # Update any workflows that reference this path
            stmt = update(Workflow).where(
                Workflow.path == old_path
            ).values(
                path=new_path,
                updated_at=now,
            )
            await self.db.execute(stmt)

            # Update module cache
            await invalidate_module(old_path)
            if old_record.content:
                await set_module(new_path, old_record.content, old_record.content_hash or "")

        # Move file in S3 _repo/ prefix for all file types
        old_s3_key = f"{REPO_PREFIX}{old_path}"
        new_s3_key = f"{REPO_PREFIX}{new_path}"
        async with self._s3_client.get_client() as s3:
            try:
                await s3.copy_object(
                    Bucket=self.settings.s3_bucket,
                    CopySource={"Bucket": self.settings.s3_bucket, "Key": old_s3_key},
                    Key=new_s3_key,
                )
                await s3.delete_object(
                    Bucket=self.settings.s3_bucket,
                    Key=old_s3_key,
                )
            except Exception as e:
                logger.warning(f"S3 move failed for {old_path} -> {new_path}: {e}")

        # Update file_index: insert new path, delete old
        new_stmt = insert(FileIndex).values(
            path=new_path,
            content=old_record.content,
            content_hash=old_record.content_hash,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=[FileIndex.path],
            set_={
                "content": old_record.content,
                "content_hash": old_record.content_hash,
                "updated_at": now,
            },
        )
        await self.db.execute(new_stmt)

        from sqlalchemy import delete
        del_stmt = delete(FileIndex).where(FileIndex.path == old_path)
        await self.db.execute(del_stmt)

        logger.info(f"File moved: {old_path} -> {new_path}")
