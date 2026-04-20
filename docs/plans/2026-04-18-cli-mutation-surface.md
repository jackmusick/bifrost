# CLI Mutation Surface — Catalog & Recommendations

**Date:** 2026-04-18
**Status:** Decision artifact — research only
**Related:** `2026-04-16-manifest-in-memory-gatekeeper.md`, `2026-04-16-manifest-compat-audit.md`

## Purpose

This document catalogs every entity-mutation operation that `.bifrost/*.yaml` files previously round-tripped, and — now that `.bifrost/` is becoming export-only — recommends per-operation whether the Bifrost CLI needs a dedicated subcommand or can rely on the existing `bifrost api <METHOD> <path> [json-body]` passthrough (`api/bifrost/cli.py:3942`).

The decision this artifact supports: **which mutations get first-class CLI UX, and which fall back to generic REST passthrough?** Organizations and roles are fundamental to the multi-tenant dev workflow (bifrost-build asks for them first), so they get prioritized UX even though their REST surface is simple.

**Explicitly out of scope:** implementation details for any command; the eventual `bifrost export --portable` scrubbing design; retirement of `.bifrost/` from watch mode (covered by the gatekeeper plan); any server-side endpoint changes.

**Ground rules:**
- Where the gatekeeper plan's mapping table (`2026-04-16-manifest-in-memory-gatekeeper.md:316–331`) disagrees with the compat audit (`2026-04-16-manifest-compat-audit.md`), the **audit wins**. Verb corrections are applied silently below.
- Every POST covered here **server-assigns UUIDs** — no entity accepts client-supplied `id` in its Create DTO (audit confirmed uniformly). The "UUID-on-create?" column reflects this.
- Every mutation goes against `RepoStorage`-backed routers, which means `bifrost api` already speaks to them correctly once auth is attached.

Dedicated-vs-generic heuristic:

- **Dedicated** when *any* of: portable-ref → UUID lookup needed; multi-step orchestration (e.g. create + deps in one UX); non-trivial JSON body that would force hand-crafted payloads; it's a first-touch command for a new dev (org/role); or the endpoint has non-obvious ergonomics the audit flagged (verb corrections, renamed fields).
- **Generic `bifrost api`** sufficient when the endpoint is flat REST, rarely run by hand, and needs no translation.

---

## 1. Organizations

**Manifest model:** `ManifestOrganization` (`api/bifrost/manifest.py:48`).
**Router:** `api/src/routers/organizations.py`. DTOs at `api/src/models/contracts/organizations.py:81` and `86`.
**Audit rating:** Yellow (server-assigned UUID only; DTO is a superset of manifest fields).

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/organizations` | — | — | **Dedicated (`bifrost orgs list`)** | First thing a new dev needs to see to scope everything else. Low-cost ergonomic win. |
| Create | `POST /api/organizations` (`organizations.py:61`) | `name, domain, is_active, is_provider, settings` | **No** — server generates | **Dedicated (`bifrost orgs create`)** | First-touch: "I need to set up a dev org before anything works." Hand-writing JSON here is unergonomic. |
| Update | `PATCH /api/organizations/{org_id}` (`organizations.py:137`) | Subset of `OrganizationUpdate` | N/A | **Dedicated (`bifrost orgs update`)** | Consistency with create/delete; PATCH-by-uuid is awkward via `api` when devs normally refer to orgs by slug/name. |
| Delete | `DELETE /api/organizations/{org_id}` (`organizations.py:199`) | — | N/A | **Dedicated (`bifrost orgs delete`)** | Needs name→UUID resolution. |

**Notes.** UI-managed fields (`domain`, `settings`, `is_provider`) should not be wiped by PATCH; dedicated command should default-omit them and only send `--name`/`--is-active`/`--domain` when the user explicitly passes the flag.

---

## 2. Roles

**Manifest model:** `ManifestRole` (`api/bifrost/manifest.py:55`).
**Router:** `api/src/routers/roles.py`. DTOs at `api/src/models/contracts/users.py:165`, `173`.
**Audit rating:** Yellow (same pattern as orgs).

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/roles` (`roles.py:69`) | — | — | **Dedicated (`bifrost roles list`)** | Paired with org listing — devs look these up when scoping workflow/form visibility. |
| Create | `POST /api/roles` (`roles.py:86`) | `name, description, permissions` | **No** | **Dedicated (`bifrost roles create`)** | First-touch command. Permissions-list should accept repeatable `--permission` flag for readability. |
| Update | `PATCH /api/roles/{role_id}` (`roles.py:154`) | `name, description, permissions` | N/A | **Dedicated (`bifrost roles update`)** | Consistency; name-resolution helper. |
| Delete | `DELETE /api/roles/{role_id}` (`roles.py:225`) | — | N/A | **Dedicated (`bifrost roles delete`)** | Name→UUID resolution. |

