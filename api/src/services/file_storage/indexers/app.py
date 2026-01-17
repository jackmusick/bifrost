"""
Application indexer for parsing and indexing .app.json files.

Handles app metadata extraction and draft definition synchronization.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contracts.app_components import AppComponent as AppComponentModel
from src.models.orm.applications import AppComponent, Application, AppPage, AppVersion

logger = logging.getLogger(__name__)


def _serialize_app_to_json(
    app: Application,
    pages_data: list[dict[str, Any]],
    workflow_map: dict[str, str] | None = None,
) -> bytes:
    """
    Serialize an Application to JSON bytes with portable workflow refs.

    Uses PageDefinition.model_dump() with serialization context to transform
    workflow UUIDs to portable refs (path::function_name format).

    Args:
        app: Application ORM instance
        pages_data: Already converted page data as list of dicts
        workflow_map: Optional mapping of workflow UUID -> portable ref.
                      If provided, workflow references are transformed.

    Returns:
        JSON serialized as UTF-8 bytes
    """
    from src.models.contracts.app_components import PageDefinition

    # Convert pages to typed PageDefinition models for proper serialization
    context = {"workflow_map": workflow_map} if workflow_map else None

    serialized_pages = []
    for page_dict in pages_data:
        # Validate and serialize through typed model
        page_def = PageDefinition.model_validate(page_dict)
        serialized_pages.append(
            page_def.model_dump(mode="json", context=context, exclude_none=True)
        )

    app_data: dict[str, Any] = {
        "name": app.name,
        "slug": app.slug,
        "description": app.description,
        "icon": app.icon,
        "navigation": app.navigation or {},
        "permissions": app.permissions or {},
        "pages": serialized_pages,
        "export_version": "1.0",
    }

    # Add export metadata if we transformed refs
    if workflow_map:
        app_data["_export"] = {
            "workflow_refs": [
                "pages.*.layout..*.props.workflow_id",
                "pages.*.data_sources.*.workflow_id",
                "pages.*.launch_workflow_id",
                "pages.*.launch_workflow.workflow_id",
            ],
            "version": "1.0",
        }

    return json.dumps(app_data, indent=2).encode("utf-8")


class AppIndexer:
    """
    Indexes .app.json files and synchronizes with the database.

    Handles ID alignment and draft definition updates.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the app indexer.

        Args:
            db: Database session for querying and updating application records
        """
        self.db = db

    async def index_app(
        self,
        path: str,
        content: bytes,
        workspace_file: Any = None,
    ) -> bool:
        """
        Parse and index application from .app.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID (for files synced from git/editor).

        Creates/updates the app with a draft version containing pages and components.

        Instance-specific fields ignored on import:
        - organization_id: Set from import context or None (global)
        - permissions: Set to {} (role IDs don't transfer across instances)
        - access_level: Set to "role_based" (locked down by default)
        - created_by: Set to "file_sync" or importing user
        - created_at/updated_at: Regenerated (ignore if present in JSON)

        Args:
            path: File path
            content: File content bytes
            workspace_file: WorkspaceFile ORM instance (optional, not currently used)

        Returns:
            True if content was modified (ID alignment), False otherwise
        """
        content_modified = False

        try:
            app_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in app file: {path}")
            return False

        # Check for portable refs from export and resolve them to UUIDs
        export_meta = app_data.pop("_export", None)
        if export_meta and "workflow_refs" in export_meta:
            from src.services.file_storage.ref_translation import (
                build_ref_to_uuid_map,
                transform_path_refs_to_uuids,
            )

            ref_to_uuid = await build_ref_to_uuid_map(self.db)
            unresolved = transform_path_refs_to_uuids(
                app_data, export_meta["workflow_refs"], ref_to_uuid
            )
            if unresolved:
                logger.warning(f"Unresolved portable refs in {path}: {unresolved}")

        # Strip instance-specific fields that don't transfer across instances
        app_data.pop("organization_id", None)
        app_data.pop("created_at", None)
        app_data.pop("updated_at", None)
        app_data.pop("published_at", None)

        name = app_data.get("name")
        if not name:
            logger.warning(f"App file missing name: {path}")
            return False

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

        now = datetime.utcnow()

        # Generate slug from name if not provided
        slug = app_data.get("slug")
        if not slug:
            slug = name.lower().replace(" ", "-").replace("_", "-")
            # Remove non-alphanumeric characters except hyphens
            slug = "".join(c for c in slug if c.isalnum() or c == "-")

        # Check if app exists
        existing_app = await self.db.execute(
            select(Application).where(Application.id == app_id)
        )
        existing_app = existing_app.scalar_one_or_none()

        if existing_app:
            # Update existing app metadata
            existing_app.name = name
            existing_app.slug = slug
            existing_app.description = app_data.get("description")
            existing_app.icon = app_data.get("icon")
            existing_app.navigation = app_data.get("navigation", {})
            # Reset instance-specific fields - don't import from file
            existing_app.permissions = {}
            existing_app.access_level = "role_based"  # Locked down by default
            existing_app.updated_at = now

            # Get existing draft version to reuse or create new
            version_id = existing_app.draft_version_id
            if not version_id:
                # Create new draft version
                version_id = uuid4()
                new_version = AppVersion(id=version_id, application_id=app_id)
                self.db.add(new_version)
                existing_app.draft_version_id = version_id
        else:
            # Create new application with draft version
            version_id = uuid4()

            new_app = Application(
                id=app_id,
                name=name,
                slug=slug,
                description=app_data.get("description"),
                icon=app_data.get("icon"),
                navigation=app_data.get("navigation", {}),
                # Instance-specific defaults
                organization_id=None,  # Import as global by default
                permissions={},  # Empty - role IDs don't transfer
                access_level="role_based",  # Locked down by default
                created_by="file_sync",
            )
            self.db.add(new_app)
            await self.db.flush()  # Flush to get app ID for FK

            new_version = AppVersion(id=version_id, application_id=app_id)
            self.db.add(new_version)
            await self.db.flush()

            # Update app with draft version pointer
            new_app.draft_version_id = version_id

        # Clear existing pages and components for this version
        await self.db.execute(
            delete(AppPage).where(AppPage.version_id == version_id)
        )

        # Create pages and components from app_data
        pages_data = app_data.get("pages", [])
        for page_order, page_data in enumerate(pages_data):
            await self._create_page_with_components(
                app_id, version_id, page_data, page_order
            )

        await self.db.flush()
        logger.debug(f"Indexed app: {name} from {path}")
        return content_modified

    async def _create_page_with_components(
        self,
        app_id: UUID,
        version_id: UUID,
        page_data: dict[str, Any],
        page_order: int,
    ) -> None:
        """Create a page and its components from page data."""
        page_id_str = page_data.get("id") or page_data.get("page_id") or f"page_{page_order}"

        # Parse launch_workflow_id - may be UUID string or None
        launch_workflow_id = None
        launch_workflow_id_raw = page_data.get("launch_workflow_id")
        if launch_workflow_id_raw:
            try:
                launch_workflow_id = UUID(launch_workflow_id_raw)
            except ValueError:
                # Could be a portable ref that wasn't resolved - leave as None
                logger.debug(f"Could not parse launch_workflow_id: {launch_workflow_id_raw}")

        # Create the page
        page = AppPage(
            application_id=app_id,
            version_id=version_id,
            page_id=page_id_str,
            title=page_data.get("title", page_id_str),
            path=page_data.get("path", f"/{page_id_str}"),
            data_sources=page_data.get("data_sources", []),
            variables=page_data.get("variables", {}),
            launch_workflow_id=launch_workflow_id,
            launch_workflow_params=page_data.get("launch_workflow_params", {}),
            launch_workflow_data_source_id=page_data.get("launch_workflow_data_source_id"),
            permission=page_data.get("permission", {}),
            page_order=page_order,
        )
        self.db.add(page)
        await self.db.flush()  # Get page.id for component FK

        # Create components from children array
        children = page_data.get("children", [])
        if children:
            await self._create_components(children, page.id, parent_id=None)

    async def _create_components(
        self,
        components: list[dict[str, Any]],
        page_db_id: UUID,
        parent_id: UUID | None = None,
    ) -> None:
        """Recursively create component records from nested children array."""
        adapter = TypeAdapter(AppComponentModel)

        for order, comp_data in enumerate(components):
            # Pop children before validation (handled recursively)
            children = comp_data.pop("children", [])

            # Validate component through discriminated union
            validated = adapter.validate_python({**comp_data, "children": []})

            # Extract flat props (everything except standard fields)
            component_dict = validated.model_dump(exclude_none=True)
            component_id_str = component_dict.pop("id")
            component_type = component_dict.pop("type")
            visible = component_dict.pop("visible", None)
            width = component_dict.pop("width", None)
            loading_workflows = component_dict.pop("loading_workflows", None)
            component_dict.pop("children", None)  # Already handled

            props = component_dict  # Remaining fields are the props

            # Create ORM record
            component_uuid = uuid4()
            record = AppComponent(
                id=component_uuid,
                page_id=page_db_id,
                component_id=component_id_str,
                parent_id=parent_id,
                type=component_type,
                props=props,
                component_order=order,
                visible=visible,
                width=width,
                loading_workflows=loading_workflows,
            )
            self.db.add(record)
            await self.db.flush()  # Get component ID for children FK

            # Recurse for children
            if children:
                await self._create_components(children, page_db_id, parent_id=component_uuid)

    async def delete_app_for_file(self, path: str) -> int:
        """
        Delete the application associated with a file.

        Called when a file is deleted to clean up application records from the database.

        Note: Applications don't have a file_path column, so we need to look up via workspace_files.

        Args:
            path: File path that was deleted

        Returns:
            Number of applications deleted
        """
        from src.models import WorkspaceFile
        from sqlalchemy import select

        # Find the app entity_id from workspace_files
        stmt = select(WorkspaceFile.entity_id).where(
            WorkspaceFile.path == path,
            WorkspaceFile.entity_type == "app",
        )
        result = await self.db.execute(stmt)
        entity_id = result.scalar_one_or_none()

        if not entity_id:
            return 0

        # Delete the application
        stmt = delete(Application).where(Application.id == entity_id)
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Deleted {count} application(s) from database for deleted file: {path}")

        return count
