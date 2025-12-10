"""
Editor Files Router

File operations for browser-based code editor.
Provides safe file I/O with path validation.
Platform admin resource - no org scoping.

All file operations use S3-based storage via FileStorageService.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    FileContentRequest,
    FileContentResponse,
    FileMetadata,
    FileType,
    SearchRequest,
    SearchResponse,
)
from src.core.auth import Context, CurrentSuperuser
from src.core.database import get_db
from src.services.editor.search import search_files
from src.services.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/editor", tags=["Editor"])


# =============================================================================
# HTTP Endpoints
# =============================================================================


@router.get(
    "/files",
    response_model=list[FileMetadata],
    summary="List directory contents",
    description="List files and folders in a directory (Platform admin only)",
)
async def list_files(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="Directory path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> list[FileMetadata]:
    """
    List files and folders in a directory.

    Args:
        path: Directory path relative to workspace root

    Returns:
        List of file and folder metadata
    """
    try:
        storage = FileStorageService(db)
        workspace_files = await storage.list_files(path)

        # Convert to FileMetadata
        files = []
        for wf in workspace_files:
            # Determine if this is a file or folder based on path structure
            is_folder = wf.path.endswith("/")
            files.append(FileMetadata(
                path=wf.path,
                name=wf.path.split("/")[-1] if not is_folder else wf.path.split("/")[-2],
                type=FileType.FOLDER if is_folder else FileType.FILE,
                size=wf.size_bytes if not is_folder else None,
                extension=wf.path.split(".")[-1] if "." in wf.path and not is_folder else None,
                modified=wf.updated_at.isoformat() if wf.updated_at else datetime.now(timezone.utc).isoformat(),
                isReadOnly=False,
            ))
        logger.info(f"Listed directory: {path} ({len(files)} items)")
        return files
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {path}",
        )
    except Exception as e:
        logger.error(f"Error listing directory {path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list directory",
        )


@router.get(
    "/files/content",
    response_model=FileContentResponse,
    summary="Read file content",
    description="Read the content of a file (Platform admin only)",
)
async def get_file_content(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="File path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> FileContentResponse:
    """
    Read file content.

    Args:
        path: File path relative to workspace root

    Returns:
        File content and metadata
    """
    try:
        storage = FileStorageService(db)
        content, file_record = await storage.read_file(path)

        # Determine encoding - try UTF-8 first
        encoding = "utf-8"
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            # Binary file - base64 encode
            import base64
            encoding = "base64"
            content_str = base64.b64encode(content).decode("ascii")

        # Compute etag
        import hashlib
        etag = hashlib.md5(content).hexdigest()

        result = FileContentResponse(
            path=path,
            content=content_str,
            encoding=encoding,
            size=len(content),
            etag=etag,
            modified=file_record.updated_at.isoformat() if file_record else datetime.now(timezone.utc).isoformat(),
        )
        logger.info(f"Read file: {path} ({result.size} bytes)")
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path}",
        )
    except Exception as e:
        logger.error(f"Error reading file {path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read file",
        )


@router.put(
    "/files/content",
    response_model=FileContentResponse,
    summary="Write file content",
    description="Write content to a file (Platform admin only)",
)
async def put_file_content(
    request: FileContentRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> FileContentResponse:
    """
    Write content to a file with optional conflict detection.

    Args:
        request: File content request with path, content, and optional expected_etag

    Returns:
        Updated file metadata with new etag

    Raises:
        409 Conflict: If expected_etag provided and doesn't match current file
    """
    try:
        storage = FileStorageService(db)

        # Convert content to bytes
        if request.encoding == "base64":
            import base64
            content = base64.b64decode(request.content)
        else:
            content = request.content.encode("utf-8")

        # Handle etag validation
        if request.expected_etag:
            try:
                existing_content, _ = await storage.read_file(request.path)
                import hashlib
                existing_etag = hashlib.md5(existing_content).hexdigest()
                if existing_etag != request.expected_etag:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"reason": "content_changed", "message": f"File has been modified (expected etag {request.expected_etag}, got {existing_etag})"}
                    )
            except FileNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"reason": "path_not_found", "message": "File was deleted by another process"}
                )

        # Write file
        updated_by = user.email if user else "system"
        file_record = await storage.write_file(request.path, content, updated_by)

        # Compute new etag
        import hashlib
        etag = hashlib.md5(content).hexdigest()

        result = FileContentResponse(
            path=request.path,
            content=request.content,
            encoding=request.encoding,
            size=len(content),
            etag=etag,
            modified=file_record.updated_at.isoformat(),
        )
        logger.info(f"Wrote file: {request.path} ({result.size} bytes, etag: {result.etag})")
        return result

    except HTTPException:
        raise
    except ValueError as e:
        error_msg = str(e)
        # Check if this is a conflict error (format: "CONFLICT:reason:message")
        if error_msg.startswith("CONFLICT:"):
            parts = error_msg.split(":", 2)
            if len(parts) == 3:
                _, reason, message = parts
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"reason": reason, "message": message}
                )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {request.path}",
        )
    except Exception as e:
        logger.error(f"Error writing file {request.path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write file",
        )


@router.post(
    "/files/folder",
    response_model=FileMetadata,
    status_code=status.HTTP_201_CREATED,
    summary="Create folder",
    description="Create a new folder (Platform admin only)",
)
async def create_new_folder(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="Folder path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    """
    Create a new folder.

    Note: In S3-based storage, folders are virtual (represented by trailing slash).
    We create an empty marker file for the folder.

    Args:
        path: Folder path relative to workspace root

    Returns:
        Folder metadata
    """
    try:
        # S3 doesn't have real folders - create a marker file
        storage = FileStorageService(db)
        folder_path = path.rstrip("/") + "/.gitkeep"

        # Check if folder already has files
        existing = await storage.list_files(path)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Folder already exists: {path}",
            )

        # Create marker file
        updated_by = user.email if user else "system"
        await storage.write_file(folder_path, b"", updated_by)

        folder_meta = FileMetadata(
            path=path,
            name=path.split("/")[-1],
            type=FileType.FOLDER,
            size=None,
            extension=None,
            modified=datetime.now(timezone.utc).isoformat(),
            isReadOnly=False,
        )
        logger.info(f"Created folder: {path}")
        return folder_meta
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Folder already exists: {path}",
        )
    except Exception as e:
        logger.error(f"Error creating folder {path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create folder",
        )


@router.delete(
    "/files",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete file or folder",
    description="Delete a file or folder recursively (Platform admin only)",
)
async def delete_file_or_directory(
    ctx: Context,
    user: CurrentSuperuser,
    path: str = Query(..., description="File or folder path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a file or folder.

    Args:
        path: File or folder path relative to workspace root

    Returns:
        No content on success (204)
    """
    try:
        storage = FileStorageService(db)

        # Check if it's a folder (has children)
        children = await storage.list_files(path)
        if children:
            # Delete all children first
            for child in children:
                await storage.delete_file(child.path)

        # Delete the path itself
        await storage.delete_file(path)
        logger.info(f"Deleted: {path}")

        return None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File or folder not found: {path}",
        )
    except Exception as e:
        logger.error(f"Error deleting {path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file or folder",
        )


