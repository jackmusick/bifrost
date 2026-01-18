"""
Virtual File Provider for GitHub Sync.

Platform entities (apps, forms, agents) don't exist in the `workspace_files` table -
they live in their own database tables. The VirtualFileProvider serializes these
entities on-the-fly so they can participate in GitHub sync.

Virtual files are generated from database entities with:
- Portable workflow refs (UUID -> path::function_name)
- Computed git blob SHA for fast comparison
- Standardized path patterns

Path patterns:
- Apps: apps/{app.id}.app.json
- Forms: forms/{form.id}.form.json
- Agents: agents/{agent.id}.agent.json
"""

import json
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Agent, Form
from src.models.orm.applications import Application, AppVersion
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.file_storage.indexers.agent import _serialize_agent_to_json
from src.services.file_storage.indexers.form import _serialize_form_to_json
from src.services.file_storage.ref_translation import build_workflow_ref_map

logger = logging.getLogger(__name__)

# Regex pattern for extracting UUID from filenames
# Matches: {uuid}.app.json, {uuid}.form.json, {uuid}.agent.json
UUID_FILENAME_PATTERN = re.compile(
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"\.(app|form|agent)\.json$"
)


@dataclass
class VirtualFile:
    """
    A virtual file representing a platform entity.

    Virtual files are generated on-the-fly from database entities (apps, forms, agents)
    and can participate in GitHub sync without being stored in workspace_files.

    Attributes:
        path: Virtual file path, e.g., "apps/{uuid}.app.json"
        entity_type: Type of entity - "app", "form", or "agent"
        entity_id: UUID of the entity
        content: Serialized JSON content as bytes (None if not yet computed)
        computed_sha: Git blob SHA of content (None if not yet computed)
    """

    path: str
    entity_type: str
    entity_id: str
    content: bytes | None = None
    computed_sha: str | None = None


@dataclass
class SerializationError:
    """
    Information about an entity that failed to serialize.

    Used to surface serialization failures in the sync preview so users can
    acknowledge and skip problematic entities.
    """

    entity_type: str  # "app", "form", or "agent"
    entity_id: str
    entity_name: str
    path: str  # Virtual file path (used as resolution key)
    error: str  # Human-readable error message


@dataclass
class VirtualFileResult:
    """
    Result of generating virtual files.

    Contains both successfully serialized files and any errors encountered.
    """

    files: list[VirtualFile]
    errors: list[SerializationError]


