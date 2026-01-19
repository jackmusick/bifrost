"""
Virtual File Provider for GitHub Sync.

Platform entities (forms, agents) don't exist in the `workspace_files` table -
they live in their own database tables. The VirtualFileProvider serializes these
entities on-the-fly so they can participate in GitHub sync.

Virtual files are generated from database entities with:
- Portable workflow refs (UUID -> path::function_name)
- Computed git blob SHA for fast comparison
- Standardized path patterns

Path patterns:
- Forms: forms/{form.id}.form.json
- Agents: agents/{agent.id}.agent.json

Note: Apps are NOT synced via virtual files - they use the app_files table
and will have their own sync mechanism.
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
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.file_storage.indexers.agent import _serialize_agent_to_json
from src.services.file_storage.indexers.form import _serialize_form_to_json
from src.services.file_storage.ref_translation import build_workflow_ref_map

logger = logging.getLogger(__name__)

# Regex pattern for extracting UUID from filenames
# Matches: {uuid}.form.json, {uuid}.agent.json
UUID_FILENAME_PATTERN = re.compile(
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"\.(form|agent)\.json$"
)


@dataclass
class VirtualFile:
    """
    A virtual file representing a platform entity.

    Virtual files are generated on-the-fly from database entities (forms, agents)
    and can participate in GitHub sync without being stored in workspace_files.

    Attributes:
        path: Virtual file path, e.g., "forms/{uuid}.form.json"
        entity_type: Type of entity - "form" or "agent"
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

    entity_type: str  # "form" or "agent"
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

    Platform entities (forms, agents) are stored in their own database tables,
    not in workspace_files. This provider serializes them to JSON with portable
    workflow references so they can be synced to GitHub.

    Usage:
        provider = VirtualFileProvider(db)
        virtual_files = await provider.get_all_virtual_files()

        # Each virtual file has:
        # - path: e.g., "forms/abc123.form.json"
        # - entity_type: "form" or "agent"
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

        Retrieves all forms and agents from the database, serializes them
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
        form_result = await self._get_form_files(workflow_map)
        agent_result = await self._get_agent_files(workflow_map)

        virtual_files.extend(form_result.files)
        virtual_files.extend(agent_result.files)

        errors.extend(form_result.errors)
        errors.extend(agent_result.errors)

        logger.info(
            f"Generated {len(virtual_files)} virtual files: "
            f"{len(form_result.files)} forms, {len(agent_result.files)} agents, "
            f"{len(errors)} errors"
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
            entity_type: Type of entity - "form" or "agent"
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

        if entity_type == "form":
            return await self._get_form_file_by_id(entity_uuid, workflow_map)
        elif entity_type == "agent":
            return await self._get_agent_file_by_id(entity_uuid, workflow_map)
        else:
            logger.warning(f"Unknown entity type: {entity_type}")
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

    @staticmethod
    def extract_id_from_filename(filename: str) -> str | None:
        """
        Extract entity UUID from a virtual file filename (fast path).

        Uses regex to match the expected filename patterns:
        - {uuid}.form.json
        - {uuid}.agent.json

        Args:
            filename: Just the filename (not the full path), e.g., "abc123.form.json"

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
            path: Virtual file path, e.g., "forms/abc123.form.json"

        Returns:
            Entity type ("form" or "agent") or None if not recognized
        """
        if path.startswith("forms/") and path.endswith(".form.json"):
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
            (path.startswith("forms/") and path.endswith(".form.json"))
            or (path.startswith("agents/") and path.endswith(".agent.json"))
        )
