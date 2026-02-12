# Unified File Storage & MCP Tool Simplification

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify app file storage into the existing S3 `_repo/` + `file_index` system, drop `entity_type` from MCP tools, and eliminate the `app_files`/`app_versions` tables.

**Architecture:** App source files move to `_repo/apps/{slug}/...` in S3 (same as workflows, modules, text). The `compiled` field is dropped entirely — compilation is already 100% client-side via Babel. Draft/live versioning uses a `published_snapshot` JSONB column on `applications` instead of copying files between versions. MCP content tools are path-only — no `entity_type`, no `app_id`. The path convention drives all routing.

**Tech Stack:** Python/FastAPI, SQLAlchemy, S3 (MinIO), PostgreSQL, Alembic migrations

**Branch:** `feat/workspace-redesign`

**App files exported to:** `exported-apps/` (microsoft-csp and pm-code drafts + active versions)

---

## Progress

### COMPLETED Tasks

| Task | Description | Commit | Notes |
|------|-------------|--------|-------|
| 1 | Entity detector: `apps/{slug}/` path detection | `190f5856` | Returns "app" for app.json, "app_file" for everything else under apps/ |
| 2 | `published_snapshot` JSONB column on applications | `9db9dd07` | Migration: `20260212_pub_snap` (revises: `20260212_uq_webhook_es`) |
| ~~3~~ | ~~app_dependencies table~~ | REVERTED | Not needed — will alter existing `app_file_dependencies` in-place during Task 11 |
| 4 | App file pubsub in write_file/delete_file | `1e334269` | Fires pubsub for real-time preview on `apps/` path writes/deletes |
| 5 | Verify read_file works for apps/ paths | N/A | No changes needed — Redis→S3 fallback already handles it |
| 6 | Publish/snapshot mechanism | `a47b1e5e` | `publish()` now populates `published_snapshot` alongside old version-copy (transition) |
| 7 | Simplify MCP content tools | `1a61e7d7` | Dropped entity_type requirement, all tools path-based. ~900 lines removed. |

### Alembic migration chain
```
20260212_uq_webhook_es → 20260212_pub_snap (head)
```

### Key decision: app_dependencies
The plan originally called for a new `app_dependencies` table (Task 3). This was reverted because the existing `app_file_dependencies` table already tracks the same relationships. During Task 11, the existing table will be altered in-place: rename `app_file_id` FK to `application_id` (pointing to `applications.id` instead of `app_files.id`). This avoids creating a redundant table.

---

## REMAINING Tasks

### Task 8: Update client for new file serving endpoints

**Depends on:** Tasks 4-6 (done)

**Files to investigate and modify:**
- `client/src/lib/app-code-resolver.ts`
- `client/src/pages/AppRouter.tsx`
- `client/src/components/jsx-app/JsxAppShell.tsx`
- `client/src/hooks/useApplications.ts`

**What to do:**

1. **Update AppRouter** — remove `version_id` from file fetching. Currently the client selects `draft_version_id` or `active_version_id` and passes it to file fetching. Instead:
   - Draft mode: fetch files from endpoint that reads from `file_index` for `apps/{slug}/`
   - Live mode: fetch files from endpoint that reads published snapshot

2. **Update resolver** — simplify API calls. Remove `versionId` from resolver calls. Files are fetched by `slug + path`, not `appId + versionId + path`.

3. **Regenerate types**: `cd client && npm run generate:types`

4. **Commit**

---

### Task 9: Update app_code_files router

**Depends on:** Tasks 4-6 (done)

**Files:**
- `api/src/routers/app_code_files.py` — rewrite to use S3 paths via FileStorageService instead of `app_files` table
- `api/src/routers/applications.py` — remove version-based file operations where possible

**What to do:**

1. **Rewrite file list endpoint** — List files for an app from `file_index` (draft mode) or `published_snapshot` (live mode):

