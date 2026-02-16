# file_index Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restrict `file_index` to search-only by routing all content reads through the Redis→S3 cache chain (`get_module()`).

**Architecture:** `get_module()` becomes the single async content resolver (Redis→S3→re-cache), mirroring `get_module_sync()` for subprocesses. `FileIndexService.read()` and `get_hash()` are removed to eliminate the trap. All callers that queried `FileIndex.content` directly switch to `get_module()`.

**Tech Stack:** Python/FastAPI, Redis (module cache), S3/MinIO (RepoStorage), SQLAlchemy (file_index search only)

**Design doc:** `docs/plans/2026-02-16-file-index-cleanup-design.md`

---

### Task 1: Add S3 fallback to async `get_module()`

**Files:**
- Modify: `api/src/core/module_cache.py:32-47`
- Test: `api/tests/unit/core/test_module_cache.py`

**Step 1: Write failing tests for S3 fallback**

Add to `TestModuleCacheAsync` in `api/tests/unit/core/test_module_cache.py`:

```python
async def test_get_module_falls_back_to_s3(self, mock_redis_client):
    """When Redis misses, get_module should fall back to S3 and re-cache."""
    mock_client, mock_redis = mock_redis_client
    mock_client.get.return_value = None  # Redis miss

    mock_repo = AsyncMock()
    mock_repo.read.return_value = b"print('from s3')"

    with (
        patch("src.core.module_cache.get_redis_client", return_value=mock_client),
        patch("src.core.module_cache.RepoStorage", return_value=mock_repo),
    ):
        from src.core.module_cache import get_module

        result = await get_module("shared/test.py")

        assert result is not None
        assert result["content"] == "print('from s3')"
        assert result["path"] == "shared/test.py"
        assert result["hash"]  # SHA-256 hash present
        # Verify re-cached to Redis
        mock_client.setex.assert_called_once()

async def test_get_module_s3_not_found(self, mock_redis_client):
    """When both Redis and S3 miss, get_module returns None."""
    mock_client, _ = mock_redis_client
    mock_client.get.return_value = None

    mock_repo = AsyncMock()
    mock_repo.read.side_effect = Exception("NoSuchKey")

    with (
        patch("src.core.module_cache.get_redis_client", return_value=mock_client),
        patch("src.core.module_cache.RepoStorage", return_value=mock_repo),
    ):
        from src.core.module_cache import get_module

        result = await get_module("nonexistent.py")
        assert result is None

async def test_get_module_s3_fallback_handles_binary(self, mock_redis_client):
    """S3 fallback gracefully handles non-UTF-8 content."""
    mock_client, _ = mock_redis_client
    mock_client.get.return_value = None

    mock_repo = AsyncMock()
    mock_repo.read.return_value = b"\x89PNG\r\n"  # Binary

    with (
        patch("src.core.module_cache.get_redis_client", return_value=mock_client),
        patch("src.core.module_cache.RepoStorage", return_value=mock_repo),
    ):
        from src.core.module_cache import get_module

        result = await get_module("image.png")
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `./test.sh tests/unit/core/test_module_cache.py -v`
Expected: 3 new tests FAIL (no S3 fallback in `get_module` yet)

**Step 3: Implement S3 fallback in `get_module()`**

In `api/src/core/module_cache.py`, add import at top and update `get_module()`:

```python
import hashlib

from src.services.repo_storage import RepoStorage
```

Replace the `get_module` function body:

```python
async def get_module(path: str) -> CachedModule | None:
    """
    Fetch a module from cache, falling back to S3.

    Lookup order:
    1. Redis cache (fast path)
    2. S3 _repo/ (fallback, re-caches to Redis)
    3. None (module not found)

    Args:
        path: Module path relative to workspace (e.g., "shared/halopsa.py")

    Returns:
        CachedModule dict if found, None otherwise
    """
    redis = get_redis_client()
    key = f"{MODULE_KEY_PREFIX}{path}"
    data = await redis.get(key)
    if data:
        return json.loads(data)

    # Redis miss — try S3 fallback
    try:
        repo = RepoStorage()
        content_bytes = await repo.read(path)
    except Exception:
        logger.debug(f"Module not in cache or S3: {path}")
        return None

    try:
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(f"Could not decode {path} as UTF-8, skipping")
        return None

    content_hash = hashlib.sha256(content_bytes).hexdigest()
    module: CachedModule = {
        "content": content_str,
        "path": path,
        "hash": content_hash,
    }

    # Re-cache to Redis (self-healing)
    try:
        await redis.setex(key, 86400, json.dumps(module))
        redis_conn = await redis._get_redis()
        from typing import Awaitable, cast
        await cast(Awaitable[int], redis_conn.sadd(MODULE_INDEX_KEY, path))
    except Exception as e:
        logger.warning(f"Failed to re-cache S3 module to Redis: {e}")

    return module
