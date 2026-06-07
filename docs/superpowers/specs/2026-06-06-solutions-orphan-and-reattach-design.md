# Solutions: orphan-and-reattach on uninstall (design addendum)

Date: 2026-06-06
Branch: `worktree-solutions-success-criteria`
Status: **design, approved in conversation — supersedes Task 14's plain-cascade delete.**
Parent spec: `2026-06-06-solutions-configs-and-management-ui-design.md`

## Why this exists

Implementing DELETE (Task 14) surfaced a data-loss hazard: owned `Table` rows have
`solution_id` with `ondelete=CASCADE`, and a Table owns its Document (row data) via a
Table→Document FK. So deleting an install **permanently destroys the customer's table
data**, not just the schema. Config *values* (operator-entered secrets) are similarly
lost (orphaned silently today). The user's decision: **don't destroy data on uninstall
— orphan it with provenance, allow reattach on reinstall, and provide a view to see and
clean up orphans.**

## The model: orphan-and-reattach

On uninstall, data-bearing owned entities (**tables + their documents**, and **config
values**) are **detached and preserved**, not cascade-deleted. Pure code/definition
entities (workflows, apps, forms, agents) still cascade — a reinstall recreates them
from the bundle, so there's nothing to preserve.

### Provenance ("tattoo")

A detached entity records where it came from, durably (these survive the Solution row's
deletion — they are NOT the live `solution_id` FK):

New nullable columns on **`Table`** and **`Config`**:
- `origin_solution_slug: str | None` — the former Solution's slug (stable across
  installs; the reattach key).
- `origin_solution_id: UUID | None` — the former install's uuid (informational).
- `orphaned_at: datetime | None` — when it was orphaned; **non-null ⇔ currently
  orphaned**. This is the orphan-state flag.

### Uninstall = detach-then-delete (tables + config values)

In the DELETE endpoint, **before** deleting the Solution row, under the per-install
write-lock:
- For each owned **Table** (`solution_id == install`): set `solution_id = NULL`,
  `organization_id = install.organization_id` (so it survives as an ordinary org table),
  `origin_solution_slug = install.slug`, `origin_solution_id = install.id`,
  `orphaned_at = now`. Documents are untouched (they hang off the Table, which now
  survives).
