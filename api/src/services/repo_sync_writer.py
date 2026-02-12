"""
Repo Sync Writer — dual-write forms/agents/apps to S3 _repo/.

When platform entities are created/updated/deleted, this writer
ensures the S3 working tree stays in sync with the DB.

Required when S3 is configured (errors propagate). Skips silently
when S3 is not configured (local dev without MinIO).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.services.file_storage.indexers.form import _serialize_form_to_yaml
from src.services.file_storage.indexers.agent import _serialize_agent_to_yaml
from src.services.file_index_service import FileIndexService
from src.services.manifest import MANIFEST_FILES, MANIFEST_LEGACY_FILE, serialize_manifest_dir
from src.services.manifest_generator import generate_manifest
from src.services.repo_storage import RepoStorage

logger = logging.getLogger(__name__)


class RepoSyncWriter:
    """Writes entity YAML files to S3 _repo/ alongside DB operations.

    Skips writes silently when S3 is not configured (e.g., dev without MinIO).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._settings = get_settings()
        self._file_index = FileIndexService(db, RepoStorage())

    @property
    def _s3_available(self) -> bool:
        return self._settings.s3_configured

    async def write_form(self, form: Any) -> None:
        """Serialize a Form ORM object to YAML and write to _repo/."""
        if not self._s3_available:
            return
        yaml_bytes = _serialize_form_to_yaml(form)
        path = f"forms/{form.id}.form.yaml"
        await self._file_index.write(path, yaml_bytes)
        logger.debug(f"Wrote form to _repo/{path}")

    async def write_agent(self, agent: Any) -> None:
        """Serialize an Agent ORM object to YAML and write to _repo/."""
        if not self._s3_available:
            return
        yaml_bytes = _serialize_agent_to_yaml(agent)
        path = f"agents/{agent.id}.agent.yaml"
        await self._file_index.write(path, yaml_bytes)
        logger.debug(f"Wrote agent to _repo/{path}")

    async def delete_entity_file(self, path: str) -> None:
        """Delete an entity file from S3 and file_index."""
        if not self._s3_available:
            return
        await self._file_index.delete(path)
        logger.debug(f"Deleted _repo/{path}")

    async def regenerate_manifest(self) -> None:
        """Generate manifest from DB and write split files to _repo/.bifrost/."""
        if not self._s3_available:
            return
        manifest = await generate_manifest(self.db)
        files = serialize_manifest_dir(manifest)
        for filename, content in files.items():
            await self._file_index.write(
                f".bifrost/{filename}",
                content.encode("utf-8"),
            )
        # Remove split files for now-empty entity types
        for filename in MANIFEST_FILES.values():
            if filename not in files:
                try:
                    await self._file_index.delete(f".bifrost/{filename}")
                except Exception:
                    pass  # File didn't exist
        # Clean up legacy single-file manifest
        try:
            await self._file_index.delete(f".bifrost/{MANIFEST_LEGACY_FILE}")
        except Exception:
            pass  # Already gone
        logger.debug("Regenerated split manifest files in _repo/.bifrost/")
