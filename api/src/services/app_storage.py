"""
App Storage Service — S3 operations scoped to _apps/ prefix.

Manages the app serving store:
  _apps/{app_id}/preview/   ← draft/editor files
  _apps/{app_id}/live/      ← published files for end users

Data flow:
1. Git sync/import: copy from _repo/{app_path}/ to _apps/{app_id}/preview/
2. Editor write: write to _apps/{app_id}/preview/
3. Publish: copy preview → live
4. Serve draft: read from preview
5. Serve live: read from live
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from aiobotocore.session import get_session

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

APPS_PREFIX = "_apps/"

AppMode = Literal["preview", "live"]


class AppStorageService:
    """S3 storage scoped to _apps/ prefix for app serving."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._bucket: str = self._settings.s3_bucket or ""

    @asynccontextmanager
    async def _get_client(self):
        session = get_session()
        async with session.create_client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
            region_name=self._settings.s3_region,
        ) as client:
            yield client

    def _key(self, app_id: str, mode: AppMode, relative_path: str = "") -> str:
        """Build S3 key: _apps/{app_id}/{mode}/{relative_path}"""
        base = f"{APPS_PREFIX}{app_id}/{mode}/"
        if relative_path:
            return f"{base}{relative_path.lstrip('/')}"
        return base

    # -----------------------------------------------------------------
    # Sync preview from repo
    # -----------------------------------------------------------------

    async def sync_preview(self, app_id: str, source_dir_in_repo: str) -> int:
        """Copy all files from _repo/{source_dir}/ to _apps/{app_id}/preview/.

        Removes stale preview files that no longer exist in the source.

        Args:
            app_id: Application UUID as string.
            source_dir_in_repo: Directory path within _repo/ (e.g. "apps/tickbox-grc/").

        Returns:
            Number of files synced.
        """
        from src.services.repo_storage import REPO_PREFIX

        source_prefix = f"{REPO_PREFIX}{source_dir_in_repo.rstrip('/')}/"
        preview_prefix = self._key(app_id, "preview")

        async with self._get_client() as client:
            # List source files in _repo/
            source_keys = await self._list_keys(client, source_prefix)

            # List existing preview files
            existing_preview_keys = await self._list_keys(client, preview_prefix)
            existing_relative = {
                k[len(preview_prefix):] for k in existing_preview_keys
            }

            synced = 0
            new_relative: set[str] = set()

            for source_key in source_keys:
                # Derive relative path within the app dir
                rel_path = source_key[len(source_prefix):]
                if not rel_path:
                    continue

                # Skip app.yaml (manifest metadata, not a source file)
                if rel_path == "app.yaml":
                    continue

                new_relative.add(rel_path)
                dest_key = f"{preview_prefix}{rel_path}"

                # Copy from source to preview
                await client.copy_object(
                    Bucket=self._bucket,
                    CopySource={"Bucket": self._bucket, "Key": source_key},
                    Key=dest_key,
                )
                synced += 1

            # Remove stale preview files
            stale = existing_relative - new_relative
            for rel_path in stale:
                await client.delete_object(
                    Bucket=self._bucket,
                    Key=f"{preview_prefix}{rel_path}",
                )

            if stale:
                logger.info(f"Removed {len(stale)} stale preview files for app {app_id}")

            logger.info(f"Synced {synced} files to preview for app {app_id}")
            return synced

    # -----------------------------------------------------------------
    # Single file operations
    # -----------------------------------------------------------------

    async def write_preview_file(
        self, app_id: str, relative_path: str, content: bytes
    ) -> None:
        """Write a single file to _apps/{app_id}/preview/."""
        key = self._key(app_id, "preview", relative_path)
        async with self._get_client() as client:
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
            )

    async def delete_preview_file(self, app_id: str, relative_path: str) -> None:
        """Delete a single file from _apps/{app_id}/preview/."""
        key = self._key(app_id, "preview", relative_path)
        async with self._get_client() as client:
            try:
                await client.delete_object(Bucket=self._bucket, Key=key)
            except Exception:
                pass  # Idempotent

    async def read_file(
        self, app_id: str, mode: AppMode, relative_path: str
    ) -> bytes:
        """Read a single file from _apps/{app_id}/{mode}/{path}.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        key = self._key(app_id, mode, relative_path)
        async with self._get_client() as client:
            try:
                response = await client.get_object(Bucket=self._bucket, Key=key)
                return await response["Body"].read()
            except client.exceptions.NoSuchKey:
                raise FileNotFoundError(f"App file not found: {relative_path} (mode={mode})")
            except Exception as e:
                if "NoSuchKey" in str(type(e).__name__) or "404" in str(e):
                    raise FileNotFoundError(f"App file not found: {relative_path} (mode={mode})")
                raise

    async def list_files(self, app_id: str, mode: AppMode) -> list[str]:
        """List relative file paths in _apps/{app_id}/{mode}/.

        Returns:
            List of relative paths (e.g. ["pages/index.tsx", "components/Button.tsx"]).
        """
        prefix = self._key(app_id, mode)
        async with self._get_client() as client:
            keys = await self._list_keys(client, prefix)
            return [k[len(prefix):] for k in keys if k[len(prefix):]]

    # -----------------------------------------------------------------
    # Publish: copy preview → live
    # -----------------------------------------------------------------

    async def publish(self, app_id: str) -> int:
        """Copy all preview files to live, removing stale live files.

        Returns:
            Number of files published.
        """
        preview_prefix = self._key(app_id, "preview")
        live_prefix = self._key(app_id, "live")

        async with self._get_client() as client:
            # List preview files
            preview_keys = await self._list_keys(client, preview_prefix)
            preview_relative = set()
            for pk in preview_keys:
                rel = pk[len(preview_prefix):]
                if rel:
                    preview_relative.add(rel)

            if not preview_relative:
                logger.warning(f"No preview files to publish for app {app_id}")
                return 0

            # Copy preview → live
            for rel_path in preview_relative:
                src_key = f"{preview_prefix}{rel_path}"
                dst_key = f"{live_prefix}{rel_path}"
                await client.copy_object(
                    Bucket=self._bucket,
                    CopySource={"Bucket": self._bucket, "Key": src_key},
                    Key=dst_key,
                )

            # Remove stale live files
            live_keys = await self._list_keys(client, live_prefix)
            live_relative = {k[len(live_prefix):] for k in live_keys if k[len(live_prefix):]}
            stale = live_relative - preview_relative
            for rel_path in stale:
                await client.delete_object(
                    Bucket=self._bucket,
                    Key=f"{live_prefix}{rel_path}",
                )

            published = len(preview_relative)
            logger.info(
                f"Published {published} files for app {app_id}"
                f" (removed {len(stale)} stale)"
            )
            return published

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    async def _list_keys(self, client, prefix: str) -> list[str]:
        """List all S3 keys under a prefix."""
        keys: list[str] = []
        continuation_token = None

        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = await client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                key = obj["Key"]
                # Skip directory markers
                if not key.endswith("/"):
                    keys.append(key)

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

        return keys
