"""
App Code Files Router

CRUD operations for code source files in code engine applications.
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
    AppCodeFileCreate,
    AppCodeFileListResponse,
    AppCodeFileResponse,
    AppCodeFileUpdate,
)
from src.models.orm.applications import Application, AppCodeFile
from src.routers.applications import ApplicationRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/applications/{app_id}/versions/{version_id}/files",
    tags=["App Code Files"],
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


async def get_code_file_or_404(
    ctx: Context,
    version_id: UUID,
    file_path: str,
) -> AppCodeFile:
    """Get code file by version_id and path or raise 404."""
    query = select(AppCodeFile).where(
        AppCodeFile.app_version_id == version_id,
        AppCodeFile.path == file_path,
    )
    result = await ctx.db.execute(query)
    code_file = result.scalar_one_or_none()

    if not code_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' not found",
        )

    return code_file


def code_file_to_response(code_file: AppCodeFile) -> AppCodeFileResponse:
    """Convert ORM model to response."""
    return AppCodeFileResponse(
        id=code_file.id,
        app_version_id=code_file.app_version_id,
        path=code_file.path,
        source=code_file.source,
        compiled=code_file.compiled,
        created_at=code_file.created_at,
        updated_at=code_file.updated_at,
    )


# =============================================================================
# Code File CRUD Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AppCodeFileListResponse,
    summary="List code files",
)
async def list_code_files(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppCodeFileListResponse:
    """List all code files for a specific app version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    query = (
        select(AppCodeFile)
        .where(AppCodeFile.app_version_id == version_id)
        .order_by(AppCodeFile.path)
    )
    result = await ctx.db.execute(query)
    files = list(result.scalars().all())

    return AppCodeFileListResponse(
        files=[code_file_to_response(f) for f in files],
        total=len(files),
    )


@router.get(
    "/{file_path:path}",
    response_model=AppCodeFileResponse,
    summary="Get code file by path",
)
async def get_code_file(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppCodeFileResponse:
    """Get a specific code file by its path."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    code_file = await get_code_file_or_404(ctx, version_id, file_path)

    return code_file_to_response(code_file)


@router.post(
    "",
    response_model=AppCodeFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create code file",
)
async def create_code_file(
    data: AppCodeFileCreate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppCodeFileResponse:
    """Create a new code file in the specified version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    # Check for duplicate path in this version
    existing_query = select(AppCodeFile).where(
        AppCodeFile.app_version_id == version_id,
        AppCodeFile.path == data.path,
    )
    existing = await ctx.db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File with path '{data.path}' already exists",
        )

    # Create the file
    code_file = AppCodeFile(
        app_version_id=version_id,
        path=data.path,
        source=data.source,
    )
    ctx.db.add(code_file)
    await ctx.db.flush()
    await ctx.db.refresh(code_file)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="code_file",
        entity_id=data.path,
    )

    logger.info(f"Created code file '{data.path}' in app {app_id} version {version_id}")
    return code_file_to_response(code_file)


@router.patch(
    "/{file_path:path}",
    response_model=AppCodeFileResponse,
    summary="Update code file",
)
async def update_code_file(
    data: AppCodeFileUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppCodeFileResponse:
    """Update a code file's source or compiled output."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    code_file = await get_code_file_or_404(ctx, version_id, file_path)

    # Apply updates
    if data.source is not None:
        code_file.source = data.source
    if data.compiled is not None:
        code_file.compiled = data.compiled

    await ctx.db.flush()
    await ctx.db.refresh(code_file)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="code_file",
        entity_id=file_path,
    )

    logger.info(f"Updated code file '{file_path}' in app {app_id} version {version_id}")
    return code_file_to_response(code_file)


@router.delete(
    "/{file_path:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete code file",
)
async def delete_code_file(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> None:
    """Delete a code file."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    code_file = await get_code_file_or_404(ctx, version_id, file_path)

    await ctx.db.delete(code_file)
    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="code_file",
        entity_id=file_path,
    )

    logger.info(f"Deleted code file '{file_path}' from app {app_id} version {version_id}")
