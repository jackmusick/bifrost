"""
File Index Service — dual-write facade for _repo/ files.

Every write goes to both S3 (_repo/) and the file_index DB table.
Searches go through the DB; content reads go through get_module() (Redis/S3).
Binary files are written to S3 only (not indexed).
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.file_index import FileIndex
from src.services.repo_storage import RepoStorage

logger = logging.getLogger(__name__)

# File extensions that should be indexed (text-searchable)
TEXT_EXTENSIONS = frozenset({
    ".py", ".yaml", ".yml", ".json", ".md", ".txt", ".rst",
    ".toml", ".ini", ".cfg", ".csv", ".tsx", ".ts", ".js",
    ".jsx", ".css", ".html", ".xml", ".sql", ".sh",
})


def _is_text_file(path: str) -> bool:
    """Check if a file should be indexed based on extension."""
    for ext in TEXT_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


class FileIndexService:
    """Dual-write facade for _repo/ files."""

    def __init__(self, db: AsyncSession, repo_storage: RepoStorage | None = None):
        self.db = db
        self.repo_storage = repo_storage or RepoStorage()

    async def write(self, path: str, content: bytes) -> str:
        """
        Write a file to S3 and index it in the DB.

        Returns the content hash.
        """
        # Always write to S3
        content_hash = await self.repo_storage.write(path, content)

        # Only index text files
        if _is_text_file(path):
            try:
                content_str = content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(f"Could not decode {path} as UTF-8, skipping index")
                return content_hash

            stmt = insert(FileIndex).values(
                path=path,
                content=content_str,
                content_hash=content_hash,
            ).on_conflict_do_update(
                index_elements=[FileIndex.path],
                set_={
                    "content": content_str,
                    "content_hash": content_hash,
                    "updated_at": text("NOW()"),
                },
            )
            await self.db.execute(stmt)

        return content_hash

    async def delete(self, path: str) -> None:
        """Delete a file from S3 and the DB index."""
        await self.repo_storage.delete(path)
        await self.db.execute(
            delete(FileIndex).where(FileIndex.path == path)
        )

    async def search(self, pattern: str) -> list[dict]:
        """
        Search file contents for a pattern.

        Returns list of dicts with 'path' and 'content' keys.
        """
        result = await self.db.execute(
            select(FileIndex.path, FileIndex.content).where(
                FileIndex.content.ilike(f"%{pattern}%")
            )
        )
        return [{"path": row.path, "content": row.content} for row in result.all()]

    async def list_paths(self, prefix: str = "") -> list[str]:
        """List all indexed file paths, optionally filtered by prefix."""
        if prefix:
            result = await self.db.execute(
                select(FileIndex.path).where(FileIndex.path.like(f"{prefix}%"))
            )
        else:
            result = await self.db.execute(select(FileIndex.path))
        return [row[0] for row in result.all()]