**Notes.** Legacy `PUT /api/roles/{role_id}` at `roles.py:208` is `include_in_schema=False` — do not use. Role *assignments* to workflows/forms/agents/apps are handled per those entities (see below).

---

## 3. Workflows (metadata only — code stays file-synced)

**Manifest model:** `ManifestWorkflow` (`api/bifrost/manifest.py:61`).
**Router:** `api/src/routers/workflows.py`. DTO `WorkflowUpdateRequest` at `api/src/models/contracts/workflows.py:261`.
**Audit rating:** Yellow. `name`, `function_name`, `path`, `type` are code-derived (not writable); all other manifest fields map to PATCH.

Workflows themselves are created by file discovery (`POST /api/workflows/register` at `workflows.py:937`) triggered by writing the `.py` through the normal file-sync path — **the CLI does not mint new workflows via an entity mutation**. The mutations cataloged here are metadata only.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/workflows` (`workflows.py:316`) | — | — | **Dedicated (`bifrost workflows list`)** | Consistent with other entities; cheap UX win. |
| Register | `POST /api/workflows/register` (`workflows.py:937`) | `path, function_name, organization_id` | N/A | **Dedicated (`bifrost workflows register`)** | Explicit registration of an existing `.py` file — useful after `git pull` or when watch isn't running. Name matches server intent. |
| Update | `PATCH /api/workflows/{id}` (`workflows.py:1073`) | `organization_id, access_level, description, category, timeout_seconds, endpoint_enabled, public_endpoint, tags` (plus UI-only fields the CLI must **not** send) | N/A | **Dedicated (`bifrost workflows update`)** | DTO has 17+ fields; CLI should expose the YAML-era subset and omit UI-managed ones by default. Also needs workflow-name→UUID lookup (devs don't memorize UUIDs). |
| Delete | `DELETE /api/workflows/{id}` (`workflows.py:1723`) | — | N/A | **Dedicated (`bifrost workflows delete`)** | Consistent with other entities; name resolution helper. |
| Add role | `POST /api/workflows/{id}/roles` (`workflows.py:1620`) | `role_id` (one per call) | N/A | **Dedicated (`bifrost workflows grant-role`)** | **Audit finding:** no replace-set endpoint exists. Watcher had to do "add new, delete stale" client-side. A dedicated command hides that diff. |
| Remove role | `DELETE /api/workflows/{id}/roles/{role_id}` (`workflows.py:1689`) | — | N/A | **Dedicated (`bifrost workflows revoke-role`)** | Same as above; also benefits from role-name lookup. |

**Notes.** Code-derived fields (`name`, `function_name`, `path`, `type`) are immutable post-registration and the CLI must refuse to accept them as mutation flags.

---

## 4. Forms (full content — now inline in the manifest)

**Manifest model:** `ManifestForm` (`api/bifrost/manifest.py:79`).
**Router:** `api/src/routers/forms.py`. DTOs `FormCreate` / `FormUpdate` at `api/src/models/contracts/forms.py:218`, `232`.
**Audit rating:** Yellow. The design decision puts form **content** (schema, workflow_id, etc.) inline under its UUID; the old `.bifrost/forms.yaml` + `forms/{uuid}.form.yaml` split goes away.

Because content now lives in the manifest (inline), the CLI has to be able to create/update forms with their full body — not the partial metadata-only shape the watcher used.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/forms` (`forms.py:208`) | — | — | **Generic** | Rarely run by hand. |
| Create | `POST /api/forms` (`forms.py:283`) | `name, description, workflow_id, launch_workflow_id, default_launch_params, allowed_query_params, form_schema, access_level, organization_id` | **No** | **Dedicated (`bifrost forms create`)** | `workflow_id` needs portable-ref → UUID lookup (users refer to workflows by `path::func` or name). `form_schema` is a nested object users don't want to hand-type as JSON — accept it via `--schema @schema.yaml`. |
| Update | `PATCH /api/forms/{id}` (`forms.py:441`) | Same set + `is_active, clear_roles` | N/A | **Dedicated (`bifrost forms update`)** | Same lookup + body-construction concerns. |
| Delete | `DELETE /api/forms/{id}` (`forms.py:583`) | — | N/A | **Dedicated (`bifrost forms delete`)** | Name-resolution helper. |

