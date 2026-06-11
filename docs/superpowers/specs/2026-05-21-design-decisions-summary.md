# Design decisions made while you were away

Context: user asked me to "summarize the design decisions and work on everything here so I can see it in preview." This file records the decisions I made unilaterally so they can be overridden on review. Each decision corresponds to an open question in the originating spec; the spec links are below.

## Phase B — Bulk user actions (issue #276)

### B-Q1: Replace vs additive roles
**Decision: replace.** Bulk "Replace roles" overwrites the user's existing role set with the selection. No additive mode in v1.

**Why:** Replace is unambiguous and matches what "replace" says on the button. Additive ("Add roles") is a useful future affordance and can be added with a second action (separate button or radio in the modal) — but adding it now doubles the surface area and we don't yet know the demand.

**Override hook:** add a `mode: "replace" | "add"` field to the bulk request body and a second action button. ~30 mins of work, no schema change.

### B-Q2: Move-org for platform admins
**Decision: refuse + show in failures list.** If the selection contains platform admins and the target is a non-provider org, the platform admins are listed in the `failed` array with reason "platform admin must be demoted first." The non-admin users in the selection still succeed.

**Why:** The existing per-user PATCH endpoint silently demotes a platform admin if you move them to a non-provider org. Doing that as a *side effect* of a bulk action would be a footgun. Surface it; let the user do the demotion explicitly.

**Override hook:** add an `allow_implicit_demote: bool` flag if surprise demotes become wanted. Default false.

### B-Q3: Self in selection
**Decision: checkbox is rendered but disabled with tooltip.** Tooltip: "You can't include your own account in bulk actions."

**Why:** Hiding the checkbox entirely is confusing ("why is this row treated differently?"). Disabling with a tooltip makes the rule discoverable.

## Phase C — Roles UX rethink (spec at `2026-05-21-roles-ux-rethink.md`)

### C-Q1: Drawer vs dialog for assign
**Decision: drawer.** Right-side panel, ~480px wide, slides in from the right. Stays open after a successful assign so batches don't require reopen-reopen-reopen.

**Why:** The current modal-of-cards is the worst part of the existing UX. Drawer is the standard pattern for "pick N from a long list and confirm" in modern admin UIs (Linear, Vercel, Stripe). It can be wider than the dialog allowed, leaves the role detail behind it visible for reference, and supports the "filter → select → assign → filter again" loop without churn.

### C-Q2: "What does this role grant" note on detail page
**Decision: yes — single-line note in the role detail page header.** Wording: *"Roles in Bifrost are labels matched against the `access_level` field on consumers. They don't carry permissions themselves."*

**Why:** Prevents the inevitable "where do I configure the permissions for this role?" support ticket. Keeps the page honest about what a role is.

### C-Q3: Are role counts on the Roles list clickable?
**Decision: yes — each count chip deep-links to the role detail page with that tab pre-selected.**

**Why:** Two clicks (chip → page → tab) collapses to one (chip → page-with-tab). URLs become shareable for support purposes. No downside.

### C-Q4: Workflows as a consumer type
**Decision: include the tab, stub the backend.**

**Why:** `WorkflowRole` is in the data model already, so future-proofing the UI to show a Workflows tab keeps the layout from churning when the backend lands. The tab will show an empty state and "Backend endpoint not yet implemented" rather than disappearing — same pattern as apps/knowledge.

**Override hook:** drop the tab entirely if you decide workflows should never have role gating.

---

# Build order (in this worktree, on `226-users-table-layout` branch)

Phase A landed as PR #275 (auto-merge queued).

Everything below ships **in the same worktree as additional commits on the same branch**. I'll push as I go so you can pull and preview at any time. The branch's PR will accumulate the new commits — when the time comes to merge it'll be one squash with several distinct features.

(If on review you'd prefer separate PRs per feature, easy to cherry-pick — but for preview purposes the single branch is faster.)

## B1 → B2: Bulk user actions

1. **B1 (backend):** new `PATCH /api/users/bulk` endpoint, `BulkUserUpdate` request model with discriminated operation, single-transaction execution with per-user guards, audit emission, `{succeeded, failed}` response. Backend e2e tests covering each operation + each guard.
2. **B2 (frontend):** select column + selection hook + sticky bottom action bar + 3 modals (move-org, replace-roles, enable/disable confirmation). Mutation calls the bulk endpoint. Toast + failure-detail dialog on partial failure. Vitest for the hook + action bar.

## C1 → C4: Roles UX

3. **C1:** `GET /api/roles` returns inline counts per consumer type. Rewrite Roles page to a card layout with count chips.
4. **C4 (backend):** bulk-unassign accepts list body on existing /users /forms /agents endpoints (keep single-ID path form for compat). New endpoints for /apps and /knowledge. Bumped out of strict order because C2/C3 frontend will call these.
5. **C2:** new `/roles/:id` route with `pages/RoleDetail.tsx`. Tabs per consumer type. Delete `RoleDetailsDialog`. Each tab has multi-select + bulk-unassign action bar.
6. **C3:** generic `AssignDrawer<T>` with search + per-type filters + virtualization. Used by each consumer tab's "+ Assign X" button. Delete `AssignUsersDialog` and `AssignFormsDialog`.

## Seed

7. Create realistic dummy data so the preview shows meaningful state — 4-6 roles, 4-6 apps, 4-6 agents, plus assignments. Done via the per-worktree CLI install at `/tmp/bifrost-cli-226`.

# Where to find things

- Debug stack URL: `http://bifrost-debug-226-users-table-layout-225-115.netbird.cloud` (login `dev@gobifrost.com` / `password`)
- CLI install: `/tmp/bifrost-cli-226/.venv/bin/bifrost`
- This worktree: `/home/jack/GitHub/bifrost/.worktrees/226-users-table-layout`
- Branch: `226-users-table-layout`
- Original specs: `docs/superpowers/specs/2026-05-21-roles-ux-rethink.md`; issue #276 for bulk actions

# Override flow when you're back

For any decision above you want changed, point at the heading (e.g. "B-Q1") and tell me what to switch to. The overrides for B-Q1 and B-Q2 are cheap (~30 min each). C decisions changed before C is built are free; changed after C is built may require a follow-up commit.

If the preview reveals something the spec didn't catch (always happens), we patch on this same branch.
