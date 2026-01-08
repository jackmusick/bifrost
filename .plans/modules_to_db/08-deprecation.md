# Phase 8: Infrastructure Deprecation

## Overview

With virtual module loading in place, we can deprecate the filesystem-based workspace sync infrastructure.

## What Gets Deprecated

### 1. Workspace Sync Service

**File:** `api/src/services/workspace_sync.py` (if exists)

This service kept `/tmp/bifrost/workspace` in sync with S3. No longer needed for Python files.

**Action:** Remove or disable for Python file types.

### 2. File Watcher

**File:** `api/src/services/workspace_watcher.py` (if exists)

Watched local filesystem for changes to sync back to S3. No longer needed.

**Action:** Remove entirely or scope to non-Python files only.

### 3. Download Queue Consumers

Any background jobs that:
- Download files from S3 to `/tmp/bifrost/workspace`
- Process file change events

**Action:** Remove Python file handling. May keep for non-Python files if needed.

### 4. Workspace Directory Setup

Code that creates `/tmp/bifrost/workspace` structure on startup:

```python
# REMOVE patterns like:
os.makedirs("/tmp/bifrost/workspace", exist_ok=True)
await sync_workspace_from_s3()
```

**Action:** Remove. Directory may still exist but is no longer managed.

## What Gets Kept

### 1. S3 Storage (for non-Python files)

S3 is still used for:
- Data files (JSON, CSV, etc.)
- Configuration files
- Binary assets
- Anything that's not a Python module

### 2. Git Integration Workspace

Git operations still use an ephemeral workspace:
- Clone repository to temp directory
- Serialize DB entities to files
- Run git commands
- Parse files back to DB
- Clean up temp directory

This is different from the persistent `/tmp/bifrost/workspace` mirror.

### 3. Virtual Workspace Path

Keep `/tmp/bifrost/workspace` as a virtual path for:
- `sys.path` entry
- `__file__` attributes in tracebacks
- Any code that references the path (will fail gracefully)

The directory doesn't need to contain files - it's just a namespace.

## Migration Path

### Phase 1: Add Virtual Imports (Non-Breaking)

1. Deploy virtual import hook alongside existing sync
2. Both systems work in parallel
3. Monitor for issues

### Phase 2: Disable Sync for Python Files

1. Stop syncing `.py` files to filesystem
2. Virtual import handles all Python imports
3. S3 still stores Python files (for now)

### Phase 3: Remove S3 for Python Files

1. Stop writing `.py` files to S3
2. DB is sole source of truth for Python
3. Clean up old S3 Python files (optional)

### Phase 4: Remove Sync Infrastructure

1. Remove file watcher code
2. Remove download queue consumers
3. Clean up unused dependencies

## Redis Pub/Sub Changes

**Current:** `bifrost:workspace:sync` channel for file change notifications

**After:** May still be needed for non-Python file changes, or can be removed entirely if all file operations go through the API.

## Worker Startup Changes

**Before:**
```python
async def worker_startup():
    await workspace_sync.start()
    await workspace_watcher.start()
    await wait_for_initial_sync()
    # ... start processing
```

**After:**
```python
async def worker_startup():
    install_virtual_import_hook()
    # ... start processing immediately
```

Workers start faster because there's no file download step.

## Rollback Plan

If issues are discovered:

1. Virtual import hook can be disabled via feature flag
2. Re-enable workspace sync
3. Workers fall back to filesystem imports

The database still has all module content, and S3 can be repopulated from DB if needed.
