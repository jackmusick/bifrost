# Upstream Convergence Plan

## Summary

The fork currently has two meaningful forms of drift from upstream:

1. Repo-model drift
   - This fork commits `.bifrost/*.yaml` as if they are source-of-truth workspace files.
   - Upstream code and tests support `.bifrost/`, but treat it as generated/system-managed workspace state rather than committed repo source.

2. Deployment-process drift
   - The dev cluster is running locally built images from this branch instead of published upstream/fork registry images.
   - That is acceptable as a temporary dev workaround, but it is not a stable operating model.

These two drifts compound each other. The more we keep source modeling and deployment modeling separate from upstream, the harder it becomes to merge upstream changes, reason about failures, and upstream platform fixes cleanly.

## Current Findings

### `.bifrost/` in this fork

Committed files:

- `.bifrost/agents.yaml`
- `.bifrost/apps.yaml`
- `.bifrost/integrations.yaml`
- `.bifrost/workflows.yaml`

This fork currently treats those files as hand-maintained operational state.

### Upstream repo behavior

Upstream does not ignore `.bifrost/`, but also does not track a committed `.bifrost/` directory on `main`.

The platform code indicates that `.bifrost/` is expected to be generated and system-managed:

- `api/src/services/github_sync.py`
- `api/src/services/repo_sync_writer.py`
- `api/src/routers/files.py`
- `api/src/services/file_storage/file_ops.py`
- `client/src/lib/file-filter.ts`

The client/editor also treats `.bifrost/` files as read-only system files.

### Consequence

The fork is not merely "ahead" of upstream. It is operating with a different source-of-truth model:

- fork: committed `.bifrost/` manifests are treated as authoritative
- upstream/platform: DB + repo content generate `.bifrost/` as an artifact

That difference already causes friction in:

- upstream PR preparation
- manifest import/sync debugging
- merge behavior
- local dev expectations
- app/integration packaging work

## Target State

The fork should converge toward upstream's model:

- Python/TS source files under `features/`, `modules/`, `shared/`, `apps/`, `api/`, and `client/` remain the canonical source.
- `.bifrost/` is treated as generated/system-managed workspace state, not long-lived hand-authored repo state.
- Dev and test environments should rely on reproducible images from normal build/publish flows rather than node-local patched images.

## Migration Strategy

### Phase 1: Stop Making Drift Worse

Immediately:

- Avoid upstream PRs that include `.bifrost/*.yaml` changes unless upstream explicitly requests them.
- Prefer splitting platform fixes onto upstream-only branches, as done for:
  - `upstream-pr/preserve-system-agents`
  - `upstream-pr/redis-decimal-cache`
  - `upstream-pr/oauth-global-connections`
  - `upstream-pr/github-url-normalization`
  - `upstream-pr/shared-path-alignment`
- Treat local dev image builds as temporary exceptions only.

### Phase 2: Inventory What `.bifrost/` Is Carrying

Before removing committed `.bifrost/`, classify every entry as one of:

- generated from source and DB state
- truly hand-authored and still needed
- stale or duplicated

This specifically applies to:

- workflow registrations
- integration registrations
- app registrations
- agent registrations

Questions to answer:

- Can the current registered workflows/apps/integrations be regenerated from source and import flows without data loss?
- Which values in `.bifrost/` exist nowhere else?
- Which values are platform-owned and should not be committed?

### Phase 3: Prove Reconstruction

In a dedicated branch:

1. Start from a clean repo state without relying on committed `.bifrost/`.
2. Regenerate/import manifests from source and platform DB.
3. Compare resulting platform state to current behavior.
4. Record any gaps that still require explicit source declarations elsewhere.

Acceptance criteria:

- integrations still register correctly
- apps still import correctly
- workflows still resolve correctly
- git sync does not require committed `.bifrost/` to function

### Phase 4: Remove Repo-Model Drift

Once reconstruction is proven:

- remove committed `.bifrost/*.yaml` from the fork's normal source path
- update fork docs/workflows to reflect that `.bifrost/` is generated
- keep any truly hand-authored metadata only if upstream has an explicit place for it

This should happen in a dedicated migration branch, not mixed with integration work.

### Phase 5: Remove Deployment-Process Drift

For dev image handling:

1. Merge and publish the platform fixes we need.
2. Switch dev back from node-local `localhost/...` images to registry-backed images.
3. Keep local image builds only for short-lived testing, never as long-lived dev state.

Related tracking:

- Issue `#34` covers current dev-image drift and the stale Dockerfile assumptions.

## Immediate Next Actions

1. Track repo-model convergence as a dedicated fork issue.
2. Keep upstream PRs limited to platform-safe code-only fixes.
3. Plan a dedicated migration branch for `.bifrost/` convergence after current integration validation stabilizes.

## Non-Goals

This plan does not propose:

- deleting `.bifrost/` immediately
- changing the current dev server model mid-validation
- rewriting the integration work that already depends on current fork behavior before a reconstruction pass exists

Those would create unnecessary risk before the migration path is proven.
