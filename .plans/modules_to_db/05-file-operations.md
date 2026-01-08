# Phase 5: File Operations Integration

## Overview

Update `file_ops.py` to handle `entity_type="module"` for read/write/delete operations. Modules are stored in `workspace_files.content` and cached in Redis.

## Read Operation

**File:** `api/src/services/file_storage/file_ops.py`

Add to `read_file()` method:

```python
async def read_file(self, path: str) -> tuple[bytes, WorkspaceFile]:
    """Read file content and metadata."""
    file_record = await self._get_file_record(path)
    if not file_record:
        raise FileNotFoundError(f"File not found: {path}")

    entity_type = file_record.entity_type

    # Route based on entity type
    if entity_type == "workflow":
        # Existing: fetch from workflows.code
        workflow = await self._get_workflow_by_path(path)
        if workflow and workflow.code:
            return workflow.code.encode("utf-8"), file_record
        raise FileNotFoundError(f"Workflow code not found: {path}")

    elif entity_type == "form":
        # Existing: fetch from forms table
        form = await self._get_form_by_path(path)
        if form:
            return self._serialize_form(form), file_record
        raise FileNotFoundError(f"Form not found: {path}")

    elif entity_type == "module":
        # NEW: fetch from workspace_files.content
        if file_record.content is not None:
            return file_record.content.encode("utf-8"), file_record
        raise FileNotFoundError(f"Module content not found: {path}")

    else:
        # Regular file: fetch from S3
        content = await self._s3_client.get_object(path)
        return content, file_record
```

## Write Operation

Add module handling to `write_file()`:

```python
async def write_file(self, path: str, content: bytes) -> WorkspaceFile:
    """Write file content."""
    # Detect entity type
    platform_entity_type = self._detect_platform_entity_type(path, content)
    is_platform_entity = platform_entity_type is not None

    # Calculate content hash
    content_hash = hashlib.sha256(content).hexdigest()

    if platform_entity_type == "workflow":
        # Existing: upsert to workflows.code
        await self._upsert_workflow(path, content)

    elif platform_entity_type == "form":
        # Existing: upsert to forms table
        await self._upsert_form(path, content)

    elif platform_entity_type == "module":
        # NEW: store in workspace_files.content
        content_str = content.decode("utf-8")

        stmt = insert(WorkspaceFile).values(
            path=path,
            content=content_str,           # Store content directly
            entity_type="module",
            content_hash=content_hash,
            is_deleted=False,
            updated_at=func.now(),
        ).on_conflict_do_update(
            index_elements=["path"],
            set_={
                "content": content_str,
                "content_hash": content_hash,
                "entity_type": "module",
                "is_deleted": False,
                "updated_at": func.now(),
            },
        )
        await self._session.execute(stmt)

        # Update Redis cache
        from src.core.module_cache import set_module
        await set_module(path, content_str, content_hash)

    else:
        # Regular file: store in S3
        await self._s3_client.put_object(path, content)

    # Upsert workspace_files record (metadata for all files)
    file_record = await self._upsert_workspace_file(
        path=path,
        content_hash=content_hash,
        entity_type=platform_entity_type,
        content=content_str if platform_entity_type == "module" else None,
    )

    return file_record
```

## Delete Operation

Add cache invalidation to `delete_file()`:

```python
async def delete_file(self, path: str) -> None:
    """Delete a file (soft delete)."""
    file_record = await self._get_file_record(path)
    if not file_record:
        raise FileNotFoundError(f"File not found: {path}")

    entity_type = file_record.entity_type

    if entity_type == "workflow":
        # Existing: soft delete workflow
        await self._delete_workflow(path)

    elif entity_type == "form":
        # Existing: soft delete form
        await self._delete_form(path)

    elif entity_type == "module":
        # NEW: invalidate Redis cache
        from src.core.module_cache import invalidate_module
        await invalidate_module(path)

    else:
        # Regular file: delete from S3
        await self._s3_client.delete_object(path)

    # Soft delete workspace_files record
    file_record.is_deleted = True
    file_record.content = None  # Clear content for modules
    await self._session.commit()
```

## Move Operation

Handle module rename with cache update:

```python
async def move_file(self, old_path: str, new_path: str) -> WorkspaceFile:
    """Move/rename a file."""
    file_record = await self._get_file_record(old_path)
    if not file_record:
        raise FileNotFoundError(f"File not found: {old_path}")

    entity_type = file_record.entity_type

    if entity_type == "module":
        # Invalidate old cache entry
        from src.core.module_cache import invalidate_module, set_module
        await invalidate_module(old_path)

        # Update path in database
        file_record.path = new_path

        # Cache at new path
        if file_record.content:
            await set_module(new_path, file_record.content, file_record.content_hash or "")

    elif entity_type == "workflow":
        # Existing: update workflow path
        await self._move_workflow(old_path, new_path)

    # ... handle other entity types ...

    await self._session.commit()
    return file_record
```

## Entity Type Detection

The existing `_detect_platform_entity_type()` method calls `entity_detector.py`:

```python
def _detect_platform_entity_type(self, path: str, content: bytes) -> str | None:
    """Detect if file is a platform entity."""
    from src.services.file_storage.entity_detector import detect_platform_entity_type
    return detect_platform_entity_type(path, content)
```

With the changes to `entity_detector.py`, this now returns `"module"` for non-workflow Python files.
