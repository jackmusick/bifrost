"""
Forms Router

CRUD operations for workflow forms.
Support for org-specific and global forms.
Form execution for org users with access control.

Forms are persisted to BOTH database AND file system:
- Database: Fast queries, org scoping, access control
- File system: Source control, deployment portability
"""

import aiofiles
import aiofiles.os
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from src.core.auth import Context, CurrentActiveUser, CurrentSuperuser
from src.core.database import DbSession
from src.models.orm import Form as FormORM, FormField as FormFieldORM, FormRole as FormRoleORM, UserRole as UserRoleORM
from src.models.models import FormCreate, FormUpdate, FormPublic
from shared.models import WorkflowExecutionResponse

# Import cache invalidation
try:
    from shared.cache import invalidate_form
    CACHE_INVALIDATION_AVAILABLE = True
except ImportError:
    CACHE_INVALIDATION_AVAILABLE = False
    invalidate_form = None  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/forms", tags=["Forms"])

# Workspace location for form files
WORKSPACE_LOCATION = Path(os.environ.get("BIFROST_WORKSPACE_LOCATION", "/workspace"))


def _generate_form_filename(form_name: str, form_id: str) -> str:
    """
    Generate filesystem-safe filename from form name.

    Format: {slugified-name}-{first-8-chars-of-uuid}.form.json
    Example: customer-onboarding-a1b2c3d4.form.json

    Args:
        form_name: Human-readable form name
        form_id: Form UUID

    Returns:
        Slugified filename
    """
    # Convert to lowercase and replace non-alphanumeric chars with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', form_name.lower()).strip('-')
    # Limit length and add short UUID prefix for uniqueness
    short_id = str(form_id)[:8]
    return f"{slug[:50]}-{short_id}.form.json"


def _form_schema_to_fields(form_schema: dict, form_id: UUID) -> list[FormFieldORM]:
    """
    Convert FormSchema dict to list of FormField ORM objects.

    Args:
        form_schema: FormSchema dict with 'fields' key
        form_id: Parent form UUID

    Returns:
        List of FormField ORM objects
    """
    from shared.models import FormSchema

    # Validate structure
    schema = FormSchema.model_validate(form_schema)

    fields = []
    for position, field in enumerate(schema.fields):
        field_orm = FormFieldORM(
            form_id=form_id,
            name=field.name,
            label=field.label,
            type=field.type.value,
            required=field.required,
            position=position,
            placeholder=field.placeholder,
            help_text=field.help_text,
            default_value=field.default_value,
            options=field.options,
            data_provider=field.data_provider,
            data_provider_inputs=field.data_provider_inputs,
            visibility_expression=field.visibility_expression,
            validation=field.validation,
            allowed_types=field.allowed_types,
            multiple=field.multiple,
            max_size_mb=field.max_size_mb,
            content=field.content,
        )
        fields.append(field_orm)

    return fields


