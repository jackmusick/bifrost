"""
File Storage Service for S3-based workspace storage.

Handles workspace files with PostgreSQL indexing and workflow extraction.
Files are stored in S3, indexed in PostgreSQL for fast querying.

S3 storage is required - no filesystem fallback.
"""

import ast
import hashlib
import json
import logging
import mimetypes
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Awaitable, Callable, TYPE_CHECKING
from uuid import UUID as UUID_type

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import Settings, get_settings
from src.core.workspace_cache import get_workspace_cache
from src.models.enums import GitStatus
from src.models import WorkspaceFile, Workflow, Form, Agent
from src.models.orm.applications import Application

if TYPE_CHECKING:
    from src.models.contracts.maintenance import ReindexResult

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
class PendingDeactivationInfo:
    """Info about a workflow that would be deactivated on save."""

    id: str  # Workflow UUID
    name: str  # Display name from decorator
    function_name: str  # Python function name
    path: str  # File path
    description: str | None
    decorator_type: str  # "workflow", "tool", "data_provider"
    has_executions: bool
    last_execution_at: str | None  # ISO 8601
    schedule: str | None
    endpoint_enabled: bool
    affected_entities: list[dict[str, str]]  # List of {entity_type, id, name, reference_type}


@dataclass
class AvailableReplacementInfo:
    """Info about a function that could replace a deactivated workflow."""

    function_name: str
    name: str  # From decorator or function name
    decorator_type: str  # "workflow", "tool", "data_provider"
    similarity_score: float  # 0.0-1.0


@dataclass
class WriteResult:
    """Result of a file write operation."""

    file_record: WorkspaceFile
    final_content: bytes
    content_modified: bool  # True if forms/agents were modified for ID alignment
    needs_indexing: bool = False  # Legacy field, always False
    workflow_id_conflicts: list[WorkflowIdConflictInfo] | None = None  # Legacy field, always None
    diagnostics: list[FileDiagnosticInfo] | None = None  # File issues detected during save
    # Deactivation protection
    pending_deactivations: list[PendingDeactivationInfo] | None = None
    available_replacements: list[AvailableReplacementInfo] | None = None


def _serialize_form_to_json(form: Form) -> bytes:
    """
    Serialize a Form (with fields) to JSON bytes.

    Uses the same format as _write_form_to_file in routers/forms.py
    for consistency with file-based storage.

    Args:
        form: Form ORM instance with fields relationship loaded

    Returns:
        JSON serialized as UTF-8 bytes
    """
    # Convert fields to form_schema format (matches _fields_to_form_schema in forms.py)
    fields_data = []
    for field in form.fields:
        field_data: dict[str, Any] = {
            "name": field.name,
            "type": field.type,
            "required": field.required,
        }

        # Add optional fields if they're set
        if field.label:
            field_data["label"] = field.label
        if field.placeholder:
            field_data["placeholder"] = field.placeholder
        if field.help_text:
            field_data["help_text"] = field.help_text
        if field.default_value is not None:
            field_data["default_value"] = field.default_value
        if field.options:
            field_data["options"] = field.options
        if field.data_provider_id:
            field_data["data_provider_id"] = str(field.data_provider_id)
        if field.data_provider_inputs:
            field_data["data_provider_inputs"] = field.data_provider_inputs
        if field.visibility_expression:
            field_data["visibility_expression"] = field.visibility_expression
        if field.validation:
            field_data["validation"] = field.validation
        if field.allowed_types:
            field_data["allowed_types"] = field.allowed_types
        if field.multiple is not None:
            field_data["multiple"] = field.multiple
        if field.max_size_mb:
            field_data["max_size_mb"] = field.max_size_mb
        if field.content:
            field_data["content"] = field.content

        fields_data.append(field_data)

    form_schema = {"fields": fields_data}

    # Build form JSON (matches _write_form_to_file format)
    # Note: org_id, is_global, access_level are NOT written to JSON
    # These are environment-specific and should only be set in the database
    form_data = {
        "id": str(form.id),
        "name": form.name,
        "description": form.description,
        "workflow_id": form.workflow_id,
        "launch_workflow_id": form.launch_workflow_id,
        "form_schema": form_schema,
        "is_active": form.is_active,
        "created_by": form.created_by,
        "created_at": form.created_at.isoformat() + "Z",
        "updated_at": form.updated_at.isoformat() + "Z",
        "allowed_query_params": form.allowed_query_params,
        "default_launch_params": form.default_launch_params,
    }

    return json.dumps(form_data, indent=2).encode("utf-8")


def _serialize_agent_to_json(agent: Agent) -> bytes:
    """
    Serialize an Agent to JSON bytes.

    Args:
        agent: Agent ORM instance

    Returns:
        JSON serialized as UTF-8 bytes
    """
    agent_data = {
        "id": str(agent.id),
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "channels": agent.channels,
        "access_level": agent.access_level.value if agent.access_level else None,
        "is_active": agent.is_active,
        "is_coding_mode": agent.is_coding_mode,
        "is_system": agent.is_system,
        "knowledge_sources": agent.knowledge_sources,
        "system_tools": agent.system_tools,
        "created_by": agent.created_by,
        "created_at": agent.created_at.isoformat() + "Z",
        "updated_at": agent.updated_at.isoformat() + "Z",
    }

    return json.dumps(agent_data, indent=2).encode("utf-8")


