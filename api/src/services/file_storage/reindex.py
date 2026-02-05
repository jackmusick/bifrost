"""
Workspace Reindexing Service for File Storage.

Handles syncing workspace indexes from S3, reindexing from local filesystem,
and smart reindexing with reference validation.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable, TYPE_CHECKING

from sqlalchemy import select, update, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings
from src.models import WorkspaceFile
from src.models.enums import GitStatus

if TYPE_CHECKING:
    from src.models.contracts.maintenance import ReindexResult

logger = logging.getLogger(__name__)


class WorkspaceReindexService:
    """Service for reindexing workspace files from S3 or filesystem."""

    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        s3_client,
        entity_resolution,
        file_hash_fn: Callable[[bytes], str],
        content_type_fn: Callable[[str], str],
        extract_metadata_fn,
        index_python_file_fn,
    ):
        """
        Initialize reindex service.

        Args:
            db: Database session
            settings: Application settings
            s3_client: S3 client context manager
            entity_resolution: EntityResolutionService instance
            file_hash_fn: Function to compute content hash
            content_type_fn: Function to guess content type
            extract_metadata_fn: Function to extract metadata from files
            index_python_file_fn: Function to index Python files
        """
        self.db = db
        self.settings = settings
        self._s3_client = s3_client
        self._entity_resolution = entity_resolution
        self._compute_hash = file_hash_fn
        self._guess_content_type = content_type_fn
        self._extract_metadata = extract_metadata_fn
        self._index_python_file = index_python_file_fn

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
        async with self._s3_client.get_client() as s3:
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
                    # Note: github_sha is NOT set here - it should only be set by the
                    # GitHub sync process. Reindexing doesn't mean the file is synced.
                    now = datetime.utcnow()
                    stmt = insert(WorkspaceFile).values(
                        path=key,
                        content_hash=content_hash,
                        # github_sha intentionally omitted - defaults to None
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
                            # github_sha intentionally NOT updated - preserve sync state
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
        self, local_path: Path
    ) -> dict[str, int | list[str]]:
        """
        Reindex workspace_files table from local filesystem.

        Called after download_workspace() to ensure DB matches actual files.
        Also reconciles orphaned workflows/data_providers.

        Args:
            local_path: Local workspace directory (e.g., /tmp/bifrost/workspace)

        Returns:
            Dict with counts: files_indexed, files_removed, workflows_deactivated,
            data_providers_deactivated
        """
        from src.models import Workflow  # Data providers are in workflows table with type='data_provider'
        from src.services.editor.file_filter import is_excluded_path

        counts: dict[str, int | list[str]] = {
            "files_indexed": 0,
            "files_removed": 0,
            "workflows_deactivated": 0,
            "data_providers_deactivated": 0,
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
        # Process files in dependency order:
        # - Python files first (define workflows, data providers, tools)
        # - Form JSON files second (may reference workflows)
        # - Agent JSON files last (reference workflows + potentially other agents)
        # This prevents FK constraint violations during indexing
        py_files = sorted([p for p in existing_paths if p.endswith(".py")])
        form_files = sorted([p for p in existing_paths if p.endswith(".form.json")])
        agent_files = sorted([p for p in existing_paths if p.endswith(".agent.json")])
        other_files = sorted([
            p for p in existing_paths
            if not p.endswith(".py") and not p.endswith(".form.json") and not p.endswith(".agent.json")
        ])
        ordered_paths = py_files + form_files + agent_files + other_files

        now = datetime.utcnow()

        for rel_path in ordered_paths:
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

            # Extract metadata (workflows/data_providers)
            await self._extract_metadata(rel_path, content)

            counts["files_indexed"] += 1

        # 4. Clean up endpoints for orphaned endpoint-enabled workflows
        result = await self.db.execute(
            select(Workflow).where(
                Workflow.is_active == True,  # noqa: E712
                Workflow.endpoint_enabled == True,  # noqa: E712
                ~Workflow.path.in_(existing_paths) if existing_paths else True,
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
            ~Workflow.path.in_(existing_paths) if existing_paths else True,
        ).values(is_active=False)
        result = await self.db.execute(stmt)
        counts["workflows_deactivated"] = result.rowcount if result.rowcount > 0 else 0

        # 6. Data providers are now in the workflows table with type='data_provider'
        # They are already handled by the orphaned workflows query above (step 5).
        # The workflows_deactivated count includes data providers.
        # We keep the key for backward compatibility but set it to 0.
        counts["data_providers_deactivated"] = 0

        if any(counts.values()):
            logger.info(f"Reindexed workspace: {counts}")

        return counts

    async def smart_reindex(
        self,
        local_path: Path,
        download_workspace_fn: Callable[[Path], Awaitable[None]],
        progress_callback: "Callable[[dict], Awaitable[None]] | None" = None,
    ) -> "ReindexResult":
        """
        Smart reindex with reference validation and ID alignment.

        This method:
        1. Downloads workspace files from S3
        2. Indexes workflow Python files and validates/aligns IDs with DB
        3. Validates forms (from DB) use valid workflow/data_provider references
        4. Validates agents (from DB) use valid workflow/agent references
        5. Silently fixes invalid references in the database
        6. Produces actionable errors when no match exists

        Note: Forms and agents are DB-first entities - they are queried from the
        database, not read from files. Only workflow Python files are read from
        the filesystem.

        Args:
            local_path: Local directory for workspace files
            download_workspace_fn: Function to download workspace from S3
            progress_callback: Optional async callback for progress updates

        Returns:
            ReindexResult with counts, warnings, and errors
        """
        from src.models import Workflow, Form, Agent
        from src.models.orm.agents import AgentTool, AgentDelegation
        from src.models.orm.forms import FormField
        from src.models.contracts.maintenance import (
            ReindexResult,
            ReindexError,
            ReindexCounts,
        )
        from src.services.editor.file_filter import is_excluded_path

        warnings: list[str] = []
        errors: list[ReindexError] = []
        counts = ReindexCounts()
        ids_corrected = 0

        async def report_progress(phase: str, current: int, total: int, file: str = ""):
            """Helper to report progress if callback is provided."""
            if progress_callback:
                await progress_callback({
                    "phase": phase,
                    "current": current,
                    "total": total,
                    "current_file": file,
                })

        try:
            # Phase 1: Clear temp directories and download workspace
            await report_progress("Preparing workspace", 0, 1)
            self._clear_temp_directories()

            await report_progress("Downloading workspace", 0, 1)
            await download_workspace_fn(local_path)
            await report_progress("Downloading workspace", 1, 1)

            # Get known workflow file paths from DB to avoid scanning large non-workflow files
            db_workflow_result = await self.db.execute(
                select(Workflow.path).distinct()
            )
            db_workflow_paths = {row[0] for row in db_workflow_result.fetchall()}

            # Collect workflow Python files only (forms/agents are DB-first)
            py_files: list[str] = []

            for file_path in local_path.rglob("*"):
                if not file_path.is_file():
                    continue
                rel_path = str(file_path.relative_to(local_path))
                if is_excluded_path(rel_path):
                    continue

                if rel_path.endswith(".py"):
                    # Only process Python files that are known workflows in DB
                    if rel_path in db_workflow_paths:
                        py_files.append(rel_path)

            py_files.sort()

            # Phase 2: Validate & align workflows (from files)
            for i, rel_path in enumerate(py_files):
                await report_progress("Validating workflows", i, len(py_files), rel_path)

                file_path = local_path / rel_path
                try:
                    content = file_path.read_bytes()
                except OSError as e:
                    logger.warning(f"Failed to read {rel_path}: {e}")
                    continue

                # Index Python file - IDs are DB-only, no file modifications
                try:
                    await self._index_python_file(rel_path, content)
                except Exception as e:
                    logger.warning(f"Failed to index {rel_path}: {e}")
                    errors.append(ReindexError(
                        file_path=rel_path,
                        field="",
                        referenced_id="",
                        message=f"Failed to parse: {str(e)}",
                    ))

                counts.files_indexed += 1

            # Phase 3: Validate forms (from DB, not files)
            db_forms_result = await self.db.execute(
                select(Form).where(Form.is_active == True)  # noqa: E712
            )
            db_forms = list(db_forms_result.scalars().all())

            for i, form in enumerate(db_forms):
                await report_progress("Validating forms", i, len(db_forms), form.name)

                form_modified = False

                # Validate workflow_id reference
                if form.workflow_id:
                    workflow = await self._entity_resolution.get_workflow_by_id(form.workflow_id)
                    if not workflow:
                        # Try to find by name
                        match = await self._entity_resolution.find_workflow_match(form.workflow_id)
                        if match:
                            old_id = form.workflow_id
                            form.workflow_id = str(match.id)
                            form_modified = True
                            ids_corrected += 1
                            warnings.append(
                                f"Form {form.name} workflow_id corrected: "
                                f"{old_id} -> {match.id}"
                            )
                        else:
                            errors.append(ReindexError(
                                file_path=form.name,
                                field="workflow_id",
                                referenced_id=form.workflow_id,
                                message="Workflow not found. No exact match in workspace.",
                            ))
                            # Clear invalid reference to prevent FK violation
                            form.workflow_id = None
                            form_modified = True

                # Validate launch_workflow_id reference
                if form.launch_workflow_id:
                    workflow = await self._entity_resolution.get_workflow_by_id(form.launch_workflow_id)
                    if not workflow:
                        match = await self._entity_resolution.find_workflow_match(form.launch_workflow_id)
                        if match:
                            old_id = form.launch_workflow_id
                            form.launch_workflow_id = str(match.id)
                            form_modified = True
                            ids_corrected += 1
                            warnings.append(
                                f"Form {form.name} launch_workflow_id corrected: "
                                f"{old_id} -> {match.id}"
                            )
                        else:
                            errors.append(ReindexError(
                                file_path=form.name,
                                field="launch_workflow_id",
                                referenced_id=form.launch_workflow_id,
                                message="Launch workflow not found.",
                            ))
                            # Clear invalid reference to prevent FK violation
                            form.launch_workflow_id = None
                            form_modified = True

                # Validate data_provider_id in form fields
                fields_result = await self.db.execute(
                    select(FormField).where(FormField.form_id == form.id)
                )
                fields = list(fields_result.scalars().all())
                for field in fields:
                    if field.data_provider_id:
                        dp = await self._entity_resolution.get_workflow_by_id(str(field.data_provider_id))
                        if not dp:
                            match = await self._entity_resolution.find_workflow_match(str(field.data_provider_id))
                            if match:
                                old_id = str(field.data_provider_id)
                                field.data_provider_id = match.id
                                ids_corrected += 1
                                warnings.append(
                                    f"Form {form.name} field {field.name} "
                                    f"data_provider_id corrected: {old_id} -> {match.id}"
                                )
                            else:
                                errors.append(ReindexError(
                                    file_path=form.name,
                                    field=f"fields.{field.name}.data_provider_id",
                                    referenced_id=str(field.data_provider_id),
                                    message="Data provider not found.",
                                ))
                                # Clear invalid reference to prevent FK violation
                                field.data_provider_id = None

                if form_modified:
                    logger.info(f"Updated form {form.name} references in DB")

            # Phase 4: Validate agents (from DB, not files)
            db_agents_result = await self.db.execute(
                select(Agent).where(Agent.is_active == True)  # noqa: E712
            )
            db_agents = list(db_agents_result.scalars().all())

            for i, agent in enumerate(db_agents):
                await report_progress("Validating agents", i, len(db_agents), agent.name)

                # Validate tool_ids (workflow references via AgentTool junction)
                tools_result = await self.db.execute(
                    select(AgentTool).where(AgentTool.agent_id == agent.id)
                )
                agent_tools = list(tools_result.scalars().all())

                for agent_tool in agent_tools:
                    workflow = await self._entity_resolution.get_workflow_by_id(str(agent_tool.workflow_id))
                    if not workflow:
                        match = await self._entity_resolution.find_workflow_match(str(agent_tool.workflow_id))
                        if match:
                            old_id = str(agent_tool.workflow_id)
                            # Delete old association and create new one
                            await self.db.execute(
                                delete(AgentTool).where(
                                    AgentTool.agent_id == agent.id,
                                    AgentTool.workflow_id == agent_tool.workflow_id,
                                )
                            )
                            self.db.add(AgentTool(agent_id=agent.id, workflow_id=match.id))
                            ids_corrected += 1
                            warnings.append(
                                f"Agent {agent.name} tool_id corrected: "
                                f"{old_id} -> {match.id}"
                            )
                        else:
                            errors.append(ReindexError(
                                file_path=agent.name,
                                field="tool_ids",
                                referenced_id=str(agent_tool.workflow_id),
                                message="Tool workflow not found.",
                            ))
                            # Remove invalid tool reference
                            await self.db.execute(
                                delete(AgentTool).where(
                                    AgentTool.agent_id == agent.id,
                                    AgentTool.workflow_id == agent_tool.workflow_id,
                                )
                            )

                # Validate delegated_agent_ids (via AgentDelegation junction)
                delegations_result = await self.db.execute(
                    select(AgentDelegation).where(AgentDelegation.parent_agent_id == agent.id)
                )
                delegations = list(delegations_result.scalars().all())

                for delegation in delegations:
                    delegated_agent = await self._entity_resolution.get_agent_by_id(str(delegation.child_agent_id))
                    if not delegated_agent:
                        match = await self._entity_resolution.find_agent_match(str(delegation.child_agent_id))
                        if match:
                            old_id = str(delegation.child_agent_id)
                            # Delete old delegation and create new one
                            await self.db.execute(
                                delete(AgentDelegation).where(
                                    AgentDelegation.parent_agent_id == agent.id,
                                    AgentDelegation.child_agent_id == delegation.child_agent_id,
                                )
                            )
                            self.db.add(AgentDelegation(parent_agent_id=agent.id, child_agent_id=match.id))
                            ids_corrected += 1
                            warnings.append(
                                f"Agent {agent.name} delegated_agent_id corrected: "
                                f"{old_id} -> {match.id}"
                            )
                        else:
                            errors.append(ReindexError(
                                file_path=agent.name,
                                field="delegated_agent_ids",
                                referenced_id=str(delegation.child_agent_id),
                                message="Delegated agent not found.",
                            ))
                            # Remove invalid delegation
                            await self.db.execute(
                                delete(AgentDelegation).where(
                                    AgentDelegation.parent_agent_id == agent.id,
                                    AgentDelegation.child_agent_id == delegation.child_agent_id,
                                )
                            )

            # Count active entities
            workflow_count = await self.db.execute(
                select(Workflow).where(Workflow.is_active == True)  # noqa: E712
            )
            counts.workflows_active = len(list(workflow_count.scalars().all()))

            form_count = await self.db.execute(
                select(Form).where(Form.is_active == True)  # noqa: E712
            )
            counts.forms_active = len(list(form_count.scalars().all()))

            agent_count = await self.db.execute(
                select(Agent).where(Agent.is_active == True)  # noqa: E712
            )
            counts.agents_active = len(list(agent_count.scalars().all()))

            counts.ids_corrected = ids_corrected

            total_entities = len(py_files) + len(db_forms) + len(db_agents)
            await report_progress("Complete", total_entities, total_entities)

            # Determine status
            if errors:
                status = "completed_with_errors"
                message = f"Reindex completed with {len(errors)} unresolved references"
            else:
                status = "completed"
                message = (
                    f"Reindex completed: {counts.files_indexed} files, "
                    f"{counts.workflows_active} workflows, "
                    f"{counts.forms_active} forms, "
                    f"{counts.agents_active} agents"
                )
                if ids_corrected > 0:
                    message += f", {ids_corrected} IDs corrected"

            return ReindexResult(
                status=status,
                counts=counts,
                warnings=warnings,
                errors=errors,
                message=message,
            )

        except Exception as e:
            logger.exception(f"Smart reindex failed: {e}")
            return ReindexResult(
                status="failed",
                counts=counts,
                warnings=warnings,
                errors=errors,
                message=f"Reindex failed: {str(e)}",
            )

    def _clear_temp_directories(self) -> None:
        """
        Clear temporary directories before reindex.

        Standard paths (all under /tmp/bifrost/):
        - /tmp/bifrost/temp - SDK temp files
        - /tmp/bifrost/uploads - Uploaded form files
        - /tmp/bifrost/git - Git operations workspace

        Note: There is no longer a central "workspace" directory.
        Files are stored in the database, not on the filesystem.
        """
        from src.core.paths import TEMP_PATH, UPLOADS_PATH, GIT_WORKSPACE_PATH

        for path in [TEMP_PATH, UPLOADS_PATH, GIT_WORKSPACE_PATH]:
            try:
                if path.exists():
                    shutil.rmtree(path)
                path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Cleared temp directory: {path}")
            except Exception as e:
                logger.warning(f"Failed to clear {path}: {e}")