def _fields_to_form_schema(fields: list[FormFieldORM]) -> dict:
    """
    Convert list of FormField ORM objects to FormSchema dict.

    Args:
        fields: List of FormField ORM objects (should be ordered by position)

    Returns:
        FormSchema dict with 'fields' key
    """
    fields_data = []
    for field in fields:
        field_data = {
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
        if field.data_provider:
            field_data["data_provider"] = field.data_provider
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

    return {"fields": fields_data}


async def _write_form_to_file(form: FormORM) -> str:
    """
    Write form to file system as *.form.json.

    Uses async file operations to avoid blocking the event loop.

    Args:
        form: Form ORM instance

    Returns:
        Workspace-relative file path (e.g., 'forms/my-form-abc123.form.json')

    Raises:
        Exception: If file write fails
    """
    # Generate filename
    filename = _generate_form_filename(form.name, str(form.id))
    # Forms are stored in the 'forms' subdirectory
    forms_dir = WORKSPACE_LOCATION / "forms"
    await aiofiles.os.makedirs(forms_dir, exist_ok=True)
    file_path = forms_dir / filename

    # Build form JSON (using snake_case for consistency with Python conventions)
    # Convert fields to form_schema format for file storage
    form_schema = _fields_to_form_schema(form.fields)

    form_data = {
        "id": str(form.id),
        "name": form.name,
        "description": form.description,
        "linked_workflow": form.linked_workflow,
        "form_schema": form_schema,
        "is_active": form.is_active,
        "is_global": form.organization_id is None,
        "org_id": str(form.organization_id) if form.organization_id else "GLOBAL",
        "access_level": form.access_level.value if form.access_level else "role_based",
        "created_by": form.created_by,
        "created_at": form.created_at.isoformat() + "Z",
        "updated_at": form.updated_at.isoformat() + "Z",
        "launch_workflow_id": form.launch_workflow_id,
        "allowed_query_params": form.allowed_query_params,
        "default_launch_params": form.default_launch_params,
    }

    # Write to file (atomic write via temp file)
    temp_file = file_path.with_suffix('.tmp')
    try:
        async with aiofiles.open(temp_file, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(form_data, indent=2))
        await aiofiles.os.replace(str(temp_file), str(file_path))
        logger.info(f"Wrote form to file: forms/{filename}")
        # Return workspace-relative path
        return f"forms/{filename}"
    except Exception as e:
        # Clean up temp file if it exists
        if await aiofiles.os.path.exists(str(temp_file)):
            await aiofiles.os.remove(str(temp_file))
        raise e


async def _update_form_file(form: FormORM, old_file_path: str | None) -> str:
    """
    Update form file, handling renames if the form name changed.

    Uses async file operations to avoid blocking the event loop.

    Args:
        form: Updated form ORM instance
        old_file_path: Previous workspace-relative file path (if known)

    Returns:
        New workspace-relative file path
    """
    # Generate new filename
    new_filename = _generate_form_filename(form.name, str(form.id))
    new_file_path = WORKSPACE_LOCATION / "forms" / new_filename

    # If we have the old file path and it's different, delete the old file
    if old_file_path:
        old_full_path = WORKSPACE_LOCATION / old_file_path
        if await aiofiles.os.path.exists(str(old_full_path)) and old_full_path != new_file_path:
            await aiofiles.os.remove(str(old_full_path))
            logger.info(f"Deleted old form file: {old_file_path}")

    # Write the updated form
    return await _write_form_to_file(form)


async def _deactivate_form_file(form_id: str) -> None:
    """
    Deactivate form file by setting isActive=false.

    Uses async file operations to avoid blocking the event loop.

    Args:
        form_id: Form UUID
    """
    # Find the form file by scanning for the ID in the forms directory
    forms_dir = WORKSPACE_LOCATION / "forms"
    if not await aiofiles.os.path.exists(str(forms_dir)):
        logger.warning(f"Forms directory not found, cannot deactivate form: {form_id}")
        return

    # List form files asynchronously
    try:
        all_files = await aiofiles.os.listdir(str(forms_dir))
        form_files = [f for f in all_files if f.endswith('.form.json')]
    except OSError as e:
        logger.warning(f"Error listing forms directory: {e}")
        return

    for filename in form_files:
        form_file = forms_dir / filename
        try:
            async with aiofiles.open(form_file, mode='r', encoding='utf-8') as f:
                content = await f.read()
            data = json.loads(content)
            if data.get("id") == form_id:
                # Update is_active to false
                data["is_active"] = False
                data["updated_at"] = datetime.utcnow().isoformat() + "Z"

                # Write back atomically
                temp_file = form_file.with_suffix('.tmp')
                async with aiofiles.open(temp_file, mode='w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, indent=2))
                await aiofiles.os.replace(str(temp_file), str(form_file))
                logger.info(f"Deactivated form file: forms/{filename}")
                return
        except Exception as e:
            logger.warning(f"Error processing form file {form_file}: {e}")
            continue

    logger.warning(f"Form file not found for deactivation: {form_id}")


@router.get(
    "",
    response_model=list[FormPublic],
    summary="List forms",
    description="List all forms visible to the user based on their permissions",
)
async def list_forms(
    ctx: Context,
    db: DbSession,
) -> list[FormPublic]:
    """List all forms visible to the user.

    - Platform admins see all forms
    - Org users see: their org's forms + global forms (org_id IS NULL)
    - Access is further filtered by access_level (public, authenticated, role_based)

    This endpoint uses a single optimized query with SQL-level filtering
    instead of multiple roundtrips and Python filtering.
    """
    # Platform admins see all forms
    if ctx.user.is_superuser:
        query = select(FormORM).options(selectinload(FormORM.fields)).order_by(FormORM.name)
        result = await db.execute(query)
        return [FormPublic.model_validate(f) for f in result.scalars().all()]

    # Build subquery for forms accessible via user's roles
    # This finds form IDs where the user has a matching role
    user_accessible_forms_subquery = (
        select(FormRoleORM.form_id)
        .join(UserRoleORM, UserRoleORM.role_id == FormRoleORM.role_id)
        .where(UserRoleORM.user_id == ctx.user.user_id)
        .distinct()
    )

    # Build main query with all access logic in SQL
    # A form is visible if:
    # 1. It's active AND
    # 2. It belongs to user's org OR is global (org_id IS NULL) AND
    # 3. Access level is 'public' OR 'authenticated' OR
    #    (access level is 'role_based' AND user has a matching role)
    if ctx.org_id:
        org_filter = or_(
            FormORM.organization_id == ctx.org_id,
            FormORM.organization_id.is_(None)
        )
    else:
        # User has no org - only global forms visible
        org_filter = FormORM.organization_id.is_(None)

    query = (
        select(FormORM)
        .options(selectinload(FormORM.fields))
        .where(FormORM.is_active)
        .where(org_filter)
        .where(
            or_(
                FormORM.access_level == "public",
                FormORM.access_level == "authenticated",
                # role_based access: user must have a role assigned to the form
                # Also include forms with NULL access_level (defaults to role_based)
                or_(
                    FormORM.access_level == "role_based",
                    FormORM.access_level.is_(None)
                ) & FormORM.id.in_(user_accessible_forms_subquery)
            )
        )
        .order_by(FormORM.name)
    )

    result = await db.execute(query)
    return [FormPublic.model_validate(f) for f in result.scalars().all()]


@router.post(
    "",
    response_model=FormPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new form",
    description="Create a new form (Platform admin only)",
)
async def create_form(
    request: FormCreate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> FormPublic:
    """
    Create a new form.

    Forms are persisted to BOTH database AND file system:
    - Database write provides immediate availability
    - File write enables version control and deployment portability
    - Discovery watcher will sync file to DB on next scan
    """
    now = datetime.utcnow()

    # Create form record
    form = FormORM(
        name=request.name,
        description=request.description,
        linked_workflow=request.linked_workflow,
        launch_workflow_id=request.launch_workflow_id,
        default_launch_params=request.default_launch_params,
        allowed_query_params=request.allowed_query_params,
        access_level=request.access_level,
        is_active=True,
        created_by=ctx.user.email,
        created_at=now,
        updated_at=now,
    )

    db.add(form)
    await db.flush()  # Get the form ID

    # Convert form_schema to FormField records
    form_schema_data: dict = request.form_schema  # type: ignore[assignment]
    if hasattr(form_schema_data, 'model_dump'):
        form_schema_data = form_schema_data.model_dump()  # type: ignore[union-attr]

    field_records = _form_schema_to_fields(form_schema_data, form.id)
    for field in field_records:
        db.add(field)

    await db.flush()

    # Reload form with fields eager-loaded
    result = await db.execute(
        select(FormORM)
        .options(selectinload(FormORM.fields))
        .where(FormORM.id == form.id)
    )
    form = result.scalar_one()

    # Write to file system (dual-write pattern)
    try:
        file_path = await _write_form_to_file(form)
        # Store file path in database for tracking
        form.file_path = file_path
        await db.flush()
    except Exception as e:
        logger.error(f"Failed to write form file for {form.id}: {e}", exc_info=True)
        # Continue - database write succeeded, file write can be retried by discovery watcher

    logger.info(f"Created form {form.id}: {form.name} (file: {form.file_path})")

    # Invalidate cache after successful create
    if CACHE_INVALIDATION_AVAILABLE and invalidate_form:
        org_id = str(form.organization_id) if form.organization_id else None
        await invalidate_form(org_id, str(form.id))

    return FormPublic.model_validate(form)


@router.get(
    "/{form_id}",
    response_model=FormPublic,
    summary="Get form by ID",
    description="Get a specific form by ID. User must have access to the form.",
)
async def get_form(
    form_id: UUID,
    ctx: Context,
    db: DbSession,
) -> FormPublic:
    """Get a specific form by ID."""
    result = await db.execute(
        select(FormORM)
        .options(selectinload(FormORM.fields))
        .where(FormORM.id == form_id)
    )
    form = result.scalar_one_or_none()

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found",
        )

    # Check access - admins can see all forms
    if ctx.user.is_superuser:
        return FormPublic.model_validate(form)

    # Non-admins can only see active forms
    if not form.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found",
        )

    # Check org access - user can access their org's forms OR global forms (org_id is NULL)
    if form.organization_id is not None and form.organization_id != ctx.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to form",
        )

    # Check access level
    access_level = form.access_level or "role_based"
    if access_level == "public" or access_level == "authenticated":
        return FormPublic.model_validate(form)

    # Role-based: check if user has a role assigned to this form
    role_query = select(UserRoleORM.role_id).where(UserRoleORM.user_id == ctx.user.user_id)
    role_result = await db.execute(role_query)
    user_role_ids = list(role_result.scalars().all())

    if user_role_ids:
        form_role_query = select(FormRoleORM).where(
            FormRoleORM.form_id == form_id,
            FormRoleORM.role_id.in_(user_role_ids),
        )
        form_role_result = await db.execute(form_role_query)
        if form_role_result.scalar_one_or_none() is not None:
            return FormPublic.model_validate(form)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to form",
    )