**Notes.** Legacy `PUT /api/forms/{id}` at `forms.py:565` is the older write path — do not use. `FormUpdate` has a `clear_roles` flag that the CLI should expose as `--clear-roles`. Role replacement is via the form's `role_ids` field in the Update DTO (replace-by-set), unlike workflows.

---

## 5. Agents (full content — now inline in the manifest)

**Manifest model:** `ManifestAgent` (`api/bifrost/manifest.py:89`).
**Router:** `api/src/routers/agents.py`. DTOs `AgentCreate` / `AgentUpdate` at `api/src/models/contracts/agents.py:37`, `58`.
**Audit rating:** Yellow. **Verb correction from the plan's table:** update is `PUT /api/agents/{id}` (`agents.py:536`), not PATCH. Handler is partial-update-semantic internally.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/agents` (`agents.py:216`) | — | — | **Generic** | Rarely run by hand. |
| Create | `POST /api/agents` (`agents.py:292`) | 14 fields incl. `system_prompt` (required), `channels`, `tool_ids`, `delegated_agent_ids`, `knowledge_sources`, `system_tools`, `llm_model`, `llm_max_tokens`, `max_iterations`, `max_token_budget`, `description`, `name`, `access_level`, `organization_id` | **No** | **Dedicated (`bifrost agents create`)** | `system_prompt` is multi-line (accept `--prompt @prompt.md`). `tool_ids` / `delegated_agent_ids` / `knowledge_sources` all need name→UUID lookup. Non-trivial body. |
| Update | `PUT /api/agents/{id}` (`agents.py:536`) | Same fields as optional + `is_active, clear_roles, role_ids` | N/A | **Dedicated (`bifrost agents update`)** | Same lookup + body concerns. Verb is PUT, not PATCH. |
| Delete | `DELETE /api/agents/{id}` (`agents.py:719`) | — | N/A | **Dedicated (`bifrost agents delete`)** | Name-resolution helper. |
| Promote draft | `POST /api/agents/{id}/promote` (`agents.py:760`) | — | N/A | **Generic** | Rare lifecycle operation, flat endpoint. |
| ~~Add tool (one)~~ | ~~`POST /api/agents/{id}/tools`~~ | — | — | **Deprecate** | Redundant with `PUT /agents/{id}` replace-set. UI can PATCH the full list. Propose removing server-side. |
| ~~Remove tool~~ | ~~`DELETE /api/agents/{id}/tools/{workflow_id}`~~ | — | — | **Deprecate** | Same. |
| ~~Add delegation~~ | ~~`POST /api/agents/{id}/delegations`~~ | — | — | **Deprecate** | Same. |
| ~~Remove delegation~~ | ~~`DELETE /api/agents/{id}/delegations/{delegate_id}`~~ | — | — | **Deprecate** | Same. |

**Notes.** On the Agent Update DTO, tool/delegation/knowledge association lists replace-by-set, which is nicer UX than the workflow's add-one/delete-one pattern. Prefer replace-by-set through the top-level `update` command.

---

## 6. Apps (metadata only + dependencies; TSX source stays file-synced)

**Manifest model:** `ManifestApp` (`api/bifrost/manifest.py:101`).
**Routers:** `api/src/routers/applications.py`; dependencies on `api/src/routers/app_code_files.py`. DTOs `ApplicationCreate` / `ApplicationUpdate` at `api/src/models/contracts/applications.py:38`, `80`.
**Audit rating:** Yellow — but the plan's mapping-table row for apps was materially wrong (used `/draft`, which is the app *definition blob* endpoint, not metadata).