- For each install **Config value** (the Config rows in the install's org scope whose
  `key` matches one of the install's `SolutionConfigSchema` declarations): same stamping
  (`origin_solution_slug`/`origin_solution_id`/`orphaned_at`). Config values have no
  `solution_id` today, so "detach" is just the provenance stamp; the value persists.
- Then delete the Solution. Workflows/apps/forms/agents cascade away as before.

**FK implication:** `Table.solution_id` can no longer rely on `ondelete=CASCADE` to
remove tables (we want them to survive). The detach NULLs `solution_id` before the
Solution delete, so the CASCADE never fires for tables. Keep the FK but the detach runs
first. (Workflows/apps/forms/agents keep CASCADE.)

### Reattach on reinstall

When a Solution installs at the same `(slug, scope)` again, after deploy, for each owned
table declaration and each config declaration:
- Look for an orphan in the install's org with `origin_solution_slug == slug`,
  `orphaned_at IS NOT NULL`, matching by **table name** / **config key**.
- If found, **re-adopt**: set `solution_id` to the new install (tables), clear
  `orphaned_at`/`origin_*`, re-stamp org. The customer's data flows back in instead of
  the deploy creating an empty table. For config values, clear the orphan stamp so the
  operator doesn't re-enter the secret.
- Reattach is name/key-based (solution-scoped uniqueness already keys tables on
  `(solution_id, name)`), so it slots into the existing deploy upsert: before creating a
  table, check for a reattachable orphan and adopt it.

### Orphan VISIBILITY rule (CRITICAL — corrects a leak in the detach design)

The org-scoping cascade (`OrgScopedRepository`) resolves **non-solution** entities by
name and explicitly excludes **solution stuff** via `WHERE solution_id IS NULL`
(`org_scoped.py:216-217`). But orphaning a table sets `solution_id = NULL` so it
survives — which means a freshly-orphaned table would **pass that filter and leak into a
normal workflow's `useTable("name")` org cascade**, exposing the former install's data to
unrelated workflows in the org.

**Rule:** "solution stuff" the cascade must NOT resolve = *has a `solution_id`* **OR**
*is orphaned from one* (`orphaned_at IS NOT NULL`). Only genuinely non-solution rows
(`solution_id IS NULL AND orphaned_at IS NULL`) resolve through the org cascade. So the
name-cascade exclusion becomes:

```python
# org_scoped.py name-cascade path (~216), for models that have the columns:
#   exclude solution_id IS NOT NULL  (owned)  OR  orphaned_at IS NOT NULL  (orphaned)
query = query.where(self.model.solution_id.is_(None))
if _model_has_orphaned_at(self.model):
    query = query.where(self.model.orphaned_at.is_(None))
```
`orphaned_at` exists only on Table & Config — guard on the column (mirror
`_model_has_solution_id`). Orphaned rows remain reachable ONLY via the explicit
"show orphaned" path (below) and the reattach lookup (which queries orphans directly),
never via the implicit org cascade. This keeps the invariant: an orphan is invisible to
normal resolution until its Solution is reinstalled (reattach) or it's explicitly managed.

### Orphans view + cleanup — a "Show orphaned" toggle on the EXISTING pages

NOT a separate page/section. The existing **Tables** and **Configs** list pages gain a
**"Show orphaned"** toggle. Default off (orphans hidden). When on, the list endpoint
includes rows with `orphaned_at IS NOT NULL`, badged with their `origin_solution_slug`
("orphaned from acme-crm"). Deleting an orphan from there is a real delete (for tables it
cascades documents — type-to-confirm).

- The existing tables/configs LIST endpoints gain an `include_orphaned: bool = False`
  query param. When false (default), they exclude orphaned rows (so orphans don't clutter
  the normal list either). When true, they include them with the origin badge.
- No new `/api/solutions/orphans` endpoint — reuse the existing list endpoints + filter.
- Delete-orphan reuses the existing table/config delete endpoints (an orphan is just a row
  with no `solution_id`; deleting it is an ordinary delete — but the UI confirms because
  it carries data + provenance).

## Delete confirmation (UI)

The type-to-confirm delete dialog must state what happens: "Workflows/apps/forms/agents
will be removed. **Tables and their data, and config values, will be kept as orphaned
data** (reattached if you reinstall this Solution; manageable under Orphaned data)." So
uninstall is non-destructive-by-default and the operator knows where the data went.

## Scope delta vs the original plan

This **replaces Task 14** (plain cascade + S3 sweep was wrong for tables/configs) and
**adds**:
- T14a: provenance columns + migration on Table & Config.
- T14b: DELETE reworked — detach tables + stamp config values, then delete Solution; S3
  sweep unchanged (source/app dist still swept — those are code, not data).
- T14c: reattach-on-reinstall in the deploy/install path (tables + config values).
- T14d (REVISED): the orphan VISIBILITY fix in `OrgScopedRepository` (exclude
  `orphaned_at IS NOT NULL` from the name cascade) + `include_orphaned` param on the
  existing tables/configs LIST endpoints. NO separate orphans endpoint.
- UI (folds into the existing Tables/Configs pages, NOT the Solutions area): a "Show
  orphaned" toggle + origin badge; and the updated delete-confirm copy on the Solutions
  uninstall dialog.

S3 artifact sweep (`_solutions/{id}/`, `_apps/{id}/dist`) is unchanged — those are built
code, not customer data, and a reinstall rebuilds them.

## Non-goals
- Orphaning workflows/apps/forms/agents (pure code; recreated from bundle on reinstall).
- Cross-slug reattach (an orphan only reattaches to a reinstall of the SAME slug).
- Automatic orphan expiry/GC (manual cleanup via the orphans view for now).
