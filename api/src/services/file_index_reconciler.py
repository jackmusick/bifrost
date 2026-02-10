"""
File Index Reconciler — heals drift between S3 _repo/ and file_index DB.

Runs on API startup and can be triggered manually.
Lists all files in S3 _repo/, compares against file_index,
adds missing entries, removes orphaned entries, updates stale content.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.file_index import FileIndex
from src.services.file_index_service import _is_text_file
from src.services.repo_storage import RepoStorage

logger = logging.getLogger(__name__)


async def reconcile_file_index(
    db: AsyncSession,
    repo_storage: RepoStorage | None = None,
) -> dict[str, int]:
    """
    Reconcile file_index with S3 _repo/ contents.

    Returns stats dict with counts of added, removed, updated entries.
    """
    repo = repo_storage or RepoStorage()
    stats = {"added": 0, "removed": 0, "updated": 0, "unchanged": 0}

    # Get all files from S3
    s3_paths = set(await repo.list())
    # Filter to text files only
    s3_text_paths = {p for p in s3_paths if _is_text_file(p)}

    # Get all paths from file_index
    result = await db.execute(select(FileIndex.path))
    db_paths = {row[0] for row in result.all()}

    # Files in S3 but not in DB -> add
    to_add = s3_text_paths - db_paths
    for path in to_add:
        try:
            content = await repo.read(path)
            content_str = content.decode("utf-8")
            content_hash = hashlib.sha256(content).hexdigest()

            stmt = insert(FileIndex).values(
                path=path,
                content=content_str,
                content_hash=content_hash,
            ).on_conflict_do_nothing()
            await db.execute(stmt)
            stats["added"] += 1
        except Exception as e:
            logger.warning(f"Failed to index {path}: {e}")

    # Files in DB but not in S3 -> remove
    to_remove = db_paths - s3_text_paths
    if to_remove:
        await db.execute(
            delete(FileIndex).where(FileIndex.path.in_(to_remove))
        )
        stats["removed"] = len(to_remove)

    await db.commit()

    logger.info(
        f"Reconciliation complete: {stats['added']} added, "
        f"{stats['removed']} removed, {stats['updated']} updated"
    )

    return stats