Verb corrections from the audit:
- Metadata update: **`PATCH /api/applications/{id}`** (`applications.py:726`), not `PATCH .../draft`.
- Dependencies: **`PUT /api/applications/{id}/dependencies`** (`app_code_files.py:660`) — body is a flat `dict[str, str]`. Not on `ApplicationUpdate`.
- Field rename: manifest `roles` ↔ DTO `role_ids`.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/applications` | — | — | **Generic** | Rarely hand-run. |
| Create | `POST /api/applications` (`applications.py:621`) | `name, description, icon, slug, access_level, role_ids, organization_id` | **No** | **Dedicated (`bifrost apps create`)** | Roles need name→UUID. If user passes `--deps @package.json` the command must orchestrate `POST` + `PUT /dependencies` atomically (two-call create). |
| Update metadata | `PATCH /api/applications/{id}` (`applications.py:726`) | `name, slug, description, icon, scope, access_level, role_ids` | N/A | **Dedicated (`bifrost apps update`)** | `roles` ↔ `role_ids` rename is easy to get wrong via `api`. |
| Update dependencies | `PUT /api/applications/{id}/dependencies` (`app_code_files.py:660`) | `dict[str, str]` | N/A | **Dedicated (`bifrost apps set-deps`)** | Separate endpoint the generic path can't discover; and hand-crafting the JSON object is clunky for a common operation. |
| Put draft (definition blob) | `PUT /api/applications/{id}/draft` (`applications.py:842`) | Opaque blob | N/A | **Generic** | Fired by the app bundler; not a user-facing mutation. |
| Delete | `DELETE /api/applications/{id}` (`applications.py:781`) | — | N/A | **Dedicated (`bifrost apps delete`)** | Slug-resolution helper. |

**Notes.** `path` on the manifest model has no DTO equivalent — it's derived from `slug` server-side. The CLI must skip `path` on outbound.

---

## 7. Integrations (+ config_schema, mappings, oauth_provider)

**Manifest model:** `ManifestIntegration` (`api/bifrost/manifest.py:152`), plus nested `ManifestIntegrationConfigSchema` (117), `ManifestOAuthProvider` (127), `ManifestIntegrationMapping` (144).
**Router:** `api/src/routers/integrations.py`. DTOs `IntegrationCreate` / `IntegrationUpdate` at `api/src/models/contracts/integrations.py:63`, `97`.
**Audit rating:** **Red.** The nastiest entity in this catalog. Three structural gaps: (a) no public mutation endpoint for `oauth_provider`; (b) `config_schema` FK-cascades through `Config` rows if PUT is destructive; (c) mapping `oauth_token_id` is UI-set and must not be overwritten.

Verb correction: update is **`PUT /api/integrations/{id}`** (`integrations.py:814`), not PATCH.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/integrations` (`integrations.py:682`) | — | — | **Generic** | Rarely hand-run. |
| Create | `POST /api/integrations` (`integrations.py:653`) | `name, config_schema (list), entity_id, entity_id_name, default_entity_id` | **No** | **Dedicated (`bifrost integrations create`)** | `config_schema` is a nested list of typed items users otherwise have to hand-type as JSON. Also the two-call create-with-mappings sequence is non-obvious. |
| Update | `PUT /api/integrations/{id}` (`integrations.py:814`) | Same + `list_entities_data_provider_id` | N/A | **Dedicated (`bifrost integrations update`)** | Same nested-body reason. Verb is PUT, not PATCH. **Verified non-destructive** (`api/src/repositories/integrations.py:228–262`) — upserts `config_schema` by `(integration_id, key)`, preserving FK-linked `Config` rows. Keys *removed* from the list cascade-delete their Config children (`ondelete=CASCADE` on `config.py:53–55`); CLI must warn + require `--force-remove-keys` when the diff contains removals. |
| Delete | `DELETE /api/integrations/{id}` (`integrations.py:840`) | — | N/A | **Generic** | Simple. |
| Add mapping | `POST /api/integrations/{id}/mappings` (`integrations.py:963`) | `organization_id, entity_id, entity_name` (+ optional `oauth_token_id`) | **No** | **Dedicated (`bifrost integrations add-mapping`)** | Org name→UUID lookup; defaulting `oauth_token_id` to null so the UI-flow value isn't accidentally overwritten. |
| Batch upsert mappings | `POST /api/integrations/{id}/mappings/batch` (`integrations.py:1176`) | List of `IntegrationMappingCreate` | **No** | **Generic** | Dropped from CLI surface per user decision — only needed for UI-driven bulk setup. Use `bifrost api` if ever scripted. |
| Update mapping | `PUT /api/integrations/{id}/mappings/{mapping_id}` (`integrations.py:1133`) | Subset of mapping fields | N/A | **Dedicated** (`integrations update-mapping`) | Same UI-field-preservation concerns. |
| Delete mapping | `DELETE /api/integrations/{id}/mappings/{mapping_id}` (`integrations.py:1241`) | — | N/A | **Generic** | Simple. |
| Get OAuth provider | `GET /api/integrations/{id}/oauth` (`integrations.py:1271`) | — | — | — | Read-only. |
| Set OAuth provider | — | — | — | **Out of scope** | User decision: manage OAuth provider config in the UI only. No CLI surface. |

