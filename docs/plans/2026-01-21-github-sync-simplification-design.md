# GitHub Sync Simplification Design

**Date**: 2026-01-21
**Status**: Ready for implementation

## Summary

Simplify the GitHub sync system by:
1. Removing unused `child_files` complexity from uncommitted changes
2. Building reference maps once per sync operation instead of multiple times
3. Caching cloned repositories between preview and execute phases

## Background

The current sync system has accumulated complexity:
- `build_workflow_ref_map()` called 2-3 times per sync preview
- `build_ref_to_uuid_map()` called per-entity during import
- Repository cloned separately for preview and execute phases
- Uncommitted changes added `child_files` and `combined_sha` that aren't used (UI groups client-side via `parent_slug`)

## Design

### Phase 0: Clean Up Uncommitted Changes

Remove unused `child_files` complexity:

**`github_sync_virtual_files.py`**:
- Remove `child_files: list["VirtualFile"] | None = None` field from VirtualFile
- Remove `_compute_combined_sha()` method
- Remove composite entry creation logic
- Keep the `entity_id = f"app::{app.id}"` change (stable IDs are good)

**`github_sync.py`**:
- Remove `if vf.child_files is None` filter (no longer needed)

### Phase 1: Build Maps Once

Pass maps through call chains instead of rebuilding.

**`github_sync_virtual_files.py`**:
```python
async def get_all_virtual_files(
    self,
    workflow_map: dict[str, str] | None = None
) -> VirtualFileResult:
    if workflow_map is None:
        workflow_map = await build_workflow_ref_map(self.db)

    # Pass to _get_form_files, _get_agent_files, _get_app_files
    form_result = await self._get_form_files(workflow_map)
    agent_result = await self._get_agent_files(workflow_map)
    app_result = await self._get_app_files(workflow_map)
    ...
```

**`github_sync.py`**:
```python
async def get_sync_preview(self, ...):
    # Build maps once at start
    workflow_map = await build_workflow_ref_map(self.db)

    # Pass to virtual file provider
    virtual_files = await self.virtual_file_provider.get_all_virtual_files(
        workflow_map=workflow_map
    )

async def execute_sync(self, ...):
    # Build ref_to_uuid map once for all imports
    ref_to_uuid = await build_ref_to_uuid_map(self.db)

    # Pass to each import operation
    for action in actions:
        await self._import_entity(action, ref_to_uuid=ref_to_uuid)
```

**Indexers** (`form.py`, `agent.py`, `app.py`):
```python
# Add optional parameter, use cached map if provided
async def index_form(
    self,
    path: str,
    content: bytes,
    ref_to_uuid: dict[str, str] | None = None
) -> Form:
    if ref_to_uuid is None:
        ref_to_uuid = await build_ref_to_uuid_map(self.db)
    ...
```

### Phase 2: Clone Caching

Cache clones in scheduler with TTL.

**`scheduler/main.py`**:
```python
class Scheduler:
    def __init__(self):
        # Cache: org_id -> (clone_path, commit_sha, timestamp)
        self._sync_clone_cache: dict[str, tuple[Path, str, float]] = {}
        self._clone_cache_ttl = 300  # 5 minutes

    async def _handle_git_sync_preview_request(self, data):
        preview = await sync_service.get_sync_preview(...)

        # Cache clone after successful preview
        if preview.clone_path:
            self._sync_clone_cache[org_id] = (
                preview.clone_path,
                preview.commit_sha,
                time.time()
            )

    async def _handle_git_sync_request(self, data):
        # Check cache
        cached = self._sync_clone_cache.get(org_id)
        clone_path = None

        if cached:
            path, sha, ts = cached
            if (time.time() - ts < self._clone_cache_ttl
                and sha == expected_sha
                and path.exists()):
                clone_path = path

        result = await sync_service.execute_sync(
            ...,
            cached_clone_path=clone_path
        )

        # Clear cache after execute
        self._sync_clone_cache.pop(org_id, None)
```

**`github_sync.py`**:
```python
async def execute_sync(
    self,
    ...,
    cached_clone_path: Path | None = None
) -> SyncResult:
    if cached_clone_path and cached_clone_path.exists():
        current_sha = self._get_head_sha(cached_clone_path)
        if current_sha == expected_sha:
            clone_path = cached_clone_path
            logger.info("Using cached clone from preview")
        else:
            clone_path = await self._clone_repo()
    else:
        clone_path = await self._clone_repo()
```

## Files Modified

| Phase | File | Changes |
|-------|------|---------|
| 0 | `api/src/services/github_sync_virtual_files.py` | Remove `child_files`, `_compute_combined_sha()` |
| 0 | `api/src/services/github_sync.py` | Remove `child_files is None` filter |
| 1 | `api/src/services/github_sync_virtual_files.py` | Add `workflow_map` parameter |
| 1 | `api/src/services/github_sync.py` | Build maps once, pass through |
| 1 | `api/src/services/file_storage/indexers/form.py` | Add optional `ref_to_uuid` param |
| 1 | `api/src/services/file_storage/indexers/agent.py` | Add optional `ref_to_uuid` param |
| 1 | `api/src/services/file_storage/indexers/app.py` | Add optional `ref_to_uuid` param |
| 2 | `api/src/scheduler/main.py` | Add clone cache dict, TTL management |
| 2 | `api/src/services/github_sync.py` | Accept `cached_clone_path` param |

## Verification

After each phase:
```bash
cd api && pyright
cd api && ruff check .
./test.sh tests/unit/services/test_github_sync.py
./test.sh tests/unit/services/test_github_sync_virtual_files.py
```

Manual verification:
1. Run sync preview
2. Run sync execute immediately after
3. Check logs for "Using cached clone from preview"

## Expected Outcomes

| Metric | Before | After |
|--------|--------|-------|
| Map builds per sync preview | 2-3 | 1 |
| Map builds per import | N (per entity) | 1 |
| Repo clones per preview+execute | 2 | 1 (if within TTL) |
| Unused complexity (`child_files`) | Present | Removed |
