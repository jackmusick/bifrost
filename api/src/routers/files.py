"""
Unified Files Router

File operations with two storage modes:
- local: Local filesystem (CWD, /tmp/bifrost/temp, /tmp/bifrost/uploads)
- cloud: S3 storage (default)

Auth: CurrentSuperuser (platform admins and workflow engine)
"""

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import Context, CurrentSuperuser
from src.core.database import get_db
from src.models import (
    AffectedEntity,
    AvailableReplacement,
    FileContentRequest,
    FileContentResponse,
    FileConflictResponse,
    FileDiagnostic,
    FileMetadata,
    FileType,
    PendingDeactivation,
    SearchRequest,
    SearchResponse,
    WorkflowIdConflict,
)
from src.services.editor.search import search_files_db
from src.services.file_backend import get_backend
from src.services.file_storage import FileStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["Files"])


# =============================================================================
# Request Models with Mode Parameter
# =============================================================================

Location = Literal["workspace", "temp", "uploads"]
Mode = Literal["local", "cloud"]


class FileReadRequest(BaseModel):
    """Request to read a file."""
    path: str = Field(..., description="File path relative to location root")
    location: Location = Field(default="workspace", description="Storage location")
    mode: Mode = Field(default="cloud", description="Storage mode: local or cloud")
    binary: bool = Field(default=False, description="If true, return base64-encoded content")


class FileWriteRequest(BaseModel):
    """Request to write a file."""
    path: str = Field(..., description="File path relative to location root")
    content: str = Field(..., description="File content (text or base64 for binary)")
    location: Location = Field(default="workspace", description="Storage location")
    mode: Mode = Field(default="cloud", description="Storage mode: local or cloud")
    binary: bool = Field(default=False, description="If true, content is base64-encoded")


class FileDeleteRequest(BaseModel):
    """Request to delete a file."""
    path: str = Field(..., description="File path relative to location root")
    location: Location = Field(default="workspace", description="Storage location")
    mode: Mode = Field(default="cloud", description="Storage mode: local or cloud")


class FileListRequest(BaseModel):
    """Request to list files."""
    directory: str = Field(default="", description="Directory path relative to location root")
    location: Location = Field(default="workspace", description="Storage location")
    mode: Mode = Field(default="cloud", description="Storage mode: local or cloud")


class FileExistsRequest(BaseModel):
    """Request to check file existence."""
    path: str = Field(..., description="File path relative to location root")
    location: Location = Field(default="workspace", description="Storage location")
    mode: Mode = Field(default="cloud", description="Storage mode: local or cloud")


class FileReadResponse(BaseModel):
    """Response for file read."""
    content: str = Field(..., description="File content (text or base64)")
    binary: bool = Field(default=False, description="True if content is base64-encoded")


class FileListResponse(BaseModel):
    """Response for file listing."""
    files: list[str] = Field(..., description="List of file/folder paths")


class FileExistsResponse(BaseModel):
    """Response for file existence check."""
    exists: bool = Field(..., description="True if file exists")


# =============================================================================
# Basic CRUD Endpoints (SDK-focused)
# =============================================================================


