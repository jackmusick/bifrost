"""
App Code Files Router

CRUD operations for code source files in App Builder applications.

Read/list: served from _apps/{app_id}/preview/ or _apps/{app_id}/live/ in S3.
Write/delete: goes through FileStorageService (_repo/ + file_index), which
also syncs to _apps/{app_id}/preview/.

Endpoints use UUID for app_id with relative file paths.
Path can contain slashes (e.g., 'pages/clients/[id].tsx').

Path conventions:
- Root: _layout, _providers only
- pages/: index, _layout, [param]/, named subfolders
- components/: files or subfolders (free naming)
- modules/: files or subfolders (free naming)
"""

import logging
import re
from enum import Enum
from uuid import UUID

import yaml

from fastapi import APIRouter, HTTPException, Path, status

from src.core.auth import Context, CurrentUser
from src.core.exceptions import AccessDeniedError
from src.models.contracts.applications import (
    AppFileUpdate,
    AppRenderResponse,
    RenderFileResponse,
    SimpleFileListResponse,
    SimpleFileResponse,
)
from src.models.orm.applications import Application
from src.routers.applications import ApplicationRepository
from src.services.app_storage import AppStorageService
from src.core.module_cache import get_module
from src.services.file_index_service import FileIndexService
from src.services.file_storage.service import get_file_storage_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/applications/{app_id}/files",
    tags=["App Code Files"],
)

render_router = APIRouter(
    prefix="/api/applications/{app_id}",
    tags=["App Rendering"],
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

# Validation patterns for npm dependencies
_PKG_NAME_RE = re.compile(r"^(@[a-z0-9-]+/)?[a-z0-9][a-z0-9._-]*$")
_VERSION_RE = re.compile(r"^\^?~?\d+(\.\d+){0,2}$")
_MAX_DEPENDENCIES = 20


def _parse_dependencies(yaml_content: str | None) -> dict[str, str]:
    """Parse and validate dependencies from app.yaml content.

    Returns validated {name: version} dict. Skips invalid entries,
    never raises.
    """
    if not yaml_content:
        return {}

    try:
        data = yaml.safe_load(yaml_content)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    raw_deps = data.get("dependencies")
    if not isinstance(raw_deps, dict):
        return {}

    deps: dict[str, str] = {}
    for name, version in raw_deps.items():
        if len(deps) >= _MAX_DEPENDENCIES:
            break

        name_str = str(name)
        version_str = str(version)

        if not _PKG_NAME_RE.match(name_str):
            logger.warning(f"Skipping invalid package name: {name_str}")
            continue
        if not _VERSION_RE.match(version_str):
            logger.warning(f"Skipping invalid version for {name_str}: {version_str}")
            continue

        deps[name_str] = version_str

    return deps


def _serialize_dependencies(
    deps: dict[str, str], existing_yaml: str | None
) -> str:
    """Serialize dependencies back into app.yaml content.

    Preserves existing non-dependency fields. If no existing YAML,
    creates a minimal file.
    """
    data: dict = {}
    if existing_yaml:
        try:
            parsed = yaml.safe_load(existing_yaml)
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            pass

    if deps:
        data["dependencies"] = deps
    else:
        data.pop("dependencies", None)

    return yaml.dump(data, default_flow_style=False, sort_keys=False)


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


class FileMode(str, Enum):
    draft = "draft"
    live = "live"


def _repo_prefix(slug: str) -> str:
    """Return the _repo/ path prefix for an app slug."""
    return f"apps/{slug}/"


# =============================================================================
# S3-backed App File Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SimpleFileListResponse,
    summary="List app files",
)
async def list_app_files(
    app_id: UUID = Path(..., description="Application UUID"),
    mode: FileMode = FileMode.draft,
    ctx: Context = None,
    user: CurrentUser = None,
) -> SimpleFileListResponse:
    """List all files for an application.

    Source content is read from the file_index (_repo/apps/{slug}/).
    Compiled content is read from _apps/{app_id}/{mode}/.
    The compiled field is only set when it differs from source.
    """
    app = await get_application_or_404(ctx, app_id)
    app_storage = AppStorageService()
    file_index = FileIndexService(ctx.db)

    # Source files live under apps/{slug}/ in the file_index
    repo_prefix = _repo_prefix(app.slug)
    source_paths = await file_index.list_paths(prefix=repo_prefix)

    if not source_paths:
        return SimpleFileListResponse(files=[], total=0)

    storage_mode = "preview" if mode == FileMode.draft else "live"

    # Read source from file_index and compiled from _apps/
    files: list[SimpleFileResponse] = []
    for full_path in sorted(source_paths):
        # Derive relative path by stripping the repo prefix
        rel_path = full_path[len(repo_prefix):]
        if not rel_path:
            continue
        # Skip app.yaml (manifest metadata, not a source file)
        if rel_path == "app.yaml":
            continue

        # Source from Redis→S3 cache
        cached = await get_module(full_path)
        source = cached["content"] if cached else ""

        # Compiled from _apps/{app_id}/{mode}/
        compiled: str | None = None
        try:
            compiled_bytes = await app_storage.read_file(str(app.id), storage_mode, rel_path)
            compiled_str = compiled_bytes.decode("utf-8", errors="replace")
            # Only set compiled if it differs from source
            if compiled_str != source:
                compiled = compiled_str
        except FileNotFoundError:
            pass

        files.append(SimpleFileResponse(path=rel_path, source=source, compiled=compiled))

    return SimpleFileListResponse(files=files, total=len(files))


