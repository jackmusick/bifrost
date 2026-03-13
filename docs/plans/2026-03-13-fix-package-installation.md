# Fix Package Installation Flow

## Context

Two bugs in the package install UI:
1. **422 on "Install from requirements.txt"** — Frontend sends `{}` but `package_name` is required (`min_length=1`).
2. **Spinner hangs forever** — Multiple workers each send WebSocket `complete` events; no way to track when all are done.

The current flow is overengineered. Workers already install from the requirements cache on process startup (`_install_requirements_from_cache_sync()` in `simple_worker.py`). The broadcast pip-install-per-worker is redundant — recycled processes handle it.

**New approach**: API updates `requirements.txt` in S3 + Redis cache, broadcasts "recycle" to workers, returns immediately. Workers recycle pools; new processes pip install from cache on startup.

## Plan

### Step 1: Make `package_name` optional

**File**: `api/src/models/contracts/common.py`
- `package_name: str | None = Field(default=None, ...)`

### Step 2: Update `requirements_cache.py` — S3 source of truth, keep Redis cache

**File**: `api/src/core/requirements_cache.py`

Currently writes to `FileIndex` table directly. Change to:
- `save_requirements()` (rename from `save_requirements_to_db`):
  - Write to S3 via `RepoStorage.write("requirements.txt", content.encode())`
  - Update Redis cache (`bifrost:requirements:content`) — workers need this for sync startup reads
  - Remove the `FileIndex` upsert
- `warm_requirements_cache()`:
  - Read from S3 via `RepoStorage.read("requirements.txt")` instead of querying `FileIndex`
  - Populate Redis cache from S3 content
- Keep `get_requirements()` / `set_requirements()` unchanged (Redis read/write for workers)
- Move `_append_package_to_requirements()` here from the consumer (shared utility)

### Step 3: Simplify the API handler

**File**: `api/src/routers/packages.py` (`install_package` handler)
- When `package_name` provided: read current requirements from Redis, append package, save via `save_requirements()`
- When `package_name` is None: just broadcast recycle (requirements.txt already in S3)
- Broadcast lightweight `{"type": "recycle_workers"}` message
- Return success immediately — no WebSocket streaming

### Step 4: Simplify the consumer to recycle-only

**File**: `api/src/jobs/consumers/package_install.py`
- `process_message()` becomes: `_mark_workers_for_recycle()` + `_update_pool_packages()`
- Remove: pip install logic, requirements persistence, WebSocket log/completion streaming
- Keep: exchange name, consumer class, `_mark_workers_for_recycle()`, `_update_pool_packages()`

### Step 5: Update frontend PackagePanel

**File**: `client/src/components/editor/PackagePanel.tsx`

Remove WebSocket streaming/completion logic entirely. New flow:
- Click Install → API call → on success, toast nudging to Diagnostics: _"Package added to requirements. Workers recycling — view progress in Diagnostics"_ with link to `/diagnostics/workers`
- Update button label/subtext to clarify what it does
- Remove: `currentInstallationId`, `isConnected`, `connectionId`, WebSocket subscription, `executionStreamStore` usage, stream completion effects
- Keep: `isInstalling` (true during API call only), `loadPackages()` (auto-refresh after short delay)

### Step 6: Regenerate types

`cd client && npm run generate:types`

## Files to modify

| File | Change |
|------|--------|
| `api/src/models/contracts/common.py` | `package_name` optional |
| `api/src/core/requirements_cache.py` | S3 source of truth + Redis cache (remove FileIndex) |
| `api/src/routers/packages.py` | Requirements update + broadcast recycle (no pip) |
| `api/src/jobs/consumers/package_install.py` | Recycle-only, move append logic out |
| `client/src/components/editor/PackagePanel.tsx` | Remove streaming, add toast + Diagnostics link |
| `client/src/lib/v1.d.ts` | Regenerated |

## Functions to reuse

- `RepoStorage.read()` / `RepoStorage.write()` — `api/src/services/repo_storage.py`
- `get_requirements()` / `set_requirements()` — `api/src/core/requirements_cache.py` (Redis)
- `publish_broadcast()` — `api/src/jobs/rabbitmq.py`
- `_append_package_to_requirements()` — move from consumer to `requirements_cache.py`

## Verification

1. `./debug.sh`
2. Install package via UI → instant success, toast with Diagnostics link
3. "requirements.txt" button → no 422
4. Check S3 (MinIO): `_repo/requirements.txt` updated
5. Worker logs: recycle signal received, processes recycling
6. After ~10s, `/api/packages` shows new package
7. `./test.sh`, `cd api && pyright`, `cd client && npm run tsc`