**Notes.** OAuth *connections* (user-authorized tokens) are on a separate router at `api/src/routers/oauth_connections.py` — not in scope for manifest round-trip. `client_secret` is never serialized anywhere.

---

## 8. Configs

**Manifest model:** `ManifestConfig` (`api/bifrost/manifest.py:165`).
**Router:** `api/src/routers/config.py`. DTOs `SetConfigRequest` / `UpdateConfigRequest` at `api/src/models/contracts/config.py:40`, `49`.
**Audit rating:** **Red for integration-owned configs, Yellow for standalone.** DTOs have no `integration_id` field — integration-owned configs cannot round-trip their FK through the public surface. Verb correction: update is `PUT /api/config/{id}` (`config.py:379`), not PATCH.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/config` (`config.py:299`) | — | — | **Generic** | Rare hand-run. |
| Create (standalone) | `POST /api/config` (`config.py:333`) | `key, value, type, description, organization_id` | **No** | **Dedicated (`bifrost configs create`)** | `config_type` → `type` rename, value JSONB envelope (server wraps as `{"value": ...}`), secret handling (omit `value` to preserve existing). `--type secret` is supported. |
| Update | `PUT /api/config/{id}` (`config.py:379`) | Same as optional | N/A | **Dedicated (`bifrost configs update`)** | Same rename/envelope concerns; omit-value-to-preserve semantic is non-obvious. |
| Delete | `DELETE /api/config/{id}` (`config.py:419`) | — | N/A | **Dedicated (`bifrost configs delete`)** | Consistent with other entities. Require `--confirm` when deleting a secret-type config to guard against accidental key loss. |
| Integration-owned config linkage | — | Server-internal | — | **By design — no CLI** | `integration_id` / `config_schema_id` are set implicitly when the integration's `config_schema` cascades. Users set *values* for existing slots via standalone `configs update`. The CLI should never expose the linkage directly. |

**Notes.** `_resolve_config` (`api/src/services/manifest_import.py:1604`) treats secret-type configs specially: omitting `value` preserves the existing value. The dedicated `configs set` command must expose `--value` as optional with clear docs.

---

## 9. Tables

**Manifest model:** `ManifestTable` (`api/bifrost/manifest.py:176`).
**Router:** `api/src/routers/tables.py`. DTOs `TableCreate` / `TableUpdate` at `api/src/models/contracts/tables.py:39`, `48`.
**Audit rating:** **Red.** `TableUpdate` lacks `name` and `application_id` — rename and app-reassignment are unsupported by the public surface.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List | `GET /api/tables` (`tables.py:246`) | — | — | **Generic** | Rare hand-run. |
| Create | `POST /api/tables` (`tables.py:460`) | `name, description, schema, organization_id` | **No** | **Dedicated (`bifrost tables create`)** | `schema` is a nested alias-using dict (`ManifestTable.table_schema` serializes as `schema`); users want to pass it via `--schema @schema.yaml`. |
| Update | `PATCH /api/tables/{id}` (`tables.py:547`) | `description, schema` (+ `name`, `application_id` after server change) | N/A | **Dedicated (`bifrost tables update`)** | Per user decision, `TableUpdate` will be extended server-side to accept `name` and `application_id`. Rename is supported but risky — llm.txt must require a codebase-wide reference search before renaming a table. |
| Delete | `DELETE /api/tables/{id}` (`tables.py:571`) | — | N/A | **Dedicated (`bifrost tables delete`)** | Consistent with other entities; name resolution helper. |

---

## 10. Events (sources + subscriptions)

**Manifest models:** `ManifestEventSource` (`api/bifrost/manifest.py:204`), `ManifestEventSubscription` (192).
**Router:** `api/src/routers/events.py`. DTOs at `api/src/models/contracts/events.py:84, 116, 151, 184`.
**Audit rating:** **Red.** Four problems: flat-vs-nested body translation (`cron_expression`, `timezone`, `schedule_enabled` flatten onto manifest but nest under `schedule:` in the DTO — similarly for webhook fields); no UUID-on-create; `target_type`/`workflow_id`/`agent_id` unchangeable via subscription PATCH (force delete+recreate); subscription refs use portable workflow refs that need client-side resolution.

| Operation | HTTP verb + path | Fields involved | UUID-on-create? | Dedicated CLI recommended? | Rationale |
|---|---|---|---|---|---|
| List sources | `GET /api/events/sources` (`events.py:269`) | — | — | **Generic** | Rare hand-run. |
| Create source | `POST /api/events/sources` (`events.py:341`) | `name, source_type, organization_id, webhook (nested), schedule (nested)` | **No** | **Dedicated (`bifrost events create-source`)** | Flat-to-nested translation: users shouldn't have to hand-build `{"schedule": {"enabled": true, "cron_expression": ...}}`. Accept flat `--cron`, `--timezone`, `--adapter` flags. |
| Update source | `PATCH /api/events/sources/{id}` (`events.py:500`) | Same nested shape | N/A | **Dedicated (`bifrost events update-source`)** | Same flat-to-nested concern. |
| Delete source | `DELETE /api/events/sources/{id}` (`events.py:581`) | — | N/A | **Generic** | Simple. |
| List subscriptions | `GET /api/events/sources/{id}/subscriptions` (`events.py:634`) | — | — | **Generic** | Rare hand-run. |
| Create subscription | `POST /api/events/sources/{id}/subscriptions` (`events.py:670`) | `target_type, workflow_id, agent_id, event_type, filter_expression, input_mapping` | **No** | **Dedicated (`bifrost events subscribe`)** | Portable-ref → UUID resolution (`workflow_id` can be `path::func` or name in user input). `input_mapping` is a JSON dict that benefits from `@file` loading. |
| Update subscription | `PATCH /api/events/sources/{id}/subscriptions/{sub_id}` (`events.py:738`) | `event_type, filter_expression, is_active, input_mapping` only | N/A | **Dedicated (`bifrost events update-subscription`)** | Clear error if user tries to change target (not allowed via PATCH); prompt them to delete+recreate. |
| Delete subscription | `DELETE /api/events/sources/{id}/subscriptions/{sub_id}` (`events.py:799`) | — | N/A | **Generic** | Simple. |

**Notes.** External webhook state (`external_id`, `expires_at`, `state`) is adapter-managed and never round-trips. Scheduled sources' enable/disable toggle lives in `schedule.enabled`, not on the source itself (audit line 212).

---

## Summary

### Counts (post-decisions)

Across 10 entity types, **47 operations** cataloged:
- **28 dedicated** — first-class `bifrost` subcommands.
- **15 generic** — use `bifrost api` passthrough.
- **4 deprecate** — redundant agent tool/delegation granular endpoints; propose server-side removal.
- **2 out-of-scope / by-design** — integration OAuth provider (UI-only) and integration-owned config linkage (server-internal).
- **1 server change required** — `TableUpdate` DTO extended to accept `name` + `application_id`.

### Proposed CLI signatures (dedicated operations only)

```
# Tenancy & access (first-touch)
bifrost orgs list
bifrost orgs create <name> [--domain ...] [--is-active]
bifrost orgs update <name|uuid> [--name ...] [--is-active ...]
bifrost orgs delete <name|uuid>