@router.get(
    "/{file_path:path}",
    response_model=SimpleFileResponse,
    summary="Read a single app file",
)
async def read_app_file(
    app_id: UUID = Path(..., description="Application UUID"),
    file_path: str = Path(..., description="Relative file path (can contain slashes)"),
    mode: FileMode = FileMode.draft,
    ctx: Context = None,
    user: CurrentUser = None,
) -> SimpleFileResponse:
    """Read a single file by relative path.

    Source content is read from the file_index (_repo/apps/{slug}/).
    Compiled content is read from _apps/{app_id}/{mode}/.
    The compiled field is only set when it differs from source.
    """
    app = await get_application_or_404(ctx, app_id)
    app_storage = AppStorageService()

    # Source from Redis→S3 cache
    repo_path = f"{_repo_prefix(app.slug)}{file_path}"
    cached = await get_module(repo_path)
    source = cached["content"] if cached else None
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' not found",
        )

    # Compiled from _apps/{app_id}/{mode}/
    compiled: str | None = None
    storage_mode = "preview" if mode == FileMode.draft else "live"
    try:
        compiled_bytes = await app_storage.read_file(str(app.id), storage_mode, file_path)
        compiled_str = compiled_bytes.decode("utf-8", errors="replace")
        # Only set compiled if it differs from source
        if compiled_str != source:
            compiled = compiled_str
    except FileNotFoundError:
        pass

    return SimpleFileResponse(path=file_path, source=source, compiled=compiled)


