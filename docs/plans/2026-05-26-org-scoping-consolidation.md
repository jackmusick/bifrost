# Org-Scoping Consolidation

**Date:** 2026-05-26
**Status:** Draft — pending approval
**Companion audits:**
- `docs/audits/2026-05-26-org-scoping-cascade-audit.md`
- `docs/audits/2026-05-26-caller-identity-audit.md`

---

## Problem

Organization scoping in Bifrost is scattered across five distinct cascade implementations, nine effective-scope resolvers, and eighteen ORM models with `organization_id` columns. The documented canonical pattern (`OrgScopedRepository` in `api/src/repositories/`) is bypassed by inline cascades in routers, parallel implementations in services, and hand-rolled queries in SDK endpoints. This has been "fixed" multiple times and continues to drift. The drift has shipped real bugs (the cross-tenant token leak in `IntegrationsRepository.get_provider_org_token`, the partial-hash cache invalidation bug, the unguarded `_get_cli_org_id` accepting any UUID).

**The goal of this plan is not to fix the next bug. The goal is to make it impossible for the pattern to drift again.** The OAuth and config bugs we know about today get fixed as a natural consequence of consolidation, not as the destination.

## Success criteria

The overhaul is complete when all of the following are true:

1. There is exactly one effective-scope resolver function, used by every entry point that needs one.
2. There is exactly one cascade implementation (the `OrgScopedRepository` base class), used by every execution-resolution entity.
3. Every ORM model with `organization_id` is classified in code as either execution-resolution (has a repository) or identity (explicitly exempt).
4. Mechanical tests fail CI if a new router introduces an inline cascade, or a new model with `organization_id` is added without classification.
5. The documented contract appears at every code surface a developer or agent would touch when working in this area.
6. The OAuth cross-tenant leak, the config cache invalidation bug, and the unguarded `_get_cli_org_id` are gone — as observable evidence the consolidation worked, not as standalone fixes.
7. All tests pass (unit, E2E, client) — `./test.sh all && ./test.sh client unit && ./test.sh client e2e`.
8. Manual end-to-end verification in the browser and via the SDK across three caller types: a regular org user, a platform org user, and a platform admin. For each, confirm:
   - UI listing pages (applications, forms, agents) show the expected entities — own-org + globals for org users; cross-org as expected for platform admins.
   - SDK reads from within a workflow resolve correctly — org users get their own org's data, platform admins can target any org by passing scope.
   - Cross-tenant isolation holds — an org user cannot surface another org's data by any means.
9. A neutral agent (fresh session, no prior context from this work) invoked with a prompt like "confirm your understanding of org scoping in this codebase" produces a sound answer derived from the documentation. If the agent gets it wrong, the docs failed and need iteration before the overhaul is considered complete.

---

## Trust model (anchoring assumption)

The engine sentinel is the security boundary. Specifically:

- The engine authenticates to the API as a single fixed superuser identity (`SYSTEM_USER_ID = "0000...0001"`).
- Each execution carries a `caller` field on its `ExecutionContext`, populated at execution start from the originating user / scheduled job / webhook event.
- The SDK (running inside the workflow process in the engine) reads `context.caller` and resolves the effective scope locally before making API calls.
- The API receives a resolved scope from the engine and trusts it, because the authenticated principal is the sentinel.
- **If the sentinel credential leaks, the entire org-isolation model collapses.** This is a known and accepted cost of the architecture, and must be stated plainly in the canonical doc.

Direct user-facing API calls (REST endpoints hit by the UI) do not pass through the engine. Those endpoints authenticate the user directly and apply the same resolver against the authenticated principal, with no caller indirection.

MCP authenticates as the user directly and does not follow the engine-sentinel pattern. MCP endpoints are out of scope for this overhaul.

---

## Architecture

### Single scope resolver

```python
def resolve_effective_scope(
    caller: Caller,
    requested_scope: Scope,
) -> UUID | None:
    """Resolve the org scope for this operation.

    Caller is the originating identity (user, scheduled job, webhook event).
    Returns the org UUID to use, or None for global.
    """
```

`Scope` distinguishes three states: unspecified (use caller default), explicit None (global), explicit UUID. In FastAPI/Pydantic this requires an `UNSET` sentinel or a tagged union — the resolver must not collapse unspecified and explicit-None into the same branch.

Rules:

| `requested_scope` | Allowed if... | Result |
|---|---|---|
| unspecified | always | caller's default org |
| explicit `None` (global) | caller is platform admin | global (no org filter) |
| `caller.org_id` | always | caller's org |
| any other UUID | caller is platform admin | that org |