class VirtualFileProvider:
    """
    Provides virtual file representations of platform entities for GitHub sync.

    Platform entities (apps, forms, agents) are stored in their own database tables,
    not in workspace_files. This provider serializes them to JSON with portable
    workflow references so they can be synced to GitHub.

    Usage:
        provider = VirtualFileProvider(db)
        virtual_files = await provider.get_all_virtual_files()

        # Each virtual file has:
        # - path: e.g., "apps/abc123.app.json"
        # - entity_type: "app", "form", or "agent"
        # - entity_id: UUID string
        # - content: serialized JSON bytes
        # - computed_sha: git blob SHA for comparison
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the virtual file provider.

        Args:
            db: Async database session for querying entities
        """
        self.db = db

    async def get_all_virtual_files(self) -> VirtualFileResult:
        """
        Get all platform entities as virtual files.

        Retrieves all apps, forms, and agents from the database, serializes them
        to JSON with portable workflow refs, and returns them as VirtualFile objects
        with computed git SHAs. Also collects any serialization errors.

        Returns:
            VirtualFileResult containing files and any errors encountered
        """
        # Build workflow ref map for portable refs
        workflow_map = await build_workflow_ref_map(self.db)
        logger.debug(f"Built workflow ref map with {len(workflow_map)} entries")

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        # Get all entity types
        app_result = await self._get_app_files(workflow_map)
        form_result = await self._get_form_files(workflow_map)
        agent_result = await self._get_agent_files(workflow_map)

        virtual_files.extend(app_result.files)
        virtual_files.extend(form_result.files)
        virtual_files.extend(agent_result.files)

        errors.extend(app_result.errors)
        errors.extend(form_result.errors)
        errors.extend(agent_result.errors)

        logger.info(
            f"Generated {len(virtual_files)} virtual files: "
            f"{len(app_result.files)} apps, {len(form_result.files)} forms, "
            f"{len(agent_result.files)} agents, {len(errors)} errors"
        )

        return VirtualFileResult(files=virtual_files, errors=errors)

    async def _get_app_files(
        self, workflow_map: dict[str, str]
    ) -> VirtualFileResult:
        """
        Generate virtual files for all applications.

        Fetches all applications with their draft version files,
        serializes them to JSON.

        Args:
            workflow_map: Mapping of workflow UUID -> "path::function_name" (unused for apps)

        Returns:
            VirtualFileResult with files and any serialization errors
        """
        # Query apps with draft version and files eagerly loaded
        stmt = select(Application).options(
            selectinload(Application.draft_version_ref).selectinload(AppVersion.files)
        )
        result = await self.db.execute(stmt)
        apps = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for app in apps:
            virtual_path = f"apps/{app.id}.app.json"

            try:
                content = self._serialize_app_to_json(app)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=virtual_path,
                        entity_type="app",
                        entity_id=str(app.id),
                        content=content,
                        computed_sha=computed_sha,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to serialize app {app.id}: {e}")
                errors.append(
                    SerializationError(
                        entity_type="app",
                        entity_id=str(app.id),
                        entity_name=app.name,
                        path=virtual_path,
                        error=str(e),
                    )
                )

        return VirtualFileResult(files=virtual_files, errors=errors)

    async def _get_form_files(
        self, workflow_map: dict[str, str]
    ) -> VirtualFileResult:
        """
        Generate virtual files for all forms.

        Fetches all active forms with their fields relationship loaded,
        serializes them to JSON with portable workflow refs.

        Args:
            workflow_map: Mapping of workflow UUID -> "path::function_name"

        Returns:
            VirtualFileResult with files and any serialization errors
        """
        # Query forms with fields eagerly loaded
        stmt = (
            select(Form)
            .options(selectinload(Form.fields))
            .where(Form.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        forms = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for form in forms:
            virtual_path = f"forms/{form.id}.form.json"
            try:
                content = _serialize_form_to_json(form, workflow_map)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=virtual_path,
                        entity_type="form",
                        entity_id=str(form.id),
                        content=content,
                        computed_sha=computed_sha,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to serialize form {form.id}: {e}")
                errors.append(
                    SerializationError(
                        entity_type="form",
                        entity_id=str(form.id),
                        entity_name=form.name,
                        path=virtual_path,
                        error=str(e),
                    )
                )

        return VirtualFileResult(files=virtual_files, errors=errors)

    async def _get_agent_files(
        self, workflow_map: dict[str, str]
    ) -> VirtualFileResult:
        """
        Generate virtual files for all agents.

        Fetches all active agents with their tools relationship loaded,
        serializes them to JSON with portable workflow refs.

        Args:
            workflow_map: Mapping of workflow UUID -> "path::function_name"

        Returns:
            VirtualFileResult with files and any serialization errors
        """
        # Query agents with all relationships eagerly loaded
        # (tools, delegated_agents, roles needed for AgentPublic validation)
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
            .where(Agent.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        agents = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for agent in agents:
            virtual_path = f"agents/{agent.id}.agent.json"
            try:
                content = _serialize_agent_to_json(agent, workflow_map)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=virtual_path,
                        entity_type="agent",
                        entity_id=str(agent.id),
                        content=content,
                        computed_sha=computed_sha,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to serialize agent {agent.id}: {e}")
                errors.append(
                    SerializationError(
                        entity_type="agent",
                        entity_id=str(agent.id),
                        entity_name=agent.name,
                        path=virtual_path,
                        error=str(e),
                    )
                )

        return VirtualFileResult(files=virtual_files, errors=errors)

    async def get_virtual_file_by_id(
        self, entity_type: str, entity_id: str
    ) -> VirtualFile | None:
        """
        Get a specific virtual file by entity type and ID.

        Args:
            entity_type: Type of entity - "app", "form", or "agent"
            entity_id: UUID string of the entity

        Returns:
            VirtualFile if found, None otherwise
        """
        # Build workflow ref map
        workflow_map = await build_workflow_ref_map(self.db)

        try:
            entity_uuid = UUID(entity_id)
        except ValueError:
            logger.warning(f"Invalid entity ID: {entity_id}")
            return None

        if entity_type == "app":
            return await self._get_app_file_by_id(entity_uuid, workflow_map)
        elif entity_type == "form":
            return await self._get_form_file_by_id(entity_uuid, workflow_map)
        elif entity_type == "agent":
            return await self._get_agent_file_by_id(entity_uuid, workflow_map)
        else:
            logger.warning(f"Unknown entity type: {entity_type}")
            return None

    async def _get_app_file_by_id(
        self, app_id: UUID, workflow_map: dict[str, str]
    ) -> VirtualFile | None:
        """Get a specific app as a virtual file."""
        stmt = (
            select(Application)
            .options(
                selectinload(Application.draft_version_ref).selectinload(
                    AppVersion.files
                )
            )
            .where(Application.id == app_id)
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            return None

        try:
            content = self._serialize_app_to_json(app)
            computed_sha = compute_git_blob_sha(content)

            return VirtualFile(
                path=f"apps/{app.id}.app.json",
                entity_type="app",
                entity_id=str(app.id),
                content=content,
                computed_sha=computed_sha,
            )
        except Exception as e:
            logger.warning(f"Failed to serialize app {app.id}: {e}")
            return None

    async def _get_form_file_by_id(
        self, form_id: UUID, workflow_map: dict[str, str]
    ) -> VirtualFile | None:
        """Get a specific form as a virtual file."""
        stmt = (
            select(Form)
            .options(selectinload(Form.fields))
            .where(Form.id == form_id, Form.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        form = result.scalar_one_or_none()

        if not form:
            return None

        try:
            content = _serialize_form_to_json(form, workflow_map)
            computed_sha = compute_git_blob_sha(content)

            return VirtualFile(
                path=f"forms/{form.id}.form.json",
                entity_type="form",
                entity_id=str(form.id),
                content=content,
                computed_sha=computed_sha,
            )
        except Exception as e:
            logger.warning(f"Failed to serialize form {form.id}: {e}")
            return None

    async def _get_agent_file_by_id(
        self, agent_id: UUID, workflow_map: dict[str, str]
    ) -> VirtualFile | None:
        """Get a specific agent as a virtual file."""
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
            .where(Agent.id == agent_id, Agent.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            return None

        try:
            content = _serialize_agent_to_json(agent, workflow_map)
            computed_sha = compute_git_blob_sha(content)

            return VirtualFile(
                path=f"agents/{agent.id}.agent.json",
                entity_type="agent",
                entity_id=str(agent.id),
                content=content,
                computed_sha=computed_sha,
            )
        except Exception as e:
            logger.warning(f"Failed to serialize agent {agent.id}: {e}")
            return None

    def _serialize_app_to_json(self, app: Application) -> bytes:
        """
        Serialize an application to JSON bytes for GitHub sync.

        Args:
            app: Application ORM model with draft_version_ref and files loaded

        Returns:
            JSON content as bytes
        """
        # Build files list from draft version
        files_data: list[dict] = []
        if app.draft_version_ref and app.draft_version_ref.files:
            for file in sorted(app.draft_version_ref.files, key=lambda f: f.path):
                file_data = {
                    "path": file.path,
                    "source": file.source,
                }
                if file.compiled:
                    file_data["compiled"] = file.compiled
                files_data.append(file_data)

        app_data = {
            "id": str(app.id),
            "name": app.name,
            "slug": app.slug,
            "description": app.description,
            "icon": app.icon,
            "navigation": app.navigation,
            "permissions": app.permissions,
            "access_level": app.access_level,
            "files": files_data,
        }

        # Remove None values for cleaner output
        app_data = {k: v for k, v in app_data.items() if v is not None}

        content = json.dumps(app_data, indent=2, sort_keys=True)
        return content.encode("utf-8")

    @staticmethod
    def extract_id_from_filename(filename: str) -> str | None:
        """
        Extract entity UUID from a virtual file filename (fast path).

        Uses regex to match the expected filename patterns:
        - {uuid}.app.json
        - {uuid}.form.json
        - {uuid}.agent.json

        Args:
            filename: Just the filename (not the full path), e.g., "abc123.app.json"

        Returns:
            UUID string if pattern matches, None otherwise
        """
        match = UUID_FILENAME_PATTERN.match(filename)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def extract_id_from_content(content: bytes) -> str | None:
        """
        Extract entity ID from JSON content (fallback for non-standard filenames).

        Parses the JSON and returns the "id" field if present.

        Args:
            content: JSON content as bytes

        Returns:
            ID string if found in content, None otherwise
        """
        try:
            data = json.loads(content.decode("utf-8"))
            entity_id = data.get("id")
            if isinstance(entity_id, str):
                return entity_id
            return None
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug(f"Failed to extract ID from content: {e}")
            return None

    @staticmethod
    def get_entity_type_from_path(path: str) -> str | None:
        """
        Determine entity type from virtual file path.

        Args:
            path: Virtual file path, e.g., "apps/abc123.app.json"

        Returns:
            Entity type ("app", "form", "agent") or None if not recognized
        """
        if path.startswith("apps/") and path.endswith(".app.json"):
            return "app"
        elif path.startswith("forms/") and path.endswith(".form.json"):
            return "form"
        elif path.startswith("agents/") and path.endswith(".agent.json"):
            return "agent"
        return None

    @staticmethod
    def is_virtual_file_path(path: str) -> bool:
        """
        Check if a path matches the virtual file pattern.

        Args:
            path: File path to check

        Returns:
            True if path matches virtual file pattern, False otherwise
        """
        return (
            (path.startswith("apps/") and path.endswith(".app.json"))
            or (path.startswith("forms/") and path.endswith(".form.json"))
            or (path.startswith("agents/") and path.endswith(".agent.json"))
        )
