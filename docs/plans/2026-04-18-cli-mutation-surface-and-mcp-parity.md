# CLI Mutation Surface & MCP Parity

**Date:** 2026-04-18
**Status:** Draft — ready for execution
**Supersedes:** `2026-04-16-manifest-in-memory-gatekeeper.md` (all scope — the in-memory gatekeeper is abandoned; see Context)
**Related:** `2026-04-16-manifest-compat-audit.md` (audit that killed the gatekeeper), `2026-04-18-cli-mutation-surface.md` (the command/tool catalog this plan executes)

---

## Context / Motivation

The gatekeeper plan tried to keep `bifrost watch` pushing `.bifrost/*.yaml` by reimplementing bulk-manifest translation client-side in an in-memory store. The compat audit (`2026-04-16-manifest-compat-audit.md`) showed that four of ten entity types (integrations, integration-owned configs, tables, events) can't round-trip through the public REST surface without significant server work or a client-side rebuild of the old `_resolve_*` logic — the exact "two parallel translation layers" the plan was meant to avoid. The disappearing-entity bug (entity silently deleted because watch pushed a stale bulk manifest) is still urgent but is already mitigated by the tactical `delete_removed_entities=False` flip on the watch push path.

The user has pivoted. `.bifrost/` becomes **export-only** — it is what `bifrost pull` / `bifrost sync` write for sharing, versioning, and cross-environment moves, never what `watch` reads to mutate entities. All entity mutations move to an explicit first-class surface: **28 dedicated CLI commands** plus **MCP parity tools** for the entity classes the assistant surface was missing. Watch stops touching `.bifrost/` entirely and only syncs code files (apps/, workflows/*.py). Agent and form content move **inline** into the manifest (the separate `.form.yaml` / `.agent.yaml` files go away on export).

The `cli-mutation-surface.md` catalog is the spec. This plan is its executable overlay: shared infrastructure first (ref resolution, DTO-driven field generation, the one required server change), then per-entity CLI commands, then MCP parity fill-ins, then watch-mode simplification and the manifest-inline migration.

---

## Architecture Overview

```
        ┌──────────────────────────────────────────────────────┐
        │                   Shared infrastructure              │
        │                                                      │
        │   resolve_ref(kind, value, *, org=None)  ─┐          │
        │     UUID | name | "path::func"            │          │
        │                                           │          │
        │   dto_flag_spec(XxxCreate|XxxUpdate)  ─┐  │          │
        │     walks Pydantic model, emits:       │  │          │
        │       CLI flag definitions             │  │          │
        │       MCP tool parameter schemas       │  │          │
        │       exclude-list for UI-managed      │  │          │
        │       fields                           │  │          │
        └───────────────────────────────┬────────┴──┴──────────┘
                                        │
                ┌───────────────────────┼──────────────────────┐
                ▼                       ▼                      ▼
     ┌───────────────────┐   ┌───────────────────┐    ┌────────────────────┐
     │   CLI commands    │   │  MCP tools (NEW)  │    │   REST routers     │
     │   (Click-based)   │   │  (thin wrappers)  │    │   (FastAPI)        │
     │                   │   │                   │    │                    │
     │  28 dedicated     │   │  parity tools for │    │   unchanged except │
     │  commands from    │   │  roles / configs  │    │   TableUpdate gets │
     │  the catalog's    │   │  integrations     │    │   name +           │
     │  "Proposed CLI    │   │  orgs / wf lifec. │    │   application_id   │
     │  signatures" blk  │   │                   │    │                    │
     │                   │   │  HTTP-in-process: │    │                    │
     │                   │   │  call REST API    │    │                    │
     │                   │   │  (no ORM, no repo)│    │                    │
     └─────────┬─────────┘   └─────────┬─────────┘    └──────────┬─────────┘
               │                       │                         │
               └───────────────────────┴─────────────────────────┘
                                       │
                                       ▼
                            Same REST endpoints, same DTOs,
                            same auth, same error shapes.

      Existing MCP tools (agents/forms/tables/apps/events): NOT touched in this plan.
      They duplicate router logic today; reconciliation is a follow-up plan.

     ┌──────────────────────────────┐      ┌──────────────────────────┐
     │   bifrost watch              │      │   bifrost sync / pull    │
     │   (simplified)               │      │   (unchanged)            │
     │                              │      │                          │
     │   syncs apps/, workflows/*.py│      │   still writes .bifrost/ │
     │   IGNORES .bifrost/          │      │   as export artifact;    │
     │   deletes the bulk-push path │      │   agents/forms now inline│
     └──────────────────────────────┘      └──────────────────────────┘
```

The CLI and MCP surfaces are peers — both generate their parameter shape from the same DTO walker, both call `resolve_ref` for name→UUID lookups, both call the same REST endpoints. Drift between them is a field-parity test away from being caught.

---

## Design decisions already made

These were settled in `cli-mutation-surface.md` and its design questions. Do not re-litigate during execution.

- `.bifrost/` is **export-only**. Watch never reads it as an entity-mutation source.
- Watch stops at code files: `apps/`, `workflows/*.py`. Nothing else.
- Agent and form **content** moves inline under UUID in the manifest. Separate `.agent.yaml` / `.form.yaml` files go away on export.
- 28 dedicated CLI commands (see catalog's "Proposed CLI signatures"). Everything else falls back to `bifrost api`.
- MCP surface gains parity tools for entity classes it's missing: roles, configs, integrations create/update + mappings, organizations update/delete, workflow lifecycle (update/delete/grant-role/revoke-role).
- CLI flag definitions and MCP tool schemas are **generated from `XxxCreate` / `XxxUpdate` Pydantic DTOs**, not hand-written.
- Field parity enforced by tests, not review discipline.
- Shared `resolve_ref(kind, value)` helper. Per-invocation cache. UUID passes through; name resolves if unambiguous; raises `AmbiguousRefError` with candidates otherwise ("pass the UUID instead"). **No `--org` scoping flag** — using names as lookup-scope is an antipattern; IDs are the source of truth. `organization_id` appears on commands only when it's a DTO field, via the generator, as a value (not a scope hint).
- `update` commands default-omit unset flags. Only send the fields the user explicitly passed. This preserves UI-managed fields without a hard-coded allowlist.
- UUID-on-create gap is documented but not fixed in this plan — server still assigns UUIDs via `uuid4()`. Blocks a future `bifrost import` but not `create`.
- One required server change: `TableUpdate` DTO extended with `name` + `application_id`. Nothing else on the server changes except the agent-granular-endpoint deprecation (subject to UI audit).
- Integration OAuth provider stays UI-only — no CLI or MCP surface.
- Integration-owned config linkage (`integration_id` / `config_schema_id`) stays server-internal — no CLI or MCP surface.
- Verb corrections from the audit are authoritative (agents=PUT, integrations=PUT, configs=PUT, apps metadata=PATCH-without-draft, deps=PUT at app_code_files endpoint).
- Watch's tactical `delete_removed_entities=False` workaround gets removed once the bulk-push code path is deleted.

---

## Tasks

Tasks are sequentially numbered. Task dependencies are called out explicitly. Where tasks are parallelizable, that's called out too.

---

### Task 1: Shared `resolve_ref` helper

Create a single client-side helper that maps `(kind, user-supplied ref)` → UUID. Used by every CLI `update`/`delete`/sub-resource command and by MCP parity tools that accept user-friendly refs.

**Behavior:**
- Signature: `resolve_ref(client, kind: Literal["org","role","workflow","form","agent","app","integration","table","event_source","config"], value: str) -> str`
- UUID input (pass-through validation): return immediately if `value` is a valid UUID.
- `path::func` input for `workflow` kind: split and lookup via `GET /api/workflows?path=...&function_name=...`.
- Name input: lookup via the entity's list endpoint across all accessible scopes.
- Slug input (apps): lookup via `GET /api/applications?slug=...`.
- Ambiguity: raise `AmbiguousRefError` with the full candidate list (name, UUID, org_id); CLI surfaces as "multiple matches; pass the UUID instead." **No `--org` disambiguation flag** — forcing users to UUID when the name is ambiguous is a feature, not a papercut.
- Not-found: raise `RefNotFoundError`.
- Per-invocation cache: `dict[(kind, key), uuid]` attached to the helper's calling context (not process-global; CLI command instance owns it).

**Files:**
- Create: `api/bifrost/refs.py` (helper + exceptions).
- Create: `api/tests/unit/test_refs.py` (one test per entity kind covering UUID/name/`path::func`/slug/ambiguity/not-found/org-scoping).

**Verification:** `./test.sh tests/unit/test_refs.py` passes. Each entity kind has at least one test for UUID, name, and ambiguity paths.

**Commit:** `feat(cli): add resolve_ref helper for portable entity refs in CLI and MCP`

---

### Task 2: DTO-driven field generator

A utility that walks `XxxCreate` / `XxxUpdate` Pydantic models and emits (a) Click flag definitions for CLI, (b) MCP tool parameter JSON schemas, (c) body-building helpers that assemble the REST payload from parsed args.

**Behavior:**
- `build_cli_flags(model_cls, *, exclude: set[str], verb_ref_lookups: dict[str, str]) -> list[click.Option]`
  - For each writable field on the DTO:
    - Bool → `--{kebab}` / `--no-{kebab}` with tri-state (unset = don't send).
    - List[str] → repeatable flag (`--tag foo --tag bar`), or comma-split if the field name ends in `_ids`.
    - Dict → `@file` loader only (`--schema @schema.yaml`).
    - Enum → `click.Choice`.
    - Plain scalar → typed flag.
  - `exclude`: set of field names the generator must skip (UI-managed fields — see catalog's cross-cutting concerns #4).
  - `verb_ref_lookups`: map `field_name → ref_kind` for fields that accept a name/UUID ref (e.g. `workflow_id → "workflow"`). Flags become `--workflow <ref>` and get resolved via `resolve_ref` before payload assembly.
- `build_mcp_schema(model_cls, *, exclude: set[str]) -> dict` — JSON schema suitable for fastmcp tool parameter declaration. Same exclude semantics. Ref-lookup fields accept string refs in the schema; resolution happens in the tool handler.
- `assemble_body(model_cls, parsed_args, *, resolver: RefResolver) -> dict` — builds the REST request payload from parsed args, resolving refs, dropping unset optionals, handling the `config_type → type` and `roles → role_ids` renames. Rename rules are declared per-call (e.g. `field_aliases={"config_type": "type"}`).

**Excludes (hard-coded per entity, enforced by tests):**
- Organizations: `domain, settings, is_provider`
- Workflows (Update): `display_name, tool_description, time_saved, value, cache_ttl_seconds, allowed_methods, execution_mode, disable_global_key`
- Integrations (Create/Update): `oauth_provider` (out-of-scope)
- Integration mappings: `oauth_token_id` (UI-set)
- Applications: `icon`

**Files:**
- Create: `api/bifrost/dto_flags.py` (the generator + rename/exclude registries).
- Create: `api/tests/unit/test_dto_flags.py` — field-parity tests: for each of the 10 entity DTOs, assert every non-excluded writable field produces a flag. When a DTO grows a new field, this test fails loudly.
- Create: `api/tests/unit/test_dto_body_assembly.py` — round-trip tests: given parsed CLI args, the assembled body matches an expected dict per entity (covers renames, omit-unset, ref resolution via a fake resolver).

**Verification:** `./test.sh tests/unit/test_dto_flags.py tests/unit/test_dto_body_assembly.py` passes. Field-parity test fails if any tested DTO adds an unhandled field.

**Depends on:** Task 1 (uses `resolve_ref`).

**Commit:** `feat(cli): add DTO-driven flag/schema generator with field-parity tests`

---

### Task 3: Server-side `TableUpdate` DTO extension

Extend `TableUpdate` to accept `name` and `application_id`. Update the handler to apply them conditionally. Required before tables CLI/MCP update commands can rename or reassign.

**Files:**
- Modify: `api/src/models/contracts/tables.py` — add `name: str | None = None`, `application_id: str | None = None` to `TableUpdate`.
- Modify: `api/src/routers/tables.py` — in `update_table` handler, apply `if request.name is not None: table.name = request.name` and likewise for `application_id`. Validate `application_id` exists and belongs to the table's org (reuse any existing validation from `TableCreate`).
- Modify: `api/tests/e2e/platform/test_tables.py` (or create) — rename + reassign-to-app tests via the public endpoint.

**Verification:** `pyright` clean on `api/src`, `ruff check api` clean, new E2E tests pass via `./test.sh tests/e2e/platform/test_tables.py`. Rename a table via PATCH and confirm `GET /api/tables/{id}` reflects the new name. Reassign to a different app and confirm the app linkage.

**Commit:** `feat(tables): allow rename and application reassignment on TableUpdate`

---

### Task 4: CLI command scaffolding

Before per-entity commands, establish the shared command skeleton so every entity file looks the same.

**Behavior:**
- A `BifrostCommand` base (Click group or mixin) that handles:
  - Auth (session token lookup from the CLI's existing auth cache; 401 surfaces as "run `bifrost login`").
  - `--json` output mode (suppresses human-friendly formatting; prints `json.dumps` of the response for scripting).
  - `RefResolver` creation per invocation (injects the per-invocation cache). No `--org` scoping flag — resolver uses IDs or unambiguous names only.
  - Error surfacing: `RefNotFoundError` → exit code 2; `AmbiguousRefError` → exit code 2 with the candidate list and "pass the UUID" hint; HTTP 4xx → exit code 1 with the server's error body; HTTP 5xx → exit code 3 with retry hint.
  - 403 special case: surface the required role/permission from the response (matches catalog cross-cutting #9).
- Subgroup registration pattern: `bifrost orgs ...`, `bifrost roles ...`, etc. Register all 10 entity subgroups up front; per-entity tasks only add commands to existing subgroups.

**Files:**
- Create: `api/bifrost/commands/__init__.py` (subgroup registration).
- Create: `api/bifrost/commands/base.py` (`BifrostCommand`, error handling, `--json`, resolver plumbing).
- Modify: `api/bifrost/cli.py` — wire the new `commands` subgroups into the top-level Click app. Remove any now-obsolete inline command definitions that are about to be replaced (only if they don't break until Tasks 5a–5j land; otherwise leave and replace per-entity).
- Create: `api/tests/unit/test_cli_base.py` — covers `--json` output, ref-resolution error surfacing, 403 permission surfacing.

**Verification:** `bifrost --help` lists all 10 entity subgroups (even if empty). `./test.sh tests/unit/test_cli_base.py` passes.

**Depends on:** Tasks 1, 2.

**Commit:** `feat(cli): add shared command scaffolding with --json and error surfacing`

---

### Tasks 5a–5j: Per-entity CLI commands

One task per entity type. All 10 tasks share the same shape. They can run in parallel after Task 4, except 5i (tables) depends on Task 3 and 5h (configs) can overlap with 5g (integrations) but the integration-owned config test coverage belongs to 5g.

Each task:
- Adds the dedicated commands from the catalog's "Proposed CLI signatures" block for that entity.
- Uses `dto_flag_spec` to generate flags from the `XxxCreate` / `XxxUpdate` DTO.
- Uses `resolve_ref` for every user-facing ref in the signatures.
- Covers sub-resources listed for that entity.
- Adds E2E tests invoking the CLI against the real API (via the existing test harness).
- Updates `bifrost <subgroup> --help` output to match the signatures.

Ordering within each task: create → update → delete → sub-resources.

#### 5a. Organizations

**Commands:** `orgs list`, `orgs create`, `orgs update`, `orgs delete`.
**Files:**
- Create: `api/bifrost/commands/orgs.py`.
- Create: `api/tests/e2e/platform/test_cli_orgs.py` — covers create/list/update/delete end-to-end.
**Verification:** E2E test creates an org, updates its name, deletes it. Required flags match `OrganizationCreate`/`OrganizationUpdate` minus the exclude list.
**Commit:** `feat(cli): add bifrost orgs CRUD commands`

#### 5b. Roles

**Commands:** `roles list`, `roles create`, `roles update`, `roles delete`.
**Files:**
- Create: `api/bifrost/commands/roles.py`.
- Create: `api/tests/e2e/platform/test_cli_roles.py`.
**Verification:** `--permission foo --permission bar` produces the permissions list correctly. E2E test creates, updates, deletes.
**Commit:** `feat(cli): add bifrost roles CRUD commands`

#### 5c. Workflows

**Commands:** `workflows list`, `workflows register`, `workflows update`, `workflows delete`, `workflows grant-role`, `workflows revoke-role`.

**Decision to make during this task** (catalog open question #3): role diff partial-failure behavior. Options from the catalog:
- (a) Accept partial failure, print failed ops. **Recommended default.** Lowest effort; matches the one-role-at-a-time endpoint shape.
- (b) Add a server replace-set endpoint (out of scope here).
- (c) Client-side rollback. Too complex.

This task implements (a): if any grant/revoke in a batch fails, print a per-role success/failure table and exit 1. `--strict` flag would make any failure abort remaining ops; skip unless trivial.

**Files:**
- Create: `api/bifrost/commands/workflows.py`.
- Create: `api/tests/e2e/platform/test_cli_workflows.py`.
**Verification:** `workflows update --roles foo,bar,baz` against an existing workflow: diffs current assignment, issues add/delete calls, reports results. E2E covers update/delete/grant-role/revoke-role.
**Commit:** `feat(cli): add bifrost workflows lifecycle and role commands`

#### 5d. Forms

**Commands:** `forms create`, `forms update`, `forms delete`. (List stays generic per the catalog.)
**Files:**
- Create: `api/bifrost/commands/forms.py`.
- Create: `api/tests/e2e/platform/test_cli_forms.py`.
**Verification:** `forms create --workflow path::func --schema @schema.yaml` resolves workflow ref, loads schema YAML, POSTs form. E2E covers the common flows.
**Commit:** `feat(cli): add bifrost forms CRUD commands with ref resolution and @file schema loading`

#### 5e. Agents

**Commands:** `agents create`, `agents update`, `agents delete`.
**Files:**
- Create: `api/bifrost/commands/agents.py`.
- Create: `api/tests/e2e/platform/test_cli_agents.py`.

Verb is PUT for update (audit correction). `--prompt @file.md` loads system prompt from file. `--tools`, `--delegates`, `--knowledge` accept comma-separated refs resolved via `resolve_ref`. `--clear-roles` is a bool flag.
**Verification:** E2E creates an agent with multi-line prompt from file, updates its model, deletes it.
**Commit:** `feat(cli): add bifrost agents CRUD commands with @file prompt loading and ref lists`

#### 5f. Apps

**Commands:** `apps create`, `apps update`, `apps set-deps`, `apps delete`.

Two-call orchestration in `apps create` when `--deps` is passed: `POST /api/applications`, then `PUT /api/applications/{id}/dependencies` with the parsed dict. If the deps call fails after the create succeeded, surface both results but leave the app created (don't try to roll back).

`roles` ↔ `role_ids` rename (audit finding).

**Files:**
- Create: `api/bifrost/commands/apps.py`.
- Create: `api/tests/e2e/platform/test_cli_apps.py`.
**Verification:** `apps create foo --deps @package.json` produces both REST calls. E2E covers update metadata, set-deps, delete.
**Commit:** `feat(cli): add bifrost apps commands with two-call create+deps orchestration`

#### 5g. Integrations

**Commands:** `integrations create`, `integrations update`, `integrations add-mapping`, `integrations update-mapping`.

`config_schema` loaded from file. When `update` detects removed keys vs current server state (fetch via `GET /api/integrations/{id}` first), the command:
- Lists the removed keys and the number of cascading `Config` rows that will be deleted.
- Refuses unless `--force-remove-keys` is set.

Mapping commands resolve org refs via `resolve_ref("org", ...)`. `update-mapping` never sends `oauth_token_id` unless explicitly `--oauth-token-id <id>`.

**Files:**
- Create: `api/bifrost/commands/integrations.py`.
- Create: `api/tests/e2e/platform/test_cli_integrations.py`.
**Verification:** Integration create with schema file, schema update with a key removed refuses without `--force-remove-keys`, add-mapping + update-mapping work end-to-end. Verify `oauth_token_id` is not clobbered on update when absent from the command.
**Commit:** `feat(cli): add bifrost integrations commands with config-schema safety and mapping CRUD`

#### 5h. Configs

**Commands:** `configs list`, `configs create`, `configs update`, `configs delete`.

**Decision to make during this task** (catalog open question #2): whether to add a `configs set` upsert alias. Decision: **yes**, implement as a small wrapper over `create` / `update` — it does a `GET /api/config?key=X&organization_id=Y`, routes to PUT if found or POST if not. Cheap, matches user intent of "idempotent config setting."

`--type` accepts the enum values (`string`, `secret`, etc.). `--value` omittable on update preserves existing (server semantic). `--confirm` required on `delete` when the config is secret-type (fetch first to check).

**Files:**
- Create: `api/bifrost/commands/configs.py`.
- Create: `api/tests/e2e/platform/test_cli_configs.py`.
**Verification:** `configs set` behaves as upsert. Deleting a secret config without `--confirm` refuses. `configs update --value` omitted leaves value intact (verified via round-trip).
**Commit:** `feat(cli): add bifrost configs commands with set upsert and secret confirm guard`

#### 5i. Tables

**Commands:** `tables list`, `tables create`, `tables update`, `tables delete`.

Uses the extended `TableUpdate` DTO from Task 3. `--schema @file.yaml` for create and update. Rename warning: when `update` detects the user is changing `--name`, the command emits a big warning telling them to grep the codebase for the old name (see Task 10).

**Depends on:** Task 3.

**Files:**
- Create: `api/bifrost/commands/tables.py`.
- Create: `api/tests/e2e/platform/test_cli_tables.py`.
**Verification:** Rename works. Reassign via `--application` works. Rename warning appears.
**Commit:** `feat(cli): add bifrost tables commands including rename and application reassignment`

#### 5j. Events

**Commands:** `events create-source`, `events update-source`, `events subscribe`, `events update-subscription`.

Flat-to-nested translation: `--cron`, `--timezone`, `--schedule-enabled` collapse into the DTO's `schedule: ScheduleSourceConfig`; `--adapter`, `--webhook-integration`, `--webhook-config @file.yaml` collapse into `webhook: WebhookSourceConfig`. Documented in `--help` text.

`events subscribe` accepts `--workflow` as portable ref (`path::func` or name). `update-subscription` refuses attempts to change `target_type`/`workflow_id`/`agent_id` with a clear error directing users to delete + recreate.

**Files:**
- Create: `api/bifrost/commands/events.py`.
- Create: `api/tests/e2e/platform/test_cli_events.py`.
**Verification:** Create a scheduled source via `--cron "*/5 * * * *" --timezone UTC`, subscribe a workflow, update the subscription's `--event-type`, confirm rejection when trying to change the workflow ref.
**Commit:** `feat(cli): add bifrost events commands with flat-to-nested translation`

---

### Task 6: MCP parity tools for missing entity classes (thin wrappers only)

The MCP server at `api/src/services/mcp_server/tools/` currently exposes tools for some entity classes but not all. Fill in:

- **Roles** — full CRUD (`list_roles`, `create_role`, `update_role`, `delete_role`).
- **Configs** — full CRUD (same surface as CLI).
- **Integrations** — create, update, add_mapping, update_mapping (no OAuth provider, no batch).
- **Organizations** — update and delete (create/list already exist; confirm and add whatever's missing).
- **Workflow lifecycle** — update, delete, grant_role, revoke_role. (List/register already exist.)

**Critical architectural constraint — thin wrappers only.** A separate drift audit (conducted during plan design, see Risks section) found that *existing* MCP tools for agents, forms, and tables **duplicate and diverge from** the REST routers' business logic — different permission models, missing side effects (`RepoSyncWriter`, role sync, cache invalidation), different validation depth, divergent `created_by` semantics. Consolidating the existing tools into shared services is a behavior-reconciliation project with product decisions (permission-model merges, migration of in-flight behavior), **not a refactor, and is out of scope for this plan.**

To avoid *adding* to the drift while this plan ships, new MCP tools added in Task 6 are **thin wrappers that call the REST endpoints internally** — same as the CLI — rather than re-implementing repository/ORM logic. Concretely:

- Each new MCP tool handler: validate minimal inputs (scope enum, required fields), call `resolve_ref` for any user-supplied refs, then issue an HTTP call to the corresponding REST endpoint using the MCP context's auth. Return the endpoint's response body as the `ToolResult` payload.
- No direct ORM, no repository imports, no `AsyncSession` access, no `RepoSyncWriter` / `sync_*_roles_to_workflows` / `invalidate_*` calls. All of that happens behind the REST endpoint, which is canonical.
- This means the HTTP-in-process pattern (MCP tool → its own REST server via an async client) is explicitly used for these new tools. It's weird but it's the forcing function for consistency.

**Behavior:**
- Tool parameter schemas generated via `build_mcp_schema` from the same DTOs as the CLI (same exclude lists, same renames).
- Ref-accepting params documented in the schema as "UUID, name, or portable ref" depending on the kind.
- Handlers call `resolve_ref` then the REST endpoint. Share the path-routing helper with the CLI so verb corrections stay in one place.
- Error surfacing: REST 4xx → `error_result` with the server's error body; REST 5xx → `error_result` with retry hint; `AmbiguousRefError` / `RefNotFoundError` → `error_result` with the candidate list.

**Files:**
- Create: `api/src/services/mcp_server/tools/roles.py`, `configs.py` (and extend `integrations.py`, `organizations.py`, `workflow.py` with the missing ops).
- Modify: `api/src/services/mcp_server/tools/__init__.py` — register the new tools.
- Create: `api/tests/e2e/mcp/test_mcp_parity.py` — for each new tool, a test that the schema is generated correctly and a happy-path call hits the right endpoint. Field-parity test (similar to the CLI one) asserts every writable DTO field is either exposed or explicitly excluded.
- Create: `api/tests/unit/test_mcp_thin_wrapper.py` — asserts new tool handlers do not import `repositories.*`, `models.orm.*`, or hold an `AsyncSession`. Fails if someone tries to add direct DB access to a new tool.

**Explicitly NOT in scope for this task:**
- Refactoring existing MCP tools (agents, forms, tables, apps, events) to thin wrappers. Their drift is documented but left alone.
- Extracting shared service functions from router handlers. Routers stay as they are.

**Follow-up plan (file during this task, do not execute):** `docs/plans/2026-04-18-mcp-router-reconciliation.md` — catalogs the drift per entity (reference the drift audit already done during this plan's design), proposes per-entity merge decisions (whose permission model wins, whether to add missing side effects, whether to promote warn-and-continue into 422s), and sequences the migration.

**Verification:** Schema-diff test between CLI flag set and MCP tool param set passes (same DTO, same exclude, same result). E2E tests create/update/delete for each new tool. Unit test confirms no new tool imports repositories or ORM.

**Depends on:** Tasks 1, 2, 3 (tables rename via MCP needs the extended DTO).

**Commit:** `feat(mcp): add thin-wrapper parity tools for roles, configs, integrations, orgs, workflow lifecycle`

---

### Task 7: Agent granular-endpoint deprecation (with UI migration)

The four redundant agent endpoints (audit cross-cutting #6):
- `POST /api/agents/{id}/tools`
- `DELETE /api/agents/{id}/tools/{workflow_id}`
- `POST /api/agents/{id}/delegations`
- `DELETE /api/agents/{id}/delegations/{delegate_id}`

Remove server-side, migrate any UI callers to `PUT /api/agents/{id}` with full `tool_ids` / `delegated_agent_ids` lists. Done in one change.

**Step 1: audit UI call sites.**

```
rg -n "/agents/.*/(tools|delegations)" client/src
```

If the call sites are non-trivial (e.g. many handlers across components, optimistic-update state, mutation caches), dispatch a subagent to map them and propose the migration shape before editing.

**Step 2: migrate UI callers.** For each call site:
- "Add tool" / "Add delegation" button: fetch the current agent, append to `tool_ids` / `delegated_agent_ids`, call `PUT /api/agents/{id}`.
- "Remove tool" / "Remove delegation" button: same pattern, filter out the UUID.
- Update optimistic-update logic and React Query invalidations to target the full agent PUT response.

**Step 3: remove server endpoints.** Delete the four handlers in `api/src/routers/agents.py` and any associated tests. Run the routers test suite to confirm nothing else referenced them.

**Files:**
- Modify: `api/src/routers/agents.py` — remove four handler functions.
- Modify: `client/src/` — UI call-site migrations (paths depend on audit output).
- Modify: `api/tests/e2e/platform/test_agents.py` (or wherever) — remove tests for the removed endpoints.

**Verification:** `rg -n "/agents/.*/(tools|delegations)" client/src` returns nothing. `pyright` clean. `ruff check` clean. `./test.sh tests/e2e/platform/test_agents.py` passes. Manually test "Add tool" and "Remove tool" in the agent UI against dev stack.

**Commit:** `refactor(agents): remove granular tool/delegation endpoints; migrate UI to full agent PUT`

---

### Task 8: Watch mode simplification

Watch is **exclusion-based**, not path-locked. It watches the workspace root and excludes specific subtrees — today that's gitignored paths; this task adds `.bifrost/` to the exclusion set. Workflows, apps, and arbitrary files (txt, json, etc.) can live anywhere in the workspace and stay watched. The only change is that `.bifrost/` stops producing events.

**Files:**
- Modify: `api/bifrost/cli.py`:
  - Watchdog observer setup / `_WatchChangeHandler`: add `.bifrost/` to the existing exclusion list (alongside `.gitignore`-derived exclusions). Events under `.bifrost/` are not delivered to the handler.
  - `_process_watch_batch`: remove the branch that detects `.bifrost/` files, parses them, and POSTs to `/api/files/manifest/import`. Dead once the observer excludes the directory, but delete the code too so nothing accidentally re-enables it.
  - Remove `state.writeback_paused` and the 0.2s sleep bandaid (cli.py:1965–1972 and 2385–2387 per the gatekeeper plan's line references — verify exact lines during execution).
  - Remove the `delete_removed_entities=False` kwarg — the call site is gone.
- Modify: `api/tests/e2e/platform/test_watch_*.py` (existing watch tests) — remove or rewrite any tests that asserted `.bifrost/` changes get pushed; add a test asserting touching `.bifrost/` files produces no events and no REST traffic.

**Verification:** Start watch, edit `.bifrost/workflows.yaml`, confirm no event is logged and no REST call fires. Edit a `workflows/foo.py` in the usual location, confirm it syncs. Create `workflows/subdir/other.py` and a `random.txt` at the workspace root, confirm both sync. Confirm a gitignored file still doesn't sync.

**Commit:** `refactor(watch): exclude .bifrost/ from the filesystem observer; watch only syncs code`

---

### Task 9: Inline agent/form content in manifest export

Move agent and form **content** from `agents/{uuid}.agent.yaml` and `forms/{uuid}.form.yaml` into the manifest (`.bifrost/agents.yaml` and `.bifrost/forms.yaml`) under each entity's UUID.

**Files:**
- Modify: `api/bifrost/manifest.py`:
  - Extend `ManifestAgent` with the full content fields (`system_prompt`, `channels`, `tool_ids`, `delegated_agent_ids`, `knowledge_sources`, `system_tools`, `llm_model`, `llm_max_tokens`, `description`).
  - Extend `ManifestForm` with `workflow_id`, `form_schema`, `description`, `launch_workflow_id`, `default_launch_params`, `allowed_query_params`.
- Modify: `api/src/services/manifest_generator.py` — serialize full content inline. Stop writing separate `.agent.yaml` / `.form.yaml` files.
- Modify: `api/src/services/github_sync.py` (or wherever import happens):
  - Read inline content from manifest.
  - **Back-compat:** during the rollout window, if a manifest doesn't carry inline content but a companion `.agent.yaml` / `.form.yaml` exists, still import from the companion file with a warning: `"Agent/form content in separate file is deprecated; regenerate with 'bifrost sync' to inline"`. Remove this back-compat branch in a follow-up plan once all checked-in manifests have been regenerated.
- Modify: existing round-trip tests in `api/tests/unit/test_manifest.py` and `api/tests/e2e/platform/test_git_sync_local.py` — update expectations to inline shape. Add a test for the deprecated-separate-file back-compat path.

**Verification:** `bifrost sync` on a workspace with agents and forms produces a `.bifrost/agents.yaml` / `.bifrost/forms.yaml` with full content, and does NOT produce `agents/*.yaml` or `forms/*.yaml` files. Round-trip (sync → wipe DB → sync-import) reproduces the same DB state. Back-compat test: a checked-in workspace with the old split layout still imports without data loss, with a warning logged.

**Depends on:** none of the other tasks strictly, but coordinating this with the CLI `forms create`/`agents create` commands (Tasks 5d, 5e) is cleaner since both cover the same content fields.

**Commit:** `feat(manifest): inline agent and form content under UUID in manifest export`

---

### Task 10: CLAUDE.md and llm.txt updates

**CLAUDE.md — add a "Keeping CLI, MCP, and manifest in sync" section.** When a DTO changes:

1. Run the DTO-parity test (`./test.sh tests/unit/test_dto_flags.py`). If it fails, either add the new field to the appropriate command/tool, or add it to the exclude list with a one-line reason.
2. If the field should round-trip in exports, update `api/bifrost/manifest.py`.
3. If the field changes a command or tool that Claude should know about, update `docs/llm.txt`.
4. For rename or ID-reassign operations on tables, workflows, or configs: grep the codebase (`rg -n "\\b<old-name>\\b"`) for references before committing. Workflows referenced by `path::func` in forms and tables referenced by name in workflow SDK calls silently break on rename. The CLI warns when it detects a rename; this rule is the author's side of the contract.

**llm.txt — document the new surface.** For each of the 28 CLI commands and each new MCP tool, a one-line description and an example invocation. Organize by entity (matches the catalog's section headers). Remove any stale documentation about editing `.bifrost/` YAML to mutate entities.

**Files:**
- Modify: `/home/jack/GitHub/bifrost/CLAUDE.md`.
- Modify: `/home/jack/GitHub/bifrost/docs/llm.txt` (if it exists; otherwise check `api/bifrost/` and top-level for the canonical location).

**Verification:** `./test.sh` passes (no new tests, just docs). Manual read-through: a new dev reading CLAUDE.md + llm.txt could figure out how to create an org, a workflow, a form, an integration without reading source.

**Commit:** `docs: document CLI/MCP sync checklist and update llm.txt with new surface`

---

### Task 11: Regression test for disappearing-entity bug

The original motivating bug (gatekeeper plan lines 12–19): UI creates event source, concurrent watch push deletes it. Task 8 fixes it structurally. Confirm via E2E.

**Files:**
- Create: `api/tests/e2e/platform/test_watch_regression_disappearing_entity.py`.

**Scenario:**
1. Start CLI watch session in a workspace.
2. Via API (simulating UI), `POST /api/events/sources` to create a new event source. Capture the UUID.
3. Concurrently (racing the WS event broadcast), touch an unrelated `workflows/foo.py` file.
4. Let watch drain.
5. Assert: `GET /api/events/sources/{uuid}` returns 200 (entity still exists).
6. Assert: no `DELETE /api/events/sources/{uuid}` call was ever made by watch (inspect recorded REST traffic or watch logs).

**Depends on:** Task 8.

**Verification:** New E2E passes. Run three times consecutively (`./test.sh tests/e2e/platform/test_watch_regression_disappearing_entity.py` 3x) with no flakes.

**Commit:** `test(watch): regression coverage for disappearing-entity race now that bulk push is gone`

---

### Task 12: Remove tactical `delete_removed_entities=False` workaround

Task 8 deletes the call site where this workaround lived. Task 12 cleans up any related dead code: comments referencing the workaround, the kwarg default in `/api/files/manifest/import` usage if it's no longer used anywhere, and the CLI's documentation of the flag.

**Files:**
- Grep `delete_removed_entities` across the repo and clean up any remaining references.
- `api/src/routers/files.py` (or wherever the manifest-import endpoint lives): the kwarg can stay (it's still used by `bifrost sync` TUI and the new `bifrost import` in Task 15), but any stale comment about the watch workaround should be removed.

**Verification:** `rg delete_removed_entities` shows only: (a) the manifest import endpoint signature, (b) `bifrost sync` TUI call site, (c) `bifrost import` call site (Task 15), (d) tests. No watch references, no tactical-workaround comments.

**Depends on:** Task 8.

**Commit:** `chore(watch): remove tactical delete_removed_entities workaround comments`

---

### Task 13: Extend `/api/files/manifest/import` with cross-env rebinding

The existing `POST /api/files/manifest/import` (`api/src/routers/files.py:427`) already does the heavy lifting for import: accepts a manifest bundle, writes to S3, calls `manifest_import.import_manifest_from_repo`, commits in one transaction, returns a diff. It **preserves UUIDs** via the `_resolve_*` upsert-by-UUID pattern in `manifest_import.py`, which sidesteps the "UUID-on-create gap" that would otherwise block import. Building `bifrost import` requires extending it with two cross-environment rebinding features.

**Behavior:**

- New optional param `target_organization_id: UUID | None` on `ManifestImportRequest`. When set, every entity in the bundle has its `organization_id` rewritten to this value before upsert. Applies to: forms, agents, workflows, apps, integrations, configs, tables, event sources, integration mappings. Does NOT apply to organizations themselves (a bundle shouldn't claim to create orgs in a target environment; surface an error if the bundle carries `organizations` and the user didn't pass `--skip-orgs`).
- New optional param `role_resolution: Literal["uuid", "name"] = "uuid"`. When `"name"`, roles in the bundle carry `role_names` instead of `role_ids`; importer resolves each name to a UUID in the target environment. Missing role names fail loud with "unknown role: X — create it first." When `"uuid"` (today's behavior), assumes role UUIDs match the target.
- `organizations` section of the manifest is rejected when `target_organization_id` is set (can't do both). Error clearly states the user should either drop the orgs section or not pass the target.

**Files:**
- Modify: `api/src/routers/files.py` — extend `ManifestImportRequest` with the two new optional fields.
- Modify: `api/src/services/manifest_import.py`:
  - Thread `target_organization_id` through `import_manifest_from_repo` → the per-entity `_resolve_*` methods. Each `_resolve_*` that reads `entity.organization_id` takes the override when present.
  - Add a role-name resolver that reads from the bundle's manifest shape (when `role_resolution="name"`) and looks up by name in the target.
- Modify: `api/tests/e2e/platform/test_manifest_import.py` (or create):
  - Bundle with explicit org A, target org B → entities land under B.
  - Bundle with role names, target env with matching roles → resolved correctly.
  - Bundle with role name that doesn't exist in target → loud error, no partial writes.
  - Bundle carrying orgs + `target_organization_id` → rejected.
  - Idempotency: import twice into the same target → second run is a no-op / updates in place.

**Verification:** New E2E tests pass. Existing `bifrost sync` TUI still works (no-op changes from its perspective — both new fields default to preserving today's behavior).

**Commit:** `feat(manifest-import): support target_organization_id and role-by-name resolution`

---

### Task 14: `bifrost export --portable` — scrubbed workspace bundle

Produces a portable bundle suitable for community sharing or cross-environment moves. CLI-side scrub of the manifest pulled from `GET /api/files/manifest`.

**Behavior:**

- `bifrost export --portable <out-dir>`:
  1. Fetches the manifest from `/api/files/manifest`.
  2. Scrubs identifying fields:
     - **Strip:** `organization_id` from every entity. `user_id`, `created_by`, `updated_by`, timestamps. OAuth `client_secret`, `oauth_token_id`, `access_token`. Config `value` for secret-type configs (replaced with null; comment preserved). `external_id`, `expires_at`, `state` on event sources (adapter-managed runtime state).
     - **Rewrite:** `role_ids` on forms/agents/apps → `role_names` by looking up roles by ID (requires list roles from source env).
     - **Keep:** workflow `path::func` refs (already portable). UUIDs on entities themselves (for round-trip / re-import into the same env).
  3. Copies workflow `.py` files and app TSX/package.json files from the workspace into `<out-dir>/workflows/` and `<out-dir>/apps/` (the bundle is a full workspace export, not just `.bifrost/`).
  4. Writes scrubbed manifest to `<out-dir>/.bifrost/`.
  5. Writes a `bundle.meta.yaml` with: source-env hostname, export timestamp, bifrost version, scrubbed-field summary.

- Without `--portable`, `bifrost export <out-dir>` writes the same as `bifrost pull` — full fidelity including org IDs and timestamps.

**Files:**
- Create: `api/bifrost/commands/export.py`.
- Create: `api/bifrost/portable.py` — the scrubbing rules as a single module used by `export` (and later as test fixtures for `import`). Pure function: `scrub(manifest_dict) -> manifest_dict`.
- Create: `api/tests/unit/test_portable_scrub.py` — asserts each scrub rule, round-trips through `import` (with Task 13's changes), detects any field that slipped through.
- Create: `api/tests/e2e/platform/test_cli_export.py` — E2E produces a bundle, inspects the written files.

**Verification:** `bifrost export --portable /tmp/bundle` produces a bundle with no org UUIDs, no secrets, no timestamps. `rg -i 'organization_id|access_token|client_secret' /tmp/bundle` returns nothing. `bundle.meta.yaml` enumerates what was scrubbed.

**Depends on:** Task 1 (resolve_ref for role lookup), Task 13 (round-trip test imports the bundle).

**Commit:** `feat(cli): add bifrost export --portable with field scrubbing for cross-env sharing`

---

### Task 15: `bifrost import` — apply a bundle to the current environment

Thin CLI wrapper over `POST /api/files/manifest/import` that posts a bundle dir.

**Behavior:**

- `bifrost import <bundle-dir> --org <target-uuid> [--role-mode name|uuid] [--dry-run] [--delete-removed]`:
  1. Validates the bundle: reads `bundle.meta.yaml` if present (version compatibility check), enumerates `.bifrost/*.yaml` files.
  2. Uploads workflow `.py` and app source files via existing per-file write endpoints first (so references resolve).
  3. POSTs the `.bifrost/` contents to `/api/files/manifest/import` with:
     - `target_organization_id = <target-uuid>` (required for portable bundles; optional if the bundle already carries org IDs that match the target).
     - `role_resolution = --role-mode` (default `"name"` — portable bundles use names).
     - `dry_run = --dry-run`.
     - `delete_removed_entities = --delete-removed` (default False; user opts in explicitly).
  4. Prints the server's response diff: entities added, updated, deleted, warnings.
- If the server returns an error (unknown role, FK violation on target org, etc.), exit 1 with the server's error body.

**Files:**
- Create: `api/bifrost/commands/import_cmd.py` (avoid `import.py` — Python keyword collision).
- Create: `api/tests/e2e/platform/test_cli_import.py` — exports a bundle, creates a target org in a fresh env, imports into it, verifies entity presence and correct org binding.

**Verification:** End-to-end: export from env A with `--portable`, import into env B with `--org <B-org-uuid> --role-mode name`, confirm all entities land correctly under org B with roles resolved by name. `--dry-run` shows what would change without writing.

**Depends on:** Tasks 1, 13, 14.

**Commit:** `feat(cli): add bifrost import for applying portable bundles to the current environment`

---

## Risks and Open Questions

1. **Configs `set` vs `create`/`update` naming** (catalog open Q #2). Decision deferred to Task 5h. Leaning `set` as upsert alias; confirm during implementation.
2. **Workflow role diff partial-failure handling** (catalog open Q #3). Decision deferred to Task 5c. Leaning "accept partial failure, print table, exit 1."
3. **Agent granular-endpoint deprecation requires UI audit** (Task 7). If UI still uses those endpoints, server removal is blocked behind a UI migration plan. That plan is a follow-up, not a blocker for anything else in this one.
4. **`.bifrost/` old-shape rollout.** Back-compat in Task 9 tolerates separate `.agent.yaml` / `.form.yaml` files with a warning. Old CLIs will still emit them; new CLIs stop. During the rollout window both shapes are in the wild. The back-compat branch should be removed in a follow-up once all active workspaces have been regenerated via `bifrost sync`.
5. **Field-parity test becomes noisy.** When someone adds a DTO field, the test fails. That's the point, but make sure the failure message is crystal clear about the two choices (expose as flag/tool OR add to exclude list with reason).
6. **Existing MCP tool drift deferred.** A drift audit during plan design found that existing MCP tools for agents, forms, and tables re-implement router logic and have diverged materially: different permission models (MCP allows org users where router requires Superuser for forms/tables), missing side effects (no `RepoSyncWriter` dual-write, no role-to-workflow sync, no cache invalidation), weaker validation (warns on invalid refs instead of 422), and different `created_by` semantics (email vs. user_id UUID). Reconciling these is a behavior-migration project with product decisions, not a refactor — so it's deferred to a follow-up plan (`docs/plans/2026-04-18-mcp-router-reconciliation.md`, filed during Task 6). New MCP tools in Task 6 are thin wrappers to avoid adding to the drift.
7. **UUID-on-create gap remains.** Documented in the catalog. Blocks a future `bifrost import` but is out of scope here.
8. **Auth scope 403s.** Dedicated commands surface 403s with the required role named, but this depends on the server's error-body shape. Spot-check during Tasks 5a–5j that the shape is actually consumable.

---

## Explicitly out of scope

- `run`/`validate`/`publish` dev-loop CLI commands — already exist or are dev-loop, separate scope.
- Knowledge-search and code-editor MCP tools — MCP-only by design, no CLI parity needed.
- `bifrost sync` / `bifrost pull` TUI changes — they keep working as today; `.bifrost/` is still written for export.
- Reconciliation of existing MCP tools (agents/forms/tables/apps/events) with router business logic — deferred to a follow-up plan filed during Task 6 (`docs/plans/2026-04-18-mcp-router-reconciliation.md`).

---

## Critical Files for Implementation

- `/home/jack/GitHub/bifrost/docs/plans/2026-04-18-cli-mutation-surface.md` — the command catalog that's this plan's spec.
- `/home/jack/GitHub/bifrost/docs/plans/2026-04-16-manifest-compat-audit.md` — audit of verb corrections and UUID-on-create gaps.
- `/home/jack/GitHub/bifrost/api/bifrost/refs.py` — **new**: `resolve_ref`, `AmbiguousRefError`, `RefNotFoundError`.
- `/home/jack/GitHub/bifrost/api/bifrost/dto_flags.py` — **new**: `build_cli_flags`, `build_mcp_schema`, `assemble_body`, exclude/rename registries.
- `/home/jack/GitHub/bifrost/api/bifrost/commands/` — **new package**: one file per entity type plus `base.py`.
- `/home/jack/GitHub/bifrost/api/bifrost/cli.py` — subgroup wiring for new commands; removal of bulk-manifest push path in `_process_watch_batch`.
- `/home/jack/GitHub/bifrost/api/bifrost/manifest.py` — `ManifestAgent` / `ManifestForm` gain full content fields.
- `/home/jack/GitHub/bifrost/api/src/services/manifest_generator.py` — inline content serialization.
- `/home/jack/GitHub/bifrost/api/src/services/github_sync.py` — inline content import + separate-file back-compat warning.
- `/home/jack/GitHub/bifrost/api/src/models/contracts/tables.py` — `TableUpdate` extended with `name` + `application_id`.
- `/home/jack/GitHub/bifrost/api/src/routers/tables.py` — handler applies the new optional fields.
- `/home/jack/GitHub/bifrost/api/src/routers/agents.py` — deprecation candidate for granular tool/delegation endpoints (subject to UI audit).
- `/home/jack/GitHub/bifrost/CLAUDE.md` — DTO-change checklist + codebase-reference-search rule.
- `/home/jack/GitHub/bifrost/docs/llm.txt` — documentation for the new CLI commands and MCP tools.
- `/home/jack/GitHub/bifrost/api/src/routers/files.py` — `/api/files/manifest/import` extended with `target_organization_id` + `role_resolution` params (Task 13).
- `/home/jack/GitHub/bifrost/api/src/services/manifest_import.py` — threads target-org override through `_resolve_*` methods; adds role-by-name resolution (Task 13).
- `/home/jack/GitHub/bifrost/api/bifrost/portable.py` — **new**: scrubbing rules for `bifrost export --portable` (Task 14).
- `/home/jack/GitHub/bifrost/api/bifrost/commands/export.py` — **new**: `bifrost export` command (Task 14).
- `/home/jack/GitHub/bifrost/api/bifrost/commands/import_cmd.py` — **new**: `bifrost import` command (Task 15).