bifrost roles list
bifrost roles create <name> [--description ...] [--permission ... (repeatable)]
bifrost roles update <name|uuid> [...]
bifrost roles delete <name|uuid>

# Workflows (code is file-synced; these handle metadata + lifecycle)
bifrost workflows list
bifrost workflows register <path> [--function <name>] [--org <ref>]
bifrost workflows update <name|path::func> [--access-level ...] [--roles ...]
                                           [--endpoint-enabled] [--public-endpoint]
                                           [--timeout-seconds ...] [--description ...]
                                           [--category ...] [--tag ... (repeatable)]
bifrost workflows delete <name|path::func>
bifrost workflows grant-role <workflow> <role>
bifrost workflows revoke-role <workflow> <role>

# Forms (inline content)
bifrost forms create <name> --workflow <ref> --schema @file.yaml
                             [--launch-workflow <ref>] [--roles ...] [--org ...]
                             [--access-level ...]
bifrost forms update <name|uuid> [...] [--clear-roles]
bifrost forms delete <name|uuid>

# Agents (inline content)
bifrost agents create <name> --prompt @file.md --model <id>
                             [--tools <ref,...>] [--delegates <ref,...>]
                             [--knowledge <ref,...>] [--channels ...]
                             [--max-iterations N] [--max-tokens N]
                             [--roles ...] [--org ...]
