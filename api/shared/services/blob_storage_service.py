"""
Blob Storage Service for runtime files.

Simple blob storage for execution outputs, uploads, and other runtime files.
No indexing - just direct S3 operations.

When S3 is not configured, falls back to filesystem operations.
"""

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


def _get_settings() -> "Settings":
    """Lazy import of settings to avoid circular dependencies."""
    from src.config import get_settings
    return get_settings()


class BlobStorageService:
    """
    Storage service for runtime files (execution outputs, uploads).

    Provides simple blob operations without PostgreSQL indexing.
    """

    def __init__(self, settings: "Settings | None" = None):
        self.settings = settings or _get_settings()

    @asynccontextmanager
    async def _get_s3_client(self):
        """Get S3 client context manager."""
        if not self.settings.s3_configured:
            raise RuntimeError("S3 storage not configured")

        from aiobotocore.session import get_session

        session = get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        ) as client:
            yield client

    def _guess_content_type(self, key: str) -> str:
        """Guess content type from file path."""
        content_type, _ = mimetypes.guess_type(key)
        return content_type or "application/octet-stream"

    async def write(
        self,
        key: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        """
        Write blob to storage.

        Args:
            key: Storage key (path-like string)
            content: File content as bytes
            content_type: MIME type (auto-detected if not provided)

        Returns:
            The storage key
        """
        content_type = content_type or self._guess_content_type(key)

        if self.settings.s3_configured:
            async with self._get_s3_client() as s3:
                await s3.put_object(
                    Bucket=self.settings.s3_files_bucket,
                    Key=key,
                    Body=content,
                    ContentType=content_type,
                )
        else:
            # Filesystem fallback using temp_location
            file_path = Path(self.settings.temp_location) / "files" / key
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

        logger.debug(f"Blob written: {key} ({len(content)} bytes)")
        return key

    async def read(self, key: str) -> bytes:
        """
        Read blob from storage.

        Args:
            key: Storage key

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If blob doesn't exist
        """
        if self.settings.s3_configured:
            async with self._get_s3_client() as s3:
                try:
                    response = await s3.get_object(
                        Bucket=self.settings.s3_files_bucket,
                        Key=key,
                    )
                    return await response["Body"].read()
                except s3.exceptions.NoSuchKey:
                    raise FileNotFoundError(f"Blob not found: {key}")
        else:
            file_path = Path(self.settings.temp_location) / "files" / key
            if not file_path.exists():
                raise FileNotFoundError(f"Blob not found: {key}")
            return file_path.read_bytes()

    async def delete(self, key: str) -> None:
        """
        Delete blob from storage.

        Args:
            key: Storage key
        """
        if self.settings.s3_configured:
            async with self._get_s3_client() as s3:
                await s3.delete_object(
                    Bucket=self.settings.s3_files_bucket,
                    Key=key,
                )
        else:
            file_path = Path(self.settings.temp_location) / "files" / key
            if file_path.exists():
                file_path.unlink()

        logger.debug(f"Blob deleted: {key}")

    async def exists(self, key: str) -> bool:
        """
        Check if blob exists.

        Args:
            key: Storage key

        Returns:
            True if blob exists
        """
        if self.settings.s3_configured:
            async with self._get_s3_client() as s3:
                try:
                    await s3.head_object(
                        Bucket=self.settings.s3_files_bucket,
                        Key=key,
                    )
                    return True
                except Exception:
                    return False
        else:
            file_path = Path(self.settings.temp_location) / "files" / key
            return file_path.exists()

    async def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        http_method: str = "GET",
    ) -> str:
        """
        Get presigned URL for direct access.

        Args:
            key: Storage key
            expires_in: Expiration time in seconds (default 1 hour)
            http_method: HTTP method (GET for download, PUT for upload)

        Returns:
            Presigned URL

        Raises:
            RuntimeError: If S3 not configured
        """
        if not self.settings.s3_configured:
            raise RuntimeError("Presigned URLs require S3 configuration")

        async with self._get_s3_client() as s3:
            url = await s3.generate_presigned_url(
                "get_object" if http_method == "GET" else "put_object",
                Params={
                    "Bucket": self.settings.s3_files_bucket,
                    "Key": key,
                },
                ExpiresIn=expires_in,
            )
            return url

    async def list_keys(self, prefix: str = "") -> list[str]:
        """
        List keys with given prefix.

        Args:
            prefix: Key prefix to filter by

        Returns:
            List of keys
        """
        keys = []

        if self.settings.s3_configured:
            async with self._get_s3_client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self.settings.s3_files_bucket,
                    Prefix=prefix,
                ):
                    for obj in page.get("Contents", []):
                        key = obj.get("Key")
                        if key:
                            keys.append(key)
        else:
            base_path = Path(self.settings.temp_location) / "files"
            if prefix:
                search_path = base_path / prefix
            else:
                search_path = base_path

            if search_path.exists():
                for file_path in search_path.rglob("*"):
                    if file_path.is_file():
                        keys.append(str(file_path.relative_to(base_path)))

        return keys

    async def delete_prefix(self, prefix: str) -> int:
        """
        Delete all blobs with given prefix.

        Args:
            prefix: Key prefix

        Returns:
            Number of blobs deleted
        """
        keys = await self.list_keys(prefix)

        for key in keys:
            await self.delete(key)

        logger.info(f"Deleted {len(keys)} blobs with prefix: {prefix}")
        return len(keys)

    # Convenience methods for common patterns

    async def write_execution_output(
        self,
        execution_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        """
        Write execution output file.

        Args:
            execution_id: Execution UUID
            filename: Output filename
            content: File content
            content_type: MIME type

        Returns:
            Storage key
        """
        key = f"executions/{execution_id}/{filename}"
        return await self.write(key, content, content_type)

    async def get_execution_outputs(self, execution_id: str) -> list[str]:
        """
        List output files for an execution.

        Args:
            execution_id: Execution UUID

        Returns:
            List of storage keys
        """
        return await self.list_keys(f"executions/{execution_id}/")

    async def write_upload(
        self,
        content: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> str:
        """
        Write uploaded file.

        Args:
            content: File content
            filename: Original filename
            content_type: MIME type

        Returns:
            Storage key
        """
        upload_id = str(uuid4())
        key = f"uploads/{upload_id}/{filename}"
        return await self.write(key, content, content_type)


# Singleton instance
_blob_storage: BlobStorageService | None = None


def get_blob_storage_service() -> BlobStorageService:
    """Get or create blob storage service instance."""
    global _blob_storage
    if _blob_storage is None:
        _blob_storage = BlobStorageService()
    return _blob_storage