```python
@router.get("/{app_id}/files")
async def list_app_files(app_id: UUID, mode: str = "draft"):
    app = await repo.get_application(app_id)
    if mode == "live" and app.published_snapshot:
        paths = list(app.published_snapshot.keys())
    else:
        result = await ctx.db.execute(
            select(FileIndex.path).where(
                FileIndex.path.startswith(f"apps/{app.slug}/"),
                ~FileIndex.path.endswith("/app.json"),
            )
        )
        paths = [row[0] for row in result.all()]
    # Return with relative paths (strip apps/{slug}/ prefix)
```

2. **Rewrite file read endpoint** — Read from Redis→S3 via full path:

```python
@router.get("/{app_id}/files/{file_path:path}")
async def get_app_file(app_id: UUID, file_path: str, mode: str = "draft"):
    app = await repo.get_application(app_id)
    full_path = f"apps/{app.slug}/{file_path}"
    content = await _read_from_cache_or_s3(full_path)
    if content is None:
        raise HTTPException(404, f"File not found: {file_path}")
    return {"path": file_path, "source": content}
```

3. **Rewrite file write endpoint** — Write through FileStorageService:

```python
@router.put("/{app_id}/files/{file_path:path}")
async def update_app_file(app_id: UUID, file_path: str, body: AppFileUpdate):
    app = await repo.get_application(app_id)
    full_path = f"apps/{app.slug}/{file_path}"
    service = FileStorageService(ctx.db)
    await service.write_file(
        path=full_path,
        content=body.source.encode("utf-8"),
        updated_by=user.email,
    )
    # write_file handles pubsub, etc.
```

4. **Commit**

---

### Task 10: Data migration — move existing app files to S3

**Depends on:** Tasks 8-9

**Files:**
- Create: `api/scripts/migrate_app_files_to_s3.py` (management command, NOT an alembic migration — requires S3 access)

**What to do:**

Write a management command (not alembic migration) that:
1. Queries all applications with their slugs
2. For each app, gets draft version files from `app_files` table
3. Writes each file to S3 `_repo/apps/{slug}/{path}` and inserts into `file_index`
4. If app has `active_version_id`, creates `published_snapshot` from active version files
5. Logs progress and is idempotent (safe to re-run)

**Important:** App files have already been exported to `exported-apps/` as a backup.

**Commit**

---

### Task 11: Drop `app_files`, `app_versions`, `app_file_dependencies` tables

**Depends on:** Task 10

**Files:**
- Create: `api/alembic/versions/YYYYMMDD_drop_app_files_tables.py`
- Modify: `api/src/models/orm/applications.py` (remove `AppVersion`, `AppFile` classes; remove `active_version_id`, `draft_version_id` columns)
- Modify: `api/src/models/__init__.py` and `api/src/models/orm/__init__.py` (remove exports)
- Delete: `api/src/models/orm/app_file_dependencies.py`
- Delete: `api/src/services/app_dependencies.py` (old per-file sync service)

**Migration steps:**

```python
def upgrade():
    # Drop FK constraints first
    op.drop_constraint('app_jsx_files_app_version_id_fkey', 'app_files')
    op.drop_constraint('fk_applications_active_version_id', 'applications')
    op.drop_constraint('fk_applications_draft_version_id', 'applications')

    # Drop columns from applications
    op.drop_column('applications', 'active_version_id')
    op.drop_column('applications', 'draft_version_id')

    # Drop tables
    op.drop_table('app_file_dependencies')
    op.drop_table('app_files')
    op.drop_table('app_versions')
```

**ORM cleanup:**
- Remove `AppVersion` and `AppFile` classes from `applications.py`
- Remove `active_version_id` and `draft_version_id` columns + relationships from `Application`
- Update `is_published` property to use `published_snapshot is not None`
- Update `has_unpublished_changes` property (may need to compare file_index state vs snapshot)
- Remove `AppFileDependency` model file
- Remove `sync_file_dependencies()` from `app_dependencies.py`
- Update all `__init__.py` exports

**Commit**

---

### Task 12: Update all consumers of removed tables

**Depends on:** Task 11

**Files to update (search for `AppFile`, `AppVersion`, `AppFileDependency`, `app_files`, `draft_version_id`, `active_version_id`):**

