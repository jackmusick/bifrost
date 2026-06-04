"""
Solution Storage Service — S3 operations scoped to ``_solutions/{solution_id}/``.

Mirrors :class:`src.services.repo_storage.RepoStorage` but every key is prefixed
with the install's ``solution_id``. Callers pass relative paths
("workflows/triage.py") and this service reads/writes
"_solutions/{solution_id}/workflows/triage.py" in S3.

Two installs of the same Solution definition (and the ad-hoc ``_repo/``
workspace) therefore never collide — this is the storage half of the
"self-contained worlds" guarantee (success-criteria §3.5/§3.6). Python source
installs here and is *executed as source* by the virtual importer; React app
``src/`` is NOT installed here (only built ``dist/`` goes to ``_apps/``).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from src.config import Settings, get_settings
from src.services.repo_storage import S3FileMetadata, _get_shared_session

logger = logging.getLogger(__name__)

SOLUTIONS_ROOT = "_solutions"


class SolutionStorage:
    """S3 storage scoped to ``_solutions/{solution_id}/`` prefix."""

    def __init__(self, solution_id: UUID | str, settings: Settings | None = None):
        self.solution_id = str(solution_id)
        self.prefix = f"{SOLUTIONS_ROOT}/{self.solution_id}/"
        self._settings = settings or get_settings()
        self._bucket: str = self._settings.s3_bucket or ""

    @asynccontextmanager
    async def _get_client(self):
        session = _get_shared_session()
        async with session.create_client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
            region_name=self._settings.s3_region,
        ) as client:
            yield client

    def _key(self, path: str) -> str:
        """Convert a relative path to an S3 key under this install's prefix."""
        return f"{self.prefix}{path.lstrip('/')}"

    async def read(self, path: str) -> bytes:
        """Read a file from this install's prefix."""
        async with self._get_client() as client:
            key = self._key(path)
            response = await client.get_object(Bucket=self._bucket, Key=key)
            return await response["Body"].read()

    async def write(self, path: str, content: bytes) -> str:
        """Write a file to this install's prefix. Returns SHA-256 content hash."""
        async with self._get_client() as client:
            key = self._key(path)
            content_hash = hashlib.sha256(content).hexdigest()
            await client.put_object(Bucket=self._bucket, Key=key, Body=content)
            return content_hash

    async def delete(self, path: str) -> None:
        """Delete a file from this install's prefix."""
        async with self._get_client() as client:
            key = self._key(path)
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def list(self, prefix: str = "") -> list[str]:
        """List files under this install (optional sub-prefix). Returns relative paths."""
        async with self._get_client() as client:
            return await self._list_from_s3(client, prefix)

    async def list_with_metadata(self, prefix: str = "") -> dict[str, S3FileMetadata]:
        """List files under this install with metadata, keyed by relative path."""
        async with self._get_client() as client:
            return await self._list_with_metadata_from_s3(client, prefix)

    async def _list_from_s3(self, client, prefix: str = "") -> list[str]:
        full_prefix = self._key(prefix)
        strip = len(self.prefix)
        paths: list[str] = []
        continuation_token = None

        while True:
            kwargs: dict = {"Bucket": self._bucket, "Prefix": full_prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = await client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                paths.append(obj["Key"][strip:])

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return paths

    async def _list_with_metadata_from_s3(
        self, client, prefix: str = ""
    ) -> dict[str, S3FileMetadata]:
        full_prefix = self._key(prefix)
        strip = len(self.prefix)
        result: dict[str, S3FileMetadata] = {}
        continuation_token = None

        while True:
            kwargs: dict = {"Bucket": self._bucket, "Prefix": full_prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = await client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                rel_path = obj["Key"][strip:]
                etag = obj["ETag"].strip('"')
                last_modified: datetime = obj["LastModified"]
                result[rel_path] = S3FileMetadata(etag=etag, last_modified=last_modified)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return result

    async def list_directory(
        self,
        prefix: str = "",
        exclude_fn: Callable[[str], bool] | None = None,
    ) -> tuple[list[str], list[str]]:
        """List direct children of a directory under this install.

        Returns (files, folders) as relative paths. Uses S3 Delimiter='/' for
        an efficient non-recursive listing.
        """
        from src.services.editor.file_filter import is_excluded_path

        filter_fn = exclude_fn or is_excluded_path

        async with self._get_client() as client:
            raw_files, raw_folders = await self._list_directory_from_s3(client, prefix)

        files = [f for f in raw_files if not filter_fn(f)]
        folders = [d for d in raw_folders if not filter_fn(d.rstrip("/"))]
        return sorted(files), sorted(folders)

    async def _list_directory_from_s3(
        self, client, prefix: str = ""
    ) -> tuple[list[str], list[str]]:
        full_prefix = self._key(prefix)
        strip = len(self.prefix)
        files: list[str] = []
        folders: list[str] = []
        continuation_token = None

        while True:
            kwargs: dict = {
                "Bucket": self._bucket,
                "Prefix": full_prefix,
                "Delimiter": "/",
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = await client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                rel_path = obj["Key"][strip:]
                if rel_path:
                    files.append(rel_path)
            for prefix_obj in response.get("CommonPrefixes", []):
                folder_path = prefix_obj["Prefix"][strip:]
                if folder_path:
                    folders.append(folder_path)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return files, folders

    async def exists(self, path: str) -> bool:
        """Check if a file exists under this install's prefix."""
        try:
            async with self._get_client() as client:
                key = self._key(path)
                await client.head_object(Bucket=self._bucket, Key=key)
                return True
        except Exception:
            # head_object raises ClientError (404) for a missing key; any other
            # transport failure also means "treat as absent" for callers here.
            return False

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()
