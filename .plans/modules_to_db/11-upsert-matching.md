# Appendix: Upsert and Matching Process

## Overview

This document explains how file identity and change detection work in the system.

## File Identity: Path-Based

Files are identified by their **path**. The path is the primary key for matching:

```sql
-- workspace_files table
CREATE UNIQUE INDEX ix_workspace_files_path ON workspace_files(path);
```

When a file is written:
1. Check if `workspace_files` has a record with this `path`
2. If exists → UPDATE the existing record
3. If not → INSERT a new record

This is the "upsert" pattern (INSERT ... ON CONFLICT DO UPDATE).

## Change Detection: Content Hash

The `content_hash` column (SHA256 of file content) detects whether content changed:

```python
content_hash = hashlib.sha256(content).hexdigest()
```

Uses:
- **Skip redundant writes:** If hash matches, content hasn't changed
- **Cache invalidation:** Changed hash triggers Redis cache update
- **Git integration:** Detect which files actually changed between commits

## The Upsert Pattern

**File:** `api/src/services/file_storage/file_ops.py`

```python
from sqlalchemy.dialects.postgresql import insert

async def _upsert_workspace_file(
    self,
    path: str,
    content_hash: str,
    entity_type: str | None,
    content: str | None = None,
) -> WorkspaceFile:
    """Upsert a workspace file record."""

    stmt = insert(WorkspaceFile).values(
        path=path,
        content=content,
        entity_type=entity_type,
        content_hash=content_hash,
        is_deleted=False,
        updated_at=func.now(),
    ).on_conflict_do_update(
        index_elements=["path"],  # Match on path
        set_={
            "content": content,
            "content_hash": content_hash,
            "entity_type": entity_type,
            "is_deleted": False,
            "updated_at": func.now(),
        },
    )

    await self._session.execute(stmt)
    await self._session.commit()

    # Fetch the record
    return await self._get_file_record(path)
```

This is PostgreSQL's `INSERT ... ON CONFLICT DO UPDATE` (upsert):
- If `path` doesn't exist → INSERT new row
- If `path` exists → UPDATE existing row with new values

## Handling Moved/Renamed Files

When a file is moved from `old_path` to `new_path`:

```python
async def move_file(self, old_path: str, new_path: str) -> WorkspaceFile:
    """Move/rename a file."""

    # Get existing record
    file_record = await self._get_file_record(old_path)
    if not file_record:
        raise FileNotFoundError(f"File not found: {old_path}")

    # Check if destination exists
    existing = await self._get_file_record(new_path)
    if existing and not existing.is_deleted:
        raise FileExistsError(f"Destination already exists: {new_path}")

    # Update the path (content stays the same)
    file_record.path = new_path

    # For modules: update cache
    if file_record.entity_type == "module":
        await invalidate_module(old_path)
        if file_record.content:
            await set_module(new_path, file_record.content, file_record.content_hash)

    # For workflows: update path in workflows table too
    if file_record.entity_type == "workflow":
        await self._move_workflow(old_path, new_path)

    await self._session.commit()
    return file_record
```

**Key points:**
- Path is updated, content is preserved
- Old cache entry is invalidated
- New cache entry is created
- For workflows, the `workflows` table path is also updated

## Comparison with File Watcher

The old file watcher approach:

```python
# OLD: File watcher pattern
async def on_file_changed(event):
    path = event.path
    content = read_file(path)
    content_hash = hash(content)

    existing = await get_by_path(path)
    if existing and existing.content_hash == content_hash:
        return  # No change, skip

    # Content changed, update DB
    await upsert(path, content, content_hash)
```

The new API-driven approach:

```python
# NEW: API-driven pattern
async def write_file(path: str, content: bytes):
    content_hash = hash(content)

    # Always upsert - DB handles deduplication
    await upsert(path, content, content_hash)

    # Update cache
    await set_module(path, content, content_hash)
```

**Difference:** No need to check if file changed - the upsert handles it. If content is the same, the row is updated with the same values (harmless). Cache is always updated to ensure consistency.

## Entity Type Detection on Write

When writing a file, entity type is detected from content:

```python
async def write_file(self, path: str, content: bytes) -> WorkspaceFile:
    # Detect entity type from content
    entity_type = detect_platform_entity_type(path, content)

    # Route based on entity type
    if entity_type == "workflow":
        await self._upsert_workflow(path, content)
    elif entity_type == "module":
        await self._upsert_module(path, content)
    elif entity_type == "form":
        await self._upsert_form(path, content)
    # ... etc
```

The entity type can change if decorators are added/removed:
- Add `@workflow` decorator → changes from `module` to `workflow`
- Remove `@workflow` decorator → changes from `workflow` to `module`

The upsert updates the `entity_type` column accordingly.

## Soft Deletes

Files are soft-deleted (marked as deleted, not removed):

```python
async def delete_file(self, path: str) -> None:
    file_record = await self._get_file_record(path)

    # Mark as deleted
    file_record.is_deleted = True
    file_record.content = None  # Clear content to save space

    await self._session.commit()
```

Benefits:
- Can restore accidentally deleted files
- Audit trail of what existed
- Foreign keys don't break

## Summary

| Aspect | How It Works |
|--------|--------------|
| Identity | Path is the unique identifier |
| Matching | Upsert matches on path |
| Change detection | content_hash column |
| Rename/move | Update path, preserve content |
| Delete | Soft delete (is_deleted = true) |
| Entity type | Detected from content on each write |