- `api/src/services/dependency_graph.py` — rewrite queries: scan `file_index` for `apps/{slug}/*` files, parse `useWorkflow*()` patterns, resolve to workflow IDs
- `api/src/routers/workflows.py` — update `_get_app_workflow_ids()` and `_compute_used_by_counts()` to scan file_index instead of joining through app_file_dependencies
- `api/src/routers/maintenance.py` — update `scan_app_dependencies()` to scan `file_index` instead of `app_files`
- `api/src/services/mcp_server/tools/apps.py` — update `list_apps()` file counting (count from `file_index` where `path.startswith(f"apps/{slug}/")`), update `create_app()` scaffolding (write via `FileStorageService.write_file()` instead of creating `AppFile` rows)
- `api/src/services/file_storage/indexers/app.py` — rewrite to write to S3 instead of `app_files` table (or remove if no longer needed)
- `api/src/services/github_sync_virtual_files.py` — simplify or remove (app files are now real files in `_repo/`, no virtual synthesis needed)
- `api/src/models/contracts/applications.py` — remove `active_version_id`, `draft_version_id` from `ApplicationPublic`. Update `is_published` and `has_unpublished_changes` fields.
- `api/src/routers/applications.py` — remove `_publish_version()` (old copy-files method), remove `_scaffold_code_files()` (uses AppFile), remove `get_files_for_version()`. Rewrite `publish()` to only use snapshot (remove old version-copy transition code). Update `create_application()` to scaffold via FileStorageService.

**Run full test suite:** `./test.sh`

**Commit**

---

### Task 13: Update frontend types and verify

**Depends on:** Task 12

**Files:**
- `client/src/lib/v1.d.ts` (regenerated)
- Various components that reference `version_id`, `draft_version_id`, `active_version_id`

**Steps:**
1. Regenerate types: `cd client && npm run generate:types`
2. Fix TypeScript errors: `cd client && npm run tsc`
3. Fix lint errors: `cd client && npm run lint`
4. Commit

---

### Task 14: Final verification

**Depends on:** Task 13

**Steps:**
1. Backend checks: `cd api && pyright && ruff check .`
2. Frontend checks: `cd client && npm run tsc && npm run lint`
3. Full test suite: `./test.sh`
4. Manual smoke test:
   - Start dev stack: `./debug.sh`
   - Create an app via MCP tools (no entity_type needed)
   - Edit a file via MCP `replace_content(path="apps/test-app/pages/index.tsx", content="...")`
   - Verify preview updates in browser
   - Publish the app
   - Verify live version serves correctly
   - Edit draft again, verify live doesn't change
   - Create a workflow via MCP tools (no entity_type needed)
   - Verify `list_content()` returns all files
5. Commit any fixes

---

## Ordering & Dependencies

```
COMPLETED ──────────────────────────────────────────────────────
Task 1  (entity_detector)          ✅ 190f5856
Task 2  (published_snapshot col)   ✅ 9db9dd07
Task 3  (app_dependencies table)   ❌ REVERTED (not needed)
Task 4  (write app files to S3)    ✅ 1e334269
Task 5  (read app files from S3)   ✅ no changes needed
Task 6  (publish/snapshot)         ✅ a47b1e5e
Task 7  (simplify MCP tools)       ✅ 1a61e7d7

REMAINING ──────────────────────────────────────────────────────
Task 8  (client updates)         ◄── next batch, parallelizable with Task 9
Task 9  (router updates)         ◄── next batch, parallelizable with Task 8
                                      │
Task 10 (data migration)         ◄───┘ depends on 8+9
                                      │
Task 11 (drop old tables)        ◄───┘ depends on 10
                                      │
Task 12 (update consumers)       ◄───┘ depends on 11
                                      │
Task 13 (frontend types)         ◄───┘ depends on 12
                                      │
Task 14 (verification)           ◄───┘ depends on 13
```

Tasks 8-9 can be parallelized. Tasks 10-14 are strictly sequential (destructive changes).