bifrost agents update <name|uuid> [...] [--clear-roles]
bifrost agents delete <name|uuid>

# Apps (metadata + deps; TSX is file-synced)
bifrost apps create <name> [--slug ...] [--description ...] [--icon ...]
                           [--roles ...] [--org ...] [--deps @package.json]
bifrost apps update <slug|uuid> [...]
bifrost apps set-deps <slug|uuid> @package.json
bifrost apps delete <slug|uuid>

# Integrations (+ mappings)
bifrost integrations create <name> --config-schema @schema.yaml [...]
bifrost integrations update <name|uuid> [--config-schema @schema.yaml]
                                         [--force-remove-keys] [...]
bifrost integrations add-mapping <integ> --org <ref> --entity-id <ext>
                                          [--entity-name ...]
bifrost integrations update-mapping <integ> <mapping-id> [...]

# Configs
bifrost configs list
bifrost configs create <key> --value <v> [--type ...] [--org ...] [--description ...]
bifrost configs update <key> [--value <v>] [--type ...] [--description ...]
bifrost configs delete <key> [--confirm]     # --confirm required for secret-type

# Tables (requires server change: TableUpdate extended with name + application_id)
bifrost tables list
bifrost tables create <name> --schema @schema.yaml [--org ...]
bifrost tables update <name|uuid> [--name ...] [--application <ref>]
                                   [--description ...] [--schema @schema.yaml]
bifrost tables delete <name|uuid>

# Events
bifrost events create-source <name> --type <webhook|schedule|internal>
                                    [--cron ...] [--timezone ...] [--adapter ...]
                                    [--webhook-integration <ref>] [--org ...]
bifrost events update-source <name|uuid> [...]
bifrost events subscribe <source> --workflow <ref> [--agent <ref>]
                                  [--event-type ...] [--filter ...]
                                  [--input-mapping @file.yaml]
