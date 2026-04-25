# Apps `replace` — repoint source path & `repo_path` cleanup

**Date:** 2026-04-19
**Status:** Draft — awaiting user review
**Scope:** CLI mutation-surface parity for apps; close the last manifest-only editing gap

## Background

We are retiring manifest editing as a mutation surface. Every field that used to be edited by hand in `.bifrost/apps.yaml` now has a CLI equivalent — **except the app's source directory**. Workflows recently got `bifrost workflows replace` to repoint an orphaned workflow at a new `.py` file. Apps need an analogous command, but with simpler semantics: apps don't have a "still works from a code snapshot" orphan state — if `repo_path` points nowhere, the app just has no source to compile. The DB record (metadata, published snapshot, dependencies) is unaffected.

While fixing this we also clean up a latent footgun: `Application.repo_path` is nullable today, and `repo_prefix` falls back to `apps/{slug}` when it's NULL. That coupling means a slug rename silently repoints source, and there's no single source of truth for where an app's files live.

## Goals

1. Make `Application.repo_path` a first-class, required, unique field. No fallback.
2. Add `bifrost apps replace <ref> --repo-path <new>` to repoint an app's source directory.
3. Mirror the workflow-replace shape: REST endpoint + thin MCP wrapper + CLI.
4. Keep the UI unchanged for this PR. Repoint is CLI-only.

## Non-goals

- No UI changes. `repo_path` is not displayed or edited in the web app.
- No orphan-detection service or `apps list-orphaned` command. Apps don't have an orphan lifecycle analogous to workflows' code-snapshot fallback.
- No S3 file moves on repoint. `replace` is a metadata-only operation.
- No changes to `apps update --slug`. Slug and `repo_path` are independent fields.

## Data model changes

### Migration

1. Backfill: `UPDATE applications SET repo_path = 'apps/' || slug WHERE repo_path IS NULL`.
2. Alter column: `repo_path VARCHAR(500) NOT NULL`.
3. Add unique index on `repo_path` (global, case-sensitive — matches the slug uniqueness pattern).

### ORM (`api/src/models/orm/applications.py`)

```python
repo_path: Mapped[str] = mapped_column(String(500), nullable=False)

@property
def repo_prefix(self) -> str:
    return f"{self.repo_path.rstrip('/')}/"
```

Drops the `| None`, drops `default=None`, drops the `apps/{slug}` fallback in `repo_prefix`.

### App creation

Wherever an `Application` row is inserted (REST create, MCP `create_app`, manifest import), `repo_path` must be set explicitly. Default at the service layer — not in the model — to `apps/{slug}` when the caller doesn't provide one. The default is applied once at create time and stored verbatim; it does not re-derive if `slug` later changes.

### Manifest import

`ManifestApp.path` already maps to `repo_path` in `_resolve_application`. With `NOT NULL` in force, confirm the manifest `path` field is required (it is, per `api/src/services/manifest.py`) and error clearly if absent.

## CLI command

```
bifrost apps replace <ref> --repo-path <new-path> [--force]
```

- `<ref>` — UUID, slug, or name. Uses the existing app `RefResolver`.
- `--repo-path` (required) — workspace-relative path (e.g. `apps/my-app-v2`). Trailing slash stripped on normalization.
- `--force` — bypass the source-exists / uniqueness / nesting checks below (see Validation).

Lives in `api/bifrost/commands/apps.py`. Pattern mirrors `bifrost workflows replace` (`workflows.py:317–374`).

## REST endpoint

```
POST /api/applications/{id}/replace
Body: {"repo_path": "...", "force": false}
Response: ApplicationPublic
```

Added to the applications router. Calls a new `app_repoint` service function (or a method on an existing app service) that performs the validation and update in one transaction.

## MCP tool

`replace_app` in `api/src/services/mcp_server/tools/apps.py` — thin HTTP wrapper calling the REST endpoint, per the project's MCP thin-wrapper rule. No direct ORM access.