```

Note: the `cast` and `Awaitable` imports are already at the top of the file. Move the `hashlib` import to the top-level imports.

**Step 4: Run tests to verify they pass**

Run: `./test.sh tests/unit/core/test_module_cache.py -v`
Expected: All tests PASS

**Step 5: Also update existing `test_get_module_not_found` test**

The existing `test_get_module_not_found` test mocks only Redis. Now that `get_module` also tries S3, this test needs to mock S3 too:

```python
async def test_get_module_not_found(self, mock_redis_client):
    """Test fetching a module that doesn't exist in cache or S3."""
    mock_client, _ = mock_redis_client
    mock_client.get.return_value = None

    mock_repo = AsyncMock()
    mock_repo.read.side_effect = Exception("NoSuchKey")

    with (
        patch("src.core.module_cache.get_redis_client", return_value=mock_client),
        patch("src.core.module_cache.RepoStorage", return_value=mock_repo),
    ):
        from src.core.module_cache import get_module

        result = await get_module("nonexistent/module.py")
        assert result is None
```

**Step 6: Run full test suite to verify no regressions**

Run: `./test.sh tests/unit/core/test_module_cache.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add api/src/core/module_cache.py api/tests/unit/core/test_module_cache.py
git commit -m "feat: add S3 fallback to async get_module() for self-healing cache"
```

---

### Task 2: Remove `read()` and `get_hash()` from FileIndexService

**Files:**
- Modify: `api/src/services/file_index_service.py:78-87` (remove `read`), `:119-125` (remove `get_hash`)
- Modify: `api/tests/unit/test_file_index_service.py`

**Step 1: Remove `read()` and `get_hash()` methods**

In `api/src/services/file_index_service.py`, delete the `read()` method (lines 78-83), the `read_bytes()` method (lines 85-87), and the `get_hash()` method (lines 119-125).

Keep: `write()`, `delete()`, `search()`, `list_paths()`.

**Step 2: Run tests to see what breaks**

Run: `./test.sh tests/unit/test_file_index_service.py -v`
Expected: PASS (no existing tests call `read()` or `get_hash()` directly — checked)

**Step 3: Run broader test to find callers**

Run: `./test.sh tests/unit/ -v --tb=short 2>&1 | head -100`
Expected: May see import/call failures in tests that use `file_index.read()`. Note them for Tasks 3-5.

**Step 4: Commit**

```bash
git add api/src/services/file_index_service.py api/tests/unit/test_file_index_service.py
git commit -m "refactor: remove read() and get_hash() from FileIndexService

These methods made it too easy to treat the search index as a content
store. All content reads should go through get_module() (Redis→S3)."
```

---

### Task 3: Fix workflow_orphan.py to use `get_module()`

**Files:**
- Modify: `api/src/services/workflow_orphan.py`
- Test: `api/tests/unit/services/test_workflow_orphan.py`

**Step 1: Replace `_get_code_from_file_index` with `get_module()`**

In `api/src/services/workflow_orphan.py`:

1. Remove the `from src.models.orm.file_index import FileIndex` import (line 28)
2. Replace `_get_code_from_file_index` method:

```python
async def _get_code(self, path: str) -> str | None:
    """Load file content via Redis→S3 cache chain."""
    from src.core.module_cache import get_module

    cached = await get_module(path)
    return cached["content"] if cached else None
```

3. Replace all calls to `self._get_code_from_file_index(...)` with `self._get_code(...)` throughout the file (lines 127, 165, 199, 315).

4. Remove `from sqlalchemy import select` import if no longer used by remaining code — check first, it may be used by `_get_workflow_references`.

**Step 2: Run tests**

Run: `./test.sh tests/unit/services/test_workflow_orphan.py -v`
Expected: PASS (existing tests only test data models, not the DB query method)

**Step 3: Commit**

```bash
git add api/src/services/workflow_orphan.py
git commit -m "refactor: workflow_orphan reads code via Redis→S3 instead of file_index"
```

---

### Task 4: Fix routers/workflows.py orphan recreation

**Files:**
- Modify: `api/src/routers/workflows.py:1389-1395`

**Step 1: Replace inline FileIndex query with `get_module()`**

In `api/src/routers/workflows.py`, replace lines 1389-1395:

```python
        # Load code from file_index
        from sqlalchemy import select as sa_select
        from src.models.orm.file_index import FileIndex
        fi_result = await db.execute(
            sa_select(FileIndex.content).where(FileIndex.path == workflow.path)
        )
        code_content = fi_result.scalar_one_or_none()