"Platform admin" means `caller.is_platform_admin` is true. (Whether the caller's organization is the `is_provider` org is a related concept — the resolver uses the flag, not the org membership; the flag is set at caller construction.)

The function lives in `api/shared/` so both the SDK (engine-side) and the API (for direct user calls) can import it. One source of truth.

### Two methods on the repository base class

`OrgScopedRepository` already exposes both. The contracts need to be made explicit and the implementations consolidated:

**`repo.get(name=...)`** — resolve one entity by identifier. Cascade with override: org-specific wins on collision, falls back to global. Returns at most one row. Used by SDK execution-time reads (`sdk.tables.get("users")`, `sdk.configs.get("api_key")`).

**`repo.list()`** — enumerate everything visible in this scope. Cascade union (org-specific + global, both visible). No override logic — collisions don't matter, both rows are returned. Role-based access filter applied automatically when the repository was constructed with a non-superuser `user_id`. Used by UI listing pages and by anyone who wants the full set of visible entities.

User-ness is encoded in the repository instance (`user_id`, `is_superuser`), not in method names. Construct the repo with the right identity and the right filters fire.

Both methods share the same cascade primitive (`or_(organization_id == X, organization_id.is_(None))`). The base class is the only place that primitive appears in the codebase. No subclass reimplements cascade. No router writes inline cascade queries.

### Entity classification

Twenty-four ORM models carry `organization_id`. They split cleanly. (The original plan estimated 18; landing the classification comments in phase 2 surfaced six additional models the cascade audit missed — primarily telemetry/aggregation tables and the events/policy entities. The increase is in both buckets and does not change the architectural conclusions.)

**Execution-resolution (15):** Table, Form, Config, SystemConfig, KnowledgeStore, Agent, MCPServer, MCPConnection, Application, IntegrationMapping, EventSource, Workflow, OAuthProvider, OAuthToken, CustomClaim. All accessed via `OrgScopedRepository` subclasses. All subject to cascade.

**Identity (9):** Execution, ExecutionMetricsDaily, WorkflowROIDaily, KnowledgeStorageDaily, User, AIUsage, KnowledgeNamespaceRole, Event, AuditLog. Belong to an org but are not resolved by name with cascade during execution. No cascade. No `OrgScopedRepository`. (Organization, UserRole, OAuthAccount are also identity entities but do not carry an `organization_id` column themselves — Organization IS the org, UserRole/OAuthAccount join to users.)

The classification is encoded in code (one-line comment above each model class) and verified by `test_org_scoped_models_have_repository`.

### Engine-facing endpoints

Rename `/api/cli/*` → `/api/sdk/*`. File rename `routers/cli.py` → `routers/sdk.py` (or split by domain: `sdk_tables.py`, `sdk_configs.py`, `sdk_integrations.py` — decision deferred to implementation).

These endpoints are thin: receive scope from request, pass to repository, return result. They do not call `resolve_effective_scope` — the engine has already resolved. They pass `is_superuser=True` to the repository because the principal is the sentinel.

Endpoints that don't touch org-scoped data (auth, health, version, cross-org platform admin operations, execution telemetry scoped by execution_id) are exempt. The exemption is explicit (allow-list in the lint test) and documented in each endpoint's docstring.

### User-facing endpoints

REST endpoints hit by the UI use `resolve_effective_scope` against the authenticated user (principal IS caller, no indirection). They pass the user's actual privileges (`is_superuser=user.is_superuser`) to the repository so role-based access checks fire.

### Caching is per-repository, cascade is centralized

Cascade is the cross-cutting concern (every execution-resolution entity has the same org-then-global pattern). It lives in `OrgScopedRepository` as the single primitive used by both `get` and `list`.

Cache is the per-entity concern (only Config caches today; maybe Knowledge later; most entities don't). When an entity needs caching, it's a thin transparent layer **inside that repository** wrapping the standard methods — callers don't know whether the result came from cache. The cache layer calls the cascade primitive for misses; it does NOT reimplement cascade.

`ConfigResolver` goes away entirely. Its `load_config_for_scope` becomes the standard `ConfigRepository.list()`, with cache concerns moved onto the repository. Callers that want a `{key: value}` dict do the shape transform at the call site — one line, no abstraction needed. `Config` is not special; it is one row in the entity classification table like every other execution-resolution entity.

The PR-308 cache invalidation bug gets fixed as part of this consolidation:

- Org-scoped config write: `delete` the org cache key (no partial `hset`). Forces re-fetch via cascade on next read.
- Global config write: `INCR bifrost:config:global_version`. Org cache keys embed the version, so a global write naturally invalidates every org cache without enumeration. No `scan_iter`. Old keys age out via TTL.

Cache invalidation hooks live on `ConfigRepository`, not in `core/cache/invalidation.py`. The `core/cache/` module retains shared Redis primitives (keys, TTL constants, client) but not entity-aware invalidation logic.

---

## Documentation tripwires

Documentation alone has not stopped drift. The plan combines docs with mechanical enforcement, but the docs still need to appear at every surface a developer or agent might touch.

**Root `CLAUDE.md`** — Add a top-level "Org Scoping" section with the four resolver rules and a pointer to the canonical doc. Every Claude session loads this; non-negotiable for stopping agent drift on routine tasks.

**`api/src/repositories/README.md`** — Single source of truth. Expand to include:
- The four-rule scope resolution table (with the trust model explained).
- The two repository methods (`get` for single-entity resolution, `list` for enumeration) and how user-ness is encoded in the repository instance, not in method names.
- The cascade-centralized / cache-per-repository split, with an example.
- The full classification table of all 18 ORM models.
- The trust assumption: "the engine sentinel credential is the security boundary; if it leaks, isolation collapses."
- "When NOT to use this pattern" section listing exempt endpoint categories.
- "Common Mistakes" with concrete anti-examples (inline cascades, raw queries in routers, trusting `requested_scope` directly).
- Pointer to the mechanical enforcement tests.

**Module docstring on `api/src/routers/sdk.py`** (post-rename) — "This is the SDK execution surface. The engine has already resolved scope; trust it. Every endpoint touching org-scoped data MUST use an `OrgScopedRepository` subclass. See `api/src/repositories/README.md`."

**Class docstring on `api/src/repositories/org_scoped.py::OrgScopedRepository`** — Expand to document the `get` vs `list_for_user` distinction with intent ("SDK resolution" vs "UI enumeration").

**One-line classification comment on every ORM model with `organization_id`** — `# Execution-resolution entity — access via <RepoClass>. See repositories/README.md` or `# Identity entity — not org-resolved. See repositories/README.md`. This is the tripwire when someone adds a column or migrates a model.

**Function docstring on `resolve_effective_scope`** — The four rules table inline. "If you find yourself writing a different version of this, stop."

`bifrost-build` skill is **not** updated. It targets workspace users building workflows/apps/forms on Bifrost; they don't touch this code.

---

## Mechanical enforcement

The pattern stops drifting when drift is detected automatically. Three new tests:

1. **`test_no_inline_org_scoping_in_routers`** — AST-walks `api/src/routers/`. Fails if any file contains a raw `organization_id == ...` comparison or `organization_id.is_(None)` outside whitelisted lines. New routers cannot introduce drift without explicitly editing the whitelist, which forces code review.

2. **`test_org_scoped_models_have_repository`** — For every ORM model with an `organization_id` column, assert there is a corresponding `OrgScopedRepository` subclass *or* the model is on the explicit identity-entity allow-list. Adding a new org-scoped model without a repository fails CI.

3. **`test_sdk_endpoints_use_resolver`** — For every endpoint in `routers/sdk.py` that declares a `scope` parameter, assert the handler calls `resolve_effective_scope`. Allow-list for exempt endpoints with one-line justification per entry.

Pattern precedent: `test_dto_flags.py` already enforces CLI/MCP/manifest parity the same way. Same shape works here.

---

## Sequence

Eight phases. Each phase ends in a green test run and is committable on its own.

### Phase 0: Plan + audit references

- This plan doc lands.
- Both audit docs are linked from the plan.
- No code changes.

### Phase 1: Centralize the resolver

- Define `Caller`, `Scope` types in `api/shared/`.
- Implement `resolve_effective_scope` in `api/shared/`.
- Unit tests for the four rules, including:
  - Cross-tenant: non-admin caller cannot resolve to other org's scope.
  - Explicit-None: only platform admin can request global.
  - Unspecified vs explicit-None distinction.
- No callers migrated yet. Function exists in isolation.

### Phase 2: Documentation surfaces land

- `api/src/repositories/README.md` expanded to canonical doc.
- Root `CLAUDE.md` "Org Scoping" section added.
- Module docstring on `routers/cli.py` (pre-rename — still useful in current location).
- Class docstring on `OrgScopedRepository`.
- One-line classification comment on all 18 ORM models.
- No behavior changes. The docs describe the target state. Subsequent phases bring code into compliance.

### Phase 3: Mechanical enforcement scaffolding

- All three lint tests written but with **complete current-state allow-lists**. They pass on day one.
- Subsequent phases shrink the allow-lists as code is migrated. The allow-list shrinking IS the migration's progress indicator.

### Phase 4: OAuth migration (the highest-impact security fix)

- Create `OAuthProviderRepository(OrgScopedRepository[OAuthProvider])` and `OAuthTokenRepository(OrgScopedRepository[OAuthToken])`.
- Migrate `sdk_integrations_get` and `sdk_integrations_refresh_token` call sites to use the new repositories.
- Delete `IntegrationsRepository.get_provider_org_token`.
- Delete `OAuthConnectionRepository`. The new `OAuthProviderRepository` absorbs both its cascade reads (via the base class) and its OAuth-specific write methods. Callers using `get_by_name` migrate to `repo.get(name=...)`. The `OAuthConnection` Pydantic return type goes away.
- E2E test: two orgs, each with their own OAuth mapping. Assert org A's SDK call cannot surface org B's token.
- Allow-list entries for the migrated sites are removed.

### Phase 5: Config cache invalidation (scoped narrower than original plan)

**Scope adjustment (2026-05-26):** the original plan called for deleting `ConfigResolver` entirely. Mid-phase audit found `ConfigResolver` has 3 callsites across `cli.py`, `workflow_execution.py`, and its own test files with substantial mocking. Deleting it would inflate Phase 5 well beyond the goal of "fix the cache invalidation bug." Narrowing the scope:

- **Fix the partial-hash bug** in `core/cache/invalidation.py`. Org-scoped writes now DELETE the merged hash instead of HSET-ing one field. This is the security-relevant fix.
- **Introduce versioned global key**. `CONFIG_GLOBAL_VERSION_KEY` is INCR'd on every global config write. Org-scoped cache keys embed the version via `config_hash_key_versioned`, so a global write naturally invalidates every org cache without enumeration. No `scan_iter`.
- **Wire reader and writer through the versioned key**. `ConfigResolver._get_config_from_cache` and `_set_config_cache` use `config_hash_key_versioned`. `upsert_config` and `invalidate_config` use it for org-scoped writes and INCR the version for global writes.
- **Regression tests** in `tests/unit/cache/test_invalidation.py` pin the partial-hash bug closed and assert the version-bump contract.
- **`ConfigResolver` is deleted.** Cascade is centralized in `OrgScopedRepository`; cache lives on `ConfigRepository` as a transparent layer. Callers use `repo.get()` / `repo.list()` like every other entity. (Originally proposed as a Phase 8 follow-up; landed in the phase 5 follow-up commit.)
- Allow-list shrinks for the cache-bug-driven allow-list entries (none today — the allow-list entries for cli.py config endpoints remain until phase 6's broader cli.py sweep).

### Phase 6: Tables / Apps relocation + SDK execution-path migration (scoped narrower than original plan)

**Scope adjustment (2026-05-26):** the original plan called for migrating every inline cascade across all routers (~47 callsites in 13 files). Mid-phase analysis showed:
- The cross-tenant security risk is in the SDK execution path (`cli.py`), not in UI-facing routers which have user auth at the endpoint level.
- Migrating UI-facing routers requires touching dozens of endpoints with their own bespoke filter logic (e.g. metrics aggregations, manifest sync) and risks breaking many tests during a phase that should ship cleanly.
- The mechanical lint test (Phase 3) tracks every remaining inline cascade in its allow-list, so they are documented and will fail CI if any drifts further.

**Phase 6 work that landed:**
- Moved `ApplicationRepository` from `routers/applications.py` (lines 91–613) to `repositories/applications.py`. Imports trimmed. Router file now imports the repository.
- Migrated `cli_list_tables` to `TableRepository.list()` — the SDK execution path that was a cross-tenant risk if any non-platform-admin caller could pass `--scope <other_org>`.
- `cli_create_table` retained its exact-scope uniqueness check (NOT a cascade). Allow-list updated to reflect this is intentional, not a cascade violation.
- Allow-list entries shrunk: ApplicationRepository (×2), `cli_list_tables` (×2). Each removed entry is observable progress per the Phase 3 design.

**Deferred to Phase 8 follow-up issues** (one issue per router file):
- `TableRepository` relocation (the class itself, distinct from `cli_list_tables` which is migrated)
- `claims.py`, `knowledge_sources.py`, `mcp_connections.py`, `tools.py`, `websocket.py`, `workflows.py`, `agents.py`, `tables.py`, `integrations.py`, `oauth_connections.py` inline cascades
- `export_import.py` manifest sync cascades (already explicitly Phase 8)

The allow-list IS the work tracker for these follow-ups.

### Phase 7: SDK scope authorization via resolver (scoped narrower than original plan)

**Scope adjustment (2026-05-26):** the original plan called for the URL rename (`/api/cli/*` → `/api/sdk/*`), file rename (`routers/cli.py` → `routers/sdk.py`), and deletion of `_get_cli_org_id` in favor of inline `resolve_effective_scope` calls. The URL/file rename is cosmetic relative to the goal "make org scoping stop drifting" — every drop of security work is in the *authorization* of the scope, not the URL path. Doing the rename as a single PR alongside CLI version-bump coordination would push this overhaul into a much larger change-set without moving the goal needle.

**Phase 7 work that landed:**
- `_get_cli_org_id` rewritten to route through `shared.scope_resolver.resolve_effective_scope`. Same signature plus a new `is_platform_admin` keyword (defaults to False — safe default for the platform-admin check). Closes the audit's "no platform-admin enforcement" gap.
- All 18 callsites in `cli.py` updated to pass `is_platform_admin=current_user.is_superuser`. One callsite (streaming AI-usage finalizer) runs without `CurrentUser` and is annotated for Phase 8 follow-up.
- `test_cli_get_org_id.py` rewritten as a security-contract pin:
  - Platform admin can request any org / global.
  - Non-admin CANNOT request other orgs (the cross-tenant traversal fix).
  - Non-admin CANNOT request explicit global.
  - Non-admin CAN request their own org (default path).
  - These tests were the carrier of the old "any UUID accepted" contract — the rewrite asserts the new contract instead. Test-discipline case (b).
- Empty string `""` preserved as UNSET (backwards compat with CLI clients passing `--scope ''`).

**Deferred to Phase 8 follow-up issues:**
- URL rename `/api/cli/*` → `/api/sdk/*` (cosmetic).
- File rename `routers/cli.py` → `routers/sdk.py` (cosmetic).
- `/api/cli/download` endpoint stays as documented exception either way.
- Inline `resolve_effective_scope` adoption in non-CLI endpoints (the SDK execution path now flows through the resolver; UI-facing endpoints can adopt incrementally).
- Streaming AI-usage finalizer (`cli.py:~2026`) plumbs the caller's admin flag explicitly.

### Phase 8: Follow-up items filed as separate issues

- Cross-org traversal hardening for any user-facing endpoints discovered during the migration (allow-list entries that survived phase 7 review).
- Redis-spoofing hardening for the `ExecutionContext` payload (sealing/signing).
- Manifest sync `_resolve_*` audit — verify whether import paths bypass repositories and migrate if so.
- Worker containers running as root (pre-existing memory entry, unrelated but adjacent).

Each follow-up gets its own GitHub issue. They are NOT in this overhaul's scope.

---

## Post-merge audit (2026-05-26, Codex)

After the verification commits landed, an independent agent (Codex) audited the
branch end-to-end and surfaced six findings. Three of them are real security
regressions that this overhaul did NOT close, and **must be addressed before
the branch ships.** They are tracked here because they invalidate parts of the
"goal met" claim above.

### CRITICAL — `_get_cli_org_id` derives `caller_org_id` from `DeveloperContext.default_org_id`

**The bypass.** `_get_cli_org_id` looks up the caller's "own org" by reading
`DeveloperContext.default_org_id` from the DB. But that field is user-settable
via `PUT /api/sdk/context` with no platform-admin check. A non-admin user can:

1. `PUT /api/sdk/context` with `default_org_id=<other_org_uuid>`.
2. Call any SDK endpoint with `scope` omitted.
3. The resolver sees `caller_org_id = <other_org_uuid>`, matches the request,
   and returns "your own org" — serving the other org's data.

The resolver is correct. The data flowing into it is forged.

References: `api/src/routers/cli.py:322`, `api/src/routers/cli.py:451`,
`api/src/core/auth.py:43`.

**Fix direction.** Source `caller_org_id` from `current_user.organization_id`
— the auth-verified DB column — not from `DeveloperContext`. The
`PUT /api/sdk/context` endpoint should either be removed entirely (see "Nuke
DeveloperContext" below) or restricted to platform admins.

**Test gap that let this through.** `test_cli_get_org_id.py` uses mocked
`DeveloperContext` fixtures that always match the caller's true org. A test
that explicitly sets `DeveloperContext.default_org_id` to a foreign org and
asserts the resolver still rejects would have caught this. Add that test
alongside the fix.

### Nuke DeveloperContext + the dev-run page (decision by user, post-audit)

The Codex finding above traced to `DeveloperContext` — a model the user has
identified as fundamentally broken in design. Direction: **remove
`DeveloperContext` entirely**, including:

- The ORM model + table + migration.
- The `PUT /api/sdk/context` and `GET /api/sdk/context` endpoints.
- All callsites that read `default_org_id` from it (most notably
  `_get_cli_org_id`).
- The dev-run page in the client (the UI that exposes/edits this state).
- The CLI commands that read/write DeveloperContext.

The replacement model:

- A user's effective org is `User.organization_id` only (never overridden
  by a per-user mutable "default").
- Scope-targeting in SDK calls happens only via the explicit `scope` parameter
  on the request, gated by `is_platform_admin` per the resolver's four rules.
- Platform admins targeting other orgs from a CLI session set `scope`
  explicitly per command, not via a persistent default-org override.

This is a substantial deletion across server, client, CLI binary, and tests.
It's the right move because as long as `DeveloperContext` exists, every SDK
endpoint that defaults to it has a forgery path — patching one site at a time
is whack-a-mole.

### HIGH — SDK-side resolver uses provider-org membership, not `is_platform_admin`

The plan says the resolver gates on `is_platform_admin`. The SDK-side caller
gate (engine, `api/bifrost/_context.py:128` and `api/src/services/execution/engine.py:280`)
reportedly still checks provider-org membership instead. Under the trust
model, the SDK-side resolver IS the security boundary for engine-routed
calls — using the wrong flag here is the real-world gate failing.

**Verify and fix.** Audit those two files. If true, switch to
`is_platform_admin`. Add tests at the SDK-resolver level that mirror the
API-side `test_cli_get_org_id.py` contract.

### HIGH — `/api/sdk/integrations/*_mapping` endpoints bypass scope authorization

Four endpoints accept arbitrary scope/org_uuid without going through
`_get_cli_org_id`:

- `list_mappings` — returns all org mappings.
- `get_mapping` — accepts arbitrary scope or scans by entity_id.
- `upsert_mapping` — accepts raw org UUIDs.
- `delete_mapping` — same.

These are `CurrentUser`-authenticated (not engine-sentinel), so a non-admin
can write/delete any org's mapping today.

References: `api/src/routers/cli.py:925`, `:991`, `:1054`, `:1139`.

**Why this slipped.** `test_sdk_endpoints_use_resolver` was checked in as a
placeholder that only verifies the resolver imports and the exempt-list shape
— NOT that endpoints actually call the resolver. The Phase 3 commit message
said the strict check would land in Phase 4 once the first caller existed.
It never got promoted. As a result, the mechanical enforcement that should
have flagged these four endpoints did not run.

**Fix direction.**

1. Migrate the four endpoints through `_get_cli_org_id` (with the
   `current_user.organization_id` fix above) so they get the
   caller-vs-platform-admin gate.
2. **Promote `test_sdk_endpoints_use_resolver` from placeholder to strict.**
   For every `/api/sdk/*` endpoint that declares a `scope` parameter, assert
   the handler body calls `resolve_effective_scope` (directly or via
   `_get_cli_org_id`). Allow-list entries with one-line justification per
   exempt endpoint.

### HIGH — Config cache invalidation incomplete on key/org changes

When a `Config` row's `organization_id` or `key` changes via REST
(`PUT /api/config/{id}`), the route only upserts the new (scope, key) cache
entry — the old (scope, key) entry stays cached until TTL, including
potentially stale secrets.

References: `api/src/routers/config.py:339`, `:345`, `:500`.

**Fix direction.** On update, if either `organization_id` or `key` changed,
explicitly delete the previous (old_scope, old_key) cache entry before
upserting the new one. Also bump `CONFIG_GLOBAL_VERSION_KEY` if the change
involves a transition to/from global scope.

### MEDIUM — `test_sdk_endpoints_use_resolver` is still a placeholder

Already covered above as the carrier of the "/api/sdk/integrations/*_mapping
bypass" issue.

### LOW — Plan body for Phase 5 contradicts the open-question resolution

Phase 5 body says "ConfigResolver kept as a thin layer; phase 8 follow-up will
fully merge into ConfigRepository." Open question #2 says
"~~Does ConfigResolver go away entirely?~~ Resolved: yes, deleted." And the
diff deletes it. Update the Phase 5 body to say "deleted" so the plan reads
consistently.

### NIT — `git diff --check` whitespace failures

Trailing whitespace in `api/src/repositories/applications.py` and the two
audit docs. Clean up before merge.

---

## Outstanding work to ship this branch (post-Codex)

Decisions locked in 2026-05-26 with the user; all of the below lands in
this same PR (the branch is the consolidation, not a hand-off):

1. **Nuke DeveloperContext entirely.** ORM model, migration to drop
   `developer_contexts`, `GET`+`PUT /api/sdk/context` endpoints, CLI
   `developer` commands, client `Developer.tsx` org-selector and
   interactive-run UI, `sdk.ts.getContext`/`updateContext`, and the
   `_get_cli_org_id` default-org sourcing. Replacement: `caller_org_id`
   comes from `current_user.organization_id` (auth-verified DB column),
   never from request body or DB-default override. Platform admins
   targeting other orgs pass `scope` explicitly per call.

2. **C2 gate, applied at both boundaries.** `is_superuser`
   (platform admin) and `is_provider` (provider-org member) remain
   independent flags. Both bypass scope. The gate is
   `caller.is_platform_admin OR caller.organization.is_provider` —
   applied identically API-side (in `_get_cli_org_id` /
   `resolve_effective_scope`) and SDK-side (in `_context.py:resolve_scope`).
   `ExecutionContext.is_platform_admin` is already plumbed through the
   engine; the SDK-side resolver just needs to read it.

3. **Mapping endpoints through the resolver.** `sdk_integrations_list_mappings`,
   `get_mapping`, `upsert_mapping`, `delete_mapping` all route through
   `_get_cli_org_id` with the C2 gate. `IntegrationsRepository.list_mappings`
   gains an org filter so non-admin/non-provider callers cannot enumerate
   other orgs' mappings.

4. **`test_sdk_endpoints_use_resolver` promoted to strict.** AST-walks
   every `/api/sdk/*` handler. Asserts the body calls `_get_cli_org_id`
   or `resolve_effective_scope`. Allow-list keyed on handler function
   qualname (not URL path — survives renames). One-line justification
   per exempt entry.

5. **Config cache invalidation on rename/move.** `PUT /api/config/{id}`:
   snapshot old `(org_id, key)` before update, `DELETE` the old cache
   key after a successful write, upsert the new entry. If the change
   crosses the global↔org boundary, `INCR CONFIG_GLOBAL_VERSION_KEY`
   so org caches that merged the global value re-fetch.

6. **Plan body + whitespace cleanup.** Phase 5 body updated to say
   "ConfigResolver deleted" (matching Open Question #2 and the diff).
   Trailing whitespace in `api/src/repositories/applications.py` and
   the two audit docs cleaned.

The OAuth cross-tenant token leak, the URL rename, the canonical pattern
mechanics, and the documentation tripwires are genuinely done. The
authorization-input-sourcing layer (caller_org_id), the SDK-side gate
correctness, the mapping-endpoint bypass, and the strict mechanical
enforcement are what items 1-5 close. Item 6 is hygiene.

---

## Phase 9 — post-Codex remediation (landed 2026-05-26)

All six items above landed in a single working session on top of the
existing 15-commit branch. Concrete file-level evidence for reviewer
verification:

### 1. DeveloperContext nuked

- ORM model deleted: `api/src/models/orm/developer.py` removed; the
  `developer_context` relationship dropped from `api/src/models/orm/users.py`;
  re-exports removed from `api/src/models/__init__.py` and
  `api/src/models/orm/__init__.py`.
- Drop-table migration: `api/alembic/versions/20260526_drop_developer_contexts.py`,
  rev `20260526_drop_developer_contexts` on top of
  `20260522_merge_claims_knowledge`. Has a downgrade for completeness.
- API: `PUT /api/sdk/context` deleted; `GET /api/sdk/context` rewritten
  to source the user and org from the auth-verified `current_user`
  only. The `?org_id=` override path applies the same C2 rule as the
  scope resolver (provider-org membership lookup is lazy).
  (`api/src/routers/cli.py`.)
- Workflow execution path: the secondary forgery surface in
  `api/src/routers/workflows.py` (platform-admin DeveloperContext
  override for global workflow execution) is gone. `request.org_id`
  remains the explicit way for admins to target another org.
- Client: `client/src/pages/user-settings/Developer.tsx` reduced to
  the SDK setup card (install/login/run snippets). The org-selector,
  track-executions Switch, and Save button are deleted.
  `client/src/services/sdk.ts` reduced to the download URL.
- CLI: no `bifrost developer` commands existed; the SDK's
  `_fetch_context` helpers continue to work against the GET endpoint.

### 2. C2 gate uniformly applied

- Resolver extended: `resolve_effective_scope` in
  `api/shared/scope_resolver.py` gains an `is_provider_org: bool`
  parameter. The four-rule table reads "bypass = is_platform_admin OR
  is_provider_org." Existing tests remain valid (kwarg-only with
  default False).
- API-side: `_get_cli_org_id` (in `api/src/routers/cli.py`) reads
  `caller_org_id` from `current_user.organization_id` (auth-verified
  DB column, no more DeveloperContext default), and looks up
  `Organization.is_provider` lazily — only when the request is not
  UNSET and not the caller's own org.
- SDK-side: `api/bifrost/_context.py:resolve_scope` reads
  `ctx.is_platform_admin` (already plumbed by the engine) and
  `ctx.organization.is_provider`. Both bypass paths exist on both
  boundaries now.

### 3. Mapping endpoints gated

All four of `sdk_integrations_list_mappings`, `get_mapping`,
`upsert_mapping`, `delete_mapping` route through `_get_cli_org_id`
with the C2 gate. `IntegrationsRepository.list_mappings` gains an
optional `organization_id` filter so non-bypass callers can no
longer enumerate other orgs. The `SDKIntegrationsListMappingsRequest`
contract gained an optional `scope` field for explicit cross-org
listing by bypass callers.

### 4. `test_sdk_endpoints_use_resolver` promoted

`TestSDKEndpointsUseResolver` in
`api/tests/unit/test_org_scoping_enforcement.py` no longer just
verifies the resolver imports — it AST-walks every `@router`-decorated
handler in `cli.py` that takes `scope` (signature or
`request.scope` body field) and asserts the body calls
`_get_cli_org_id` or `resolve_effective_scope`. Allow-list keyed on
handler function name (not URL path — survives renames). Currently
zero exempt entries; every scope-taking handler goes through the
gate.

### 5. Config cache invalidation on rename/move

`ConfigRepository.update_config_by_id` now returns
`(response, old_org_id, old_key)`. The PUT handler in
`api/src/routers/config.py` invalidates the old cache entry when
either field changed, and `INCR`s `CONFIG_GLOBAL_VERSION_KEY` on
global↔org transitions so org-merged caches re-fetch. Regression
tests: `api/tests/unit/routers/test_config_update_cache.py`.

### 6. Production-shaped scenario coverage (added during user review)

The user's review surfaced a real coverage gap: the C2 bypass for
non-admin provider-org members existed at the unit level but had
never been exercised end-to-end against a real seeded user. Filled:

- New fixture `provider_org_user` in `api/tests/e2e/fixtures/setup.py`:
  a regular (`is_superuser=False`) user inside the seeded provider
  org at UUID `00000000-0000-0000-0000-000000000002` (created by
  migration `20260107_022300_add_provider_org`).
- New test file
  `api/tests/e2e/api/test_org_scoping_scenarios.py` (12 tests)
  mapping 1:1 to the four scenarios the user named:

  | Scenario | Tests |
  |---|---|
  | (1) Orgs reach own data | UNSET resolves to own org; explicit own-org succeeds |
  | (2a) Platform admin reaches all | cross-org read; explicit global |
  | (2b) Provider-org member reaches all (new path) | cross-org read; explicit global — both by non-admin user |
  | (3) Org-then-global cascade | org row overrides global on UNSET; falls back to global when org row absent |
  | (4) Cross-org blocked | explicit other-org → 403; explicit global → 403; UNSET cannot leak (DeveloperContext-forgery regression pin); mapping endpoint isolation |

All 12 pass; full e2e is 1322 passed (was 1310 before the additions),
52 skipped (pre-existing), 0 failed.

### Verification summary (final state)

| Suite | Pass |
|---|---|
| Unit (api) | 3987 |
| **E2E (api)** | **1322** (12 new scenario tests) |
| Client unit (vitest) | 1045 across 145 files |
| Pyright | 0 errors in changed files (41 pre-existing in unrelated tests) |
| Ruff / TSC / lint | clean |

---

## Phase 10 — Codex round-2 remediation (landed 2026-05-26)

After the user took the branch to Codex for an independent review, five
findings came back. All addressed in this branch:

### P2.1 — Preserve 403 in mapping endpoint exception handlers

`sdk_integrations_get`, `list_mappings`, `get_mapping`, and
`delete_mapping` each had a blanket `except Exception` that downgraded
the resolver's 403 into a 200/null response or `{"deleted": False}`.
Each now has `except HTTPException: raise` ahead of the generic
handler, so 403 surfaces cleanly. Six `cli_knowledge_*` handlers had
the same swallow pattern (Codex didn't call them out, but the risk is
identical); patched the same way for consistency. `cli.py` audited:
every scope-taking SDK handler that has a generic exception catch now
re-raises `HTTPException` first.

### P2.2 — Strengthen mapping isolation e2e

The previous `test_mapping_endpoint_isolation` used a nonexistent
integration name, so the handler returned before `_get_cli_org_id`
fired and the test accepted `200+null`. Rewritten to:

1. Seed a real integration and a real org2-scoped mapping.
2. Hit list_mappings / get_mapping / delete_mapping / upsert_mapping
   from `org1_user` with `scope=org2["id"]` — each must be 403.
3. After the forbidden delete attempt, verify the org2 mapping still
   exists (the delete didn't quietly fall through to a no-op).

This now actually exercises the gate. A swallowed-403 regression would
fail.

### P2.3 — Lint test is Pydantic-model-aware

`test_every_scope_taking_handler_calls_resolver` previously detected
scope-taking handlers via (a) direct `scope` parameter or (b) body
references to `request.scope`. A future handler could ship a body
model declaring `scope: str | None` and never reference it; the test
would skip it entirely. Added a third detector: static AST inspection
of `api/src/models/contracts/cli.py` finds every Pydantic model
declaring a `scope` field. Any handler whose body parameter is
annotated with one of those models is treated as scope-taking. Two
new tests pin the detector:

- `test_scope_model_inventory_is_nonempty` — fails if the contract
  scan finds zero scope-bearing models (i.e., the walker silently
  broke).
- `test_synthetic_handler_with_scope_model_no_resolver_is_caught` —
  builds a fake handler that takes a real scope-bearing model and
  never calls the resolver; confirms the detector flags it.

### P3.1 — `ExecutionContext.set_scope` uses the C2 rule

The ambient `ctx.set_scope("...")` call (separate from explicit
`resolve_scope()` in SDK reads) still gated on
`is_provider` alone — so a platform admin in a non-provider org could
not override scope ambient. Now applies
`is_platform_admin OR is_provider_org`, matching the rule everywhere
else. Five tests added at `tests/unit/test_resolve_scope_sdk.py`
covering each path: admin in non-provider org, provider-org member,
non-admin/non-provider blocked, same-org noop, None resets.

### P3.2 — Repositories README reflects C2 rule

`api/src/repositories/README.md` updated. The four-rule table now
shows `is_platform_admin OR is_provider_org` for the bypass rows.
Added a "Why two independent bypass flags?" subsection explaining
why the flags can't collapse into one (platform admin in a
non-provider org; non-admin in the provider org).

### Codex round-2 verification

| Suite | Pass | Delta |
|---|---|---|
| Unit (targeted org-scoping) | 59 | +7 (5 set_scope, 2 lint-detector) |
| E2E (scenario file) | 12 | unchanged; mapping-isolation test now hits real gate |
| Pyright / ruff / tsc / lint | clean | — |

---

## Phase 11 — Codex round-3 remediation (landed 2026-05-26)

Codex's third pass surfaced a remaining HIGH-severity gap that the
phase-10 work missed: the SDK-side resolver was correct, but **three
SDK methods bypassed it entirely**, posting caller-supplied `scope`
raw. Under workflow execution the API authenticates as the engine
sentinel (`is_superuser=True`), so the API-side gate ALWAYS passes —
which makes the SDK-side `resolve_scope` the only real gate for
engine-routed calls. With that gate skipped, a non-admin workflow
could mutate any org's mapping by passing a victim UUID.

### HIGH — SDK mapping mutators must resolve_scope locally

Fixed in `api/bifrost/integrations.py`:

- `list_mappings(name, scope=None)` — gained a `scope` parameter,
  calls `resolve_scope(scope)` locally, posts the resolved value.
- `upsert_mapping(name, scope, ...)` — calls `resolve_scope(scope)`
  before posting; raises `PermissionError` SDK-side if the caller is
  not platform-admin / provider-org and asks for a foreign scope.
- `delete_mapping(name, scope)` — same.

`get_mapping` was already correct; the other three matched its pattern
now.

The mechanical-enforcement test continues to assert API-side
gating, but the test fixture for engine-sentinel calls can't exercise
SDK-side gating — the real regression pin is the e2e below.

### Regression e2e: engine-sentinel cross-org mutation blocked

New test `test_workflow_via_engine_cannot_mutate_other_org_mapping`
in `tests/e2e/api/test_org_scoping_scenarios.py`:

1. Seeds an integration with a real org2 mapping.
2. Registers a workflow in org1 (non-provider).
3. Executes it as `org1_user` (non-admin, non-provider) — so the
   engine spins up an ExecutionContext with `is_platform_admin=False`
   and `organization.is_provider=False`.
4. Inside the workflow: `integrations.upsert_mapping(..., scope=org2_id)`.
5. Asserts the workflow caught a `PermissionError` (raised SDK-side,
   never reaches the API) AND that the org2 mapping is unchanged.

This is the load-bearing test for the round-3 fix. Pre-fix it would
have raised no error and the org2 mapping would have been clobbered.

### MEDIUM — Stale `client/src/lib/v1.d.ts`

Regenerated against the worktree's API container. Removes the deleted
`PUT /api/cli/context` operation and `DeveloperContextUpdate` schema;
adds the new `scope` field to `SDKIntegrationsListMappingsRequest`.

### LOW/MEDIUM — Repositories README endpoint-surfaces section

`api/src/repositories/README.md` previously said `/api/sdk/*` was
engine-only and that org users don't hit it directly. Current code
explicitly supports direct CLI calls gated by `_get_cli_org_id`;
README now describes both call paths and which gate (SDK-side vs
API-side) catches an unauthorized request for each.

### Round-3 verification

| Suite | Pass | Delta |
|---|---|---|
| E2E scenarios | 13 | +1 (engine-sentinel regression) |

Full `./test.sh all` to follow.

---

## Phase 12 — Knowledge audit + client URL fixes (landed 2026-05-26)

User asked for knowledge scoping status. Audited end-to-end:

| Layer | Result |
|---|---|
| SDK (`api/bifrost/knowledge.py`) | All 7 methods (`store`, `store_many`, `search`, `delete`, `delete_namespace`, `list_namespaces`, `get`) call `resolve_scope(scope)` before posting. |
| API handlers (cli.py, 7 `cli_knowledge_*` routes) | All call `_get_cli_org_id` with C2 gate. All preserve `HTTPException` ahead of generic exception catch (round-2 fix). |
| Repository (`KnowledgeRepository`) | Extends `OrgScopedRepository`. Cascade is the same shared primitive every other org-scoped entity uses. |
| Existing e2e | `test_org_workflow_sees_org1_data_in_all_modules` etc. exercise full cross-org knowledge isolation through the workflow engine, gated behind `EMBEDDINGS_AI_TEST_KEY`. |

Added a focused gate-check e2e that does NOT require embeddings:
`test_knowledge_endpoint_isolation`. It hits `list_namespaces`,
`delete_namespace`, and `search` with cross-org `scope` from a regular
org user and asserts 403; UNSET on the same user returns 200. This
covers the C2 boundary specifically, independent of the embedding
infrastructure.

### Client-side URL fixes (latent bugs surfaced by the audit)

Two client files still referenced pre-rename paths under `/api/cli/*`:

- `client/src/hooks/useKnowledge.ts` — `GET /api/cli/knowledge/namespaces`
  → `/api/sdk/knowledge/namespaces`. Stale comments on the `scope`
  param ("backend uses DeveloperContext") also corrected to describe
  the auth-verified caller org / C2 resolver default.
- `client/src/services/cli.ts` — four references to
  `/api/cli/sessions*` → `/api/sdk/sessions*`. These would have
  returned 404 (the router prefix changed in phase-7 follow-up).

`/api/cli/download` is the deliberate exception and stays — it's the
URL embedded in install commands.

### Round-4 verification

| Suite | Pass | Delta |
|---|---|---|
| E2E scenarios | 14 | +1 (knowledge isolation) |
| Client tsc + lint | clean | — |

Full `./test.sh all` re-run pending.

---

## Test discipline (during migration)

When tests fail during this migration, **stop and consider why the test expected what it did before adjusting it.** Default assumption: the test was right and the code change is wrong. Tests are claims about behavior; adjusting them silently to match new output erodes the contract they were protecting.

This rule is saved as feedback memory (`feedback_test_failure_discipline.md`) and applies to every phase. If a test fails:

1. Read the test name and the assertion. What was it claiming?
2. Check git history for the commit that introduced it. What bug was it preventing?
3. Decide: (a) my change broke a valid contract, fix the code; (b) the contract is intentionally obsolete, document why and update; (c) the test was wrong from the start (rare, needs justification).
4. Never silently update assertions to match new output.

If a test only covered happy path and now fails because the new code raises on a previously-accepted scope, the failure may be telling you the test was incomplete. Add the missing coverage rather than weakening the assertion.

---

## Risks and mitigations

**Risk: phase 4 (OAuth) is a behavior change that could affect production OAuth flows.**
Mitigation: E2E test pinned at phase 4 entry. Stage the change behind feature flag if the test surface isn't strong enough. Rollback plan: revert the repository wiring, fall back to current behavior.

**Risk: cache invalidation versioning (phase 5) could cause a stampede on the first global config write after deploy.**
Mitigation: pre-compute the global version key on deploy if absent. Document the warm-up.

**Risk: `/api/cli/*` rename (phase 7) breaks deployed CLI binaries.**
Not actually a risk. The CLI does `sys.exit(1)` on any version mismatch with the server (verified in `test_cli_version_check.py`), so deployed CLIs are already forced to upgrade against the matching API build. Single coordinated CLI version bump in the same release. The `/api/cli/download` endpoint stays at its existing path so install URLs in docs and elsewhere keep working; it's reachable by source/dev installs which skip the version check.

**Risk: the mechanical lint tests have allow-lists that grow over time as people exempt themselves.**
Mitigation: the allow-list requires a one-line comment per entry. Code review catches additions. The audit can be re-run periodically to ensure shrinkage.

**Risk: identity-classification of the 18 models is wrong in subtle cases.**
Mitigation: phase 2 docs include the table. Phase 3 lint test exercises every model. If a classification is wrong, the test fails or the missing repository surfaces in phase 4-6.

**Risk: SDK-side `resolve_effective_scope` is bypassed by some sneaky path.**
Mitigation: SDK has cross-tenant tests at the SDK boundary, not just the API boundary. Phase 4 sets the test pattern; subsequent phases follow it.

---

## What this overhaul does NOT do

Explicit non-goals, so the scope stays bounded:

- Does not change MCP authentication or scope handling. MCP is user-direct and stays that way.
- Does not redesign the engine sentinel credential or rotate it.
- Does not seal/sign the `ExecutionContext` payload in Redis. (Follow-up.)
- Does not migrate identity models (Organization, User, etc.) to `OrgScopedRepository`. They are not cascade entities by design.
- Does not change `bifrost-build` or any workspace-facing skill. This is platform-development work.
- Does not address worker root-user hardening.

---

## Open questions

1. ~~Should the engine-facing endpoint rename land in this overhaul?~~ **Resolved: yes, in phase 7.** CLI enforces strict version equality so backwards-compatibility is not needed. `/api/cli/download` stays at its current path as the deliberate, permanent home for the install endpoint (served by a separate `install_router`).

2. ~~Does `ConfigResolver` go away entirely?~~ **Resolved: yes, deleted.** Cascade is centralized in `OrgScopedRepository`; cache lives on `ConfigRepository` as a transparent layer. No separate resolver class. Callers use `repo.get()` and `repo.list()` like every other entity. The CLI download endpoint stays at `/api/cli/download` as a documented exception to the `/api/cli/*` rename.

3. ~~The five identity models — are any edge cases?~~ **Resolved: no.** Verified `UserOAuthAccount` is only touched by `services/oauth_sso.py` (login flows) and the user/MFA models. Never resolved by SDK or execution paths. The five-model identity classification stands as-is: Organization, User, UserRole, OAuthAccount, AuditLog.

4. ~~`OAuthConnectionRepository` — migrate or leave as sibling?~~ **Resolved: migrate.** The "exactly one cascade implementation" success criterion isn't met if a sibling class with parallel-but-correct cascade semantics survives. `OAuthProviderRepository(OrgScopedRepository[OAuthProvider])` becomes the canonical class. OAuth-specific operations (`update_connection`, `delete_connection`, `store_tokens`, encryption/decryption around client secrets) move onto the new repository as additional methods rather than a sibling service. The current `OAuthConnection` Pydantic return type disappears — callers work with the `OAuthProvider` ORM row directly.

5. ~~Feature flag on phase 4?~~ **Resolved: no flag.** Feature flags on security fixes are an anti-pattern — the "off" state preserves the vulnerability. Phase 4 lands as one cohesive PR with two-org cross-tenant tests at the SDK boundary. Rollback path is a normal revert.

All open questions resolved. Phases 0-3 can begin once the plan is approved.
