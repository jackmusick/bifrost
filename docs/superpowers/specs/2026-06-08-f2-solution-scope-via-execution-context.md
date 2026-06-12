# F2 — a solution workflow resolves its own entities (via ExecutionContext, no new header)

Date: 2026-06-08
Worktree: `solutions-success-criteria` · Branch `worktree-solutions-success-criteria` · Draft PR #347
Fixes shakeout CRITICAL: "Solution workflow cannot resolve its OWN solution-managed table by
name (insert 404s; query/count 404 silently into empty)". This is the F2 item ("centralize
solution-first resolution") scoped to the path that actually broke.

## The bug

A running solution workflow calls `sdk.tables.get("lab_widgets")` (or query/insert/count). The
table is solution-managed (`solution_id` set). The call resolves by NAME with no solution scope,
so it never prefers the install's own table → `insert()` 404s the run; `query()/count()` 404
silently into an empty `DocumentList` (the SDK swallows 404). The **app** path works because the
browser sends `X-Bifrost-App` → server maps `app_id → Application.solution_id` →
`_resolve_solution_table_by_name` prefers the install's own table. The **workflow** path has no
equivalent.

## Why no new header (the key realization)

The engine **already builds an `ExecutionContext` per execution** and already plumbs it to the
SDK, and the SDK already appends a per-call `?scope=` derived from it. The executing workflow's
`solution_id` is **already known server-side** (the engine looked the workflow row up by ID; the
row carries `solution_id`; it's already in `context_data`). So the scope does not need a new wire
mechanism — it rides the **same `ExecutionContext` that already carries org/user**, and the SDK
appends it the **same way it appends `?scope=`**.

This also answers the trust question: passing the scope from the engine is not a privilege grant.
Org-resolution + role-based access still gate every call (the audit verified a forged foreign
`X-Bifrost-App` is blocked for non-superusers by the org gate in `_resolve_solution_table_by_name`).
The scope is a **resolution hint** ("prefer this install's own entity"), not authorization. Omit
it → you resolve against `_repo/`. That's the correct, safe fallback.

Events / schedules / sub-workflow calls all run **by workflow ID** → resolve to a row that already
carries `solution_id` → that execution's `ExecutionContext` carries it → their downstream calls
resolve own-first too. One mechanism, all callers. Apps are unchanged (they keep `X-Bifrost-App`).

## The chain (verified, file:line)

1. **Consumer already has it.** `api/src/jobs/consumers/workflow_execution.py` loads the workflow
   row and sets `solution_id = workflow_data.get("solution_id")`, already placing it in
   `context_data["solution_id"]` (and `solution_global_repo_access`). No change needed to obtain it.
2. **Request build** — `api/src/services/execution/worker.py` builds `ExecutionRequest(...)` from
   `context_data`. → **ADD** `solution_id=context_data.get("solution_id")`.
3. **Request DTO** — `api/src/services/execution/engine.py::ExecutionRequest` (dataclass, ~line 75).
   → **ADD** `solution_id: str | None = None`.
4. **Context build** — `engine.py:280` builds `ExecutionContext(...)` (the class from
   `src/sdk/context.py`) and passes it to `bifrost._context.set_execution_context` (line 298),
   which stores it in the ContextVar the SDK reads. → **ADD** `solution_id=request.solution_id`.
5. **Context class** — `api/src/sdk/context.py::ExecutionContext` (the one the SDK ContextVar
   holds; `bifrost/_execution_context.py` is a TYPE_CHECKING alias of the same). → **ADD**
   `solution_id: str | None = None`.
6. **SDK send side** — `api/bifrost/tables.py` builds URLs with `_scope_query(scope)` (`?scope=`),
   `scope` resolved from the ContextVar via `resolve_scope`/`get_default_scope`
   (`api/bifrost/_context.py`). → the table SDK functions **also append** the install scope when
   the ContextVar carries `solution_id` (a `solution=` query param), the same way `scope` is
   appended. (Reuse `_scope_query`-style helper; one place.)
7. **Server read side** — `api/src/routers/tables.py` table routes read `scope` as a `Query(...)`.
   → **ADD** a `solution: str | None = Query(None)` (or read it where `scope` is read) and feed it
   to `get_table_or_404` / `_resolve_solution_table_by_name`.
8. **Server resolve side** — `_resolve_solution_table_by_name(ctx, name, target_org_id)` already
   does own-first given a `solution_id` (today derived from `ctx.app_id`). → make it accept the
   install scope from **either** `ctx.app_id → Application.solution_id` **or** the `solution`
   param — ONE own-first resolver, two sources of the scope (the F2 centralization). Keep the
   existing org gate (a non-superuser only reaches its-org-or-global tables, so a forged foreign
   `solution` is still blocked).

## Scope of THIS change

Tables only, end to end (the reproduced critical). Configs-by-key and workflow-by-name have the
same latent gap; once `ExecutionContext.solution_id` + the SDK append are in place, each is a
small follow-up (the config/workflow resolver consults the same scope). Called out, not built here.

## Trust / safety (explicit)

- The `solution` scope is engine-set from the workflow row, not user-typed; even if user code
  could influence it, the server's org/role gate (unchanged) authorizes the actual row access.
- Omitting it resolves against `_repo/` (safe default; pre-branch behavior).
- A forged foreign install scope is blocked for non-superusers by the existing org gate in
  `_resolve_solution_table_by_name` (audit-verified for the `X-Bifrost-App` twin).

## Testing

- **Unit:** `ExecutionRequest`/`ExecutionContext` carry `solution_id` (round-trip through the
  builders); the SDK appends the install scope when the ContextVar has `solution_id`;
  `_resolve_solution_table_by_name` prefers the install's table given the param (and respects the
  org gate — a foreign scope as non-superuser yields None / 404).
- **E2e (the reproduced repro):** install a solution with a workflow that does
  `sdk.tables.insert("lab_widgets", {...})` then `sdk.tables.query("lab_widgets")`; run it as the
  install's org; assert insert succeeds and query returns the row (own table resolved). Negative:
  a _repo/ caller (no solution scope) does NOT resolve the solution table by name. Cross-org: a
  workflow in OrgB cannot reach OrgA's install table even with a forged scope (org gate holds).
- **Live drive:** reproduce the exact failing case from the shakeout (`bifrost solution install`
  a solution owning a table + a `lab_seed` workflow; `bifrost workflows execute lab_seed --org
  <OrgA>`; confirm it no longer 404s and the row lands).

## Non-goals

- No new header. No change to the app path (`X-Bifrost-App` stays).
- Configs/workflows own-first: follow-ups (foundation laid here).
- No change to the engine token (it's a shared long-lived token; scope is per-execution via the
  ExecutionContext, correctly).
