# Phase 10: Data Migration

## Overview

One-time migration to populate `workspace_files.content` from S3 for existing Python modules.

## Migration Script

**File:** `api/scripts/migrate_modules_to_db.py`

```python
#!/usr/bin/env python3
"""
One-time migration: Copy Python module content from S3 to workspace_files.content.

Run this AFTER deploying the content column migration, BEFORE enabling virtual imports.

Usage:
    python -m scripts.migrate_modules_to_db
    python -m scripts.migrate_modules_to_db --dry-run
"""

import argparse
import asyncio
import logging
from typing import AsyncIterator

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.core.s3 import get_s3_client
from src.models.orm.workspace import WorkspaceFile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate_modules")


async def get_python_files_without_content(
    session: AsyncSession,
) -> AsyncIterator[WorkspaceFile]:
    """Get Python files that don't have content in DB yet."""
    stmt = select(WorkspaceFile).where(
        WorkspaceFile.path.like("%.py"),
        WorkspaceFile.is_deleted == False,
        WorkspaceFile.content.is_(None),
        # Exclude workflows (they have content in workflows.code)
        WorkspaceFile.entity_type != "workflow",
    )
    result = await session.execute(stmt)
    for file in result.scalars():
        yield file


async def migrate_file(
    session: AsyncSession,
    s3_client,
    file: WorkspaceFile,
    dry_run: bool = False,
) -> bool:
    """Migrate a single file from S3 to DB."""
    try:
        # Fetch content from S3
        content_bytes = await s3_client.get_object(file.path)
        content = content_bytes.decode("utf-8")

        if dry_run:
            logger.info(f"[DRY RUN] Would migrate: {file.path} ({len(content)} bytes)")
            return True

        # Update database
        file.content = content
        file.entity_type = "module"
        await session.commit()

        logger.info(f"Migrated: {file.path} ({len(content)} bytes)")
        return True

    except s3_client.exceptions.NoSuchKey:
        logger.warning(f"S3 object not found: {file.path}")
        return False

    except UnicodeDecodeError:
        logger.warning(f"Not UTF-8 text: {file.path}")
        return False

    except Exception as e:
        logger.error(f"Failed to migrate {file.path}: {e}")
        return False


async def main(dry_run: bool = False) -> None:
    """Run the migration."""
    logger.info("Starting module migration from S3 to DB...")
    if dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    s3_client = await get_s3_client()
    success_count = 0
    error_count = 0

    async with get_async_session() as session:
        async for file in get_python_files_without_content(session):
            if await migrate_file(session, s3_client, file, dry_run):
                success_count += 1
            else:
                error_count += 1

    logger.info(f"Migration complete: {success_count} succeeded, {error_count} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Python modules from S3 to DB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
```

## Migration Steps

### 1. Deploy Schema Migration

```bash
# Deploy the content column migration
alembic upgrade head
```

This adds `workspace_files.content` column and index.

### 2. Run Data Migration (Dry Run)

```bash
# See what would be migrated
python -m scripts.migrate_modules_to_db --dry-run
```

Review output to ensure it looks correct.

### 3. Run Data Migration

```bash
# Actually migrate the data
python -m scripts.migrate_modules_to_db
```

### 4. Verify Migration

```sql
-- Check migration results
SELECT
    COUNT(*) as total_modules,
    COUNT(content) as with_content,
    COUNT(*) - COUNT(content) as missing_content
FROM workspace_files
WHERE path LIKE '%.py'
  AND entity_type = 'module'
  AND NOT is_deleted;
```

### 5. Enable Virtual Imports

Deploy the virtual import hook and worker changes.

### 6. Clean Up S3 (Optional)

After confirming virtual imports work:

```python
# Optional: Remove Python files from S3
async def cleanup_s3_python_files():
    s3_client = await get_s3_client()
    async with get_async_session() as session:
        stmt = select(WorkspaceFile).where(
            WorkspaceFile.path.like("%.py"),
            WorkspaceFile.entity_type == "module",
            WorkspaceFile.content.isnot(None),
        )
        result = await session.execute(stmt)
        for file in result.scalars():
            try:
                await s3_client.delete_object(file.path)
                logger.info(f"Deleted from S3: {file.path}")
            except Exception as e:
                logger.warning(f"Failed to delete {file.path}: {e}")
```

## Rollback

If issues are discovered:

1. **Re-populate S3 from DB:**
   ```python
   async def restore_s3_from_db():
       s3_client = await get_s3_client()
       async with get_async_session() as session:
           stmt = select(WorkspaceFile).where(
               WorkspaceFile.entity_type == "module",
               WorkspaceFile.content.isnot(None),
           )
           result = await session.execute(stmt)
           for file in result.scalars():
               await s3_client.put_object(file.path, file.content.encode())
   ```

2. **Disable virtual import hook** (feature flag or code revert)

3. **Re-enable workspace sync** infrastructure

The DB content column can remain - it doesn't hurt anything if not used.

## Performance Considerations

- Migration runs sequentially to avoid overwhelming S3/DB
- For large codebases, consider batching with progress tracking
- Can be run during low-traffic periods
- Idempotent - can be re-run safely (checks for existing content)

## Monitoring

Track migration progress:

```sql
-- Migration progress
SELECT
    entity_type,
    COUNT(*) as count,
    COUNT(content) as migrated
FROM workspace_files
WHERE path LIKE '%.py'
  AND NOT is_deleted
GROUP BY entity_type;
```
