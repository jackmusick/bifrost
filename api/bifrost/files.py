"""
File management SDK for Bifrost.

Provides async Python API for file operations in workspace/files/, temp directories,
and S3-stored uploads.

Works in two modes:
1. Platform context (inside workflows): Direct filesystem/S3 access
2. External context (via dev API key): API calls to SDK endpoints

Location Options:
- "temp": Temporary files (cleared periodically, for execution-scoped data)
- "workspace": Persistent workspace files (survives across executions)
- "uploads": Files uploaded via form file fields (stored in S3)

Usage:
    from bifrost import files

    # Write to temp (execution-scoped)
    await files.write("temp-data.txt", "content", location="temp")

    # Write to workspace (persistent)
    await files.write("exports/report.csv", data, location="workspace")

    # Read uploaded file (from form file field)
    content = await files.read("uploads/form_id/uuid/filename.txt", location="uploads")
"""

import shutil
from pathlib import Path
from typing import Literal

from ._context import _execution_context


def _is_platform_context() -> bool:
    """Check if running inside platform execution context."""
    return _execution_context.get() is not None


def _get_client():
    """Get the BifrostClient for API calls."""
    from .client import get_client
    return get_client()


async def _read_from_s3(path: str) -> bytes:
    """Read file from S3 bucket.

    Reads directly from S3 without requiring a database session.
    This is used for uploaded files (form file fields).
    """
    from aiobotocore.session import get_session
    from src.config import get_settings

    settings = get_settings()
    if not settings.s3_configured:
        raise RuntimeError("S3 storage not configured - cannot read uploaded files")

    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    ) as s3:
        try:
            response = await s3.get_object(
                Bucket=settings.s3_bucket,
                Key=path,
            )
            return await response["Body"].read()
        except Exception as e:
            # Handle NoSuchKey or any S3 error
            if "NoSuchKey" in str(type(e).__name__) or "NoSuchKey" in str(e):
                raise FileNotFoundError(f"File not found in S3: {path}")
            raise