@router.put(
    "/{file_path:path}",
    response_model=SimpleFileResponse,
    summary="Create or update an app file",
)
async def write_app_file(
    data: AppFileUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    file_path: str = Path(..., description="Relative file path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> SimpleFileResponse:
    """Create or update a file at the given path.

    Validates the path, then writes via FileStorageService (which handles
    S3 _repo/ storage, file_index update, pubsub, and preview sync).
    """
    app = await get_application_or_404(ctx, app_id)

    # Validate path conventions
    validate_file_path(file_path)

    prefix = _repo_prefix(app.slug)
    full_path = f"{prefix}{file_path}"
    source = data.source or ""

    storage = get_file_storage_service(ctx.db)
    await storage.write_file(
        path=full_path,
        content=source.encode("utf-8"),
        updated_by=user.email or "unknown",
    )

    # Compile server-side and return compiled code in the response
    compiled_js: str | None = None
    if file_path.endswith((".tsx", ".ts")):
        from src.services.app_compiler import AppCompilerService
        compiler = AppCompilerService()
        result = await compiler.compile_file(source, file_path)
        if result.success:
            compiled_js = result.compiled

    logger.info(f"Wrote app file '{file_path}' for app {app_id} (slug={app.slug})")
    return SimpleFileResponse(path=file_path, source=source, compiled=compiled_js)


@router.delete(
    "/{file_path:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an app file",
)
async def delete_app_file(
    app_id: UUID = Path(..., description="Application UUID"),
    file_path: str = Path(..., description="Relative file path (can contain slashes)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> None:
    """Delete a file at the given path.

    Deletes via FileStorageService (which handles S3 _repo/ deletion,
    file_index cleanup, pubsub, and preview sync).
    """
    app = await get_application_or_404(ctx, app_id)
    prefix = _repo_prefix(app.slug)
    full_path = f"{prefix}{file_path}"

    storage = get_file_storage_service(ctx.db)
    await storage.delete_file(full_path)

    logger.info(f"Deleted app file '{file_path}' from app {app_id} (slug={app.slug})")


# =============================================================================
# Render endpoint — compiled JS only, reads from S3 (_apps/)
# =============================================================================

_COMPILABLE_EXTENSIONS = (".tsx", ".ts")


def _looks_like_jsx(content: str) -> bool:
    """Quick heuristic: uncompiled TSX/TS contains JSX or import statements."""
    return "import " in content or "</" in content or "=>" in content


@render_router.get(
    "/render",
    response_model=AppRenderResponse,
    summary="Get all compiled files for rendering",
)
async def render_app(
    app_id: UUID = Path(..., description="Application UUID"),
    mode: FileMode = FileMode.draft,
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppRenderResponse:
    """Return all files as compiled JS, ready for client-side execution.

    Reads entirely from S3 (_apps/{app_id}/{mode}/).  If any compilable
    files still contain raw TSX/TS (pre-compilation era), the entire app
    is batch-compiled and the results written back to S3.

    Unlike /files, this returns only `path` + `code` (no source).
    """
    app = await get_application_or_404(ctx, app_id)
    app_storage = AppStorageService()
    storage_mode = "preview" if mode == FileMode.draft else "live"
    app_id_str = str(app.id)

    # Read dependencies from app.yaml in file_index (fast DB read, not cached)
    dependencies: dict[str, str] = {}
    try:
        cached = await get_module(f"apps/{app.slug}/app.yaml")
        yaml_content = cached["content"] if cached else None
        dependencies = _parse_dependencies(yaml_content)
    except Exception:
        pass

    # 1. Try Redis cache first
    cached = await app_storage.get_render_cache(app_id_str, storage_mode)
    if cached:
        files = [
            RenderFileResponse(path=p, code=c)
            for p, c in sorted(cached.items())
        ]
        return AppRenderResponse(files=files, total=len(files), dependencies=dependencies)

    # 2. Cache miss — read from S3
    rel_paths = await app_storage.list_files(app_id_str, storage_mode)
    if not rel_paths:
        return AppRenderResponse(files=[], total=0, dependencies=dependencies)

    file_contents: dict[str, str] = {}
    for rel_path in rel_paths:
        if rel_path == "app.yaml":
            continue
        content_bytes = await app_storage.read_file(app_id_str, storage_mode, rel_path)
        file_contents[rel_path] = content_bytes.decode("utf-8", errors="replace")

    # 3. If any compilable files look uncompiled, batch-compile and write back
    needs_compile = [
        rel for rel, content in file_contents.items()
        if rel.endswith(_COMPILABLE_EXTENSIONS) and _looks_like_jsx(content)
    ]

    if needs_compile:
        from src.services.app_compiler import AppCompilerService

        compiler = AppCompilerService()
        batch_input = [
            {"path": rel, "source": file_contents[rel]}
            for rel in needs_compile
        ]

        results = await compiler.compile_batch(batch_input)
        for result in results:
            if result.success and result.compiled:
                file_contents[result.path] = result.compiled
                await app_storage.write_preview_file(
                    app_id_str,
                    result.path,
                    result.compiled.encode("utf-8"),
                )

        logger.info(
            f"On-demand compiled {len(needs_compile)} files for app {app_id}"
        )

    # 4. Warm the Redis cache
    await app_storage.set_render_cache(app_id_str, storage_mode, file_contents)

    # 5. Build response
    files = [
        RenderFileResponse(path=rel_path, code=code)
        for rel_path, code in sorted(file_contents.items())
    ]

    return AppRenderResponse(files=files, total=len(files), dependencies=dependencies)


# =============================================================================
# Dependencies endpoints — read/write app.yaml dependencies section
# =============================================================================


@render_router.get(
    "/dependencies",
    response_model=dict[str, str],
    summary="Get app dependencies",
)
async def get_dependencies(
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> dict[str, str]:
    """Return the validated dependencies dict from app.yaml."""
    app = await get_application_or_404(ctx, app_id)
    cached = await get_module(f"apps/{app.slug}/app.yaml")
    yaml_content = cached["content"] if cached else None
    return _parse_dependencies(yaml_content)


@render_router.put(
    "/dependencies",
    response_model=dict[str, str],
    summary="Update app dependencies",
)
async def put_dependencies(
    deps: dict[str, str],
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> dict[str, str]:
    """Replace the dependencies section of app.yaml.

    Validates every package name and version, enforces the max-dependency
    limit, then writes back to app.yaml preserving other fields.
    """
    app = await get_application_or_404(ctx, app_id)

    # Validate
    if len(deps) > _MAX_DEPENDENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many dependencies (max {_MAX_DEPENDENCIES})",
        )
    for name, version in deps.items():
        if not _PKG_NAME_RE.match(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid package name: {name}",
            )
        if not _VERSION_RE.match(version):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid version for {name}: {version}",
            )

    # Read existing app.yaml
    yaml_path = f"apps/{app.slug}/app.yaml"
    cached = await get_module(yaml_path)
    existing_yaml = cached["content"] if cached else None

    # Serialize and write back
    new_yaml = _serialize_dependencies(deps, existing_yaml)
    storage = get_file_storage_service(ctx.db)
    await storage.write_file(
        path=yaml_path,
        content=new_yaml.encode("utf-8"),
        updated_by=user.email or "unknown",
    )

    # Invalidate render cache
    app_storage = AppStorageService()
    await app_storage.invalidate_render_cache(str(app.id))

    logger.info(f"Updated dependencies for app {app_id}: {list(deps.keys())}")
    return deps