```

With:

```python
        # Load code via Redis→S3 cache chain
        from src.core.module_cache import get_module
        cached = await get_module(workflow.path)
        code_content = cached["content"] if cached else None
```

**Step 2: Run relevant tests**

Run: `./test.sh tests/unit/ -v -k "workflow" --tb=short`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/routers/workflows.py
git commit -m "refactor: orphan file recreation reads code via Redis→S3"
```

---

### Task 5: Remove content_hash pinning from workflow_execution consumer

**Files:**
- Modify: `api/src/jobs/consumers/workflow_execution.py:621-631`

**Step 1: Delete the hash pinning block**

In `api/src/jobs/consumers/workflow_execution.py`, delete lines 621-631 (the block that imports FileIndex and queries content_hash). Also set `content_hash = None` if it's used later, or remove references to it downstream.

Check what uses `content_hash` after this block — search for it in the same file:

```python
                    # Pin execution to content hash for reproducibility.
                    # Worker validates loaded code matches this hash.
                    from sqlalchemy import select as sa_select
                    from src.models.orm.file_index import FileIndex

                    hash_result = await db.execute(
                        sa_select(FileIndex.content_hash).where(
                            FileIndex.path == file_path
                        )
                    )
                    content_hash = hash_result.scalar_one_or_none()
```

Replace the entire block with just:

```python
                    content_hash = None
```

Or if `content_hash` isn't referenced downstream, delete it entirely.

**Step 2: Run relevant tests**

