"""
Application indexer for parsing and indexing .app.json files.

Handles app metadata extraction and draft definition synchronization.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.applications import Application

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
        "global_data_sources": app.global_data_sources or [],
        "global_variables": app.global_variables or {},
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

        Updates app draft_definition in the applications table.

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

        # Build definition from app_data (exclude top-level metadata)
        definition = {
            k: v for k, v in app_data.items()
            if k not in ("id", "name", "slug", "description", "icon", "organization_id",
                         "created_at", "updated_at", "created_by")
        }

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
        from src.models import WorkspaceFile

        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="app",
            entity_id=app_id if isinstance(app_id, UUID_type) else UUID_type(str(app_id)),
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed app: {name} from {path}")
        return content_modified

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
