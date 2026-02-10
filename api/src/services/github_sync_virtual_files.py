"""
Virtual File Provider for GitHub Sync.

Platform entities (forms, agents, apps) don't exist in the `workspace_files` table -
they live in their own database tables. The VirtualFileProvider serializes these
entities on-the-fly so they can participate in GitHub sync.

Virtual files are generated from database entities with:
- UUIDs used directly for all cross-references
- Computed git blob SHA for fast comparison
- Standardized path patterns

Path patterns:
- Forms: forms/{form.id}.form.json
- Agents: agents/{agent.id}.agent.json
- Apps: apps/{slug}/app.json + apps/{slug}/**/*.tsx (directory-based)

Apps are serialized as directories:
- apps/{slug}/app.json - portable metadata (name, slug, description, icon, navigation)
- apps/{slug}/_layout.tsx, pages/*.tsx, components/*.tsx, modules/*.ts - code files
"""

import json
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Agent, Application, AppVersion, Form
from src.services.file_storage.file_ops import compute_git_blob_sha
from src.services.file_storage.indexers.agent import _serialize_agent_to_json
from src.services.file_storage.indexers.app import _serialize_app_to_json
from src.services.file_storage.indexers.form import _serialize_form_to_json

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

    Virtual files are generated on-the-fly from database entities (forms, agents, apps)
    and can participate in GitHub sync without being stored in workspace_files.

    Attributes:
        path: Virtual file path, e.g., "forms/{uuid}.form.json" or "apps/{slug}/app.json"
        entity_type: Type of entity - "form", "agent", "app", or "app_file"
        entity_id: Stable identifier - UUID for forms/agents, "app::{uuid}" for apps, path for app_files
        content: Serialized content as bytes
        computed_sha: Git blob SHA of content
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
    not in workspace_files. This provider serializes them to JSON so they can
    be synced to GitHub. UUIDs are used directly for all cross-references.

    Usage:
        provider = VirtualFileProvider(db)
        virtual_files = await provider.get_all_virtual_files()
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the virtual file provider.

        Args:
            db: Async database session for querying entities
        """
        self.db = db

    async def get_all_virtual_files(
        self,
        include_content: bool = True,
    ) -> VirtualFileResult:
        """
        Get all platform entities as virtual files.

        Retrieves all forms, agents, and apps from the database, serializes them
        and returns them as VirtualFile objects with computed git SHAs.

        Args:
            include_content: If True (default), include serialized content in each
                          VirtualFile. If False, only compute SHA and set content
                          to None. Use False to reduce memory usage when only
                          comparing SHAs (e.g., during sync preview).

        Returns:
            VirtualFileResult containing files and any errors encountered
        """
        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        form_result = await self._get_form_files(include_content)
        agent_result = await self._get_agent_files(include_content)
        app_result = await self._get_app_files(include_content)

        virtual_files.extend(form_result.files)
        virtual_files.extend(agent_result.files)
        virtual_files.extend(app_result.files)

        errors.extend(form_result.errors)
        errors.extend(agent_result.errors)
        errors.extend(app_result.errors)

        logger.info(
            f"Generated {len(virtual_files)} virtual files: "
            f"{len(form_result.files)} forms, {len(agent_result.files)} agents, "
            f"{len(app_result.files)} app files, "
            f"{len(errors)} errors"
        )

        return VirtualFileResult(files=virtual_files, errors=errors)

    async def _get_form_files(
        self,
        include_content: bool = True,
    ) -> VirtualFileResult:
        """
        Generate virtual files for all forms.

        Args:
            include_content: If True, include content in VirtualFile. If False,
                          compute SHA only and set content to None.

        Returns:
            VirtualFileResult with files and any serialization errors
        """
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
                content = _serialize_form_to_json(form)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=virtual_path,
                        entity_type="form",
                        entity_id=str(form.id),
                        content=content if include_content else None,
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
        self,
        include_content: bool = True,
    ) -> VirtualFileResult:
        """
        Generate virtual files for all agents.

        Built-in/system agents (like "Coding Assistant") are excluded from sync
        because they are auto-created on startup and shouldn't vary between
        environments.

        Args:
            include_content: If True, include content in VirtualFile. If False,
                          compute SHA only and set content to None.

        Returns:
            VirtualFileResult with files and any serialization errors
        """
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.tools),
                selectinload(Agent.delegated_agents),
                selectinload(Agent.roles),
            )
            .where(
                Agent.is_active == True,  # noqa: E712
                Agent.is_system == False,  # noqa: E712  Exclude built-in agents
            )
        )
        result = await self.db.execute(stmt)
        agents = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for agent in agents:
            virtual_path = f"agents/{agent.id}.agent.json"
            try:
                content = _serialize_agent_to_json(agent)
                computed_sha = compute_git_blob_sha(content)

                virtual_files.append(
                    VirtualFile(
                        path=virtual_path,
                        entity_type="agent",
                        entity_id=str(agent.id),
                        content=content if include_content else None,
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

    async def _get_app_files(
        self,
        include_content: bool = True,
    ) -> VirtualFileResult:
        """
        Generate virtual files for all applications.

        Each app produces multiple virtual files:
        - apps/{slug}/app.json - portable metadata
        - apps/{slug}/{path} - each code file (pages/*.tsx, components/*.tsx, etc.)

        Uses the app's active_version if published, otherwise draft_version.

        Args:
            include_content: If True, include content in VirtualFile. If False,
                          compute SHA only and set content to None.
        """
        stmt = (
            select(Application)
            .options(
                selectinload(Application.active_version).selectinload(AppVersion.files),
                selectinload(Application.draft_version_ref).selectinload(AppVersion.files),
            )
        )
        result = await self.db.execute(stmt)
        apps = result.scalars().all()

        virtual_files: list[VirtualFile] = []
        errors: list[SerializationError] = []

        for app in apps:
            # Use active_version if published, otherwise draft
            version = app.active_version or app.draft_version_ref
            if not version:
                logger.debug(f"App {app.slug} has no version, skipping")
                continue

            app_dir = f"apps/{app.slug}"
            app_entity_id = f"app::{app.id}"  # Stable ID regardless of slug/directory

            # 1. Serialize app.json (portable metadata only)
            try:
                app_json_content = _serialize_app_to_json(app)
                app_json_sha = compute_git_blob_sha(app_json_content)

                virtual_files.append(
                    VirtualFile(
                        path=f"{app_dir}/app.json",
                        entity_type="app",
                        entity_id=app_entity_id,
                        content=app_json_content if include_content else None,
                        computed_sha=app_json_sha,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to serialize app {app.slug}: {e}")
                errors.append(
                    SerializationError(
                        entity_type="app",
                        entity_id=app_entity_id,
                        entity_name=app.name,
                        path=f"{app_dir}/app.json",
                        error=str(e),
                    )
                )
                continue  # Skip files if app.json fails

            # 2. Serialize each code file (UUIDs used directly, no transformation)
            for file in version.files:
                file_path = f"{app_dir}/{file.path}"
                try:
                    file_content = file.source.encode("utf-8")
                    file_sha = compute_git_blob_sha(file_content)

                    virtual_files.append(
                        VirtualFile(
                            path=file_path,
                            entity_type="app_file",
                            entity_id=file_path,
                            content=file_content if include_content else None,
                            computed_sha=file_sha,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to serialize app file {file.path}: {e}")
                    errors.append(
                        SerializationError(
                            entity_type="app_file",
                            entity_id=str(file.id),
                            entity_name=file.path,
                            path=file_path,
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
            entity_type: Type of entity - "form", "agent", "app", or "app_file"
            entity_id: UUID string of the entity

        Returns:
            VirtualFile if found, None otherwise
        """
        try:
            entity_uuid = UUID(entity_id)
        except ValueError:
            logger.warning(f"Invalid entity ID: {entity_id}")
            return None

        if entity_type == "form":
            return await self._get_form_file_by_id(entity_uuid)
        elif entity_type == "agent":
            return await self._get_agent_file_by_id(entity_uuid)
        else:
            logger.warning(f"Unknown entity type: {entity_type}")
            return None

    async def _get_form_file_by_id(self, form_id: UUID) -> VirtualFile | None:
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
            content = _serialize_form_to_json(form)
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

    async def _get_agent_file_by_id(self, agent_id: UUID) -> VirtualFile | None:
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
            content = _serialize_agent_to_json(agent)
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

    async def get_virtual_file_content(
        self,
        path: str,
    ) -> bytes | None:
        """
        Load content for a single virtual file by path.

        This is a lazy loading method for fetching virtual file content on-demand,
        rather than pre-loading all virtual file content at once.

        Args:
            path: Virtual file path, e.g., "forms/{uuid}.form.json" or "apps/{slug}/pages/index.tsx"

        Returns:
            File content as bytes, or None if not found or serialization fails
        """
        if not self.is_virtual_file_path(path):
            return None

        entity_type = self.get_entity_type_from_path(path)

        if entity_type == "form":
            filename = path.split("/")[-1]
            entity_id = self.extract_id_from_filename(filename)
            if entity_id:
                try:
                    vf = await self._get_form_file_by_id(UUID(entity_id))
                    return vf.content if vf else None
                except ValueError:
                    return None

        elif entity_type == "agent":
            filename = path.split("/")[-1]
            entity_id = self.extract_id_from_filename(filename)
            if entity_id:
                try:
                    vf = await self._get_agent_file_by_id(UUID(entity_id))
                    return vf.content if vf else None
                except ValueError:
                    return None

        elif entity_type == "app":
            slug = self.extract_app_slug_from_path(path)
            if slug:
                return await self._get_app_json_content(slug)

        elif entity_type == "app_file":
            slug = self.extract_app_slug_from_path(path)
            file_rel_path = self.extract_app_file_path(path)
            if slug and file_rel_path:
                return await self._get_app_file_content(slug, file_rel_path)

        return None

    async def _get_app_json_content(self, slug: str) -> bytes | None:
        """Get app.json content for a specific app by slug."""
        stmt = select(Application).where(Application.slug == slug)
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            return None

        try:
            return _serialize_app_to_json(app)
        except Exception as e:
            logger.warning(f"Failed to serialize app {slug}: {e}")
            return None

    async def _get_app_file_content(
        self,
        slug: str,
        file_rel_path: str,
    ) -> bytes | None:
        """Get content for a specific app file."""
        stmt = (
            select(Application)
            .options(
                selectinload(Application.active_version).selectinload(AppVersion.files),
                selectinload(Application.draft_version_ref).selectinload(AppVersion.files),
            )
            .where(Application.slug == slug)
        )
        result = await self.db.execute(stmt)
        app = result.scalar_one_or_none()

        if not app:
            return None

        # Use active_version if published, otherwise draft
        version = app.active_version or app.draft_version_ref
        if not version:
            return None

        # Find the file with matching path
        for file in version.files:
            if file.path == file_rel_path:
                try:
                    return file.source.encode("utf-8")
                except Exception as e:
                    logger.warning(f"Failed to serialize app file {file.path}: {e}")
                    return None

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
            Entity type ("form", "agent", "app", or "app_file") or None if not recognized
        """
        if path.startswith("forms/") and path.endswith(".form.json"):
            return "form"
        elif path.startswith("agents/") and path.endswith(".agent.json"):
            return "agent"
        elif path.startswith("apps/"):
            # apps/{slug}/app.json -> "app"
            # apps/{slug}/**/* -> "app_file"
            if path.endswith("/app.json"):
                return "app"
            else:
                return "app_file"
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
            or path.startswith("apps/")
        )

    @staticmethod
    def extract_app_slug_from_path(path: str) -> str | None:
        """
        Extract app slug from an apps/ path.

        Args:
            path: Virtual file path, e.g., "apps/my-app/app.json" or "apps/my-app/pages/index.tsx"

        Returns:
            App slug if path is in apps/ directory, None otherwise
        """
        if not path.startswith("apps/"):
            return None
        parts = path.split("/")
        if len(parts) >= 2:
            return parts[1]
        return None

    @staticmethod
    def extract_app_file_path(path: str) -> str | None:
        """
        Extract the relative file path within an app.

        Args:
            path: Virtual file path, e.g., "apps/my-app/pages/index.tsx"

        Returns:
            Relative path within app (e.g., "pages/index.tsx"), None if not an app file
        """
        if not path.startswith("apps/"):
            return None
        parts = path.split("/", 2)  # Split into ["apps", "slug", "rest/of/path"]
        if len(parts) >= 3:
            return parts[2]
        return None
