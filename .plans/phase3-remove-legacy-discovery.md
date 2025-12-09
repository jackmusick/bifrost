# Phase 3: Remove Legacy Discovery System

## Overview

The legacy discovery system (`discovery.py`, `discovery_watcher.py`) performs background scanning of workflow files with full Python imports. This is redundant because `FileStorageService` already does **write-time detection** using AST parsing when files are created/modified.

### Current Architecture (Duplicated)
```
File writes → FileStorageService → DB ✅
Background scan → discovery_watcher → DB (duplicate)
API endpoints → scan_all_workflows() → File system scan (slow)
```

### Target Architecture (Write-time Only)
```
File writes → FileStorageService → DB ✅
Git sync → FileStorageService → DB ✅
API endpoints → Query DB (fast)
```

## Important Note

**`is_platform_admin`** (user role) is a DIFFERENT concept from the removed `is_platform` workflow field and must be KEPT.

---

## Files to DELETE

| File | Reason |
|------|--------|
| `api/shared/discovery.py` | Replaced by FileStorageService AST parsing |
| `api/shared/discovery_watcher.py` | No longer needed - write-time detection |
| `api/src/discovery/main.py` | Discovery container no longer needed |
| `api/src/discovery/__init__.py` | Part of discovery package |

---

## Files to MODIFY

### 1. `api/shared/handlers/discovery_handlers.py`

**Current:** Calls `scan_all_workflows()`, `scan_all_data_providers()`, `scan_all_forms()` from `discovery.py`

**Change:** Query database instead

```python
# BEFORE
from shared.discovery import scan_all_workflows, scan_all_data_providers, scan_all_forms

async def get_discovery_metadata(context):
    workflows = []
    for w in scan_all_workflows():
        workflows.append(convert_workflow_metadata_to_model(w))
    # ...

# AFTER
from sqlalchemy import select
from src.models.orm import Workflow, DataProvider, Form

async def get_discovery_metadata(context, db: AsyncSession):
    # Query workflows from DB
    result = await db.execute(select(Workflow).where(Workflow.org_id == context.org_id))
    workflows = [convert_orm_to_metadata(w) for w in result.scalars().all()]
    # ...
```

### 2. `api/shared/handlers/workflows_logic.py`

**Current:** May call `scan_all_workflows()` for workflow lookup

**Change:** Query database instead

### 3. `api/src/jobs/consumers/git_sync.py` and `api/shared/consumers/git_sync.py`

**Current:** May trigger discovery scan after git operations

**Change:** Use FileStorageService for file writes (already does AST detection)

```python
# Use FileStorageService which auto-detects workflow metadata
from shared.services.file_storage_service import FileStorageService

async def sync_file(file_path, content, db):
    storage = FileStorageService(db, org_id)
    await storage.write_file(file_path, content)  # Auto-detects workflows
```

### 4. `api/src/jobs/main.py`

**Current:** May initialize discovery watcher

**Change:** Remove discovery watcher initialization

### 5. `docker-compose.yml`

**Current:** Has discovery service defined

**Change:** Remove discovery service

```yaml
# DELETE this service block:
discovery:
  build: ...
  # ...
```

### 6. `docker-compose.test.yml`

**Current:** Has discovery service for tests

**Change:** Remove discovery service

---

## Tests to UPDATE or DELETE

### Delete
- `api/tests/unit/test_incremental_discovery.py` - Tests discovery scanning (no longer needed)

### Update
- `api/tests/integration/engine/test_auto_discovery.py` - Change to query DB instead of file scanning
- Any tests that mock `scan_all_workflows()` or similar functions

---

## Implementation Steps

### Step 1: Update Discovery Handlers (Low Risk)
1. Modify `discovery_handlers.py` to query DB instead of scanning files
2. Add database session parameter to `get_discovery_metadata()`
3. Create converter functions for ORM → API models

### Step 2: Update Workflows Logic (Low Risk)
1. Modify `workflows_logic.py` to use DB queries
2. Remove imports from `discovery.py`

### Step 3: Update Git Sync (Medium Risk)
1. Ensure git sync uses FileStorageService for all file operations
2. FileStorageService already does AST-based workflow detection on write
3. Remove any calls to discovery scanning after sync

### Step 4: Update API Routers (Low Risk)
1. Pass database session to discovery handlers
2. Update any direct calls to discovery functions

### Step 5: Remove Discovery Files (High Risk - Do Last)
1. Delete `api/shared/discovery.py`
2. Delete `api/shared/discovery_watcher.py`
3. Delete `api/src/discovery/` directory

### Step 6: Update Docker Configuration
1. Remove discovery service from `docker-compose.yml`
2. Remove discovery service from `docker-compose.test.yml`

### Step 7: Update Tests
1. Delete discovery-specific unit tests
2. Update integration tests to use DB queries
3. Run full test suite

---

## Verification Checklist

- [ ] All unit tests pass (`./test.sh tests/unit/`)
- [ ] All integration tests pass (`./test.sh tests/integration/`)
- [ ] All E2E tests pass (`./test.sh --e2e`)
- [ ] Pyright type checking passes
- [ ] Workflows are correctly discovered via DB queries
- [ ] Data providers are correctly discovered via DB queries
- [ ] Forms are correctly discovered via DB queries
- [ ] Git sync still works correctly
- [ ] File edits in UI still work correctly
- [ ] Docker services start without discovery service

---

## Rollback Plan

If issues arise:
1. Revert the commits
2. Re-add discovery files from git history
3. Re-add discovery service to docker-compose

---

## Dependencies

This plan assumes:
1. FileStorageService correctly detects workflows/data providers via AST parsing (verified)
2. Database has all necessary tables for workflows, data providers, forms (verified)
3. ORM models are up to date with required fields (verified)

---

## Estimated Complexity

| Step | Complexity | Risk |
|------|------------|------|
| Step 1: Discovery Handlers | Medium | Low |
| Step 2: Workflows Logic | Low | Low |
| Step 3: Git Sync | Medium | Medium |
| Step 4: API Routers | Low | Low |
| Step 5: Delete Discovery | Low | High (do last) |
| Step 6: Docker Config | Low | Low |
| Step 7: Tests | Medium | Low |

**Total Estimated Effort:** 4-6 hours
