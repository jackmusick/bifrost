# Design: Restrict file_index to Search Only

**Date:** 2026-02-16
**Status:** Proposed

## Problem

`file_index` was created as a search index for text content in `_repo/`. Its model docstring says "Search index for text content" and "No entity routing, no polymorphic references." But over time, multiple services started querying `FileIndex.content` directly to load code and read files, turning it into a de facto replacement for the old `workspace_files` table.

This defeats the architecture where:
- **S3** (`RepoStorage`) is the source of truth for all file content
- **Redis** (`module_cache`) is the hot cache for execution
- **file_index** is a search index only (text search via ILIKE/regex)

The `FileIndexService.read()` method is the main trap — it makes it trivially easy to treat the index as a data store. The existing Redis → S3 cache chain (`get_module` async, `get_module_sync` subprocess) is the intended read path but callers bypass it.

This also matters for the SDK subprocess architecture: workers should only need Redis + S3, not a database connection. Every `FileIndex` query in the execution path adds an unnecessary DB dependency.

## Design

### 1. Add S3 fallback to async `get_module()`

**File:** `api/src/core/module_cache.py`

Currently `get_module()` only checks Redis and returns `None` on miss. The sync version (`get_module_sync()` in `module_cache_sync.py`) already does Redis → S3 → re-cache. Make the async version match:

```
get_module(path):
  1. Redis lookup (existing, unchanged)
  2. On miss → RepoStorage.read(path)
  3. Decode UTF-8, compute SHA-256 hash
  4. Cache to Redis (self-healing)
  5. Return CachedModule | None
```

This makes `get_module()` the single way to get file content in async context, just as `get_module_sync()` is for sync context. No caller needs to remember a fallback chain.

### 2. Fix violators

| File | Current (wrong) | After |
|------|-----------------|-------|
| `workflow_orphan.py` | `_get_code_from_file_index()` queries `FileIndex.content` | Use `get_module(path)`, extract `.content` |
| `routers/workflows.py:1389-1395` | Inline `FileIndex.content` query for orphan file recreation | Use `get_module(path)` |
| `jobs/consumers/workflow_execution.py:623-631` | Reads `FileIndex.content_hash` to pin execution version | Delete entirely (best-effort check not worth the DB dependency) |
| `mcp_server/tools/code_editor.py` `list_content()` | Queries `FileIndex.path` to list files | Use `RepoStorage.list(prefix)` |
| `mcp_server/tools/code_editor.py` `delete_content()` | Checks `FileIndex.path` for existence | Use `RepoStorage.exists(path)` |

### 3. Remove trap methods from FileIndexService

**File:** `api/src/services/file_index_service.py`

Remove:
- `read()` — reads content from DB, the main attractive nuisance
- `get_hash()` — reads content_hash from DB

Keep:
- `write()` — dual-write on save (S3 + DB index)
- `delete()` — cleanup on file removal
- `search()` — text search via ILIKE (the whole point)
- `list_paths()` — listing indexed paths (still useful for search/reconciliation)

### 4. Out of scope

- **`dependency_graph.py`** — Uses `FileIndex.content` to scan app source files for workflow references. This is search-like behavior but architecturally different from the execution path violations. Separate cleanup.
- **`editor/search.py`** — Queries `FileIndex.content` for full-text regex search. This is legitimate search index usage.
- **`mcp_server/tools/code_editor.py` `search_content()`** — Same, legitimate search.

## Testing

- Update `workflow_orphan` unit tests to mock `get_module()` instead of `FileIndex` queries
- Update `workflow_execution` consumer tests to remove hash pinning assertions
- Add/verify async `get_module()` tests for S3 fallback + re-cache behavior
- Update `test_file_index_service.py` to remove tests for `read()`/`get_hash()`
- Verify code editor `list_content` works with `RepoStorage.list()`
- Verify code editor `delete_content` existence check works with `RepoStorage.exists()`
