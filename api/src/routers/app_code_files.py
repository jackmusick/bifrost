"""
App Code Files Router

CRUD operations for code source files in code engine applications.
Files are versioned - each file belongs to a specific app version.

Endpoints use UUID for app_id and version_id, with path as file identifier.
Path can contain slashes (e.g., 'pages/clients/[id]').

Path conventions:
- Root: _layout, _providers only
- pages/: index, _layout, [param]/, named subfolders
- components/: files or subfolders (free naming)
- modules/: files or subfolders (free naming)
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.core.exceptions import AccessDeniedError
from src.core.pubsub import publish_app_code_file_update
from src.models.contracts.applications import (
    AppFileCreate,
    AppFileListResponse,
    AppFileResponse,
    AppFileUpdate,
)
from src.models.orm.applications import Application, AppFile
from src.routers.applications import ApplicationRepository

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/applications/{app_id}/versions/{version_id}/files",
    tags=["App Code Files"],
)


# =============================================================================
# Path Validation
# =============================================================================

# Valid root-level files (no directory prefix)
ROOT_ALLOWED_FILES = {"_layout", "_providers"}

# Valid top-level directories
VALID_TOP_DIRS = {"pages", "components", "modules"}

# Pattern for dynamic route segments like [id] or [slug], with optional .ts/.tsx extension
DYNAMIC_SEGMENT_PATTERN = re.compile(r"^\[[\w-]+\](\.tsx?)?$")

# Pattern for valid folder names (alphanumeric, underscore, hyphen)
VALID_NAME_PATTERN = re.compile(r"^[\w-]+$")

# Pattern for valid file names (requires .ts or .tsx extension)
VALID_FILENAME_PATTERN = re.compile(r"^[\w-]+\.tsx?$")


def validate_file_path(path: str) -> None:
    """Validate file path against conventions.

    Path conventions:
    - Root: only _layout, _providers allowed
    - pages/: index, _layout, [param]/, named subfolders
    - components/: files or subfolders (free naming)
    - modules/: files or subfolders (free naming)

    Raises:
        HTTPException 400 if path is invalid
    """
    if not path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File path cannot be empty",
        )

    # Normalize path (remove leading/trailing slashes)
    path = path.strip("/")

    # Split into segments
    segments = path.split("/")

    # Check for empty segments (double slashes)
    if any(not seg for seg in segments):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path cannot contain empty segments (double slashes)",
        )

    # Root level file (no directory)
    if len(segments) == 1:
        filename = segments[0]

        # Must have .ts or .tsx extension
        if not re.search(r"\.tsx?$", filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Files must have a .ts or .tsx extension",
            )

        # Check root name without extension
        root_name = re.sub(r"\.tsx?$", "", filename)
        if root_name not in ROOT_ALLOWED_FILES:
            allowed = ", ".join(sorted(f"{f}.tsx" for f in ROOT_ALLOWED_FILES))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Root-level file must be one of: {allowed}. "
                f"Use pages/, components/, or modules/ directories for other files.",
            )
        return

    # Check top-level directory
    top_dir = segments[0]
    if top_dir not in VALID_TOP_DIRS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Files must be in one of: {', '.join(sorted(VALID_TOP_DIRS))}. "
            f"Got: '{top_dir}'",
        )

    # Validate remaining segments
    remaining_segments = segments[1:]
    for i, segment in enumerate(remaining_segments):
        is_last_segment = i == len(remaining_segments) - 1

        # Dynamic segments only allowed in pages/
        if DYNAMIC_SEGMENT_PATTERN.match(segment):
            if top_dir != "pages":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Dynamic segments like [{segment[1:-1]}] are only allowed in pages/",
                )
            # For last segment, require extension
            if is_last_segment and not segment.endswith((".ts", ".tsx")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Files must have a .ts or .tsx extension. Got: '{segment}'",
                )
            continue

        # Validate segment name - use filename pattern for last segment
        pattern = VALID_FILENAME_PATTERN if is_last_segment else VALID_NAME_PATTERN
        if not pattern.match(segment):
            if is_last_segment:
                # Check if missing extension
                if VALID_NAME_PATTERN.match(segment):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Files must have a .ts or .tsx extension. Got: '{segment}'",
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid filename '{segment}'. "
                    "Use alphanumeric characters, underscores, hyphens, with .ts or .tsx extension.",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid path segment '{segment}'. "
                "Use only alphanumeric characters, underscores, and hyphens.",
            )

        # Strip extension for special file checks
        segment_name = re.sub(r"\.tsx?$", "", segment)

        # Special files in pages/
        if top_dir == "pages" and segment_name in ("index", "_layout"):
            continue

        # _layout only allowed in pages/ at any level
        if segment_name == "_layout" and top_dir != "pages":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="_layout files are only allowed in pages/",
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
) -> AppFile:
    """Get code file by version_id and path or raise 404."""
    query = select(AppFile).where(
        AppFile.app_version_id == version_id,
        AppFile.path == file_path,
    )
    result = await ctx.db.execute(query)
    code_file = result.scalar_one_or_none()

    if not code_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' not found",
        )

    return code_file


def code_file_to_response(code_file: AppFile) -> AppFileResponse:
    """Convert ORM model to response."""
    return AppFileResponse(
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
    response_model=AppFileListResponse,
    summary="List code files",
)
async def list_code_files(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppFileListResponse:
    """List all code files for a specific app version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    query = (
        select(AppFile)
        .where(AppFile.app_version_id == version_id)
        .order_by(AppFile.path)
    )
    result = await ctx.db.execute(query)
    files = list(result.scalars().all())

    return AppFileListResponse(
        files=[code_file_to_response(f) for f in files],
        total=len(files),
    )


@router.get(
    "/{file_path:path}",
    response_model=AppFileResponse,
    summary="Get code file by path",
)
async def get_code_file(
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppFileResponse:
    """Get a specific code file by its path."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    code_file = await get_code_file_or_404(ctx, version_id, file_path)

    return code_file_to_response(code_file)


@router.post(
    "",
    response_model=AppFileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create code file",
)
async def create_code_file(
    data: AppFileCreate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppFileResponse:
    """Create a new code file in the specified version."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    await validate_version_id(ctx, app, version_id)

    # Validate path conventions
    validate_file_path(data.path)

    # Check for duplicate path in this version
    existing_query = select(AppFile).where(
        AppFile.app_version_id == version_id,
        AppFile.path == data.path,
    )
    existing = await ctx.db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File with path '{data.path}' already exists",
        )

    # Create the file
    code_file = AppFile(
        app_version_id=version_id,
        path=data.path,
        source=data.source,
    )
    ctx.db.add(code_file)
    await ctx.db.flush()
    await ctx.db.refresh(code_file)

    # Emit event for real-time updates with full content
    await publish_app_code_file_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        path=data.path,
        source=data.source,
        compiled=None,
        action="create",
    )

    logger.info(f"Created code file '{data.path}' in app {app_id} version {version_id}")
    return code_file_to_response(code_file)


@router.patch(
    "/{file_path:path}",
    response_model=AppFileResponse,
    summary="Update code file",
)
async def update_code_file(
    data: AppFileUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    version_id: UUID = Path(..., description="Version UUID"),
    file_path: str = Path(..., description="File path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppFileResponse:
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

    # Emit event for real-time updates with full content
    await publish_app_code_file_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        path=file_path,
        source=code_file.source,
        compiled=code_file.compiled,
        action="update",
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
    await publish_app_code_file_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        path=file_path,
        source=None,
        compiled=None,
        action="delete",
    )

    logger.info(f"Deleted code file '{file_path}' from app {app_id} version {version_id}")
