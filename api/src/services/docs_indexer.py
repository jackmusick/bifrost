"""
Documentation Indexer Service

Indexes bundled platform documentation into the knowledge store on startup.
Enables the Coding Agent to search Bifrost docs for accurate SDK guidance.

Uses content hashing to avoid unnecessary OpenAI API calls - only re-indexes
documents whose content has actually changed since the last indexing run.
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.database import get_db_context
from src.repositories.knowledge import KnowledgeRepository
from src.services.embeddings.factory import get_embedding_client

logger = logging.getLogger(__name__)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

# Path to bundled documentation (in shared/ which is mounted as /app/shared)
DOCS_PATH = Path(__file__).parent.parent.parent / "shared" / "docs"

# Knowledge store namespace for platform docs
NAMESPACE = "bifrost-docs"


async def index_docs_background() -> None:
    """
    Index platform documentation as a background task.

    Called on API startup. Safe to run on every startup - uses upsert
    for idempotency and cleans up orphaned documents.

    This is a fire-and-forget task that logs its own errors.
    """
    try:
        result = await index_platform_docs()
        if result["status"] == "complete":
            logger.info(
                f"Documentation indexing complete: "
                f"{result['indexed']} indexed, {result.get('skipped', 0)} unchanged, "
                f"{result['deleted']} orphaned deleted"
            )
        elif result["status"] == "skipped":
            logger.info(f"Documentation indexing skipped: {result.get('reason', 'unknown')}")
        else:
            logger.warning(f"Documentation indexing result: {result}")
    except Exception as e:
        # Don't fail startup if docs indexing fails
        logger.error(f"Documentation indexing failed: {e}", exc_info=True)


async def index_platform_docs() -> dict[str, Any]:
    """
    Index all platform documentation into the knowledge store.

    Process:
    1. Fetch existing docs and their content hashes
    2. Read all .txt files from api/docs/
    3. Compare content hashes - only re-index changed files
    4. Delete orphaned documents (files that no longer exist)

    Uses content hashing to avoid unnecessary OpenAI API calls.

    Returns:
        Summary dict with status, counts, and any errors
    """
    if not DOCS_PATH.exists():
        return {"status": "skipped", "reason": "docs directory not found"}

    doc_files = list(DOCS_PATH.rglob("*.txt"))
    if not doc_files:
        return {"status": "skipped", "reason": "no documentation files found"}

    indexed_at = datetime.utcnow().isoformat()
    current_keys: set[str] = set()  # All keys from current files (for orphan detection)
    indexed_count = 0
    skipped_count = 0
    errors: list[str] = []

    async with get_db_context() as db:
        try:
            embedding_client = await get_embedding_client(db)
        except ValueError as e:
            # No embedding configuration - skip gracefully
            return {"status": "skipped", "reason": str(e)}

        repo = KnowledgeRepository(db, org_id=None, is_superuser=True)

        # Fetch existing docs upfront to compare content hashes
        existing_docs = await repo.get_all_by_namespace(
            namespace=NAMESPACE,
        )

        logger.info(
            f"Checking {len(doc_files)} documentation files "
            f"({len(existing_docs)} already indexed)..."
        )

        for doc_file in doc_files:
            try:
                content = doc_file.read_text(encoding="utf-8")
                # Key is the relative path without extension
                key = str(doc_file.relative_to(DOCS_PATH)).replace(".txt", "")
                current_keys.add(key)

                # Compute hash of current content
                content_hash = compute_content_hash(content)

                # Check if this doc already exists with the same content
                existing_doc = existing_docs.get(key)
                if existing_doc:
                    existing_hash = existing_doc.metadata.get("content_hash")
                    if existing_hash == content_hash:
                        # Content unchanged - skip embedding generation
                        skipped_count += 1
                        continue

                # Content is new or changed - generate embedding
                embedding = await embedding_client.embed_single(content)

                # Store with upsert (org_id=None for global scope set in repo constructor)
                await repo.store(
                    content=content,
                    embedding=embedding,
                    namespace=NAMESPACE,
                    key=key,
                    metadata={
                        "source": "bifrost-docs",
                        "path": key,
                        "indexed_at": indexed_at,
                        "content_hash": content_hash,
                    },
                )

                indexed_count += 1

            except Exception as e:
                error_msg = f"Failed to index {doc_file.name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Phase 2: Delete orphaned documents (files that no longer exist)
        deleted_count = 0
        if current_keys:  # Only cleanup if we have valid files
            try:
                deleted_count = await repo.delete_orphaned_docs(
                    namespace=NAMESPACE,
                    valid_keys=current_keys,
                )
                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} orphaned documentation entries")
            except Exception as e:
                error_msg = f"Failed to cleanup orphaned docs: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        await db.commit()

    return {
        "status": "complete",
        "indexed": indexed_count,
        "skipped": skipped_count,
        "deleted": deleted_count,
        "errors": errors if errors else None,
        "namespace": NAMESPACE,
    }


async def reindex_docs() -> dict[str, Any]:
    """
    Force reindex all documentation.

    Useful for manual refresh via admin API or CLI.
    Same as index_platform_docs() but meant for explicit invocation.
    """
    return await index_platform_docs()