## Validation

All performed server-side in the repoint service, in this order:

1. **App exists.** 404 otherwise.
2. **No-op check.** If `new_repo_path == current_repo_path`, succeed without writing (return the app unchanged).
3. **Uniqueness.** No other app has `repo_path == new_repo_path`. Bypassable with `--force`.
4. **Nesting.** No other app's `repo_path` is a prefix of `<new>/`, and `<new>/` is not a prefix of any other app's `repo_path`. Bypassable with `--force`.
5. **Source exists.** `file_index` has at least one non-deleted entry whose path starts with `<new>/`. Bypassable with `--force`.

Nesting check rationale: `_find_app_by_path` uses longest-prefix-match, so nested `repo_path` values would silently route files to whichever app wins the match. Rejecting nesting at replace-time prevents the ambiguity.

`--force` bypasses checks 3–5. Checks 1 and 2 always enforced.

## Side effects

- **No file move.** Files at the old `repo_path` remain in S3 and become unowned; the user reconciles with `bifrost sync` (or manual cleanup).
- **Cache invalidation.** Bundle render cache is keyed on app ID, not `repo_path`, so the next render rebuilds from the new source automatically. No explicit cache-bust required.
- **Published snapshot unchanged.** `published_snapshot` is `{path: content_hash}` captured at publish time — it continues to reflect the previously-published state regardless of `repo_path` changes. Next publish will snapshot the new paths.

## Error handling

| Condition | Behavior |
|-----------|----------|
| App not found | 404 |
| `--repo-path` same as current | Success, no write, return app |
| Another app owns `repo_path` exactly | 409 Conflict, names the conflicting app's UUID and slug. `--force` bypasses. |
| Another app's `repo_path` nests or is nested under target | 409 Conflict, names the conflicting app. `--force` bypasses. |
| No files under target in `file_index` | 400 Bad Request, message suggests running `bifrost sync` or passing `--force`. |
| Migration: duplicate `apps/{slug}` values at backfill time | Migration fails fast with a clear error listing the colliding rows. Operator resolves manually before retry. (Not expected in practice since `slug` is unique, but backstop for corrupted data.) |

## Testing

### Unit (`api/tests/unit/`)

- Migration backfill: NULL → `apps/{slug}` for existing rows.
- `repo_prefix` property: trailing slash preserved, no fallback behavior.
- Repoint service validation:
  - Uniqueness conflict (exact match on another app)
  - Nesting conflict — new path is prefix of another app
  - Nesting conflict — another app's path is prefix of new path
  - Empty prefix rejected without `--force`
  - `--force` bypasses each of the above
  - No-op (same path) succeeds without write

### E2E (`api/tests/e2e/platform/`)

- `bifrost apps replace` happy path: files at new path, repoint succeeds, subsequent compile reads from new source.
- Reject duplicate `repo_path`.
- Reject nested `repo_path` (both directions).
- Reject empty prefix without `--force`.
- `--force` allows all three rejection cases.
- Manifest round-trip: export app, modify `path` in manifest, import, verify DB `repo_path` updated.
- DTO-parity test (`test_dto_flags.py`) — ensures `ApplicationUpdate` flag surface still matches CLI after the change. `repo_path` is **not** added to `apps update` — it's mutated only through `apps replace` — so it belongs in `DTO_EXCLUDES` with a comment pointing at `apps replace`.

## Docs

- Update `docs/llm.txt` to mention `bifrost apps replace` alongside the other mutation commands.
- Update `.claude/skills/bifrost-build/SKILL.md` if it references the old "rename app folder" flow.

## Rollout

Single PR:

1. Migration (backfill + NOT NULL + unique index)
2. ORM change (drop nullable, drop fallback)
3. Service creation defaults populated to `apps/{slug}` explicitly
4. REST endpoint + service function
5. MCP thin wrapper
6. CLI command
7. Tests
8. Docs

No feature flag; this is a trivial data-shape tightening with a safe backfill.