@router.patch(
    "/{form_id}",
    response_model=FormPublic,
    summary="Update a form",
    description="Update an existing form (Platform admin only)",
)
async def update_form(
    form_id: UUID,
    request: FormUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> FormPublic:
    """
    Update a form.

    Updates are written to BOTH database AND file system.
    If the form name changes, the file is renamed to match.
    """
    result = await db.execute(
        select(FormORM)
        .options(selectinload(FormORM.fields))
        .where(FormORM.id == form_id)
    )
    form = result.scalar_one_or_none()

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found",
        )

    # Track old file path for cleanup
    old_file_path = form.file_path

    if request.name is not None:
        form.name = request.name
    if request.description is not None:
        form.description = request.description
    if request.linked_workflow is not None:
        form.linked_workflow = request.linked_workflow
    if request.launch_workflow_id is not None:
        form.launch_workflow_id = request.launch_workflow_id
    if request.default_launch_params is not None:
        form.default_launch_params = request.default_launch_params
    if request.allowed_query_params is not None:
        form.allowed_query_params = request.allowed_query_params
    if request.form_schema is not None:
        # Delete all existing fields and recreate them
        await db.execute(
            select(FormFieldORM).where(FormFieldORM.form_id == form_id)
        )
        for field in form.fields:
            await db.delete(field)
        await db.flush()

        # Convert new form_schema to FormField records
        form_schema_data: dict = request.form_schema  # type: ignore[assignment]
        if hasattr(form_schema_data, 'model_dump'):
            form_schema_data = form_schema_data.model_dump()  # type: ignore[union-attr]

        field_records = _form_schema_to_fields(form_schema_data, form_id)
        for field in field_records:
            db.add(field)

    if request.is_active is not None:
        form.is_active = request.is_active
    if request.access_level is not None:
        form.access_level = request.access_level

    form.updated_at = datetime.utcnow()

    await db.flush()

    # Reload form with fields eager-loaded
    result = await db.execute(
        select(FormORM)
        .options(selectinload(FormORM.fields))
        .where(FormORM.id == form_id)
    )
    form = result.scalar_one()

    # Update file system (dual-write pattern)
    try:
        new_file_path = await _update_form_file(form, old_file_path)
        form.file_path = new_file_path
        await db.flush()
    except Exception as e:
        logger.error(f"Failed to update form file for {form_id}: {e}", exc_info=True)
        # Continue - database write succeeded

    logger.info(f"Updated form {form_id} (file: {form.file_path})")

    # Invalidate cache after successful update
    if CACHE_INVALIDATION_AVAILABLE and invalidate_form:
        org_id = str(form.organization_id) if form.organization_id else None
        await invalidate_form(org_id, str(form_id))

    return FormPublic.model_validate(form)


