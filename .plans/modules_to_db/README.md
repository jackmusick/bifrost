# Virtual Python Module Loading

Replace filesystem-based Python module loading with database-backed virtual modules using Redis caching. This eliminates S3 storage and `/tmp/bifrost/workspace` sync for Python files.

## Summary

- Add new entity type `"module"` for non-workflow Python files
- Store module content in `workspace_files.content` column (follows existing entity pattern)
- Load modules lazily via custom import hook, fetching from Redis cache
- Warm cache on startup via init container
- Invalidate cache on file mutation via API

## Key Design Decisions

1. **Follow existing entity pattern** - `entity_detector.py` already classifies files. Add `"module"` type for Python files that aren't workflows/data_providers
2. **workspace_files.content for modules** - like workflows use `workflows.code`, modules use `workspace_files.content`
3. **Lazy loading** - only fetch modules when actually imported (via import hook)
4. **Redis as primary cache** - workers read from Redis, never touch DB directly
5. **Init container** - handles migrations + cache warming before services start

## Plan Files

| File | Description |
|------|-------------|
| [00-agent-split.md](./00-agent-split.md) | **Work split across 4 parallel agents** |
| [01-entity-detection.md](./01-entity-detection.md) | Entity detection changes |
| [02-database-schema.md](./02-database-schema.md) | Database schema and migration |
| [03-redis-cache.md](./03-redis-cache.md) | Redis caching layer |
| [04-import-hook.md](./04-import-hook.md) | Virtual import hook implementation |
| [05-file-operations.md](./05-file-operations.md) | File operations integration |
| [06-worker-integration.md](./06-worker-integration.md) | Worker startup changes |
| [07-init-container.md](./07-init-container.md) | Init container setup |
| [08-deprecation.md](./08-deprecation.md) | Infrastructure deprecation |
| [09-git-integration.md](./09-git-integration.md) | GitHub integration compatibility |
| [10-migration.md](./10-migration.md) | Data migration from S3 |
| [11-upsert-matching.md](./11-upsert-matching.md) | Upsert and matching process explained |
| [12-package-installation.md](./12-package-installation.md) | Package installation clarification |

## Files to Modify

| File | Changes |
|------|---------|
| `api/src/services/file_storage/entity_detector.py` | Return `"module"` for non-workflow Python files |
| `api/src/models/orm/workspace.py` | Add `content` column |
| `api/alembic/versions/...` | Migration for content column + index |
| `api/src/core/module_cache.py` | NEW - Redis caching layer (async) |
| `api/src/core/module_cache_sync.py` | NEW - Sync Redis for import hook |
| `api/src/services/execution/virtual_import.py` | NEW - Import hook (MetaPathFinder) |
| `api/src/services/execution/worker.py` | Install import hook, remove workspace sync |
| `api/src/services/file_storage/file_ops.py` | Handle `entity_type="module"` read/write/delete |
| `api/src/services/git_integration.py` | Add module serialization/parsing to git ops |
| `api/scripts/init_container.py` | NEW - Migrations + cache warming |
| `docker-compose.yml` | Add init container, remove alembic from API |
| `docker-compose.dev.yml` | Add init container, remove alembic from API |

## Testing Strategy

### Unit tests
- `test_virtual_import.py` - module name → path conversion, package detection
- `test_module_cache.py` - cache get/set/invalidate, warm from DB

### Integration tests
- Workflow imports virtual module successfully
- Cache invalidation on file update
- Cold start with empty cache (fallback behavior)

### E2E tests
- Write Python file via API → execute workflow that imports it
- Update file → next execution sees new code
- Delete file → import fails gracefully
