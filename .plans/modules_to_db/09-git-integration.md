# Phase 9: GitHub Integration Compatibility

## Overview

Ensure Git operations (push/pull) continue to work with database-backed modules. Git operations use an ephemeral workspace pattern.

## Ephemeral Workspace Pattern

Git operations don't use the persistent `/tmp/bifrost/workspace` mirror. Instead:

1. **Push (DB → Git):**
   - Create temp directory
   - Serialize DB entities to files
   - Run git commit + push
   - Delete temp directory

2. **Pull (Git → DB):**
   - Clone/pull to temp directory
   - Parse files and upsert to DB
   - Delete temp directory

This pattern already exists for workflows, forms, apps. We extend it to modules.

## Push: Serialize Modules

**File:** `api/src/services/git_integration.py`

Add to `_serialize_platform_entities_to_workspace()`:

```python
async def _serialize_platform_entities_to_workspace(
    self,
    workspace_path: Path,
) -> list[str]:
    """
    Serialize all platform entities from DB to filesystem for git push.

    Returns list of paths that were serialized.
    """
    serialized_paths = []

    # Existing: Serialize workflows
    workflows = await self._get_all_workflows()
    for workflow in workflows:
        file_path = workspace_path / workflow.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(workflow.code)
        serialized_paths.append(workflow.path)

    # Existing: Serialize forms
    forms = await self._get_all_forms()
    for form in forms:
        file_path = workspace_path / form.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(form.to_dict(), indent=2))
        serialized_paths.append(form.path)

    # NEW: Serialize modules from workspace_files.content
    modules = await self._get_all_modules()
    for module in modules:
        file_path = workspace_path / module.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(module.content)
        serialized_paths.append(module.path)

    return serialized_paths


async def _get_all_modules(self) -> list[WorkspaceFile]:
    """Get all module files from database."""
    stmt = select(WorkspaceFile).where(
        WorkspaceFile.entity_type == "module",
        WorkspaceFile.is_deleted == False,
        WorkspaceFile.content.isnot(None),
    )
    result = await self._session.execute(stmt)
    return list(result.scalars().all())
```

## Pull: Parse Modules

Add to `_parse_and_upsert_platform_entities()`:

```python
async def _parse_and_upsert_platform_entities(
    self,
    workspace_path: Path,
    updated_files: list[str],
) -> None:
    """
    Parse files from workspace and upsert to database.

    Called after git pull to sync repository changes to DB.
    """
    for file_path_str in updated_files:
        full_path = workspace_path / file_path_str

        if not full_path.exists():
            # File was deleted - handle soft delete
            await self._handle_deleted_file(file_path_str)
            continue

        if file_path_str.endswith(".py"):
            content = full_path.read_text()
            content_bytes = content.encode("utf-8")

            # Detect entity type
            entity_type = detect_python_entity_type(content_bytes)

            if entity_type == "workflow":
                # Existing: parse and upsert workflow
                await self._parse_python_file(file_path_str, content)

            elif entity_type == "module":
                # NEW: upsert module to workspace_files
                await self._parse_module_file(file_path_str, content)

        elif file_path_str.endswith(".form.json"):
            # Existing: parse and upsert form
            await self._parse_form_file(file_path_str, full_path)

        # ... other entity types ...


async def _parse_module_file(self, path: str, content: str) -> None:
    """Parse and upsert a module file."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    stmt = insert(WorkspaceFile).values(
        path=path,
        content=content,
        entity_type="module",
        content_hash=content_hash,
        is_deleted=False,
        updated_at=func.now(),
    ).on_conflict_do_update(
        index_elements=["path"],
        set_={
            "content": content,
            "content_hash": content_hash,
            "entity_type": "module",
            "is_deleted": False,
            "updated_at": func.now(),
        },
    )
    await self._session.execute(stmt)

    # Update Redis cache
    from src.core.module_cache import set_module
    await set_module(path, content, content_hash)

    logger.info(f"Upserted module from git: {path}")
```

## Handling Deleted Files

When git pull shows a file was deleted:

```python
async def _handle_deleted_file(self, path: str) -> None:
    """Handle a file that was deleted in git."""
    file_record = await self._get_file_record(path)
    if not file_record:
        return  # Already doesn't exist

    if file_record.entity_type == "module":
        # Soft delete and invalidate cache
        file_record.is_deleted = True
        file_record.content = None

        from src.core.module_cache import invalidate_module
        await invalidate_module(path)

    elif file_record.entity_type == "workflow":
        # Existing: soft delete workflow
        await self._delete_workflow(path)

    # ... other entity types ...

    await self._session.commit()
```

## Conflict Resolution

When the same file changed in both DB and Git:

| Scenario | Resolution |
|----------|------------|
| User pushed | DB version wins (user explicitly pushed their changes) |
| User pulled | Git version wins (user explicitly pulled remote changes) |
| Merge conflict | Show conflict to user for manual resolution |

This matches existing behavior for workflows.

## Python Files Without Decorators

**Question:** What about Python files in the repo that don't have workflow decorators?

**Answer:** With the new entity detection:
- Files without decorators become `entity_type="module"`
- They're stored in `workspace_files.content`
- Available for import by workflows

This is actually better - ALL Python code in the repo is captured in DB.

## Syntax Errors

If a file has Python syntax errors:
- `detect_python_entity_type()` returns `"module"` (can't parse for decorators)
- Content is stored as-is
- Import will fail with SyntaxError at runtime
- This matches filesystem behavior (broken file would also fail on import)

## Git Ignore Patterns

Consider `.gitignore` patterns for generated/temporary files:

```gitignore
# Don't commit these even if they exist
__pycache__/
*.pyc
.pytest_cache/
```

The git integration already respects `.gitignore` when serializing/parsing.
