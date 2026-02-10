"""
File Backend Abstraction

Provides unified interface for file operations with two backends:
- LocalBackend: Local filesystem (for CLI mode)
- S3Backend: S3 storage (for cloud/platform mode)
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.paths import TEMP_PATH, UPLOADS_PATH
from src.services.file_storage import FileStorageService
from src.services.repo_storage import REPO_PREFIX

Location = Literal["workspace", "temp", "uploads"]


class FileBackend(ABC):
    """Abstract backend for file operations."""

    @abstractmethod
    async def read(self, path: str, location: Location) -> bytes:
        """Read file content."""
        ...

    @abstractmethod
    async def write(self, path: str, content: bytes, location: Location, updated_by: str = "system") -> None:
        """Write file content."""
        ...

    @abstractmethod
    async def delete(self, path: str, location: Location) -> None:
        """Delete a file."""
        ...

    @abstractmethod
    async def list(self, directory: str, location: Location) -> list[str]:
        """List files in a directory."""
        ...

    @abstractmethod
    async def exists(self, path: str, location: Location) -> bool:
        """Check if a file exists."""
        ...


class LocalBackend(FileBackend):
    """Local filesystem backend for local CLI mode."""

    def __init__(self):
        # Use CWD for workspace - this is where the user's workflow files are
        self.workspace_root = Path.cwd()
        self.temp_root = TEMP_PATH
        self.uploads_root = UPLOADS_PATH

        # Ensure temp directories exist
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.uploads_root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str, location: Location) -> Path:
        """Resolve path to absolute filesystem path with sandboxing."""
        if location == "temp":
            base_dir = self.temp_root
        elif location == "uploads":
            base_dir = self.uploads_root
        else:
            base_dir = self.workspace_root

        # Resolve the path
        p = Path(path)
        if not p.is_absolute():
            p = base_dir / p

        try:
            p = p.resolve()
        except Exception as e:
            raise ValueError(f"Invalid path: {path}") from e

        # Sandbox check - ensure path is within the base directory
        if not str(p).startswith(str(base_dir.resolve())):
            raise ValueError(f"Path must be within {location} directory: {path}")

        return p

    async def read(self, path: str, location: Location) -> bytes:
        """Read file from local filesystem."""
        resolved = self._resolve_path(path, location)
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return await asyncio.to_thread(resolved.read_bytes)

    async def write(self, path: str, content: bytes, location: Location, updated_by: str = "system") -> None:
        """Write file to local filesystem."""
        resolved = self._resolve_path(path, location)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(resolved.write_bytes, content)

    async def delete(self, path: str, location: Location) -> None:
        """Delete file from local filesystem."""
        resolved = self._resolve_path(path, location)
        if resolved.exists():
            await asyncio.to_thread(resolved.unlink)

    async def list(self, directory: str, location: Location) -> list[str]:
        """List files in a local directory."""
        resolved = self._resolve_path(directory, location)
        if not resolved.exists():
            return []

        def _list_dir():
            items = []
            for item in resolved.iterdir():
                rel_path = str(item.relative_to(self._resolve_path("", location)))
                if item.is_dir():
                    rel_path += "/"
                items.append(rel_path)
            return sorted(items)

        return await asyncio.to_thread(_list_dir)

    async def exists(self, path: str, location: Location) -> bool:
        """Check if file exists on local filesystem."""
        try:
            resolved = self._resolve_path(path, location)
            return await asyncio.to_thread(resolved.exists)
        except ValueError:
            return False


class S3Backend(FileBackend):
    """S3-based file storage for cloud/platform mode."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = FileStorageService(db)

    def _validate_path(self, path: str) -> None:
        """Validate path doesn't contain traversal patterns."""
        # Reject paths with .. or absolute paths
        if ".." in path or path.startswith("/"):
            raise ValueError(f"Invalid path: path traversal not allowed: {path}")

    def _resolve_path(self, path: str, location: Location) -> str:
        """Resolve path to S3 key with location prefix."""
        self._validate_path(path)
        if location == "temp":
            return f"_tmp/{path}"
        elif location == "uploads":
            return f"uploads/{path}"
        return f"{REPO_PREFIX}{path}"  # workspace: _repo/ prefix in bucket

    async def read(self, path: str, location: Location) -> bytes:
        """Read file from S3."""
        s3_path = self._resolve_path(path, location)
        try:
            if location in ("temp", "uploads"):
                # Direct S3 read — temp/uploads don't go through workspace index
                return await self.storage.read_uploaded_file(s3_path)
            content, _ = await self.storage.read_file(s3_path)
            return content
        except Exception as e:
            # Convert S3 errors to appropriate exceptions
            error_msg = str(e).lower()
            if "not found" in error_msg or "nosuchkey" in error_msg:
                raise FileNotFoundError(f"File not found: {path}")
            if "bad components" in error_msg or "invalid" in error_msg:
                raise ValueError(f"Invalid path: {path}")
            raise

    async def write(self, path: str, content: bytes, location: Location, updated_by: str = "system") -> None:
        """Write file to S3."""
        s3_path = self._resolve_path(path, location)
        if location in ("temp", "uploads"):
            # No workspace indexing for temp/uploads - write directly to S3
            await self.storage.write_raw_to_s3(s3_path, content)
        else:
            # Workspace files get full indexing
            await self.storage.write_file(s3_path, content, updated_by)

    async def delete(self, path: str, location: Location) -> None:
        """Delete file from S3."""
        s3_path = self._resolve_path(path, location)
        if location in ("temp", "uploads"):
            # Direct S3 delete for temp/uploads
            await self.storage.delete_raw_from_s3(s3_path)
        else:
            # Workspace files go through full delete with index update
            await self.storage.delete_file(s3_path)

    async def list(self, directory: str, location: Location) -> list[str]:
        """List files in S3 directory."""
        s3_dir = self._resolve_path(directory, location)
        if location in ("temp", "uploads"):
            # Direct S3 listing for temp/uploads
            return await self.storage.list_raw_s3(s3_dir)
        else:
            # Workspace listing through index
            files = await self.storage.list_files(s3_dir)
            return [f.path for f in files]

    async def exists(self, path: str, location: Location) -> bool:
        """Check if file exists in S3."""
        s3_path = self._resolve_path(path, location)
        return await self.storage.file_exists(s3_path)


def get_backend(mode: str, db: AsyncSession | None = None) -> FileBackend:
    """Get the appropriate file backend based on mode."""
    if mode == "local":
        return LocalBackend()
    if db is None:
        raise ValueError("Database session required for cloud mode")
    return S3Backend(db)