@router.post(
    "/files/rename",
    response_model=FileMetadata,
    summary="Rename or move file/folder",
    description="Rename or move a file or folder (Platform admin only)",
)
async def rename_or_move(
    ctx: Context,
    user: CurrentSuperuser,
    old_path: str = Query(..., description="Current path relative to workspace root"),
    new_path: str = Query(..., description="New path relative to workspace root"),
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    """
    Rename or move a file or folder.

    Args:
        old_path: Current path relative to workspace root
        new_path: New path relative to workspace root

    Returns:
        Updated file metadata
    """
    try:
        # S3-based rename (copy + delete)
        storage = FileStorageService(db)

        # Read old file
        content, _ = await storage.read_file(old_path)

        # Write to new location
        updated_by = user.email if user else "system"
        file_record = await storage.write_file(new_path, content, updated_by)

        # Delete old file
        await storage.delete_file(old_path)

        # Determine type
        is_folder = new_path.endswith("/")

        file_meta = FileMetadata(
            path=new_path,
            name=new_path.split("/")[-1] if not is_folder else new_path.split("/")[-2],
            type=FileType.FOLDER if is_folder else FileType.FILE,
            size=file_record.size_bytes if not is_folder else None,
            extension=new_path.split(".")[-1] if "." in new_path and not is_folder else None,
            modified=file_record.updated_at.isoformat(),
            isReadOnly=False,
        )
        logger.info(f"Renamed: {old_path} -> {new_path}")
        return file_meta
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File or folder not found: {old_path}",
        )
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Destination already exists: {new_path}",
        )
    except Exception as e:
        logger.error(f"Error renaming {old_path}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rename file or folder",
        )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search file contents",
    description="Search for text or regex patterns in files (Platform admin only)",
)
async def search_file_contents(
    request: SearchRequest,
    ctx: Context,
    user: CurrentSuperuser,
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    Search file contents for text or regex patterns.

    Note: For S3 storage, this downloads files to search. For large workspaces,
    consider using database-indexed search instead.

    Args:
        request: Search request with query and options

    Returns:
        Search results with matches and metadata
    """
    try:
        # For now, search always uses filesystem (either direct or via downloaded workspace)
        # TODO: Implement S3-aware search that downloads files on demand
        results = search_files(request, root_path="")
        logger.info(f"Search complete: {results.total_matches} matches in {len(results.results)} files")
        return results
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error searching files: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search files",
        )
