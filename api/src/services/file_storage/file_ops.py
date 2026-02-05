"""
File Operations Service for File Storage.

Handles read, write, delete, and move operations for individual files.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import Settings
from src.models import WorkspaceFile, Workflow, Form, Agent
from src.models.orm.applications import Application
from src.models.enums import GitStatus
from src.core.module_cache import set_module, invalidate_module
from .models import WriteResult
from .utils import serialize_form_to_json, serialize_agent_to_json

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

    async def read_file(self, path: str) -> tuple[bytes, WorkspaceFile | None]:
        """
        Read file content and metadata.

        Routes reads based on workspace_files.entity_type:
        - If entity_type='workflow' and entity_id is set: fetch from workflows.code column
        - If entity_type='form' and entity_id is set: fetch from forms table and serialize
        - If entity_type='app' and entity_id is set: fetch from applications.draft_definition
        - If entity_type='agent' and entity_id is set: fetch from agents table and serialize
        - If entity_type is NULL: fetch from S3 (existing behavior)

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

        logger.info(f"read_file({path}): file_record={file_record is not None}, entity_type={file_record.entity_type if file_record else None}")

        # Route based on entity type - platform entities are stored in the database
        if file_record is not None:
            entity_type = file_record.entity_type
            entity_id = file_record.entity_id

            # Workflow: fetch code column (requires entity_id)
            if entity_type == "workflow" and entity_id is not None:
                workflow_stmt = select(Workflow).where(Workflow.id == entity_id)
                workflow_result = await self.db.execute(workflow_stmt)
                workflow = workflow_result.scalar_one_or_none()

                if workflow is not None and workflow.code is not None:
                    return workflow.code.encode("utf-8"), file_record
                # Fall through to S3 if workflow not found or code is None

            # Form: serialize to JSON (requires entity_id)
            elif entity_type == "form" and entity_id is not None:
                form_stmt = (
                    select(Form)
                    .options(selectinload(Form.fields))
                    .where(Form.id == entity_id)
                )
                form_result = await self.db.execute(form_stmt)
                form = form_result.scalar_one_or_none()

                if form is not None:
                    return serialize_form_to_json(form), file_record
                raise FileNotFoundError(f"Form not found: {entity_id}")

            # App: return draft_definition as JSON (requires entity_id)
            elif entity_type == "app" and entity_id is not None:
                app_stmt = select(Application).where(Application.id == entity_id)
                app_result = await self.db.execute(app_stmt)
                app = app_result.scalar_one_or_none()

                if app is not None:
                    definition = app.draft_definition if app.draft_definition else {}
                    return json.dumps(definition, indent=2).encode("utf-8"), file_record
                raise FileNotFoundError(f"Application not found: {entity_id}")

            # Agent: serialize to JSON (requires entity_id)
            elif entity_type == "agent" and entity_id is not None:
                agent_stmt = select(Agent).where(Agent.id == entity_id)
                agent_result = await self.db.execute(agent_stmt)
                agent = agent_result.scalar_one_or_none()

                if agent is not None:
                    return serialize_agent_to_json(agent), file_record
                raise FileNotFoundError(f"Agent not found: {entity_id}")

            # Module: fetch from workspace_files.content (no entity_id needed)
            elif entity_type == "module":
                if file_record.content is not None:
                    return file_record.content.encode("utf-8"), file_record
                raise FileNotFoundError(f"Module content not found: {path}")

            # Text: fetch from workspace_files.content (no entity_id needed)
            elif entity_type == "text":
                if file_record.content is not None:
                    return file_record.content.encode("utf-8"), file_record
                raise FileNotFoundError(f"Text file content not found: {path}")

        # Default: fetch from S3 (entity_type is NULL or unknown)
        logger.info(f"read_file({path}): falling through to S3 (file_record={file_record is not None})")
        async with self._s3_client.get_client() as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                )
                content = await response["Body"].read()
                return content, file_record
            except s3.exceptions.NoSuchKey:
                logger.info(f"read_file({path}): S3 NoSuchKey - file not found")
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

        # Detect if this is a platform entity (workflow, form, app, agent)
        # Platform entities are stored in the database, not S3
        #
        # For Python files, we use detect_python_entity_type_with_ast to get
        # the cached AST tree and decoded content string. This avoids parsing
        # the AST multiple times (was 3x before, now 1x) - critical for large
        # files like halopsa.py (4MB) where each parse uses ~100MB.
        cached_ast = None
        cached_content_str = None
        if path.endswith(".py"):
            from src.services.file_storage.entity_detector import (
                detect_python_entity_type_with_ast,
            )
            detection_result = detect_python_entity_type_with_ast(content)
            platform_entity_type = detection_result.entity_type
            cached_ast = detection_result.ast_tree
            cached_content_str = detection_result.content_str
        else:
            platform_entity_type = self._detect_platform_entity_type(path, content)

        is_platform_entity = platform_entity_type is not None
        logger.info(f"write_file({path}): platform_entity_type={platform_entity_type}")

        # Only write to S3 for regular files (not platform entities)
        # Platform entity content is stored in DB tables via _extract_metadata
        if not is_platform_entity:
            async with self._s3_client.get_client() as s3:
                await s3.put_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                    Body=content,
                    ContentType=content_type,
                )

        # Upsert index record
        # Use UTC datetime without timezone info to match SQLAlchemy model defaults
        now = datetime.utcnow()

        # For modules and text files, store content directly in workspace_files.content
        # Other entity types store content in their respective tables
        inline_content: str | None = None
        if platform_entity_type in ("module", "text"):
            # Reuse cached decoded string if available (avoids another decode)
            inline_content = cached_content_str or content.decode("utf-8")

        # Note: github_sha is NOT set here - it should only be set by the GitHub sync
        # process when a file is actually pushed to or pulled from GitHub. Setting it
        # here would confuse the sync logic into thinking the file was synced when it wasn't.
        # git_status=MODIFIED indicates the file has local changes that need to be pushed.
        stmt = insert(WorkspaceFile).values(
            path=path,
            content_hash=content_hash,
            # github_sha intentionally omitted - defaults to None for new files
            size_bytes=size_bytes,
            content_type=content_type,
            git_status=GitStatus.MODIFIED,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            entity_type=platform_entity_type,
            content=inline_content,
        ).on_conflict_do_update(
            index_elements=[WorkspaceFile.path],
            set_={
                "content_hash": content_hash,
                # github_sha intentionally NOT updated - preserve existing sync state
                "size_bytes": size_bytes,
                "content_type": content_type,
                "git_status": GitStatus.MODIFIED,
                "is_deleted": False,
                "updated_at": now,
                "entity_type": platform_entity_type,
                "content": inline_content,
            },
        ).returning(WorkspaceFile)

        result = await self.db.execute(stmt)
        file_record = result.scalar_one()
        await self.db.flush()  # Ensure changes are flushed before continuing
        logger.info(f"write_file({path}): upserted record entity_type={file_record.entity_type}, content_len={len(file_record.content) if file_record.content else None}")

        # Update module cache in Redis for immediate availability in virtual imports
        if platform_entity_type == "module" and inline_content:
            await set_module(path, inline_content, content_hash)
            logger.info(f"write_file({path}): cached module in Redis")
            # Release the decoded string copy - can be 4MB+ for large modules
            del inline_content

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
        # (AST for 4MB Python file uses ~100MB, content_str is another 4MB)
        del cached_ast
        del cached_content_str

        # If there are pending deactivations, return early (caller should raise 409)
        if pending_deactivations:
            return WriteResult(
                file_record=file_record,
                final_content=final_content,
                content_modified=content_modified,
                needs_indexing=needs_indexing,
                workflow_id_conflicts=workflow_id_conflicts,
                diagnostics=diagnostics if diagnostics else None,
                pending_deactivations=pending_deactivations,
                available_replacements=available_replacements,
            )

        # Scan Python files for missing SDK references (config.get, integrations.get)
        # and create platform admin notifications if issues are found
        if path.endswith(".py"):
            try:
                await self._diagnostics.scan_for_sdk_issues(path, final_content)
            except Exception as e:
                logger.warning(f"Failed to scan for SDK issues in {path}: {e}")

        # Create or clear system notification based on diagnostic errors
        # This ensures visibility when files are written from any source (editor, git sync, MCP)
        has_errors = diagnostics and any(d.severity == "error" for d in diagnostics)
        if has_errors:
            try:
                await self._diagnostics.create_diagnostic_notification(path, diagnostics)
            except Exception as e:
                logger.warning(f"Failed to create diagnostic notification for {path}: {e}")
        else:
            # Clear any existing diagnostic notification for this file
            try:
                await self._diagnostics.clear_diagnostic_notification(path)
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

    async def delete_file(self, path: str) -> None:
        """
        Delete a file from storage.

        For platform entities (workflows, forms, apps, agents), only DB cleanup is needed.
        For regular files, also deletes from S3.

        Args:
            path: Relative path within workspace
        """
        # Check if this is a platform entity by looking at entity_type in workspace_files
        # Platform entities have content in DB, not S3, so we skip S3 delete
        stmt = select(WorkspaceFile.entity_type).where(
            WorkspaceFile.path == path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        entity_type = result.scalar_one_or_none()

        # Only delete from S3 if not a platform entity
        if entity_type is None:
            async with self._s3_client.get_client() as s3:
                await s3.delete_object(
                    Bucket=self.settings.s3_bucket,
                    Key=path,
                )

        # Soft delete in index and clear content for modules
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.path == path,
        ).values(
            is_deleted=True,
            git_status=GitStatus.DELETED,
            updated_at=datetime.utcnow(),
            content=None,  # Clear module content on delete
        )
        await self.db.execute(stmt)

        # Clean up related metadata
        await self._remove_metadata(path)

        # Invalidate module cache if this was a module
        if entity_type == "module":
            await invalidate_module(path)
            logger.info(f"delete_file({path}): invalidated module cache")

        logger.info(f"File deleted: {path}")

    async def move_file(self, old_path: str, new_path: str) -> WorkspaceFile:
        """
        Move/rename a file, preserving platform entity associations.

        For platform entities (workflows, forms, apps, agents), updates the path
        columns in both workspace_files and the entity table. No content is
        re-parsed, so all metadata (org_id, role assignments, etc.) is preserved.

        For regular files, copies content in S3 and updates the index.

        Args:
            old_path: Current relative path within workspace
            new_path: New relative path within workspace

        Returns:
            Updated WorkspaceFile record

        Raises:
            FileNotFoundError: If old_path doesn't exist
            FileExistsError: If new_path already exists
        """
        now = datetime.utcnow()

        # Get the existing file record
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == old_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        file_record = result.scalar_one_or_none()

        if not file_record:
            raise FileNotFoundError(f"File not found: {old_path}")

        # Check if new_path already exists
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == new_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise FileExistsError(f"File already exists: {new_path}")

        entity_type = file_record.entity_type
        entity_id = file_record.entity_id

        # Handle based on entity type
        if entity_type == "workflow" and entity_id:
            # Update workflow.path
            stmt = update(Workflow).where(
                Workflow.id == entity_id
            ).values(
                path=new_path,
                updated_at=now,
            )
            await self.db.execute(stmt)
            logger.info(f"Updated workflow {entity_id} path: {old_path} -> {new_path}")

        elif entity_type == "form" and entity_id:
            # Forms are now "fully virtual" - their path is computed from their ID
            # (forms/{uuid}.form.json), so we don't track file_path separately.
            # Just log the rename for debugging.
            logger.info(f"Form {entity_id} virtual path update: {old_path} -> {new_path}")

        elif entity_type == "app" and entity_id:
            # Update application (no file_path column, apps are in applications table)
            # Apps don't have a file_path column - they're stored by ID
            # Nothing to update in the entity table
            logger.info(f"App {entity_id} path update: {old_path} -> {new_path}")

        elif entity_type == "agent" and entity_id:
            # Agents are now "fully virtual" - their path is computed from their ID
            # (agents/{uuid}.agent.json), so we don't track file_path separately.
            # Just log the rename for debugging.
            logger.info(f"Agent {entity_id} virtual path update: {old_path} -> {new_path}")

        elif entity_type == "module":
            # Module content is stored in workspace_files.content
            # No entity table to update, just workspace_files path (handled below)
            # Update module cache: invalidate old path, cache at new path
            await invalidate_module(old_path)
            if file_record.content:
                await set_module(new_path, file_record.content, file_record.content_hash or "")
            logger.info(f"Module path update: {old_path} -> {new_path}")

        else:
            # Regular file: copy in S3
            async with self._s3_client.get_client() as s3:
                # Copy object
                await s3.copy_object(
                    Bucket=self.settings.s3_bucket,
                    CopySource={"Bucket": self.settings.s3_bucket, "Key": old_path},
                    Key=new_path,
                )
                # Delete old object
                await s3.delete_object(
                    Bucket=self.settings.s3_bucket,
                    Key=old_path,
                )
            logger.info(f"Moved S3 object: {old_path} -> {new_path}")

        # Update workspace_files record path
        stmt = update(WorkspaceFile).where(
            WorkspaceFile.id == file_record.id
        ).values(
            path=new_path,
            updated_at=now,
        )
        await self.db.execute(stmt)

        # Refresh the record to get updated values
        await self.db.refresh(file_record)
        logger.info(f"File moved: {old_path} -> {new_path}")
        return file_record
