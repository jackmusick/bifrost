"""
Form indexer for parsing and indexing .form.json files.

Handles form metadata extraction, ID alignment, and field synchronization.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Form, FormField as FormFieldORM, Workflow
from src.models.contracts.forms import FormPublic

logger = logging.getLogger(__name__)


def _serialize_form_to_json(
    form: Form,
    workflow_map: dict[str, str] | None = None
) -> bytes:
    """
    Serialize a Form (with fields) to JSON bytes using Pydantic model_dump.

    Uses FormPublic.model_dump() with serialization context to support
    portable workflow refs (UUID → path::function_name transformation).

    Args:
        form: Form ORM instance with fields relationship loaded
        workflow_map: Optional mapping of workflow UUID → portable ref.
                      If provided, workflow references are transformed.

    Returns:
        JSON serialized as UTF-8 bytes
    """
    # Convert ORM to Pydantic model (triggers @model_validator to build form_schema)
    form_public = FormPublic.model_validate(form)

    # Serialize with context for portable refs
    context = {"workflow_map": workflow_map} if workflow_map else None
    form_data = form_public.model_dump(mode="json", context=context, exclude_none=True)

    # Add export metadata if we transformed refs
    if workflow_map:
        form_data["_export"] = {
            "workflow_refs": [
                "workflow_id",
                "launch_workflow_id",
                "form_schema.fields.*.data_provider_id"
            ],
            "version": "1.0"
        }

    return json.dumps(form_data, indent=2).encode("utf-8")


class FormIndexer:
    """
    Indexes .form.json files and synchronizes with the database.

    Handles ID alignment, workflow name resolution, and field synchronization.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the form indexer.

        Args:
            db: Database session for querying and updating form records
        """
        self.db = db

    async def resolve_workflow_name_to_id(self, workflow_name: str) -> str | None:
        """
        Resolve a workflow name to its UUID.

        Used for legacy form files that use linked_workflow (name) instead of workflow_id (UUID).

        Args:
            workflow_name: The workflow name to resolve

        Returns:
            The workflow UUID as a string, or None if not found
        """
        result = await self.db.execute(
            select(Workflow.id).where(
                Workflow.name == workflow_name,
                Workflow.is_active == True,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None

    async def index_form(
        self,
        path: str,
        content: bytes,
        workspace_file: Any = None,
    ) -> bool:
        """
        Parse and index form from .form.json file.

        If the JSON contains an 'id' field, uses that ID (for dual-write from API).
        Otherwise generates a new ID and writes it back to the file.

        Updates form definition (name, description, workflow_id, form_schema, etc.)
        but preserves environment-specific fields (organization_id, access_level).

        Uses ON CONFLICT on primary key (id) to update existing forms.

        Args:
            path: File path
            content: File content bytes
            workspace_file: WorkspaceFile ORM instance (optional, not currently used)

        Returns:
            True if content was modified (ID alignment), False otherwise
        """
        content_modified = False

        try:
            form_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in form file: {path}")
            return False

        # Check for portable refs from export and resolve them to UUIDs
        export_meta = form_data.pop("_export", None)
        if export_meta and "workflow_refs" in export_meta:
            from src.services.file_storage.ref_translation import (
                build_ref_to_uuid_map,
                transform_path_refs_to_uuids,
            )
            ref_to_uuid = await build_ref_to_uuid_map(self.db)
            unresolved = transform_path_refs_to_uuids(
                form_data, export_meta["workflow_refs"], ref_to_uuid
            )
            if unresolved:
                logger.warning(f"Unresolved portable refs in {path}: {unresolved}")

        name = form_data.get("name")
        if not name:
            logger.warning(f"Form file missing name: {path}")
            return False

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

        now = datetime.utcnow()

        # Get workflow_id - prefer explicit workflow_id, fall back to linked_workflow (name lookup)
        workflow_id = form_data.get("workflow_id")
        if not workflow_id:
            linked_workflow = form_data.get("linked_workflow")
            if linked_workflow:
                # Legacy format - resolve workflow name to UUID
                workflow_id = await self.resolve_workflow_name_to_id(linked_workflow)
                if workflow_id:
                    logger.info(f"Resolved legacy linked_workflow '{linked_workflow}' to workflow_id '{workflow_id}'")
                else:
                    logger.warning(f"Could not resolve linked_workflow '{linked_workflow}' to workflow ID for form {path}")

        # Same fallback for launch_workflow_id
        launch_workflow_id = form_data.get("launch_workflow_id")
        if not launch_workflow_id:
            launch_workflow_name = form_data.get("launch_workflow")
            if launch_workflow_name:
                launch_workflow_id = await self.resolve_workflow_name_to_id(launch_workflow_name)

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
        from src.models import WorkspaceFile
        from sqlalchemy import update

        stmt = update(WorkspaceFile).where(WorkspaceFile.path == path).values(
            entity_type="form",
            entity_id=form_id if isinstance(form_id, UUID_type) else UUID_type(form_id),
        )
        await self.db.execute(stmt)

        logger.debug(f"Indexed form: {name} from {path}")
        return content_modified

    async def delete_form_for_file(self, path: str) -> int:
        """
        Delete the form associated with a file.

        Called when a file is deleted to clean up form records from the database.

        Args:
            path: File path that was deleted

        Returns:
            Number of forms deleted
        """
        # Delete the form for this path (cascade will delete form_fields)
        stmt = delete(Form).where(Form.file_path == path)
        result = await self.db.execute(stmt)
        count = result.rowcount if result.rowcount else 0

        if count > 0:
            logger.info(f"Deleted {count} form(s) from database for deleted file: {path}")

        return count
