# Agent Work Split

This work can be parallelized across 4 agents. Each agent produces a self-contained deliverable that can be reviewed and merged independently.

## Dependency Graph

```
Agent A (DB Layer)  ────────┬──────────────> Agent C (Worker/Infra)
                            │
Agent B (Import Layer) ─────┘
                            │
                            └──────────────> Agent D (Git/Migration)
```

**Wave 1 (parallel):** Agents A and B can start immediately
**Wave 2 (parallel):** Agents C and D can start once A and B are complete

---

## Agent A: Database Layer

**Scope:** Schema, entity detection, file operations

**Files to create/modify:**
- `api/alembic/versions/YYYYMMDD_add_workspace_content.py` (NEW)
- `api/src/models/orm/workspace.py` (add content column)
- `api/src/services/file_storage/entity_detector.py` (return "module")
- `api/src/services/file_storage/file_ops.py` (handle entity_type="module")

**Deliverable:**
- Migration that adds `content` column to `workspace_files`
- Entity detector returns `"module"` for non-workflow Python files
- File ops can read/write/delete modules from `workspace_files.content`

**Tests:**
- `tests/unit/services/test_entity_detector.py` - module detection
- `tests/unit/services/test_file_ops_modules.py` - CRUD for modules

**Plan files:** 01, 02, 05

**No dependencies** - can start immediately

---

## Agent B: Import Layer

**Scope:** Redis cache and virtual import hook

**Files to create:**
- `api/src/core/module_cache.py` (NEW - async Redis client)
- `api/src/core/module_cache_sync.py` (NEW - sync Redis client)
- `api/src/services/execution/virtual_import.py` (NEW - MetaPathFinder)

**Deliverable:**
- Async module cache with get/set/invalidate/warm operations
- Sync module cache for import hook
- Virtual import hook that loads modules from Redis

**Tests:**
- `tests/unit/core/test_module_cache.py` - cache operations
- `tests/unit/services/test_virtual_import.py` - import hook, path conversion

**Plan files:** 03, 04

**No dependencies** - can start immediately

---

## Agent C: Worker & Infrastructure

**Scope:** Worker integration, init container, Docker changes

**Files to create/modify:**
- `api/src/services/execution/worker.py` (install import hook)
- `api/scripts/init_container.py` (NEW - migrations + cache warming)
- `docker-compose.yml` (add init service)
- `docker-compose.dev.yml` (add init service)

**Deliverable:**
- Worker installs virtual import hook on startup
- Init container runs migrations and warms cache
- Docker services depend on init container

**Tests:**
- `tests/integration/test_worker_virtual_import.py` - worker imports module from cache
- `tests/integration/test_init_container.py` - cache warming works

**Plan files:** 06, 07, 08

**Dependencies:** Agent A (schema), Agent B (cache + hook)

---

## Agent D: Git Integration & Migration

**Scope:** Git operations for modules, data migration script

**Files to create/modify:**
- `api/src/services/git_integration.py` (add module serialization/parsing)
- `api/scripts/migrate_modules_to_db.py` (NEW - S3 → DB migration)

**Deliverable:**
- Git push serializes modules from `workspace_files.content`
- Git pull parses modules and upserts to DB
- Migration script copies existing Python files from S3 to DB

**Tests:**
- `tests/integration/test_git_modules.py` - push/pull with modules
- `tests/unit/scripts/test_migrate_modules.py` - migration logic

**Plan files:** 09, 10

**Dependencies:** Agent A (schema + file ops)

---

## Execution Order

### Phase 1: Parallel Start
```
┌─────────────────────────────────────────┐
│  Agent A: DB Layer     (2-3 hours)      │
│  Agent B: Import Layer (2-3 hours)      │
└─────────────────────────────────────────┘
```

### Phase 2: Integration
```
┌─────────────────────────────────────────┐
│  Agent C: Worker/Infra (2-3 hours)      │
│  Agent D: Git/Migration (2-3 hours)     │
└─────────────────────────────────────────┘
```

### Phase 3: E2E Testing
```
┌─────────────────────────────────────────┐
│  Full integration test suite            │
│  - Write module via API                 │
│  - Execute workflow that imports it     │
│  - Git push/pull with modules           │
│  - Run migration script                 │
└─────────────────────────────────────────┘
```

---

## Agent Task Prompts

### Agent A Prompt
```
Implement database layer for virtual Python module storage.

Context: We're adding a new entity type "module" for non-workflow Python files.
Modules will be stored in workspace_files.content column.

Tasks:
1. Create migration adding `content` (TEXT, nullable) column to workspace_files
2. Add partial index for module lookups
3. Update ORM model with content column
4. Update entity_detector.py to return "module" for Python files without @workflow/@data_provider
5. Update file_ops.py to handle entity_type="module" for read/write/delete
6. Write unit tests for entity detection and file operations

Reference: .plans/modules_to_db/01-entity-detection.md, 02-database-schema.md, 05-file-operations.md
```

### Agent B Prompt
```
Implement Redis cache and virtual import hook for Python modules.

Context: We're loading Python modules from Redis cache instead of filesystem.
Workers will use a MetaPathFinder to intercept imports and load from cache.

Tasks:
1. Create api/src/core/module_cache.py with async Redis operations (get/set/invalidate/warm)
2. Create api/src/core/module_cache_sync.py with sync Redis operations for import hook
3. Create api/src/services/execution/virtual_import.py with MetaPathFinder + Loader
4. Follow pattern from import_restrictor.py for the MetaPathFinder
5. Write unit tests for cache operations and import hook

Reference: .plans/modules_to_db/03-redis-cache.md, 04-import-hook.md
```

### Agent C Prompt
```
Integrate virtual imports into worker and create init container.

Context: Workers need to install the virtual import hook before executing workflows.
An init container handles migrations and cache warming before services start.

Tasks:
1. Update worker.py to install virtual import hook on startup
2. Remove any workspace sync/download logic from worker
3. Create api/scripts/init_container.py for migrations + cache warming
4. Update docker-compose.yml and docker-compose.dev.yml with init service
5. Ensure services depend on init container completing successfully
6. Write integration tests for worker importing from cache

Reference: .plans/modules_to_db/06-worker-integration.md, 07-init-container.md, 08-deprecation.md
```

### Agent D Prompt
```
Add module support to git integration and create data migration script.

Context: Git push/pull needs to handle modules stored in workspace_files.content.
A one-time migration copies existing Python files from S3 to the database.

Tasks:
1. Update git_integration.py _serialize_platform_entities_to_workspace() to include modules
2. Update git_integration.py _parse_and_upsert_platform_entities() to handle modules
3. Create api/scripts/migrate_modules_to_db.py for S3 → DB migration
4. Add --dry-run support to migration script
5. Write tests for git operations with modules and migration script

Reference: .plans/modules_to_db/09-git-integration.md, 10-migration.md
```

---

## Merge Order

1. **Agent A** - Must merge first (schema required by all)
2. **Agent B** - Can merge after A (or in parallel if no schema dependency in tests)
3. **Agent C** - Merge after A and B
4. **Agent D** - Merge after A (can be parallel with C)

## Feature Flag (Optional)

Consider a feature flag to enable virtual imports:

```python
VIRTUAL_IMPORTS_ENABLED = os.environ.get("VIRTUAL_IMPORTS_ENABLED", "false") == "true"

if VIRTUAL_IMPORTS_ENABLED:
    install_virtual_import_hook()
```

This allows merging all agents before fully enabling the feature in production.
