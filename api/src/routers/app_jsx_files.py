"""
App JSX Files Router

CRUD operations for JSX/TypeScript source files in JSX engine applications.
Files are versioned - each file belongs to a specific app version.

Endpoints use UUID for app_id and version_id, with path as file identifier.
Path can contain slashes (e.g., 'pages/clients/[id]').
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.core.exceptions import AccessDeniedError
from src.core.pubsub import publish_app_draft_update
from src.models.contracts.applications import (
    JsxFileCreate,
    JsxFileListResponse,
    JsxFileResponse,
    JsxFileUpdate,
)
from src.models.orm.applications import Application, JsxFile
from src.routers.applications import ApplicationRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/applications/{app_id}/versions/{version_id}/files",
    tags=["App JSX Files"],
)


# =============================================================================
# Helper Functions
# =============================================================================


async def get_application_or_404(ctx: Context, app_id: UUID) -> Application:
    """Get application by UUID with access control.

    Uses ApplicationRepository for cascade scoping and role-based access.
    Returns 404 for both not found and access denied to avoid leaking
    existence information.

    Returns:
        Application if found and accessible

    Raises:
        HTTPException 404 if not found or access denied
    """
    repo = ApplicationRepository(
        session=ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        is_superuser=ctx.user.is_platform_admin,
    )
    try:
        return await repo.can_access(id=app_id)
    except AccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )


async def validate_version_id(
    ctx: Context,
    app: Application,
    version_id: UUID,
) -> None:
    """Validate that version_id belongs to the application.

    Raises HTTPException 404 if version is not valid for this app.
    """
    # Check that the version belongs to this app
    valid_version_ids = {app.draft_version_id, app.active_version_id}
    # Also check versions relationship if we need historical versions
    if version_id not in valid_version_ids:
        # Query to verify the version exists and belongs to this app
        from src.models.orm.applications import AppVersion

        query = select(AppVersion).where(
            AppVersion.id == version_id,
            AppVersion.application_id == app.id,
        )
        result = await ctx.db.execute(query)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version '{version_id}' not found for application '{app.id}'",
            )


async def get_jsx_file_or_404(
    ctx: Context,
    version_id: UUID,
    file_path: str,
) -> JsxFile:
    """Get JSX file by version_id and path or raise 404."""
    query = select(JsxFile).where(
        JsxFile.app_version_id == version_id,
        JsxFile.path == file_path,
    )
    result = await ctx.db.execute(query)
    jsx_file = result.scalar_one_or_none()

    if not jsx_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' not found",
        )

    return jsx_file


def jsx_file_to_response(jsx_file: JsxFile) -> JsxFileResponse:
    """Convert ORM model to response."""
    return JsxFileResponse(
        id=jsx_file.id,
        app_version_id=jsx_file.app_version_id,
        path=jsx_file.path,
        source=jsx_file.source,
        compiled=jsx_file.compiled,
        created_at=jsx_file.created_at,
        updated_at=jsx_file.updated_at,
    )


# =============================================================================
# JSX File CRUD Endpoints
# =============================================================================


@router.get(
    "",
    response_model=JsxFileListResponse,
    summary="List JSX files",
)
async def list_jsx_files(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> JsxFileListResponse:
    """List all JSX files for a specific app version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    query = (
        select(JsxFile)
        .where(JsxFile.app_version_id == version_id)
        .order_by(JsxFile.path)
    )
    result = await ctx.db.execute(query)
    files = list(result.scalars().all())

    return JsxFileListResponse(
        files=[jsx_file_to_response(f) for f in files],
        total=len(files),
    )


@router.get(
    "/{file_path:path}",
    response_model=JsxFileResponse,
    summary="Get JSX file by path",
)
async def get_jsx_file(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> JsxFileResponse:
    """Get a specific JSX file by its path."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    jsx_file = await get_jsx_file_or_404(ctx, version_id, file_path)

    return jsx_file_to_response(jsx_file)


@router.post(
    "",
    response_model=JsxFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create JSX file",
)
async def create_jsx_file(
    data: JsxFileCreate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> JsxFileResponse:
    """Create a new JSX file in the specified version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    # Check for duplicate path in this version
    existing_query = select(JsxFile).where(
        JsxFile.app_version_id == version_id,
        JsxFile.path == data.path,
    )
    existing = await ctx.db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File with path '{data.path}' already exists",
        )

    # Create the file
    jsx_file = JsxFile(
        app_version_id=version_id,
        path=data.path,
        source=data.source,
    )
    ctx.db.add(jsx_file)
    await ctx.db.flush()
    await ctx.db.refresh(jsx_file)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="jsx_file",
        entity_id=data.path,
    )

    logger.info(f"Created JSX file '{data.path}' in app {app_id} version {version_id}")
    return jsx_file_to_response(jsx_file)


@router.patch(
    "/{file_path:path}",
    response_model=JsxFileResponse,
    summary="Update JSX file",
)
async def update_jsx_file(
    data: JsxFileUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> JsxFileResponse:
    """Update a JSX file's source or compiled output."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    jsx_file = await get_jsx_file_or_404(ctx, version_id, file_path)

    # Apply updates
    if data.source is not None:
        jsx_file.source = data.source
    if data.compiled is not None:
        jsx_file.compiled = data.compiled

    await ctx.db.flush()
    await ctx.db.refresh(jsx_file)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="jsx_file",
        entity_id=file_path,
    )

    logger.info(f"Updated JSX file '{file_path}' in app {app_id} version {version_id}")
    return jsx_file_to_response(jsx_file)


@router.delete(
    "/{file_path:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete JSX file",
)
async def delete_jsx_file(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> None:
    """Delete a JSX file."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    jsx_file = await get_jsx_file_or_404(ctx, version_id, file_path)

    await ctx.db.delete(jsx_file)
    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="jsx_file",
        entity_id=file_path,
    )

    logger.info(f"Deleted JSX file '{file_path}' from app {app_id} version {version_id}")