@router.post("/read", response_model=FileReadResponse)
async def read_file(
    request: FileReadRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> FileReadResponse:
    """Read a file from workspace, temp, or uploads."""
    try:
        backend = get_backend(request.mode, db)
        content = await backend.read(request.path, request.location)

        if request.binary:
            return FileReadResponse(content=base64.b64encode(content).decode(), binary=True)
        return FileReadResponse(content=content.decode("utf-8"), binary=False)

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {request.path}",
        )
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is binary. Use binary=true to read as base64.",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/write", status_code=status.HTTP_204_NO_CONTENT)
async def write_file(
    request: FileWriteRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Write a file to workspace, temp, or uploads."""
    try:
        backend = get_backend(request.mode, db)

        if request.binary:
            content = base64.b64decode(request.content)
        else:
            content = request.content.encode("utf-8")

        updated_by = user.email if user else "system"
        await backend.write(request.path, content, request.location, updated_by)

        logger.info(f"Wrote file: {request.path} ({len(content)} bytes, mode={request.mode}, location={request.location})")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    request: FileDeleteRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a file from workspace, temp, or uploads."""
    try:
        backend = get_backend(request.mode, db)
        await backend.delete(request.path, request.location)

        logger.info(f"Deleted file: {request.path} (mode={request.mode}, location={request.location})")

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {request.path}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/list", response_model=FileListResponse)
async def list_files_simple(
    request: FileListRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> FileListResponse:
    """List files in a directory (simple SDK-focused endpoint)."""
    try:
        backend = get_backend(request.mode, db)
        files = await backend.list(request.directory, request.location)
        return FileListResponse(files=files)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/exists", response_model=FileExistsResponse)
async def file_exists(
    request: FileExistsRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> FileExistsResponse:
    """Check if a file exists."""
    try:
        backend = get_backend(request.mode, db)
        exists = await backend.exists(request.path, request.location)
        return FileExistsResponse(exists=exists)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Editor Endpoints (Cloud mode only, with rich metadata)
# These endpoints are used by the browser-based editor and maintain
# backward compatibility with /api/editor/files/* functionality.
# =============================================================================


@router.get(
    "/editor",
    response_model=list[FileMetadata],
    summary="List directory contents (editor)",
)
async def list_files_editor(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="Directory path relative to workspace root"),
    recursive: bool = Query(default=False, description="If true, return all files recursively"),
    db: AsyncSession = Depends(get_db),
) -> list[FileMetadata]:
    """
    List files and folders in a directory with rich metadata.

    Cloud mode only - used by browser editor.
    """
    try:
        storage = FileStorageService(db)
        workspace_files = await storage.list_files(path, recursive=recursive)

        files = []
        for wf in workspace_files:
            is_folder = wf.path.endswith("/")
            clean_path = wf.path.rstrip("/") if is_folder else wf.path
            files.append(FileMetadata(
                path=clean_path,
                name=clean_path.split("/")[-1],
                type=FileType.FOLDER if is_folder else FileType.FILE,
                size=wf.size_bytes if not is_folder else None,
                extension=wf.path.split(".")[-1] if "." in wf.path and not is_folder else None,
                modified=wf.updated_at.isoformat() if wf.updated_at else datetime.now(timezone.utc).isoformat(),
                entity_type=wf.entity_type if not is_folder else None,
                entity_id=str(wf.entity_id) if wf.entity_id and not is_folder else None,
            ))
        return files

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Directory not found: {path}")


@router.get(
    "/editor/content",
    response_model=FileContentResponse,
    summary="Read file content (editor)",
)
async def get_file_content_editor(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="File path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> FileContentResponse:
    """
    Read file content with rich metadata.

    Cloud mode only - used by browser editor.
    """
    try:
        storage = FileStorageService(db)
        content, file_record = await storage.read_file(path)

        # Determine encoding
        encoding = "utf-8"
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            encoding = "base64"
            content_str = base64.b64encode(content).decode("ascii")

        etag = hashlib.md5(content).hexdigest()

        return FileContentResponse(
            path=path,
            content=content_str,
            encoding=encoding,
            size=len(content),
            etag=etag,
            modified=file_record.updated_at.isoformat() if file_record else datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {path}")


@router.put(
    "/editor/content",
    response_model=FileContentResponse,
    summary="Write file content (editor)",
    responses={409: {"model": FileConflictResponse, "description": "File conflict"}},
)
async def put_file_content_editor(
    request: FileContentRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> FileContentResponse:
    """
    Write file content with conflict detection.

    Cloud mode only - used by browser editor.
    """
    try:
        storage = FileStorageService(db)

        # Convert content to bytes
        if request.encoding == "base64":
            content = base64.b64decode(request.content)
        else:
            content = request.content.encode("utf-8")

        # Handle etag validation
        if request.expected_etag:
            try:
                existing_content, _ = await storage.read_file(request.path)
                existing_etag = hashlib.md5(existing_content).hexdigest()
                if existing_etag != request.expected_etag:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"reason": "content_changed", "message": "File has been modified"}
                    )
            except FileNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"reason": "path_not_found", "message": "File was deleted"}
                )

        # Write file with deactivation protection
        updated_by = user.email if user else "system"
        write_result = await storage.write_file(
            request.path,
            content,
            updated_by,
            force_deactivation=request.force_deactivation,
            replacements=request.replacements,
        )

        # Check for pending deactivations - return 409 if any
        if write_result.pending_deactivations:
            pending = [
                PendingDeactivation(
                    id=pd.id,
                    name=pd.name,
                    function_name=pd.function_name,
                    path=pd.path,
                    description=pd.description,
                    decorator_type=pd.decorator_type,  # type: ignore[arg-type]
                    has_executions=pd.has_executions,
                    last_execution_at=pd.last_execution_at,
                    schedule=pd.schedule,
                    endpoint_enabled=pd.endpoint_enabled,
                    affected_entities=[
                        AffectedEntity(
                            entity_type=ae["entity_type"],  # type: ignore[arg-type]
                            id=ae["id"],
                            name=ae["name"],
                            reference_type=ae["reference_type"],
                        )
                        for ae in pd.affected_entities
                    ],
                )
                for pd in write_result.pending_deactivations
            ]
            replacements = [
                AvailableReplacement(
                    function_name=ar.function_name,
                    name=ar.name,
                    decorator_type=ar.decorator_type,  # type: ignore[arg-type]
                    similarity_score=ar.similarity_score,
                )
                for ar in (write_result.available_replacements or [])
            ]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "reason": "workflows_would_deactivate",
                    "message": f"{len(pending)} workflow(s) would be deactivated",
                    "pending_deactivations": [p.model_dump() for p in pending],
                    "available_replacements": [r.model_dump() for r in replacements],
                }
            )

        etag = hashlib.md5(write_result.final_content).hexdigest()

        if write_result.content_modified:
            response_content = write_result.final_content.decode("utf-8")
            response_encoding = "utf-8"
            response_size = len(write_result.final_content)
        else:
            response_content = request.content
            response_encoding = request.encoding
            response_size = len(content)

        # Convert conflicts to response model
        conflicts = []
        if write_result.workflow_id_conflicts:
            for c in write_result.workflow_id_conflicts:
                conflicts.append(WorkflowIdConflict(
                    name=c.name,
                    function_name=c.function_name,
                    existing_id=c.existing_id,
                    file_path=c.file_path,
                ))

        # Convert diagnostics to response model
        diagnostics = []
        if write_result.diagnostics:
            for d in write_result.diagnostics:
                diagnostics.append(FileDiagnostic(
                    severity=d.severity,  # type: ignore[arg-type]
                    message=d.message,
                    line=d.line,
                    column=d.column,
                    source=d.source,
                ))

        return FileContentResponse(
            path=request.path,
            content=response_content,
            encoding=response_encoding,
            size=response_size,
            etag=etag,
            modified=write_result.file_record.updated_at.isoformat(),
            content_modified=write_result.content_modified,
            needs_indexing=write_result.needs_indexing,
            workflow_id_conflicts=conflicts,
            diagnostics=diagnostics,
        )

    except HTTPException:
        raise
    except ValueError as e:
        error_msg = str(e)
        if error_msg.startswith("CONFLICT:"):
            parts = error_msg.split(":", 2)
            if len(parts) == 3:
                _, reason, message = parts
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"reason": reason, "message": message}
                )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)