class files:
    """
    File management operations (async).

    Provides safe file access within workspace/files/, temp directories, and S3 uploads.
    All paths are sandboxed to prevent access outside allowed directories.

    Works in both platform context (direct access) and external context (API calls).
    """

    # Hardcoded file storage paths - workspace kept in sync with S3 by WorkspaceSyncService
    WORKSPACE_FILES_DIR = Path("/tmp/bifrost/workspace")
    TEMP_FILES_DIR = Path("/tmp/bifrost/tmp")

    @staticmethod
    def _resolve_path(path: str, location: Literal["temp", "workspace"]) -> Path:
        """
        Resolve and validate a file path.

        Args:
            path: Relative or absolute path
            location: Storage location ("temp" or "workspace")

        Returns:
            Path: Resolved absolute path

        Raises:
            ValueError: If path is outside allowed directories
        """
        # Determine base directory based on location
        if location == "temp":
            base_dir = files.TEMP_FILES_DIR
        else:  # workspace
            base_dir = files.WORKSPACE_FILES_DIR

        # Convert to Path object
        p = Path(path)

        # If relative, resolve against base directory
        if not p.is_absolute():
            p = base_dir / p

        # Resolve to absolute path (handles .. and symlinks)
        try:
            p = p.resolve()
        except Exception as e:
            raise ValueError(f"Invalid path: {path}") from e

        # Check if path is within allowed directory
        try:
            if not p.is_relative_to(base_dir):
                raise ValueError(
                    f"Path must be within {location} files directory: {path}")
        except AttributeError:
            # Python < 3.9 doesn't have is_relative_to
            # Fallback to string comparison
            if not str(p).startswith(str(base_dir)):
                raise ValueError(
                    f"Path must be within {location} files directory: {path}")

        return p

    @staticmethod
    async def read(path: str, location: Literal["temp", "workspace", "uploads"] = "workspace") -> str:
        """
        Read a text file.

        Args:
            path: File path (relative or absolute, or S3 key for uploads)
            location: Storage location:
                - "workspace": Persistent workspace files (default)
                - "temp": Temporary execution-scoped files
                - "uploads": Files uploaded via form file fields (from S3)

        Returns:
            str: File contents

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> content = await files.read("data/customers.csv", location="workspace")
            >>> uploaded = await files.read("uploads/form_id/uuid/file.txt", location="uploads")
        """
        if _is_platform_context():
            if location == "uploads":
                # Read from S3 for uploaded files
                content_bytes = await _read_from_s3(path)
                return content_bytes.decode('utf-8')
            else:
                # Direct filesystem access (platform mode)
                file_path = files._resolve_path(path, location)
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/files/read",
                json={"path": path, "location": location}
            )
            response.raise_for_status()
            return response.text

    @staticmethod
    async def read_bytes(path: str, location: Literal["temp", "workspace", "uploads"] = "workspace") -> bytes:
        """
        Read a binary file.

        Args:
            path: File path (relative or absolute, or S3 key for uploads)
            location: Storage location:
                - "workspace": Persistent workspace files (default)
                - "temp": Temporary execution-scoped files
                - "uploads": Files uploaded via form file fields (from S3)

        Returns:
            bytes: File contents

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> data = await files.read_bytes("reports/report.pdf", location="workspace")
        """
        if _is_platform_context():
            if location == "uploads":
                # Read from S3 for uploaded files
                return await _read_from_s3(path)
            else:
                # Direct filesystem access (platform mode)
                file_path = files._resolve_path(path, location)
                with open(file_path, 'rb') as f:
                    return f.read()
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/files/read",
                json={"path": path, "location": location}
            )
            response.raise_for_status()
            return response.content

    @staticmethod
    async def write(path: str, content: str, location: Literal["temp", "workspace"] = "workspace") -> None:
        """
        Write text to a file.

        Args:
            path: File path (relative or absolute)
            content: Text content to write
            location: Storage location ("temp" or "workspace", default: "workspace")

        Raises:
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> await files.write("output/report.txt", "Report data", location="workspace")
        """
        if _is_platform_context():
            # Direct filesystem access (platform mode)
            file_path = files._resolve_path(path, location)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/files/write",
                json={"path": path, "content": content, "location": location}
            )
            response.raise_for_status()

    @staticmethod
    async def write_bytes(path: str, content: bytes, location: Literal["temp", "workspace"] = "workspace") -> None:
        """
        Write binary data to a file.

        Args:
            path: File path (relative or absolute)
            content: Binary content to write
            location: Storage location ("temp" or "workspace", default: "workspace")

        Raises:
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> await files.write_bytes("uploads/image.png", image_data, location="workspace")
        """
        if _is_platform_context():
            # Direct filesystem access (platform mode)
            file_path = files._resolve_path(path, location)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(content)
        else:
            # API call (external mode) - convert bytes to base64 for transport
            import base64
            client = _get_client()
            response = await client.post(
                "/api/cli/files/write",
                json={"path": path, "content": base64.b64encode(content).decode(), "location": location}
            )
            response.raise_for_status()

    @staticmethod
    async def list(directory: str = "", location: Literal["temp", "workspace"] = "workspace") -> list[str]:
        """
        List files in a directory.

        Args:
            directory: Directory path (relative, default: root)
            location: Storage location ("temp" or "workspace", default: "workspace")

        Returns:
            list[str]: List of file and directory names

        Raises:
            FileNotFoundError: If directory doesn't exist
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> items = await files.list("uploads", location="workspace")
            >>> for item in items:
            ...     print(item)
        """
        if _is_platform_context():
            # Direct filesystem access (platform mode)
            dir_path = files._resolve_path(directory, location)
            if not dir_path.exists():
                raise FileNotFoundError(f"Directory not found: {directory}")
            if not dir_path.is_dir():
                raise ValueError(f"Not a directory: {directory}")
            return [item.name for item in dir_path.iterdir()]
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/files/list",
                json={"directory": directory, "location": location}
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def delete(path: str, location: Literal["temp", "workspace"] = "workspace") -> None:
        """
        Delete a file or directory.

        Args:
            path: File or directory path (relative or absolute)
            location: Storage location ("temp" or "workspace", default: "workspace")

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> await files.delete("temp/old_file.txt", location="temp")
        """
        if _is_platform_context():
            # Direct filesystem access (platform mode)
            file_path = files._resolve_path(path, location)
            if not file_path.exists():
                raise FileNotFoundError(f"Path not found: {path}")
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/files/delete",
                json={"path": path, "location": location}
            )
            response.raise_for_status()

    @staticmethod
    async def exists(path: str, location: Literal["temp", "workspace"] = "workspace") -> bool:
        """
        Check if a file or directory exists.

        Args:
            path: File or directory path (relative or absolute)
            location: Storage location ("temp" or "workspace", default: "workspace")

        Returns:
            bool: True if path exists

        Raises:
            ValueError: If path is outside allowed directories
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import files
            >>> if await files.exists("data/customers.csv", location="workspace"):
            ...     data = await files.read("data/customers.csv", location="workspace")
        """
        if _is_platform_context():
            # Direct filesystem access (platform mode)
            try:
                file_path = files._resolve_path(path, location)
                return file_path.exists()
            except ValueError:
                return False
        else:
            # API call (external mode) - try to list and catch 404
            try:
                client = _get_client()
                response = await client.post(
                    "/api/cli/files/read",
                    json={"path": path, "location": location}
                )
                return response.status_code == 200
            except Exception:
                return False
