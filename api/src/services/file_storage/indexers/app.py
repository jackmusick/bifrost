"""
App indexer for parsing and indexing apps from GitHub sync.

Handles:
- apps/{slug}/app.json -> Application record
- apps/{slug}/**/*.tsx -> AppFile records

Serialization excludes instance-specific fields (permissions, access_level,
organization_id, role_ids, timestamps) - these are set to safe defaults on import.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Application, AppFile, AppVersion
from src.services.app_dependencies import sync_file_dependencies

logger = logging.getLogger(__name__)


def _serialize_app_to_json(app: Application) -> bytes:
    """
    Serialize an Application to JSON bytes for GitHub export.

    Includes:
    - id (required for entity matching during sync)
    - name, slug, description, icon, navigation

    Excludes instance-specific fields:
    - permissions, access_level, organization_id, role_ids
    - created_by, created_at, updated_at, published_at
    - active_version_id, draft_version_id

    Args:
        app: Application ORM instance

    Returns:
        JSON serialized as UTF-8 bytes
    """
    app_data: dict[str, Any] = {
        "id": str(app.id),  # Required for entity matching during sync
        "name": app.name,
        "slug": app.slug,
    }

    # Optional fields - only include if set
    if app.description:
        app_data["description"] = app.description
    if app.icon:
        app_data["icon"] = app.icon
    if app.navigation:
        app_data["navigation"] = app.navigation

    return json.dumps(app_data, indent=2).encode("utf-8")


class AppIndexer:
    """
    Indexes apps from GitHub sync.

    Handles:
    - apps/{slug}/app.json -> creates/updates Application
    - apps/{slug}/**/* -> creates/updates AppFile in draft version
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the app indexer.

        Args:
            db: Database session for querying and updating records
        """
        self.db = db

    async def index_app_json(
        self,
        path: str,
        content: bytes,
    ) -> bool:
        """
        Parse and index app from app.json file.

        Creates or updates the Application record based on slug.
        Instance-specific fields are set to safe defaults on create,
        preserved on update.

        Args:
            path: File path (e.g., "apps/my-app/app.json")
            content: JSON content bytes

        Returns:
            True if content was modified (not currently used for apps), False otherwise
        """
        try:
            app_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in app file: {path}")
            return False

        # Extract slug from path
        # Path format: apps/{slug}/app.json
        parts = path.split("/")
        if len(parts) < 3 or parts[0] != "apps" or parts[2] != "app.json":
            logger.warning(f"Invalid app.json path format: {path}")
            return False

        slug = parts[1]

        # Validate required fields
        name = app_data.get("name")
        if not name:
            logger.warning(f"App file missing name: {path}")
            return False

        # Check if slug in path matches slug in JSON (if provided)
        json_slug = app_data.get("slug")
        if json_slug and json_slug != slug:
            logger.warning(
                f"Slug mismatch in {path}: path has '{slug}', JSON has '{json_slug}'. Using path slug."
            )

        # Use naive UTC datetime - columns defined without timezone
        now = datetime.now(timezone.utc)

        # Check if app already exists by slug
        existing_app = await self._get_app_by_slug(slug)

        if existing_app:
            # Update existing app - preserve instance-specific fields
            existing_app.name = name
            existing_app.description = app_data.get("description")
            existing_app.icon = app_data.get("icon")
            if "navigation" in app_data:
                existing_app.navigation = app_data["navigation"]
            existing_app.updated_at = now

            logger.info(f"Updated app: {slug}")
        else:
            # Create new app with safe defaults
            app_id = uuid4()
            draft_version_id = uuid4()

            # Create application first (required for FK constraint)
            new_app = Application(
                id=app_id,
                name=name,
                slug=slug,
                description=app_data.get("description"),
                icon=app_data.get("icon"),
                navigation=app_data.get("navigation", {}),
                # Safe defaults for instance-specific fields
                organization_id=None,  # Global
                access_level="role_based",  # Locked down by default
                permissions={},
                # Version references - set draft_version_id after flush
                draft_version_id=None,
                active_version_id=None,  # Not published
                # Metadata
                created_at=now,
                updated_at=now,
                created_by="github_sync",
            )
            self.db.add(new_app)
            await self.db.flush()  # Get the app ID persisted

            # Create draft version after application exists
            draft_version = AppVersion(
                id=draft_version_id,
                application_id=app_id,
                created_at=now,
            )
            self.db.add(draft_version)
            await self.db.flush()  # Get the version ID

            # Update app to point to draft version
            new_app.draft_version_id = draft_version_id

            logger.info(f"Created app: {slug}")

        return False

    async def index_app_file(
        self,
        path: str,
        content: bytes,
    ) -> bool:
        """
        Parse and index an app code file.

        Creates or updates the AppFile record in the app's draft version.
        UUIDs are used directly in source code for workflow references.

        Args:
            path: File path (e.g., "apps/my-app/pages/index.tsx")
            content: File content bytes

        Returns:
            True if content was modified, False otherwise
        """
        # Extract slug and relative path
        # Path format: apps/{slug}/{relative_path}
        parts = path.split("/", 2)
        if len(parts) < 3 or parts[0] != "apps":
            logger.warning(f"Invalid app file path format: {path}")
            return False

        slug = parts[1]
        relative_path = parts[2]

        # Skip app.json - handled by index_app_json
        if relative_path == "app.json":
            return False

        # Get the app by slug
        app = await self._get_app_by_slug(slug)
        if not app:
            logger.warning(f"App not found for file {path}. Index app.json first.")
            return False

        # Ensure draft version exists
        if not app.draft_version_id:
            logger.warning(f"App {slug} has no draft version")
            return False

        # Decode content
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Invalid UTF-8 in app file: {path}")
            return False

        now = datetime.now(timezone.utc)

        # Upsert the file
        file_id = uuid4()
        stmt = insert(AppFile).values(
            id=file_id,
            app_version_id=app.draft_version_id,
            path=relative_path,
            source=source,
            compiled=None,
            created_at=now,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=["app_version_id", "path"],
            set_={
                "source": source,
                "compiled": None,  # Clear compiled on update
                "updated_at": now,
            },
        ).returning(AppFile.id)
        result = await self.db.execute(stmt)
        actual_file_id = result.scalar_one()

        # Sync dependencies for this file
        await sync_file_dependencies(self.db, actual_file_id, source, app.organization_id)

        logger.debug(f"Indexed app file: {relative_path} in app {slug}")
        return False

    async def delete_app(self, slug: str) -> int:
        """
        Delete an application by slug.

        Called when app.json is deleted from remote.
        Cascades to delete versions and files.

        Args:
            slug: App slug

        Returns:
            Number of apps deleted (0 or 1)
        """
        from sqlalchemy import delete

        stmt = delete(Application).where(Application.slug == slug)
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Deleted app: {slug}")

        return count

    async def delete_app_file(self, path: str) -> int:
        """
        Delete an app file.

        Called when a file is deleted from remote.

        Args:
            path: Full path (e.g., "apps/my-app/pages/old.tsx")

        Returns:
            Number of files deleted
        """
        from sqlalchemy import delete

        # Extract slug and relative path
        parts = path.split("/", 2)
        if len(parts) < 3 or parts[0] != "apps":
            return 0

        slug = parts[1]
        relative_path = parts[2]

        # Get the app
        app = await self._get_app_by_slug(slug)
        if not app or not app.draft_version_id:
            return 0

        stmt = delete(AppFile).where(
            AppFile.app_version_id == app.draft_version_id,
            AppFile.path == relative_path,
        )
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Deleted app file: {relative_path} from app {slug}")

        return count

    async def _get_app_by_slug(self, slug: str) -> Application | None:
        """Get an application by slug."""
        stmt = select(Application).where(Application.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_app_by_id(self, app_id: UUID | str) -> Application | None:
        """Get an application by ID."""
        if isinstance(app_id, str):
            app_id = UUID(app_id)
        stmt = select(Application).where(Application.id == app_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def import_app(
        self,
        app_dir: str,
        files: dict[str, bytes],
    ) -> Application | None:
        """
        Import an app atomically with all its files.

        This method processes the entire app bundle at once, eliminating
        ordering issues where app_files were imported before app.json.
        UUIDs are used directly in source code for workflow references.

        Args:
            app_dir: App directory path (e.g., "apps/my-app")
            files: Dict mapping relative paths to content
                   {"app.json": content, "pages/index.tsx": content, ...}

        Returns:
            The created/updated Application, or None on failure

        Example:
            await indexer.import_app("apps/my-app", {
                "app.json": b'{"id": "...", "name": "My App", "slug": "my-app"}',
                "pages/index.tsx": b'export default function Index() { ... }',
                "components/Button.tsx": b'export function Button() { ... }',
            })
        """
        # Validate and extract app.json
        if "app.json" not in files:
            logger.warning(f"Missing app.json in app bundle: {app_dir}")
            return None

        try:
            app_data = json.loads(files["app.json"].decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in app.json for: {app_dir}")
            return None

        # Extract slug from path
        parts = app_dir.split("/")
        if len(parts) < 2 or parts[0] != "apps":
            logger.warning(f"Invalid app directory path: {app_dir}")
            return None

        slug = parts[1]
        name = app_data.get("name")
        if not name:
            logger.warning(f"App missing name in: {app_dir}")
            return None

        # Check for UUID in app.json for stable matching
        app_uuid_str = app_data.get("id")

        now = datetime.now(timezone.utc)

        # Try to find existing app by UUID first, then by slug
        existing_app = None
        if app_uuid_str:
            existing_app = await self._get_app_by_id(app_uuid_str)

        if not existing_app:
            existing_app = await self._get_app_by_slug(slug)

        if existing_app:
            # Update existing app
            existing_app.name = name
            existing_app.description = app_data.get("description")
            existing_app.icon = app_data.get("icon")
            if "navigation" in app_data:
                existing_app.navigation = app_data["navigation"]
            existing_app.updated_at = now

            # If slug changed, update it
            if existing_app.slug != slug:
                existing_app.slug = slug

            app = existing_app
            logger.info(f"Updated app atomically: {slug}")
        else:
            # Create new app
            app_id = UUID(app_uuid_str) if app_uuid_str else uuid4()
            draft_version_id = uuid4()

            new_app = Application(
                id=app_id,
                name=name,
                slug=slug,
                description=app_data.get("description"),
                icon=app_data.get("icon"),
                navigation=app_data.get("navigation", {}),
                organization_id=None,
                access_level="role_based",
                permissions={},
                draft_version_id=None,
                active_version_id=None,
                created_at=now,
                updated_at=now,
                created_by="github_sync",
            )
            self.db.add(new_app)
            await self.db.flush()

            # Create draft version
            draft_version = AppVersion(
                id=draft_version_id,
                application_id=app_id,
                created_at=now,
            )
            self.db.add(draft_version)
            await self.db.flush()

            new_app.draft_version_id = draft_version_id
            app = new_app
            logger.info(f"Created app atomically: {slug}")

        # Now process all code files
        if not app.draft_version_id:
            logger.warning(f"App {slug} has no draft version after creation")
            return None

        for file_path, content in files.items():
            if file_path == "app.json":
                continue  # Already processed

            try:
                source = content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"Invalid UTF-8 in app file: {app_dir}/{file_path}")
                continue

            # Upsert the file
            file_id = uuid4()
            stmt = insert(AppFile).values(
                id=file_id,
                app_version_id=app.draft_version_id,
                path=file_path,
                source=source,
                compiled=None,
                created_at=now,
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=["app_version_id", "path"],
                set_={
                    "source": source,
                    "compiled": None,
                    "updated_at": now,
                },
            ).returning(AppFile.id)
            result = await self.db.execute(stmt)
            actual_file_id = result.scalar_one()

            # Sync dependencies
            await sync_file_dependencies(self.db, actual_file_id, source, app.organization_id)

        logger.info(f"Imported app atomically with {len(files) - 1} code files: {slug}")
        return app