@router.post(
    "/editor/folder",
    response_model=FileMetadata,
    status_code=status.HTTP_201_CREATED,
    summary="Create folder (editor)",
)
async def create_folder_editor(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="Folder path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    """
    Create a new folder.

    Cloud mode only - used by browser editor.
    """
    try:
        storage = FileStorageService(db)
        updated_by = user.email if user else "system"
        folder_record = await storage.create_folder(path, updated_by)

        clean_path = path.rstrip("/")
        return FileMetadata(
            path=clean_path,
            name=clean_path.split("/")[-1],
            type=FileType.FOLDER,
            size=None,
            extension=None,
            modified=folder_record.updated_at.isoformat() if folder_record.updated_at else datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/editor",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete file or folder (editor)",
)
async def delete_file_editor(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="File or folder path"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a file or folder recursively.

    Cloud mode only - used by browser editor.
    """
    from sqlalchemy import select
    from src.models import WorkspaceFile

    try:
        storage = FileStorageService(db)

        # Check if this is a folder
        folder_path = path.rstrip("/") + "/"
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path == folder_path,
            WorkspaceFile.is_deleted == False,  # noqa: E712
        )
        result = await db.execute(stmt)
        folder_record = result.scalar_one_or_none()

        if folder_record:
            await storage.delete_folder(path)
        else:
            await storage.delete_file(path)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Not found: {path}")


@router.post(
    "/editor/rename",
    response_model=FileMetadata,
    summary="Rename or move file/folder (editor)",
)
async def rename_file_editor(
    ctx: Context,
    user: CurrentSuperuser,
    old_path: str = Query(..., description="Current path"),
    new_path: str = Query(..., description="New path"),
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    """
    Rename or move a file or folder.

    For platform entities (workflows, forms, apps, agents), this updates the path
    in both workspace_files and the entity table, preserving all metadata.

    For regular files, copies content in S3 and updates the index.

    Cloud mode only - used by browser editor.
    """
    try:
        storage = FileStorageService(db)

        # Use move_file which preserves entity associations
        file_record = await storage.move_file(old_path, new_path)

        is_folder = new_path.endswith("/")
        return FileMetadata(
            path=new_path,
            name=new_path.split("/")[-1] if not is_folder else new_path.split("/")[-2],
            type=FileType.FOLDER if is_folder else FileType.FILE,
            size=file_record.size_bytes if not is_folder else None,
            extension=new_path.split(".")[-1] if "." in new_path and not is_folder else None,
            modified=file_record.updated_at.isoformat(),
            entity_type=file_record.entity_type if not is_folder else None,
            entity_id=str(file_record.entity_id) if file_record.entity_id and not is_folder else None,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Not found: {old_path}")
    except FileExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Already exists: {new_path}")


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search file contents",
)
async def search_file_contents(
    request: SearchRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    Search file contents for text or regex patterns.

    Searches database directly - workflows, modules, forms, and agents.
    """
    try:
        results = await search_files_db(db, request, root_path="")
        return results

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