class FileStorageService:
    """
    Storage service for workspace files.

    Provides a unified interface for file operations that:
    - Stores platform entity content in PostgreSQL (workflows, forms, apps, agents)
    - Stores regular file content in S3 (modules, data files, configs)
    - Maintains PostgreSQL index for fast queries
    - Extracts workflow/form metadata at write time
    """

    def __init__(self, db: AsyncSession, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self._s3_client = None

    def _detect_platform_entity_type(self, path: str, content: bytes) -> str | None:
        """
        Detect if a file is a platform entity that should be stored in the database.

        Platform entities are stored in the database, not S3:
        - Workflows (.py with @workflow decorator): stored in workflows.code
        - Data providers (.py with @data_provider decorator): stored in workflows.code
        - Forms (.form.json): stored in forms table
        - Apps (.app.json): stored in applications table
        - Agents (.agent.json): stored in agents table

        Regular files (modules, data files, configs) go to S3.

        Args:
            path: File path
            content: File content

        Returns:
            Entity type ("workflow", "form", "app", "agent") or None for regular files
        """
        # JSON platform entities - always go to DB
        if path.endswith(".form.json"):
            return "form"
        if path.endswith(".app.json"):
            return "app"
        if path.endswith(".agent.json"):
            return "agent"

        # Python files - check for SDK decorators
        if path.endswith(".py"):
            return self._detect_python_entity_type(content)

        # Regular file - goes to S3
        return None

    def _detect_python_entity_type(self, content: bytes) -> str | None:
        """
        Check if Python content has SDK decorators (@workflow, @data_provider).

        Uses fast regex check first, then AST verification if needed.
        Returns "workflow" if decorators are found (includes data_provider since
        it's stored in the workflows table).

        Args:
            content: Python file content

        Returns:
            "workflow" if SDK decorators found, None otherwise
        """
        try:
            content_str = content.decode("utf-8", errors="replace")
        except Exception:
            return None

        # Fast regex check - if no decorator-like patterns, skip AST parsing
        if "@workflow" not in content_str and "@data_provider" not in content_str:
            return None

        # AST verification - confirm decorators are actually used
        try:
            tree = ast.parse(content_str)
        except SyntaxError:
            # Syntax error - can't determine entity type, treat as regular file
            # The _index_python_file will report the syntax error
            return None

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if decorator_info:
                    decorator_name, _ = decorator_info
                    if decorator_name in ("workflow", "data_provider"):
                        return "workflow"  # Both are in workflows table

        return None

    # ==================== DEACTIVATION PROTECTION ====================

    def _compute_similarity(self, old_name: str, new_name: str) -> float:
        """
        Compute similarity score between old and new function names.

        Uses SequenceMatcher for basic similarity plus bonus for shared word parts.

        Args:
            old_name: Original function name
            new_name: New function name

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Basic sequence matching
        ratio = SequenceMatcher(None, old_name.lower(), new_name.lower()).ratio()

        # Bonus for common word parts (split by underscore for snake_case)
        old_parts = set(old_name.lower().split("_"))
        new_parts = set(new_name.lower().split("_"))
        if old_parts and new_parts:
            overlap = len(old_parts & new_parts) / max(len(old_parts), len(new_parts))
        else:
            overlap = 0.0

        return (ratio * 0.7) + (overlap * 0.3)

    async def _find_affected_entities(
        self,
        workflow_id: str,
    ) -> list[dict[str, str]]:
        """
        Find forms, agents, and apps that reference a workflow.

        Args:
            workflow_id: UUID of the workflow

        Returns:
            List of affected entities with entity_type, id, name, reference_type
        """
        from src.models import Form, FormField, Agent, AgentTool
        from src.models.orm.applications import Application
        from sqlalchemy import or_

        affected: list[dict[str, str]] = []

        # Find forms that reference this workflow
        # Forms reference workflows via workflow_id (main) and launch_workflow_id
        form_stmt = select(Form).where(
            Form.is_active == True,  # noqa: E712
            or_(
                Form.workflow_id == workflow_id,
                Form.launch_workflow_id == workflow_id,
            )
        )
        form_result = await self.db.execute(form_stmt)
        forms = form_result.scalars().all()

        for form in forms:
            ref_types = []
            if form.workflow_id == workflow_id:
                ref_types.append("workflow")
            if form.launch_workflow_id == workflow_id:
                ref_types.append("launch_workflow")

            affected.append({
                "entity_type": "form",
                "id": str(form.id),
                "name": form.name,
                "reference_type": ", ".join(ref_types),
            })

        # Find form fields that use this workflow as a data provider
        field_stmt = select(FormField).where(
            FormField.data_provider_id == UUID_type(workflow_id)
        )
        field_result = await self.db.execute(field_stmt)
        form_fields = field_result.scalars().all()

        # Get unique form IDs from fields and fetch form names
        form_ids_from_fields = {field.form_id for field in form_fields}
        for form_id in form_ids_from_fields:
            # Skip if we already have this form
            if any(e["entity_type"] == "form" and e["id"] == str(form_id) for e in affected):
                continue

            form_stmt = select(Form).where(Form.id == form_id)
            form_result = await self.db.execute(form_stmt)
            form = form_result.scalar_one_or_none()
            if form:
                affected.append({
                    "entity_type": "form",
                    "id": str(form.id),
                    "name": form.name,
                    "reference_type": "data_provider",
                })

        # Find agents that use this workflow as a tool
        agent_stmt = (
            select(Agent)
            .join(AgentTool, Agent.id == AgentTool.agent_id)
            .where(
                Agent.is_active == True,  # noqa: E712
                AgentTool.workflow_id == UUID_type(workflow_id),
            )
        )
        agent_result = await self.db.execute(agent_stmt)
        agents = agent_result.scalars().all()

        for agent in agents:
            affected.append({
                "entity_type": "agent",
                "id": str(agent.id),
                "name": agent.name,
                "reference_type": "tool",
            })

        # Find apps that reference this workflow
        # Apps use a versioned page/component structure:
        # - AppPage.launch_workflow_id references workflows
        # - AppComponent.props may contain workflow_id references
        from src.models.orm.applications import AppPage, AppComponent

        try:
            workflow_uuid = UUID_type(workflow_id)
        except ValueError:
            workflow_uuid = None

        if workflow_uuid:
            # Check pages with this workflow as launch_workflow_id
            page_stmt = select(AppPage).where(AppPage.launch_workflow_id == workflow_uuid)
            page_result = await self.db.execute(page_stmt)
            pages = page_result.scalars().all()

            # Track which apps we've already added
            added_app_ids: set[UUID_type] = set()
            for page in pages:
                if page.application_id not in added_app_ids:
                    # Get the app to include its name
                    app_stmt = select(Application).where(Application.id == page.application_id)
                    app_result = await self.db.execute(app_stmt)
                    app = app_result.scalar_one_or_none()
                    if app:
                        affected.append({
                            "entity_type": "app",
                            "id": str(app.id),
                            "name": app.name,
                            "reference_type": "page_launch_workflow",
                        })
                        added_app_ids.add(page.application_id)

        return affected

    async def _detect_pending_deactivations(
        self,
        path: str,
        new_function_names: set[str],
        new_decorator_info: dict[str, tuple[str, str]],  # function_name -> (decorator_type, display_name)
    ) -> tuple[list[PendingDeactivationInfo], list[AvailableReplacementInfo]]:
        """
        Detect workflows that would be deactivated by saving a file.

        Compares existing active workflows at this path against the new
        function names found in the file content.

        Args:
            path: File path being saved
            new_function_names: Set of function names with decorators in new content
            new_decorator_info: Mapping of function_name to (decorator_type, display_name)

        Returns:
            Tuple of (pending_deactivations, available_replacements)
        """
        from src.models import Workflow, Execution

        pending_deactivations: list[PendingDeactivationInfo] = []
        available_replacements: list[AvailableReplacementInfo] = []

        # Get all active workflows at this path
        stmt = select(Workflow).where(
            Workflow.path == path,
            Workflow.is_active == True,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        existing_workflows = list(result.scalars().all())

        # Find workflows that would be deactivated
        existing_function_names = {wf.function_name for wf in existing_workflows}

        for wf in existing_workflows:
            if wf.function_name not in new_function_names:
                # This workflow would be deactivated

                # Check for execution history
                # Note: Executions are linked by workflow_name, not workflow_id
                exec_stmt = (
                    select(Execution)
                    .where(Execution.workflow_name == wf.function_name)
                    .order_by(Execution.started_at.desc())
                    .limit(1)
                )
                exec_result = await self.db.execute(exec_stmt)
                last_exec = exec_result.scalar_one_or_none()

                # Find affected entities
                affected_entities = await self._find_affected_entities(str(wf.id))

                pending_deactivations.append(PendingDeactivationInfo(
                    id=str(wf.id),
                    name=wf.name,
                    function_name=wf.function_name,
                    path=wf.path,
                    description=wf.description,
                    decorator_type=wf.type or "workflow",
                    has_executions=last_exec is not None,
                    last_execution_at=last_exec.started_at.isoformat() if last_exec else None,
                    schedule=wf.schedule,
                    endpoint_enabled=wf.endpoint_enabled or False,
                    affected_entities=affected_entities,
                ))

        # Find available replacements (new functions not in existing)
        if pending_deactivations:
            new_only_functions = new_function_names - existing_function_names

            for func_name in new_only_functions:
                decorator_type, display_name = new_decorator_info.get(
                    func_name, ("workflow", func_name)
                )

                # Calculate best similarity score against any pending deactivation
                best_score = 0.0
                for pd in pending_deactivations:
                    score = self._compute_similarity(pd.function_name, func_name)
                    best_score = max(best_score, score)

                # Only include if there's some similarity (threshold 0.2)
                if best_score >= 0.2:
                    available_replacements.append(AvailableReplacementInfo(
                        function_name=func_name,
                        name=display_name,
                        decorator_type=decorator_type,
                        similarity_score=round(best_score, 2),
                    ))

            # Sort by similarity descending
            available_replacements.sort(key=lambda x: x.similarity_score, reverse=True)

        return pending_deactivations, available_replacements

    async def _apply_workflow_replacements(
        self,
        replacements: dict[str, str],
    ) -> None:
        """
        Apply workflow identity replacements.

        For each mapping of old_workflow_id -> new_function_name, update the
        existing workflow record to use the new function name while preserving
        the ID (and thus execution history, schedules, etc.).

        Args:
            replacements: Mapping of workflow_id -> new_function_name
        """
        from src.models import Workflow

        for old_id, new_function_name in replacements.items():
            try:
                workflow_uuid = UUID_type(old_id)
            except ValueError:
                logger.warning(f"Invalid workflow ID in replacement: {old_id}")
                continue

            # Update the workflow's function_name
            # The rest of the metadata will be updated by the indexing pass
            stmt = (
                update(Workflow)
                .where(Workflow.id == workflow_uuid)
                .values(function_name=new_function_name)
            )
            await self.db.execute(stmt)
            logger.info(f"Applied replacement: workflow {old_id} -> function {new_function_name}")

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

        # Route based on entity type - platform entities are stored in the database
        if file_record is not None and file_record.entity_id is not None:
            entity_type = file_record.entity_type
            entity_id = file_record.entity_id

            # Workflow: fetch code column
            if entity_type == "workflow":
                workflow_stmt = select(Workflow).where(Workflow.id == entity_id)
                workflow_result = await self.db.execute(workflow_stmt)
                workflow = workflow_result.scalar_one_or_none()

                if workflow is not None and workflow.code is not None:
                    return workflow.code.encode("utf-8"), file_record
                # Fall through to S3 if workflow not found or code is None

            # Form: serialize to JSON
            elif entity_type == "form":
                form_stmt = (
                    select(Form)
                    .options(selectinload(Form.fields))
                    .where(Form.id == entity_id)
                )
                form_result = await self.db.execute(form_stmt)
                form = form_result.scalar_one_or_none()

                if form is not None:
                    return _serialize_form_to_json(form), file_record
                raise FileNotFoundError(f"Form not found: {entity_id}")

            # App: return draft_definition as JSON
            elif entity_type == "app":
                app_stmt = select(Application).where(Application.id == entity_id)
                app_result = await self.db.execute(app_stmt)
                app = app_result.scalar_one_or_none()

                if app is not None:
                    definition = app.draft_definition if app.draft_definition else {}
                    return json.dumps(definition, indent=2).encode("utf-8"), file_record
                raise FileNotFoundError(f"Application not found: {entity_id}")

            # Agent: serialize to JSON
            elif entity_type == "agent":
                agent_stmt = select(Agent).where(Agent.id == entity_id)
                agent_result = await self.db.execute(agent_stmt)
                agent = agent_result.scalar_one_or_none()

                if agent is not None:
                    return _serialize_agent_to_json(agent), file_record
                raise FileNotFoundError(f"Agent not found: {entity_id}")

        # Default: fetch from S3 (entity_type is NULL or unknown)
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
        platform_entity_type = self._detect_platform_entity_type(path, content)
        is_platform_entity = platform_entity_type is not None

        # Only write to S3 for regular files (not platform entities)
        # Platform entity content is stored in DB tables via _extract_metadata
        if not is_platform_entity:
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

        # Extract metadata for workflows/forms/agents
        (
            final_content,
            content_modified,
            needs_indexing,
            workflow_id_conflicts,
            diagnostics,
            pending_deactivations,
            available_replacements,
        ) = await self._extract_metadata(path, content, force_deactivation, replacements)

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
            # Update form.file_path
            stmt = update(Form).where(
                Form.id == entity_id
            ).values(
                file_path=new_path,
                updated_at=now,
            )
            await self.db.execute(stmt)
            logger.info(f"Updated form {entity_id} path: {old_path} -> {new_path}")

        elif entity_type == "app" and entity_id:
            # Update application (no file_path column, apps are in applications table)
            # Apps don't have a file_path column - they're stored by ID
            # Nothing to update in the entity table
            logger.info(f"App {entity_id} path update: {old_path} -> {new_path}")

        elif entity_type == "agent" and entity_id:
            # Update agent.file_path
            stmt = update(Agent).where(
                Agent.id == entity_id
            ).values(
                file_path=new_path,
                updated_at=now,
            )
            await self.db.execute(stmt)
            logger.info(f"Updated agent {entity_id} path: {old_path} -> {new_path}")

        else:
            # Regular file: copy in S3
            async with self._get_s3_client() as s3:
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

        # Update Redis cache
        cache = get_workspace_cache()
        await cache.set_file_state(old_path, content_hash=None, is_deleted=True)
        await cache.set_file_state(new_path, content_hash=file_record.content_hash, is_deleted=False)

        # Publish events
        try:
            from src.core.pubsub import publish_workspace_file_delete, publish_workspace_file_change
            await publish_workspace_file_delete(old_path)
            await publish_workspace_file_change(new_path)
        except Exception as e:
            logger.warning(f"Failed to publish workspace file move events: {e}")

        # Refresh the record to get updated values
        await self.db.refresh(file_record)
        logger.info(f"File moved: {old_path} -> {new_path}")
        return file_record

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

        # Delete children from S3 (regular files only) and soft-delete in DB
        # Platform entities (entity_type is not None) have content in DB, not S3
        async with self._get_s3_client() as s3:
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
        cache = get_workspace_cache()

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

            # Update Redis cache so watcher has correct state
            await cache.set_file_state(rel_path, content_hash, is_deleted=False)

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
        from sqlalchemy import delete

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
            await self.download_workspace(local_path)
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
                    workflow = await self._get_workflow_by_id(form.workflow_id)
                    if not workflow:
                        # Try to find by name
                        match = await self._find_workflow_match(form.workflow_id)
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
                    workflow = await self._get_workflow_by_id(form.launch_workflow_id)
                    if not workflow:
                        match = await self._find_workflow_match(form.launch_workflow_id)
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
                        dp = await self._get_workflow_by_id(str(field.data_provider_id))
                        if not dp:
                            match = await self._find_workflow_match(str(field.data_provider_id))
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
                    workflow = await self._get_workflow_by_id(str(agent_tool.workflow_id))
                    if not workflow:
                        match = await self._find_workflow_match(str(agent_tool.workflow_id))
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
                    delegated_agent = await self._get_agent_by_id(str(delegation.child_agent_id))
                    if not delegated_agent:
                        match = await self._find_agent_match(str(delegation.child_agent_id))
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
        Clear all temp directories before reindex.

        Standard paths (all under /tmp/bifrost/):
        - /tmp/bifrost/workspace - Main workspace files
        - /tmp/bifrost/temp - SDK temp files
        - /tmp/bifrost/uploads - Uploaded form files
        """
        import shutil

        from src.core.workspace_sync import WORKSPACE_PATH, TEMP_PATH, UPLOADS_PATH

        for path in [WORKSPACE_PATH, TEMP_PATH, UPLOADS_PATH]:
            try:
                if path.exists():
                    shutil.rmtree(path)
                path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Cleared temp directory: {path}")
            except Exception as e:
                logger.warning(f"Failed to clear {path}: {e}")

    async def _get_workflow_by_id(self, workflow_id: str) -> "Workflow | None":
        """Get a workflow by its ID (string UUID)."""
        from uuid import UUID as UUID_type
        from src.models import Workflow

        try:
            workflow_uuid = UUID_type(workflow_id)
        except ValueError:
            return None

        result = await self.db.execute(
            select(Workflow).where(Workflow.id == workflow_uuid)
        )
        return result.scalar_one_or_none()

    async def _get_agent_by_id(self, agent_id: str) -> "Agent | None":
        """Get an agent by its ID (string UUID)."""
        from uuid import UUID as UUID_type
        from src.models import Agent

        try:
            agent_uuid = UUID_type(agent_id)
        except ValueError:
            return None

        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_uuid)
        )
        return result.scalar_one_or_none()

    async def _find_workflow_match(self, stale_id: str) -> "Workflow | None":
        """
        Try to find a workflow that matches a stale/invalid ID.

        Strategy:
        1. Check if stale_id is actually a workflow name (legacy format)

        Args:
            stale_id: The ID or name that could not be resolved

        Returns:
            Matching Workflow if found, None otherwise
        """
        from src.models import Workflow

        # 1. Check if stale_id is a workflow name
        result = await self.db.execute(
            select(Workflow).where(
                Workflow.name == stale_id,
                Workflow.is_active == True,  # noqa: E712
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow:
            return workflow

        return None

    async def _find_agent_match(self, stale_id: str) -> "Agent | None":
        """
        Try to find an agent that matches a stale/invalid ID.

        Strategy:
        1. Check if stale_id is actually an agent name (legacy format)

        Args:
            stale_id: The ID or name that could not be resolved

        Returns:
            Matching Agent if found, None otherwise
        """
        from src.models import Agent

        # 1. Check if stale_id is an agent name
        result = await self.db.execute(
            select(Agent).where(
                Agent.name == stale_id,
                Agent.is_active == True,  # noqa: E712
            )
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent

        return None

    async def _extract_metadata(
        self,
        path: str,
        content: bytes,
        force_deactivation: bool = False,
        replacements: dict[str, str] | None = None,
    ) -> tuple[
        bytes,
        bool,
        bool,
        list[WorkflowIdConflictInfo] | None,
        list[FileDiagnosticInfo],
        list[PendingDeactivationInfo] | None,
        list[AvailableReplacementInfo] | None,
    ]:
        """
        Extract workflow/form/agent metadata from file content.

        Called at write time to keep registry in sync.

        Args:
            path: Relative file path
            content: File content bytes
            force_deactivation: Skip deactivation protection for Python files
            replacements: Map of workflow_id -> new_function_name for identity transfer

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics,
                      pending_deactivations, available_replacements) where:
            - final_content: The content (unchanged for Python files)
            - content_modified: True if the content was modified (for forms/agents with ID alignment)
            - needs_indexing: Always False (legacy field)
            - conflicts: Always None (legacy field)
            - diagnostics: List of file issues detected during indexing
            - pending_deactivations: Workflows that would be deactivated (Python files only)
            - available_replacements: New functions that could replace deactivated workflows
        """
        try:
            if path.endswith(".py"):
                return await self._index_python_file(
                    path, content, force_deactivation, replacements
                )
            elif path.endswith(".form.json"):
                result = await self._index_form(path, content)
                # Extend result with None for deactivation fields
                return (*result, None, None)
            elif path.endswith(".app.json"):
                result = await self._index_app(path, content)
                return (*result, None, None)
            elif path.endswith(".agent.json"):
                result = await self._index_agent(path, content)
                return (*result, None, None)
        except Exception as e:
            # Log but don't fail the write
            logger.warning(f"Failed to extract metadata from {path}: {e}")

        return content, False, False, None, [], None, None

    async def _index_python_file(
        self,
        path: str,
        content: bytes,
        force_deactivation: bool = False,
        replacements: dict[str, str] | None = None,
    ) -> tuple[
        bytes,
        bool,
        bool,
        list[WorkflowIdConflictInfo] | None,
        list[FileDiagnosticInfo],
        list[PendingDeactivationInfo] | None,
        list[AvailableReplacementInfo] | None,
    ]:
        """
        Extract and index workflows/providers from Python file.

        Uses AST-based parsing to extract metadata from @workflow and
        @data_provider decorators without importing the module.
        Also updates workspace_files.is_workflow/is_data_provider flags.

        IDs are DB-only. Workflows without IDs in decorators will have IDs
        generated in the database using path + function_name as the identity key.

        Includes deactivation protection: if a save would deactivate workflows,
        returns early with pending_deactivations unless force_deactivation=True.

        Args:
            path: File path
            content: File content
            force_deactivation: If True, skip deactivation protection
            replacements: Map of workflow_id -> new_function_name for identity transfer

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics,
                      pending_deactivations, available_replacements) where:
            - final_content: The content (unchanged)
            - content_modified: Always False (no file modifications)
            - needs_indexing: Always False (legacy field)
            - conflicts: Always None (legacy field)
            - diagnostics: List of file issues detected during indexing
            - pending_deactivations: Workflows that would be deactivated (None if force or none found)
            - available_replacements: New functions that could replace deactivated workflows
        """
        from src.models import Workflow  # Data providers are in workflows table with type='data_provider'

        content_str = content.decode("utf-8", errors="replace")
        final_content = content
        content_modified = False
        needs_indexing = False
        workflow_id_conflicts: list[WorkflowIdConflictInfo] | None = None
        diagnostics: list[FileDiagnosticInfo] = []
        pending_deactivations: list[PendingDeactivationInfo] | None = None
        available_replacements: list[AvailableReplacementInfo] | None = None

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
            return (
                final_content, content_modified, needs_indexing, workflow_id_conflicts, diagnostics,
                pending_deactivations, available_replacements
            )

        now = datetime.utcnow()

        # === PHASE 1: Pre-scan for deactivation detection ===
        # First pass: collect all decorated function names and their info
        new_function_names: set[str] = set()
        new_decorator_info: dict[str, tuple[str, str]] = {}  # func_name -> (decorator_type, display_name)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if not decorator_info:
                    continue
                decorator_name, kwargs = decorator_info
                if decorator_name in ("workflow", "tool", "data_provider"):
                    func_name = node.name
                    new_function_names.add(func_name)
                    display_name = kwargs.get("name") or func_name
                    # Map decorator type
                    if decorator_name == "tool":
                        dtype = "tool"
                    elif decorator_name == "data_provider":
                        dtype = "data_provider"
                    else:
                        dtype = "workflow"
                    new_decorator_info[func_name] = (dtype, display_name)

        # Apply replacements first if provided
        # This transfers workflow identity (preserves ID, execution history, schedules)
        # by updating the existing record's function_name
        if replacements:
            await self._apply_workflow_replacements(replacements)

        # Check for pending deactivations (unless forced)
        # This runs AFTER replacements so transferred workflows are not flagged
        if not force_deactivation:
            pending, replacements_available = await self._detect_pending_deactivations(
                path, new_function_names, new_decorator_info
            )
            if pending:
                # Return early - caller should raise 409
                return (
                    final_content, content_modified, needs_indexing, workflow_id_conflicts, diagnostics,
                    pending, replacements_available
                )

        # If force_deactivation is True, deactivate workflows that are no longer in the file
        # This happens after replacements are applied, so transferred identities are preserved
        if force_deactivation:
            # Get workflows at this path that are not in the new content
            existing_stmt = (
                select(Workflow)
                .where(
                    Workflow.path == path,
                    Workflow.is_active == True,  # noqa: E712
                )
            )
            existing_result = await self.db.execute(existing_stmt)
            existing_workflows = existing_result.scalars().all()

            for wf in existing_workflows:
                if wf.function_name not in new_function_names:
                    # Deactivate this workflow
                    deactivate_stmt = (
                        update(Workflow)
                        .where(Workflow.id == wf.id)
                        .values(is_active=False)
                    )
                    await self.db.execute(deactivate_stmt)
                    logger.info(f"Deactivated workflow: {wf.name} ({wf.function_name}) at {path}")

        # === PHASE 2: Main indexing loop ===
        # Track what decorators we find to update workspace_files
        found_workflow = False
        found_data_provider = False
        # Track the primary entity for this file (first workflow or data_provider found)
        # Used to set entity_type and entity_id in workspace_files
        primary_entity_type: str | None = None
        primary_entity_id: str | None = None

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                decorator_info = self._parse_decorator(decorator)
                if not decorator_info:
                    continue

                decorator_name, kwargs = decorator_info

                if decorator_name in ("workflow", "tool"):
                    found_workflow = True

                    # @tool decorator is an alias for @workflow(is_tool=True)
                    # If using @tool, force is_tool=True
                    if decorator_name == "tool":
                        kwargs["is_tool"] = True

                    # function_name is the actual Python function name (unique per file)
                    function_name = node.name

                    # Phase 6 (DB-first): IDs are DB-only.
                    # If ID is in decorator, use it. Otherwise, look up by path + function_name
                    # or generate a new one.
                    from uuid import UUID as UUID_type, uuid4
                    workflow_id_str = kwargs.get("id")
                    workflow_uuid: UUID_type

                    if workflow_id_str:
                        # ID in decorator - validate and use it
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
                    else:
                        # No ID in decorator - look up existing workflow by path + function_name
                        # This is the DB-first approach: identities are in the database
                        stmt = select(Workflow).where(
                            Workflow.path == path,
                            Workflow.function_name == function_name
                        )
                        result = await self.db.execute(stmt)
                        existing_workflow = result.scalar_one_or_none()

                        if existing_workflow:
                            # Reuse existing ID
                            workflow_uuid = existing_workflow.id
                            logger.debug(
                                f"Workflow {function_name} in {path} has no ID in decorator, "
                                f"reusing existing DB ID: {workflow_uuid}"
                            )
                        else:
                            # Generate new ID
                            workflow_uuid = uuid4()
                            logger.info(
                                f"Workflow {function_name} in {path} has no ID, "
                                f"generating new DB ID: {workflow_uuid}"
                            )

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
                    timeout_seconds = kwargs.get("timeout_seconds", 1800)

                    # Determine type based on is_tool flag
                    workflow_type = "tool" if is_tool else "workflow"

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    # workflow_name is the display name from decorator (can have duplicates)
                    # function_name was set earlier and is the actual Python function name

                    # Use workflow ID as the conflict key for upsert
                    # workflow_uuid was resolved above (from decorator, existing DB record, or generated)
                    # Compute code hash for change detection
                    code_hash = hashlib.sha256(content).hexdigest()

                    stmt = insert(Workflow).values(
                        id=workflow_uuid,
                        name=workflow_name,
                        function_name=function_name,
                        path=path,
                        code=content_str,
                        code_hash=code_hash,
                        description=description,
                        category=category,
                        parameters_schema=parameters_schema,
                        tags=tags,
                        schedule=schedule,
                        endpoint_enabled=endpoint_enabled,
                        allowed_methods=allowed_methods,
                        execution_mode=execution_mode,
                        type=workflow_type,
                        tool_description=tool_description,
                        timeout_seconds=timeout_seconds,
                        time_saved=time_saved,
                        value=value,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.id],
                        set_={
                            "name": workflow_name,
                            "function_name": function_name,
                            "path": path,
                            "code": content_str,
                            "code_hash": code_hash,
                            "description": description,
                            "category": category,
                            "parameters_schema": parameters_schema,
                            "tags": tags,
                            "schedule": schedule,
                            "endpoint_enabled": endpoint_enabled,
                            "allowed_methods": allowed_methods,
                            "execution_mode": execution_mode,
                            "type": workflow_type,
                            "tool_description": tool_description,
                            "timeout_seconds": timeout_seconds,
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

                    # Set primary entity for workspace_files (first one wins)
                    if primary_entity_type is None:
                        primary_entity_type = "workflow"
                        primary_entity_id = str(workflow.id)

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
                    category = kwargs.get("category", "General")
                    tags = kwargs.get("tags", [])
                    timeout_seconds = kwargs.get("timeout_seconds", 300)
                    cache_ttl_seconds = kwargs.get("cache_ttl_seconds", 300)

                    # Extract parameters from function signature
                    parameters_schema = self._extract_parameters_from_ast(node)

                    # function_name is the actual Python function name (unique per file)
                    # provider_name is the display name from decorator (can have duplicates)
                    function_name = node.name

                    # Data providers are stored in workflows table with type='data_provider'
                    # Compute code hash for change detection
                    dp_code_hash = hashlib.sha256(content).hexdigest()

                    stmt = insert(Workflow).values(
                        name=provider_name,
                        function_name=function_name,
                        path=path,
                        code=content_str,
                        code_hash=dp_code_hash,
                        description=description,
                        category=category,
                        tags=tags,
                        parameters_schema=parameters_schema,
                        type="data_provider",
                        timeout_seconds=timeout_seconds,
                        cache_ttl_seconds=cache_ttl_seconds,
                        is_active=True,
                        last_seen_at=now,
                    ).on_conflict_do_update(
                        index_elements=[Workflow.path, Workflow.function_name],
                        set_={
                            "name": provider_name,
                            "code": content_str,
                            "code_hash": dp_code_hash,
                            "description": description,
                            "category": category,
                            "tags": tags,
                            "parameters_schema": parameters_schema,
                            "type": "data_provider",
                            "timeout_seconds": timeout_seconds,
                            "cache_ttl_seconds": cache_ttl_seconds,
                            "is_active": True,
                            "last_seen_at": now,
                            "updated_at": now,
                        },
                    ).returning(Workflow)
                    dp_result = await self.db.execute(stmt)
                    data_provider = dp_result.scalar_one()
                    logger.debug(f"Indexed data provider: {provider_name} ({function_name}) from {path}")

                    # Set primary entity for workspace_files (first one wins)
                    # Note: data_provider is stored in workflows table with type='data_provider'
                    if primary_entity_type is None:
                        primary_entity_type = "workflow"  # Use 'workflow' since it's in workflows table
                        primary_entity_id = str(data_provider.id)

        # Update workspace_files with detection results and entity routing
        from uuid import UUID as UUID_type
        update_values: dict[str, Any] = {
            "is_workflow": found_workflow,
            "is_data_provider": found_data_provider,
        }
        # Set entity routing for platform entities
        if primary_entity_type and primary_entity_id:
            update_values["entity_type"] = primary_entity_type
            update_values["entity_id"] = UUID_type(primary_entity_id)
        else:
            # Clear entity routing if no platform entities found (e.g., file became regular)
            update_values["entity_type"] = None
            update_values["entity_id"] = None

        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(**update_values)
        await self.db.execute(stmt)

        return (
            final_content, content_modified, needs_indexing, workflow_id_conflicts, diagnostics,
            pending_deactivations, available_replacements
        )

    def _parse_decorator(self, decorator: ast.AST) -> tuple[str, dict[str, Any]] | None:
        """
        Parse a decorator AST node to extract name and keyword arguments.

        Returns:
            Tuple of (decorator_name, kwargs_dict) or None if not a workflow/provider decorator
        """
        # Handle @workflow (no parentheses)
        if isinstance(decorator, ast.Name):
            if decorator.id in ("workflow", "tool", "data_provider"):
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

            if decorator_name not in ("workflow", "tool", "data_provider"):
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

    async def _index_form(
        self, path: str, content: bytes
    ) -> tuple[bytes, bool, bool, list[WorkflowIdConflictInfo] | None, list[FileDiagnosticInfo]]:
        """
        Parse and index form from .form.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID and writes it back to the file.

        Updates form definition (name, description, workflow_id, form_schema, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT on primary key (id) to update existing forms.

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics)
        """
        import json
        from uuid import UUID, uuid4
        from src.models import Form, FormField as FormFieldORM

        content_modified = False
        final_content = content
        diagnostics: list[FileDiagnosticInfo] = []

        try:
            form_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in form file: {path}")
            return content, False, False, None, []

        name = form_data.get("name")
        if not name:
            logger.warning(f"Form file missing name: {path}")
            return content, False, False, None, []

        # Use ID from JSON if present (for API-created forms), otherwise generate and inject
        form_id_str = form_data.get("id")
        if form_id_str:
            try:
                form_id = UUID(form_id_str)
            except ValueError:
                logger.warning(f"Invalid form ID in {path}: {form_id_str}")
                form_id = uuid4()
                form_data["id"] = str(form_id)
                content_modified = True
        else:
            # Generate new ID and inject it into the file
            form_id = uuid4()
            form_data["id"] = str(form_id)
            content_modified = True
            logger.info(f"Injecting ID {form_id} into form file: {path}")

        # Pre-check: Does a form already exist at this file_path with a different ID?
        # This prevents "duplicate key" errors on the file_path unique constraint
        # and ensures we preserve the DB's ID (which may have FK references)
        existing_form_stmt = select(Form).where(Form.file_path == path)
        existing_form_result = await self.db.execute(existing_form_stmt)
        existing_form = existing_form_result.scalar_one_or_none()

        if existing_form and existing_form.id != form_id:
            # ID mismatch! The DB has a different ID than the JSON file.
            # Use DB's ID to preserve FK references (form_role_assignments, etc.)
            old_file_id = form_id
            form_id = existing_form.id
            form_data["id"] = str(form_id)
            content_modified = True
            logger.warning(
                f"Form at {path} had ID mismatch. "
                f"File had {old_file_id}, DB has {form_id}. Using DB ID."
            )
            diagnostics.append(FileDiagnosticInfo(
                severity="warning",
                message=f"ID corrected: file had {old_file_id}, using DB ID {form_id}",
                line=None,
                column=None,
            ))

        # DB-first: Forms are database entities. We update the DB record but do NOT
        # write back to S3 or filesystem. The DB is the source of truth.
        if content_modified:
            final_content = json.dumps(form_data, indent=2).encode("utf-8")

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

        # Update workspace_files with entity routing
        from uuid import UUID as UUID_type
        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="form",
            entity_id=form_id if isinstance(form_id, UUID_type) else UUID_type(form_id),
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed form: {name} from {path}")
        return final_content, content_modified, True, None, diagnostics

    async def _index_app(
        self, path: str, content: bytes
    ) -> tuple[bytes, bool, bool, list[WorkflowIdConflictInfo] | None, list[FileDiagnosticInfo]]:
        """
        Parse and index application from .app.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Updates app draft_definition in the applications table.

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics)
        """
        import json
        from uuid import UUID, uuid4

        content_modified = False
        final_content = content
        diagnostics: list[FileDiagnosticInfo] = []

        try:
            app_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in app file: {path}")
            return content, False, False, None, []

        name = app_data.get("name")
        if not name:
            logger.warning(f"App file missing name: {path}")
            return content, False, False, None, []

        # Use ID from JSON if present, otherwise generate new
        app_id_str = app_data.get("id")
        if app_id_str:
            try:
                app_id = UUID(app_id_str)
            except ValueError:
                logger.warning(f"Invalid app ID in {path}: {app_id_str}")
                app_id = uuid4()
                app_data["id"] = str(app_id)
                content_modified = True
        else:
            app_id = uuid4()
            app_data["id"] = str(app_id)
            content_modified = True
            logger.info(f"Injecting ID {app_id} into app file: {path}")

        from src.models.orm.applications import Application

        now = datetime.utcnow()

        # Generate slug from name if not provided
        slug = app_data.get("slug")
        if not slug:
            slug = name.lower().replace(" ", "-").replace("_", "-")
            # Remove non-alphanumeric characters except hyphens
            slug = "".join(c for c in slug if c.isalnum() or c == "-")

        # Build definition from app_data (exclude top-level metadata)
        definition = {
            k: v for k, v in app_data.items()
            if k not in ("id", "name", "slug", "description", "icon", "organization_id",
                         "created_at", "updated_at", "created_by")
        }

        if content_modified:
            final_content = json.dumps(app_data, indent=2).encode("utf-8")

        # Upsert application
        stmt = insert(Application).values(
            id=app_id,
            name=name,
            slug=slug,
            description=app_data.get("description"),
            icon=app_data.get("icon"),
            draft_definition=definition,
            created_by="file_sync",
        ).on_conflict_do_update(
            index_elements=[Application.id],
            set_={
                "name": name,
                "slug": slug,
                "description": app_data.get("description"),
                "icon": app_data.get("icon"),
                "draft_definition": definition,
                "updated_at": now,
            },
        )
        await self.db.execute(stmt)

        # Update workspace_files with entity routing
        from uuid import UUID as UUID_type
        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="app",
            entity_id=app_id if isinstance(app_id, UUID_type) else UUID_type(str(app_id)),
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed app: {name} from {path}")
        return final_content, content_modified, True, None, diagnostics

    async def _index_agent(
        self, path: str, content: bytes
    ) -> tuple[bytes, bool, bool, list[WorkflowIdConflictInfo] | None, list[FileDiagnosticInfo]]:
        """
        Parse and index agent from .agent.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Updates agent definition (name, description, system_prompt, tools, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT to update existing agents.

        Returns:
            Tuple of (final_content, content_modified, needs_indexing, conflicts, diagnostics)
        """
        import json
        from uuid import UUID, uuid4
        from src.models.orm import Agent, AgentTool, AgentDelegation

        content_modified = False
        final_content = content
        diagnostics: list[FileDiagnosticInfo] = []

        try:
            agent_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in agent file: {path}")
            return content, False, False, None, []

        name = agent_data.get("name")
        if not name:
            logger.warning(f"Agent file missing name: {path}")
            return content, False, False, None, []

        system_prompt = agent_data.get("system_prompt")
        if not system_prompt:
            logger.warning(f"Agent file missing system_prompt: {path}")
            return content, False, False, None, []

        # Use ID from JSON if present (for API-created agents), otherwise generate new
        agent_id_str = agent_data.get("id")
        if agent_id_str:
            try:
                agent_id = UUID(agent_id_str)
            except ValueError:
                logger.warning(f"Invalid agent ID in {path}: {agent_id_str}")
                agent_id = uuid4()
                agent_data["id"] = str(agent_id)
                content_modified = True
        else:
            agent_id = uuid4()
            agent_data["id"] = str(agent_id)
            content_modified = True
            logger.info(f"Injecting ID {agent_id} into agent file: {path}")

        # Pre-check: Does an agent already exist at this file_path with a different ID?
        # This prevents "duplicate key" errors on the file_path unique constraint
        # and ensures we preserve the DB's ID (which may have FK references)
        existing_agent_stmt = select(Agent).where(Agent.file_path == path)
        existing_agent_result = await self.db.execute(existing_agent_stmt)
        existing_agent = existing_agent_result.scalar_one_or_none()

        if existing_agent and existing_agent.id != agent_id:
            # ID mismatch! The DB has a different ID than the JSON file.
            # Use DB's ID to preserve FK references (agent_tools, delegations, etc.)
            old_file_id = agent_id
            agent_id = existing_agent.id
            agent_data["id"] = str(agent_id)
            content_modified = True
            logger.warning(
                f"Agent at {path} had ID mismatch. "
                f"File had {old_file_id}, DB has {agent_id}. Using DB ID."
            )
            diagnostics.append(FileDiagnosticInfo(
                severity="warning",
                message=f"ID corrected: file had {old_file_id}, using DB ID {agent_id}",
                line=None,
                column=None,
            ))

        # DB-first: Agents are database entities. We update the DB record but do NOT
        # write back to S3 or filesystem. The DB is the source of truth.
        if content_modified:
            final_content = json.dumps(agent_data, indent=2).encode("utf-8")

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
            # Create new tool associations (with existence check to prevent FK violations)
            for tool_id_str in tool_ids:
                try:
                    workflow_id = UUID(tool_id_str)
                    # Check if workflow exists before creating FK relationship
                    workflow_exists = await self.db.execute(
                        select(Workflow.id).where(Workflow.id == workflow_id)
                    )
                    if workflow_exists.scalar_one_or_none():
                        self.db.add(AgentTool(agent_id=agent_id, workflow_id=workflow_id))
                    else:
                        logger.warning(f"Agent {name} references non-existent workflow {workflow_id}")
                        diagnostics.append(FileDiagnosticInfo(
                            severity="warning",
                            message=f"Tool workflow {workflow_id} not found - skipping",
                            line=None,
                            column=None,
                        ))
                except ValueError:
                    logger.warning(f"Invalid tool_id in agent {name}: {tool_id_str}")

        # Sync delegated agent associations
        delegated_agent_ids = agent_data.get("delegated_agent_ids", [])
        if isinstance(delegated_agent_ids, list):
            # Delete existing delegations
            await self.db.execute(
                delete(AgentDelegation).where(AgentDelegation.parent_agent_id == agent_id)
            )
            # Create new delegations (with existence check to prevent FK violations)
            for child_id_str in delegated_agent_ids:
                try:
                    child_agent_id = UUID(child_id_str)
                    # Check if child agent exists before creating FK relationship
                    agent_exists = await self.db.execute(
                        select(Agent.id).where(Agent.id == child_agent_id)
                    )
                    if agent_exists.scalar_one_or_none():
                        self.db.add(AgentDelegation(parent_agent_id=agent_id, child_agent_id=child_agent_id))
                    else:
                        logger.warning(f"Agent {name} references non-existent agent {child_agent_id}")
                        diagnostics.append(FileDiagnosticInfo(
                            severity="warning",
                            message=f"Delegated agent {child_agent_id} not found - skipping",
                            line=None,
                            column=None,
                        ))
                except ValueError:
                    logger.warning(f"Invalid delegated_agent_id in agent {name}: {child_id_str}")

        # Update workspace_files with entity routing
        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="agent",
            entity_id=agent_id,
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed agent: {name} from {path}")
        return final_content, content_modified, True, None, diagnostics

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
        from src.models import Workflow, Form  # Data providers are in workflows table with type='data_provider'
        from src.models.orm import Agent

        # Get workflows being removed (to clean up endpoints)
        result = await self.db.execute(
            select(Workflow).where(Workflow.path == path, Workflow.endpoint_enabled == True)  # noqa: E712
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
        # Mark workflows and data providers from this file as inactive
        # (Data providers are now in the workflows table with type='data_provider')
        await self.db.execute(
            update(Workflow).where(Workflow.path == path).values(is_active=False)
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