# Keep PUT for backwards compatibility
@router.put(
    "/{form_id}",
    response_model=FormPublic,
    summary="Update a form",
    description="Update an existing form (Platform admin only)",
    include_in_schema=False,  # Hide from OpenAPI, use PATCH instead
)
async def update_form_put(
    form_id: UUID,
    request: FormUpdate,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> FormPublic:
    """Update a form (PUT - for backwards compatibility)."""
    return await update_form(form_id, request, ctx, user, db)


@router.delete(
    "/{form_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a form",
    description="Soft delete a form (Platform admin only)",
)
async def delete_form(
    form_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """
    Soft delete a form.

    Sets isActive=false in BOTH database AND file system.
    The form file remains for version control, but is marked inactive.
    """
    result = await db.execute(select(FormORM).where(FormORM.id == form_id))
    form = result.scalar_one_or_none()

    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found",
        )

    form.is_active = False
    form.updated_at = datetime.utcnow()

    await db.flush()

    # Deactivate in file system (dual-write pattern)
    try:
        await _deactivate_form_file(str(form_id))
    except Exception as e:
        logger.error(f"Failed to deactivate form file for {form_id}: {e}", exc_info=True)
        # Continue - database write succeeded

    logger.info(f"Soft deleted form {form_id}")

    # Invalidate cache
    if CACHE_INVALIDATION_AVAILABLE and invalidate_form:
        org_id = str(form.organization_id) if form.organization_id else None
        await invalidate_form(org_id, str(form_id))


# =============================================================================
# Form Execution
# =============================================================================


async def _check_form_access(
    db: DbSession,
    form: FormORM,
    user_id: UUID,
    is_superuser: bool,
) -> bool:
    """
    Check if user has access to execute a form.

    Access levels:
    - 'public': Anyone can access (not recommended for production)
    - 'authenticated': Any logged-in user can access
    - 'role_based': User must be assigned to a role that has this form
    """
    # Platform admins always have access
    if is_superuser:
        return True

    access_level = form.access_level or "authenticated"

    if access_level == "public":
        return True

    if access_level == "authenticated":
        return True  # User is already authenticated to reach this point

    if access_level == "role_based":
        # Check if user has a role that is assigned to this form
        # 1. Get all roles the user has
        user_roles_query = select(UserRoleORM.role_id).where(
            UserRoleORM.user_id == user_id
        )
        user_roles_result = await db.execute(user_roles_query)
        user_role_ids = list(user_roles_result.scalars().all())

        if not user_role_ids:
            return False

        # 2. Check if any of those roles have this form assigned
        form_role_query = select(FormRoleORM).where(
            FormRoleORM.form_id == form.id,
            FormRoleORM.role_id.in_(user_role_ids),
        )
        form_role_result = await db.execute(form_role_query)
        has_access = form_role_result.scalar_one_or_none() is not None

        return has_access

    # Unknown access level - deny by default
    return False


@router.post(
    "/{form_id}/execute",
    response_model=WorkflowExecutionResponse,
    summary="Execute a form",
    description="Execute the workflow linked to a form. Requires appropriate access based on form's access_level.",
)
async def execute_form(
    form_id: UUID,
    ctx: Context,
    user: CurrentActiveUser,
    db: DbSession,
    input_data: dict = Body(default={}),
) -> WorkflowExecutionResponse:
    """
    Execute the workflow linked to a form.

    This endpoint allows org users to execute workflows through forms they have access to.
    Access control is based on the form's access_level:
    - 'authenticated': Any logged-in user can execute
    - 'role_based': User must be assigned to a role that has this form
    """
    from shared.context import ExecutionContext as SharedContext, Organization
    from shared.handlers.workflows_handlers import execute_workflow_internal
    from shared.models import ExecutionStatus

    # Get the form
    result = await db.execute(select(FormORM).where(FormORM.id == form_id))
    form = result.scalar_one_or_none()

    if not form or not form.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form not found",
        )

    # Check access
    has_access = await _check_form_access(db, form, ctx.user.user_id, ctx.user.is_superuser)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this form",
        )

    # Form must have a linked workflow
    if not form.linked_workflow:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Form has no linked workflow",
        )

    # Merge default launch params with provided input
    merged_params = {**(form.default_launch_params or {}), **input_data}

    # Create organization object if org_id is set
    org = None
    if ctx.org_id:
        org = Organization(id=str(ctx.org_id), name="", is_active=True)

    # Create shared context compatible with existing handlers
    shared_ctx = SharedContext(
        user_id=str(ctx.user.user_id),
        name=ctx.user.name,
        email=ctx.user.email,
        scope=str(ctx.org_id) if ctx.org_id else "GLOBAL",
        organization=org,
        is_platform_admin=ctx.user.is_superuser,
        is_function_key=False,
        execution_id=str(uuid4()),
    )

    try:
        # Execute the linked workflow
        result_dict, status_code = await execute_workflow_internal(
            context=shared_ctx,
            workflow_name=form.linked_workflow,
            parameters=merged_params,
            form_id=str(form.id),
            transient=False,
        )

        # Convert to response model
        if status_code >= 400:
            # Error response
            raise HTTPException(
                status_code=status_code,
                detail=result_dict.get("message", "Execution failed"),
            )

        # Success or pending response
        execution_id = result_dict.get("executionId", "")
        status_str = result_dict.get("status", "Pending")

        # Map status string to enum
        status_map = {
            "Pending": ExecutionStatus.PENDING,
            "Running": ExecutionStatus.RUNNING,
            "Success": ExecutionStatus.SUCCESS,
            "Failed": ExecutionStatus.FAILED,
        }
        exec_status = status_map.get(status_str, ExecutionStatus.PENDING)

        # Note: WebSocket broadcast removed - worker handles this when it picks up the job
        # This enables Redis-first architecture where API returns immediately

        logger.info(f"Form {form_id} executed by user {ctx.user.email}, execution_id={execution_id}")

        return WorkflowExecutionResponse(
            execution_id=execution_id,
            status=exec_status,
            result=result_dict.get("result"),
            error=result_dict.get("error"),
            error_type=result_dict.get("errorType"),
            duration_ms=result_dict.get("durationMs"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing form {form_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute form",
        )