Run: `./test.sh tests/e2e/api/test_executions.py -v --tb=short`
Expected: PASS (hash was best-effort, removing it shouldn't break execution)

**Step 3: Commit**

```bash
git add api/src/jobs/consumers/workflow_execution.py
git commit -m "refactor: remove content_hash pinning from execution consumer

The hash check was best-effort and added an unnecessary DB dependency
to the execution path. Workers load code via Redis→S3."
```

---

### Task 6: Fix app_code_files.py to use `get_module()`

**Files:**
- Modify: `api/src/routers/app_code_files.py` (5 calls to `file_index.read()`)

**Step 1: Replace all `file_index.read()` calls**

There are 5 occurrences in `app_code_files.py`:

1. **Line 356** — reading app source files in list endpoint
2. **Line 398** — reading a single app file
3. **Line 532** — reading app.yaml for dependencies
4. **Line 617** — reading app.yaml for get_dependencies endpoint
5. **Line 660** — reading app.yaml for put_dependencies endpoint

For each, replace the `file_index.read(path)` call with:

```python
from src.core.module_cache import get_module

cached = await get_module(path)
content = cached["content"] if cached else None
```

Remove `FileIndexService` instantiation where it's only used for `read()`. If it's also used for `list_paths()` in the same function, keep it.

**Step 2: Run tests**

Run: `./test.sh tests/unit/ -v -k "app" --tb=short`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/routers/app_code_files.py
git commit -m "refactor: app_code_files reads content via Redis→S3 instead of file_index"
```

---

### Task 7: Fix MCP apps tool to use `get_module()`

**Files:**
- Modify: `api/src/services/mcp_server/tools/apps.py` (2 calls to `file_index.read()`)

**Step 1: Replace `file_index.read()` calls**

1. **Line 1082** — reading app.yaml for get_app_dependencies
2. **Line 1168** — reading app.yaml for update_app_dependencies

Replace each with:

```python
from src.core.module_cache import get_module

cached = await get_module(f"apps/{app.slug}/app.yaml")
yaml_content = cached["content"] if cached else None
```

Remove `FileIndexService` import/instantiation if no longer needed in those functions.

**Step 2: Run tests**

Run: `./test.sh tests/unit/services/mcp_server/ -v --tb=short`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/services/mcp_server/tools/apps.py
git commit -m "refactor: MCP apps tool reads content via Redis→S3 instead of file_index"
```

---

### Task 8: Fix code_editor list_content to use RepoStorage.list()

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py` (lines 290-319)
- Test: `api/tests/unit/services/mcp_server/test_code_editor_tools.py`

**Step 1: Replace `list_content` implementation**

Replace the body of `list_content()` (lines 298-319):

```python
async def list_content(
    context: Any,
    organization_id: str | None = None,
    path_prefix: str | None = None,
) -> ToolResult:
    """List files in the workspace. Optionally filter by path prefix."""
    logger.info(f"MCP list_content: path_prefix={path_prefix}")

    try:
        repo = RepoStorage()
        paths = await repo.list(path_prefix or "")
        files = [{"path": p} for p in sorted(paths)]

        if not files:
            display = "No files found"
        else:
            lines = [f"Found {len(files)} file(s):", ""]
            for f in files:
                lines.append(f"  {f['path']}")
            display = "\n".join(lines)

        return success_result(display, {"files": files, "count": len(files)})
    except Exception as e:
        logger.exception(f"Error in list_content: {e}")
        return error_result(f"List failed: {str(e)}")
```

This removes the `get_db_context` and `FileIndex` query. Add `RepoStorage` import at top if not already imported.

**Step 2: Fix `delete_content` existence check**

In `delete_content()` (line 721-728), replace the FileIndex existence check:

```python
        async with get_db_context() as db:
            # Verify file exists before deleting
            fi_result = await db.execute(
                select(FileIndex.path).where(FileIndex.path == path)
            )
            if fi_result.scalar_one_or_none() is None:
                # Also check S3 as a fallback (file might not be indexed yet)
                content = await _read_from_cache_or_s3(path)
                if content is None:
                    return error_result(f"File not found: {path}")
```

With:

```python
        async with get_db_context() as db:
            # Verify file exists in S3 before deleting
            repo = RepoStorage()
            if not await repo.exists(path):
                return error_result(f"File not found: {path}")
```

**Step 3: Remove unused imports**

Check if `FileIndex` and `select` are still needed in `code_editor.py` after these changes. `search_content` still uses them, so `FileIndex` and `select` stay. But `list_content` no longer needs `get_db_context` — check if other functions still use it (yes, `search_content` and `delete_content` do).

Add `from src.services.repo_storage import RepoStorage` at the top if not already present.

**Step 4: Run tests**

Run: `./test.sh tests/unit/services/mcp_server/test_code_editor_tools.py -v --tb=short`
Expected: PASS (or update mocks if tests mock FileIndex queries for list/delete)

**Step 5: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py
git commit -m "refactor: code_editor list/delete use S3 instead of file_index"
```

---

### Task 9: Remove `_read_from_cache_or_s3` helper from code_editor

**Files:**
- Modify: `api/src/services/mcp_server/tools/code_editor.py`

**Step 1: Replace `_read_from_cache_or_s3` with `get_module()`**

Now that `get_module()` itself does Redis→S3→re-cache, the `_read_from_cache_or_s3` helper (lines 151-177) in `code_editor.py` is redundant. It duplicates the same logic.

Replace `_read_from_cache_or_s3`:

```python
async def _read_from_cache_or_s3(path: str) -> str | None:
    """Load file content via Redis→S3 cache chain."""
    from src.core.module_cache import get_module

    cached = await get_module(path)
    return cached["content"] if cached else None
```

This simplifies the function to a thin wrapper around `get_module()`, which now handles the full chain.

**Step 2: Run tests**

Run: `./test.sh tests/unit/services/mcp_server/test_code_editor_tools.py -v --tb=short`
Expected: PASS

**Step 3: Commit**

```bash
git add api/src/services/mcp_server/tools/code_editor.py
git commit -m "refactor: simplify code_editor content reads to use get_module()"
```

---

### Task 10: Final verification

**Step 1: Check no remaining `file_index.read(` or `FileIndex.content` in non-search paths**

Run from repo root:

```bash
cd api && grep -rn "file_index\.read\b\|FileIndex\.content[^_]" src/ --include="*.py" | grep -v "search\|test\|__pycache__"
```

Expected: Only search-related hits (editor/search.py, search_content in code_editor.py, file_index_service.py search method, dependency_graph.py which is out of scope).

**Step 2: Run full test suite**

Run: `./test.sh`
Expected: All tests PASS

**Step 3: Run linting**

Run: `cd api && ruff check . && pyright`
Expected: Clean

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: cleanup after file_index restriction to search-only"
```