bifrost events update-subscription <source> <sub-id> [...]
```

Everything not listed falls back to `bifrost api <VERB> <path> [body]`.

### Cross-cutting concerns

1. **CLI flags generated from DTOs.** The biggest risk in this proposal is drift: the CLI catalogs fields the DTO has, and if the DTO grows new ones, the CLI silently misses them. **Strategy:** generate Click/argparse flag definitions from `XxxCreate` / `XxxUpdate` Pydantic models at CLI import time. A test per command asserts "every writable field on the DTO is either a flag, explicitly excluded with a reason, or the test fails." Combined with a CLAUDE.md note (see below), this keeps the surface in sync without manual upkeep.

2. **CLAUDE.md addition — API and manifest updates.** When changing a DTO, the author must:
    - Regenerate CLI flags (or run the field-parity test to confirm coverage).
    - Update `api/bifrost/manifest.py` if the field should round-trip in exports.
    - Update `docs/llm.txt` if the operation is one Claude should know about.
    - For **rename/reassign** operations on tables, workflows, or configs: grep the codebase for references by name before committing. These entities can be referenced by name in workflow `.py` files and user-authored forms; renames silently break those references. The CLI will warn when it detects a rename is in progress, but the author is responsible for the codebase search.

3. **Portable-ref → UUID resolution.** Multiple commands need a helper that takes `(kind, value, org=...)` and returns UUID — resolving UUID / `path::func` / name with org-scoping to disambiguate. **Recommendation:** single `resolve_ref(kind, value, *, org=None)` helper with per-invocation cache. Raises on ambiguity, prompting user to pass `--org` or full UUID. Matches `_resolve_workflow_ref` in `api/src/services/manifest_import.py:1093` semantically but client-side.

4. **UI-managed field preservation.** Entities have fields set by UI flows that the CLI must default to *not* sending: org `settings`/`is_provider`; mapping `oauth_token_id`; integration `oauth_provider.client_id` when `__NEEDS_SETUP__`; workflow `display_name`/`tool_description` (agent-tuning fields); app `icon`; config secret `value`. Every dedicated `update` command should adopt the pattern: only send a field when the user explicitly passes the corresponding flag. The generated-from-DTO approach in (1) preserves this naturally because unset flags = `None` = "don't send."

5. **Explicit `--org` flag on every dedicated command.** Always a first-class flag, never just a JSON body field. Required by `resolve_ref` for disambiguation; also the most common user intent.

6. **Server-side endpoint deprecations.** Propose removing (subject to UI compatibility check):
    - `POST /api/agents/{id}/tools` + `DELETE /api/agents/{id}/tools/{workflow_id}`
    - `POST /api/agents/{id}/delegations` + `DELETE /api/agents/{id}/delegations/{delegate_id}`
   All four are redundant with `PUT /agents/{id}` replace-set. UI can PATCH the full list. Radical-simplification win.

7. **Server-side endpoint additions (required).** `TableUpdate` DTO must be extended with optional `name` and `application_id` fields. `update_table` handler already has capacity; just DTO+handler changes. Workflow roles *could* get a replace-set endpoint (`PUT /api/workflows/{id}/roles`) to match other entities, but not strictly required — CLI can diff client-side for now.

8. **UUID-on-create gap.** *No* Create DTO accepts a client-supplied `id`. The server generates UUIDs via `uuid4()` or the ORM default. This isn't a blocker for `create` commands (they work, the server just picks the UUID), but any future `bifrost import` that needs stable UUIDs across environments would need server changes. Flagged here for awareness; not part of this plan's scope.

9. **Auth scope.** Some mutations are superuser-gated (org create/delete, role CRUD). Dedicated commands must surface 403s cleanly with the required role/permission named in the error.

10. **Name-vs-UUID UX.** Every `update` / `delete` / sub-resource command accepts a user-friendly ref (name, slug, `path::func`). Devs don't memorize UUIDs. This is the core reason dedicated commands beat `bifrost api` for any operation that refers to an entity by ID.

### Open questions / loose ends

1. **Is the UI still using the deprecated agent granular endpoints?** Before server-side removal lands, audit frontend calls to `POST/DELETE /api/agents/{id}/tools` and `.../delegations`. If yes, migrate UI to the replace-set PUT first.

2. **Configs `create` vs `update` distinction.** The server endpoint for create (`POST /api/config`) is a full-body create, but for convenience the CLI might want a single `bifrost configs set <key>` that acts as upsert (looks up existing key+org, calls PUT if found, POST if not). **Recommendation:** keep `create`/`update` separate per the entity-consistency principle, but add a `bifrost configs set` alias that does the upsert for ergonomics. Decide during implementation.

3. **Workflow role diff implementation.** CLI does `--roles a,b,c` → diff existing → N POSTs + M DELETEs in parallel. Failure mode: partial application (3 roles added, 1 delete failed) leaves inconsistent state. Either (a) accept it and print failed ops, (b) add server replace-set endpoint, (c) wrap in a single POST on a new replace endpoint. Lowest-effort: (a). Cleanest: (b).
