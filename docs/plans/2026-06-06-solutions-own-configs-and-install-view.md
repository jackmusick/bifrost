# Solutions own their entities + a per-install management view (design note)

Date: 2026-06-06
Status: **design, not built** — hand off to a fresh session to execute as a real feature.
Branch: `worktree-solutions-success-criteria` (the in-flight Solutions work).
Companion: `2026-06-04-solutions-success-criteria.md` (the original 18 criteria) and
`2026-06-05-solutions-RESUME.md` (the build/audit history).

## Why this note exists

The original spec framed a Solution as something that **deploys** entities — they
land on the instance and live as normal scoped entities tagged with `solution_id`.
Working through the scoping during the session-4 audit, the model **evolved**: a
Solution should **OWN** the things it installs (tables, configs, preferences,
workflows, apps, forms, agents), not merely drop them in. This note records that
evolved model so it can be built deliberately rather than hand-patched.

This was a genuine clarification, not scope creep — see "the users-table argument".

## The model: Solutions own their entities ("World B")

The one novel user-facing rule a Solution introduces is **resolution order**:
*prefer an entity from a Solution you have access to, then fall through to the
normal `scope + name` org→global cascade.* Everything else (uniqueness, identity,
visibility) stays `scope + name` — but **scoped to the solution** for
solution-owned entities, exactly like workflows already work.

### The users-table argument (why ownership, not just deployment)
A developer authoring a Solution must **never have to reason about the global
namespace.** Two different Solutions may each ship a `users` table, or a `users`
config; neither should conflict with the other or with a global `_repo/` `users`.
So uniqueness for a solution-owned entity is keyed by `(solution_id, name)`, and a
caller resolving `users` gets *their own install's* `users` first. The developer
writes `useTable("users")` and it Just Works inside their Solution.

### What this means per entity type
| Entity | Owned by Solution? | Uniqueness | Resolution |
|--------|-------------------|-----------|-----------|
| workflows | yes (built) | `(solution_id, name)` + `(solution_id, path, fn)` partial-unique | solution-first path-ref, then `_repo/` |
| apps | yes (built) | `(solution_id, slug)` + `(solution_id, repo_path)` partial-unique | per-install id (uuid5) |
| forms | yes (built) | per-install id | per-install id |
| agents | yes (built) | per-install id | per-install id |
| tables | yes (built, uniqueness FIXED 2026-06-06) | `(solution_id, name)` partial-unique | solution-first by name via `X-Bifrost-App` |
| **configs** | **NOT built — this note** | should be `(solution_id, key)` | solution-first by key |

## The configs piece (the net-new work)

Configs are currently NOT solution-managed at all: `Config` ORM has no
`solution_id`, configs aren't in `SolutionBundle`/deploy. The original spec
**deliberately** kept config *values* instance-owned because they hold secrets /
OAuth tokens, and there was nowhere coherent for a Solution to hold "you must
provide an API key."

**The evolved model resolves that tension with a schema-vs-value split:**

- A Solution **owns the config DECLARATION / schema** — "this install requires
  `STRIPE_KEY` (secret), `REGION` (string, default us-east)". This is portable,
  deploy-owned, part of the bundle.
- The **install owns the VALUE** — the operator supplies `STRIPE_KEY`'s actual
  secret **in a per-install management view** (see below). Values stay
  instance-owned (the original secret-safety constraint holds); only the
  *requirement* travels with the Solution.

So: Solution declares the config keys/types/required-ness; the install view is
where required secrets/values get entered. This is the missing home that the
original "config values stay instance-owned" decision lacked.

### Build sketch (for the fresh session — verify against current code first)
1. `Config` (and/or a new `IntegrationConfigSchema`-like) gains `solution_id`
   (nullable) + deploy support in `SolutionBundle` / `_upsert_configs`.
2. Config SCHEMA (key, type, required, secret?, default) is solution-owned and
   portable in the manifest; uniqueness `(solution_id, key)`. Config VALUE stays
   on the existing instance-owned `Config` row (never in the portable bundle —
   matches the existing scrub rules in `bifrost/portable.py`).
3. Resolution: solution-first by key, then org→global cascade (mirror the
   workflow/table pattern + the `X-Bifrost-App` install-scope plumbing already
   built in `tables.py` / `ExecutionContext.app_id`).
4. Reuse `OrgScopedRepository` for scoping — do NOT reinvent the cascade
   (see `api/src/repositories/README.md`).

## The per-install management view (net-new UI)

"A special view where you see all of [an install's] stuff in one area, including
configs that might need required input like secrets." Concretely:
- One screen per install: lists its owned workflows/apps/forms/agents/tables AND
  its config declarations, with required-but-unset values surfaced (the operator
  fills in secrets here).
- This is also the natural home for the read-only affordances and an install's
  status/health.

## Loose ends to fold in (from the audit, NORMAL-USE)
- **Read-only-UI gap (INCONSISTENCY):** `Applications.tsx` shows a "Managed" lock
  badge + hides edit/delete for solution-managed apps, but the **Forms,
  Workflows, and agents Fleet LIST pages do NOT** condition Edit/Delete on
  `is_solution_managed` (5 hits in v1.d.ts confirm the field exists). Apply the
  same affordance to those list pages. (Small, ships independent of the configs
  work.)

## What's already DONE on the branch (don't redo)
The identity/ownership apparatus for workflows/apps/forms/agents/tables is built
and audited: uuid5 per-install ids, solution-scoped uniqueness, solution-first
resolution (`WorkflowRepository._resolve_by_path_ref`, `_resolve_solution_table_by_name`),
`X-Bifrost-App` install-scope plumbing, deploy of all five types incl access_level
/ agent limits / MCP grants, read-only enforcement (REST/MCP/S3), the per-install
write lock, and the v2 app model. Configs are the one owned-entity type NOT yet
built — that + the install view is this note's scope.
