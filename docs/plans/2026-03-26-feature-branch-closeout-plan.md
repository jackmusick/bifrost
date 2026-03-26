# Feature Branch Closeout Plan

## Objective

Close out `feat/autotask-cove-integrations`, merge it back into fork `main`,
and immediately shift follow-on cleanup work into a dedicated convergence
branch rather than extending the integration branch indefinitely.

## Why This Needs To Happen Now

The feature branch has accumulated three different kinds of work:

1. vendor integrations and app packaging
2. platform bug fixes discovered during validation
3. fork/process cleanup planning

That was acceptable while the integration push was still exploratory, but it is
now the wrong shape for ongoing development. The branch should be stabilized,
validated, merged, and frozen. Repo-model convergence should happen on a new
branch off `main`.

## Branch Exit Criteria

`feat/autotask-cove-integrations` is ready to merge into fork `main` when all of
the following are true:

1. Dev is running the latest branch tip.
2. Core platform fixes from this branch are present on dev:
   - system-agent preservation workaround understood
   - latest OAuth admin-list fix available after next image rollout
   - latest shared-path alignment fix available after next image rollout
3. Key integration smoke tests are green or explicitly blocked on credentials:
   - Autotask
   - Cove Data Protection
   - DNSFilter
   - Meraki
   - IT Glue
   - Huntress
   - NinjaOne
   - Datto RMM
   - Datto Networking
   - Datto SaaS Protection
   - VIPRE
   - HaloPSA
   - AutoElevate
4. Microsoft status is reduced to the intended blocker:
   - `Microsoft` connected
   - `Microsoft CSP` awaiting interactive OAuth reconnect
5. No uncommitted local changes remain on the feature branch.

## Known Remaining User-Required Actions

These do not block the technical branch closeout itself, but they do block some
final userland validation:

1. Reconnect `Microsoft CSP` interactively to obtain a delegated refresh token.
2. Run the `Microsoft CSP` / GDAP app smoke test after that reconnect.
3. Optionally validate any remaining vendor credentials not currently present on dev.

## Execution Sequence

### Phase 1: Stabilize Dev On Latest Feature Branch

1. Rebuild/redeploy the dev image from the latest `feat/autotask-cove-integrations`.
2. Re-run targeted checks:
   - Microsoft setup workflow
   - OAuth/admin visibility behavior
   - representative vendor picker/data-provider executions
3. Record the remaining blockers precisely.

### Phase 2: Merge Feature Branch Back To Fork Main

1. Merge `feat/autotask-cove-integrations` into fork `main`.
2. Sync dev/fork `main` to that merged state.
3. Stop doing new feature work on `feat/autotask-cove-integrations`.

### Phase 3: Start Dedicated Convergence Work

Create a new branch from updated `main`, e.g.:

- `chore/upstream-convergence`

That branch owns:

- `.bifrost/` repo-model convergence
- dev image / deployment-process convergence
- upstream fix PR preparation and follow-through

See:

- `docs/plans/2026-03-26-upstream-convergence-plan.md`
- fork issues `#34` and `#36`

## What Should Not Happen

Do not:

- keep adding new integrations to `feat/autotask-cove-integrations`
- start deleting `.bifrost/` from the active feature branch
- keep long-lived node-local dev images as a steady-state practice
- mix convergence work into the merge-back path more than necessary

## Immediate Next Step

Roll the latest feature-branch tip to dev and re-run the key merge-readiness
checks. That is the last substantial technical step before merging back to
fork `main`.
