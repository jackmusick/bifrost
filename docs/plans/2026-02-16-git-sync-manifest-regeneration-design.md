# Git Sync Manifest Regeneration Fix

**Date:** 2026-02-16
**Status:** Approved

## Problem

`.bifrost/*.yaml` manifest files are only regenerated from the DB at commit time (`desktop_commit`). When an instance has a stale or empty `_repo/` (e.g. after an upgrade), all git operations see manifest files as deleted compared to HEAD, causing data loss on sync.

The dual-write system (`RepoSyncWriter`) only covers individual entity files (forms, agents). Manifest files — `configs.yaml`, `integrations.yaml`, `events.yaml`, `roles.yaml`, `tables.yaml`, `knowledge.yaml`, `organizations.yaml` — are not incrementally updated.

## Root Cause

When production syncs with a stale `_repo/`:
1. Refresh shows `.bifrost/configs.yaml` etc. as "deleted" (empty working tree vs HEAD)
2. Commit/pull proceeds with these deletions
3. `_delete_removed_entities` reads the empty manifest and deletes all entities from the DB

## Solution

Regenerate `.bifrost/*.yaml` from the DB as the **first step** of every git operation that reads the working tree. This ensures the working tree always reflects the current platform state before git compares, merges, or commits anything.

## Validated Approach

Shell tests confirmed three scenarios work correctly with regeneration:

- **Scenario A (regenerate → commit → pull):** Prod deletes config-2, dev adds config-4. Git's three-way merge produces config-1, config-3, config-4. No conflict.
- **Scenario B (regenerate → stash → merge → pop):** Same correct result via stash/pop path.
- **Scenario C (empty _repo → pull):** Remote files come in cleanly on a fresh instance.

## Changes

### `desktop_fetch`
Add `_regenerate_manifest_to_dir` before `git fetch`. Entry point from the refresh button — subsequent `desktop_status` sees an accurate diff.

### `desktop_status`
Add `_regenerate_manifest_to_dir` before `git add -A`. Belt-and-suspenders in case status is called without a prior fetch.

### `desktop_pull`
Add `_regenerate_manifest_to_dir` before the stash/fetch/merge sequence. Regenerated state gets stashed, remote merges in, stash pops back (Scenario B).

### `sync_execute` (scheduler)
Change order from `pull → commit → push` to `commit → pull → push`. The commit already regenerates, locking local platform state into git history. Pull then does a proper three-way merge (Scenario A).

### `desktop_commit`
No change — already regenerates first.

## Testing

Extend `test_git_sync_local.py` E2E tests to cover cross-instance scenarios:
- Instance A deletes a manifest entity, Instance B adds one — merge reconciles correctly
- Fresh instance with empty `_repo/` — pull brings in remote state without data loss
