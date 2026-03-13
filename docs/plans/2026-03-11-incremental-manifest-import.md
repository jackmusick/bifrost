# Incremental Manifest Import

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make manifest import incremental — only upsert/index entities that actually changed, and eliminate the expensive `sync_down` (full S3 download) from the import path.

**Architecture:** Use `_diff_manifests()` to identify which entities changed, then pass that changeset through `plan_import` and the indexer blocks so they skip unchanged entities. Replace filesystem reads (`work_dir / path`) with direct `RepoStorage` calls (`repo.exists()`, `repo.read()`). This removes the temp directory and `sync_down` entirely.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Pydantic, S3 (MinIO) via aiobotocore

---

## Progress

### Done (prior sessions)

These existed as uncommitted work on main before this plan was created:

- **`_diff_manifests()` and `_diff_list_entities()`** — Pure in-memory comparison of two Manifest objects using `model_dump(mode="json", by_alias=True)` equality. Returns list of `{action, entity_type, name, organization}` dicts for add/update/delete. Resolves org names and integration prefixes for display.
- **`ManifestImportResult` expanded** — Added `dry_run`, `deleted_entities`, `entity_changes` fields.
- **`import_manifest_from_repo()` expanded** — Added `delete_removed_entities` and `dry_run` params. Dry-run path uses `_diff_manifests` to compare incoming manifest against DB manifest without writing.
- **`plan_import()` dry_run support** — Added `dry_run: bool` param. When true, infers `action_taken` from prefetch cache instead of executing DB writes.
- **`_resolve_deletions()` dry_run support** — Added `dry_run: bool` param. When true, detects stale entities without executing deletes.
- **Entity type names normalized** — Changed from singular ("workflow", "form") to plural ("workflows", "forms") everywhere for consistency with manifest keys.
- **Router/CLI changes** — `files.py` router and `cli.py` updated to pass `delete_removed_entities`/`dry_run` through. CLI displays entity changes.

### Done (this branch — `feature/incremental-manifest-import`)

- **Task 1: `repo` parameter on `plan_import`** — Added `repo: "RepoStorage | None" = None`. Created async `_file_exists()` and `_file_read()` helpers inside `plan_import` that abstract over `repo` (S3) vs `work_dir` (filesystem). All workflow/form/agent file reads in plan_import use these helpers. Runtime guard: raises `ValueError` if neither `work_dir` nor `repo` provided.
- **Task 2: `repo`/`manifest` parameters on `_resolve_deletions` and `_detect_stale_entities`** — Both methods now accept optional `manifest` and `repo` params. When `manifest` not provided, falls back to reading from `work_dir / ".bifrost"`. Builds `_path_exists()`/`_dir_exists()` closures using either `repo.list("")` (single S3 LIST) or filesystem checks.
- **Task 3: Eliminated temp dir from `import_manifest_from_repo`** — Removed the entire `tempfile.TemporaryDirectory` + `sync_down` block. Passes `repo=repo` directly to `plan_import`. Indexer side-effects (forms, agents) read from S3 via `_read_or_none()` helper. Deletions pass `manifest=manifest, repo=repo` instead of `work_dir`.
- **Merge commit** — Combined the prior-session uncommitted work with the above into a single coherent state. Resolved 4 conflicts in function signatures where both sides added parameters.

---

## Remaining Tasks

### Task 4: Make `plan_import` incremental — skip unchanged entities

**Files:** `api/src/services/github_sync.py`

The big optimization. Currently `plan_import` upserts every entity in the manifest even when nothing changed. Use `_diff_manifests` (already exists) to compute which entities changed, then skip the rest.

1. Add `changed_ids: set[str] | None = None` param to `plan_import`
2. In each entity resolution loop, skip entities whose `.id` is not in `changed_ids` (when set is provided)
3. In `import_manifest_from_repo`, before calling `plan_import`:
   - Call `generate_manifest(db)` to get current DB state
   - Call `_diff_manifests(manifest, db_manifest)` to compute diff
   - If no changes, short-circuit (set `result.applied = True`, regenerate manifest, return)
   - Otherwise, build `changed_ids` set from the diff and pass to `plan_import`
4. Add `_collect_changed_ids()` helper to extract entity IDs from diff results (including dependent configs when an integration changes)
5. Skip unchanged forms/agents in the indexer blocks too
6. Skip `_resolve_deletions` when no deletes in diff

**Commit:** `perf: make plan_import incremental — skip unchanged entities via manifest diff`

### Task 5: Eliminate double `generate_manifest` call

**Files:** `api/src/routers/files.py`

The `/manifest/import` endpoint (line ~604) calls `import_manifest_from_repo(db)` which already populates `result.manifest_files` via `generate_manifest` + `serialize_manifest_dir`. The router then redundantly calls `generate_manifest(db)` again at line ~619.

1. Remove the redundant `generate_manifest` and `serialize_manifest_dir` imports/calls from the router
2. Use `result.manifest_files` directly

**Commit:** `perf: remove redundant generate_manifest call from manifest import router`

### Task 6: Unit tests for `_diff_manifests` and `_collect_changed_ids`

**Files:** `api/tests/unit/test_manifest.py`

Tests for:
- Identical manifests → empty diff
- New entity → "add"
- Removed entity → "delete"
- Modified entity → "update"
- Unchanged entities omitted
- Config display names (key, integration prefix)
- Organization resolution
- Sort order
- `_collect_changed_ids` returns correct IDs, includes dependent configs

**Commit:** `test: add unit tests for _diff_manifests and _collect_changed_ids`

### Task 7: E2E test for incremental import

**Files:** `api/tests/e2e/platform/test_cli_push_pull.py`

Test that importing the same manifest twice reports no entity_changes on the second import.

**Commit:** `test: add E2E test verifying incremental manifest import skips unchanged entities`

### Task 8: Lint and full test suite

Run `ruff check`, `pyright`, and `./test.sh` to verify everything passes.

---

## Summary of performance impact

| Operation | Before | After |
|-----------|--------|-------|
| `sync_down` (download entire _repo/) | ~3-4 seconds | **Eliminated** |
| `plan_import` upserts | All entities (~50+) | Only changed entities |
| Form/agent indexing | All forms + agents | Only changed forms/agents |
| `_resolve_deletions` | Always runs | Only runs if diff has deletes |
| `generate_manifest` | Runs 2x | Runs 1x (reused for diff) |
| **Total for no-change push** | **~5-6 seconds** | **<0.5 seconds** |
| **Total for single-entity change** | **~5-6 seconds** | **~1 second** |

## Files modified

| File | Changes |
|------|---------|
| `api/src/services/github_sync.py` | `_diff_manifests`, `_diff_list_entities`, `_collect_changed_ids` (new); `plan_import` gets `repo`/`dry_run`/`changed_ids` params; `_resolve_deletions`/`_detect_stale_entities` get `manifest`/`repo`/`dry_run` params; `import_manifest_from_repo` rewritten — no temp dir, direct S3, incremental diff |
| `api/src/routers/files.py` | Remove redundant `generate_manifest` call; pass `delete_removed_entities`/`dry_run` through |
| `api/src/models/contracts/github.py` | `EntityChange.action` includes `"keep"`; entity type names pluralized |
| `api/src/models/contracts/files.py` | `ManifestImportResponse` expanded with `dry_run`, `deleted_entities`, `entity_changes` |
| `api/bifrost/cli.py` | CLI displays entity changes from push; passes new params |
| `api/tests/unit/test_manifest.py` | Unit tests for `_diff_manifests` and `_collect_changed_ids` |
| `api/tests/e2e/platform/test_cli_push_pull.py` | E2E test for incremental import |
