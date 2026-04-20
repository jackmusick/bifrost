# Manifest ↔ REST DTO Compatibility Audit

**Date:** 2026-04-18
**For:** `docs/plans/2026-04-16-manifest-in-memory-gatekeeper.md` (Task 0 — Decision Gate)
**Scope:** Research only. No code changes, no commits.

## Purpose

The gatekeeper plan replaces bulk manifest import (`POST /api/files/manifest/import` → `_resolve_*` methods in `api/src/services/manifest_import.py`) with **per-entity REST calls** against existing routers. This audit verifies each `ManifestXxx` Pydantic model in `api/bifrost/manifest.py` can be round-tripped via the corresponding `POST` / `PATCH|PUT` / `DELETE` endpoints and `XxxCreate` / `XxxUpdate` DTOs in `api/src/models/contracts/`.

Each entity is rated **Green / Yellow / Red**. The bottom-line recommendation is at the end.

### Corrections to the plan's mapping table (plan lines 316–331)

Verified directly against router source. **The plan is wrong on several rows:**

| Entity | Plan says | Actual |
|---|---|---|
| integrations update | `PATCH /api/integrations/{id}` | **`PUT /api/integrations/{id}`** (`integrations.py:814`) |
| configs update | `PATCH /api/config/{id}` | **`PUT /api/config/{id}`** (`config.py:379`) |
| agents update | `PATCH /api/agents/{id}` | **`PUT /api/agents/{id}`** (`agents.py:536`) |
| apps update | `PATCH /api/applications/{id}/draft` | **`PATCH /api/applications/{id}`** for metadata (`applications.py:726`); `PUT /api/applications/{id}/draft` is for the app **definition blob**, not metadata. Dependencies are a separate `PUT /api/applications/{app_id}/dependencies` (`app_code_files.py:660`). |
| workflows add | "N/A — file-based" | Correct (`POST /api/workflows/register` exists, but creation still hinges on the `.py` file). |

The watcher's routing table needs the correct verbs or the client calls will 405.

---

## Per-Entity Audit

### 1. Organizations

**Manifest:** `ManifestOrganization` (`api/bifrost/manifest.py:48`) — `id, name, is_active`.
**DTOs:** `OrganizationCreate` (`organizations.py:81`) — `name, domain, is_active, is_provider, settings`. `OrganizationUpdate` (`organizations.py:86`) — `name, domain, is_active, settings`.
**Endpoints:** `POST /api/organizations` (`organizations.py:61`), `PATCH /api/organizations/{org_id}` (`organizations.py:137`), `DELETE /api/organizations/{org_id}` (`organizations.py:199`).

| Q | Answer |
|---|---|
| Field parity | Manifest subset of DTO. DTO extras (`domain`, `is_provider`, `settings`) are omitted from YAML and round-trip unchanged through PATCH because PATCH only applies set fields. No manifest-only fields. **Green on parity.** |
| Aliases/casing | None. |
| Nested entities | None. |
| UI-managed fields | `domain`, `settings`, `is_provider` — watcher must *never* send these, since PATCH with no set field leaves them alone. |
| UUID-on-create | **No.** `POST /api/organizations` does not accept a body `id`; server generates via ORM default. `_resolve_organization` (`manifest_import.py:893`) bypasses the DTO and writes the manifest UUID directly with `Upsert(... values={"id": ...})`. |
| `_resolve_*` rules | ID-first then name-fallback upsert. `created_by` is hard-coded `"git-sync"`. No per-entity REST equivalent, but the watcher only creates new orgs rarely — the server-assigned UUID can be captured from the 201 response and written back to the store + YAML. |

**Rating: Yellow.** Functionally portable via PATCH, but POST can't round-trip the UUID — delete-then-recreate-with-same-UUID fails. Plan already notes this is rare.

---

### 2. Roles

**Manifest:** `ManifestRole` (`manifest.py:55`) — `id, name`.
**DTOs:** `RoleCreate` (`users.py:165`) — `name, description, permissions`. `RoleUpdate` (`users.py:173`) — `name, description, permissions`.
**Endpoints:** `POST /api/roles` (`roles.py:86`), `PATCH /api/roles/{role_id}` (`roles.py:154`), `PUT /api/roles/{role_id}` (`roles.py:208`, `include_in_schema=False` — legacy), `DELETE /api/roles/{role_id}` (`roles.py:225`).

| Q | Answer |
|---|---|
| Field parity | Manifest is a strict subset (`id, name`). DTO has `description, permissions` that the YAML doesn't carry — those are UI-managed. |
| Aliases/casing | None. |
| Nested entities | None (role *assignments* to workflows/agents/forms/apps are separate junction endpoints, not part of the role). |
| UI-managed fields | `description`, `permissions` — watcher must not send these. |
| UUID-on-create | **No.** `POST /api/roles` (`roles.py:93`) does not accept `id`. `_resolve_role` (`manifest_import.py:933`) writes manifest UUID directly. Same limitation as organizations. |
| `_resolve_*` rules | ID-first, name-fallback upsert, `created_by="git-sync"`. |

**Rating: Yellow.** Same UUID-on-create gap as organizations. Watcher can otherwise route trivially.

---

### 3. Workflows

**Manifest:** `ManifestWorkflow` (`manifest.py:61`) — `id, name, path, function_name, type, organization_id, roles, access_level, endpoint_enabled, timeout_seconds, public_endpoint, description, category, tags`.
**DTOs:** No `WorkflowCreate` — workflows are created by file discovery (via `POST /api/workflows/register` (`workflows.py:937`) with `path, function_name, organization_id`). `WorkflowUpdateRequest` (`workflows.py:261`) — `organization_id, access_level, clear_roles, display_name, description, category, timeout_seconds, execution_mode, time_saved, value, tool_description, cache_ttl_seconds, tags, endpoint_enabled, allowed_methods, public_endpoint, disable_global_key`.
**Endpoints:** `PATCH /api/workflows/{id}` (`workflows.py:1073`), `DELETE /api/workflows/{id}` (`workflows.py:1723`). Role assignments: `POST /api/workflows/{id}/roles` (ADD-only, `workflows.py:1620`), `DELETE /api/workflows/{id}/roles/{role_id}` (`workflows.py:1689`).

| Q | Answer |
|---|---|
| Field parity | All writable manifest fields exist on PATCH. Manifest's `name` and `function_name` and `path` are **not** on PATCH — correct per plan; they are `.py`-derived. `type` is also not writable (discovery-derived). Manifest has no `display_name`, `tool_description`, `time_saved`, `value`, `cache_ttl_seconds`, `allowed_methods`, `execution_mode`, `disable_global_key` — these are UI-managed additions. |
| Aliases/casing | None. |
| Nested entities | None (roles handled separately). |
| UI-managed fields | `display_name`, `tool_description`, `time_saved`, `value`, `cache_ttl_seconds`, `allowed_methods`, `execution_mode`, `disable_global_key` — PATCH preserves them when watcher omits them. |
| UUID-on-create | N/A — code-derived. Creation happens via the decorator discovery path + `/register`. The manifest UUID is NOT supplied on create; it's surfaced after discovery. Watcher never POSTs a workflow. |
| `_resolve_*` rules | `_resolve_workflow` (`manifest_import.py:1015`) uses natural key `(path, function_name)` first, then ID. Handles path/function renames. Writes `created_by="git-sync"`. **Role sync is via `_sync_role_assignments` (`manifest_import.py:973`) — add-first-then-remove.** The two public role endpoints only ADD or DELETE one at a time; there is no "replace-set" endpoint. Watcher must compute diff and issue N POST + M DELETE calls. |

**Rating: Yellow.** PATCH works for metadata. Role-set replace is multi-call (add new, then delete stale) which the watcher can replicate. Code-derived fields (`name`, `function_name`, `path`) stay YAML-read-only per plan Task 6.

---

### 4. Forms

**Manifest:** `ManifestForm` (`manifest.py:79`) — `id, name, path, organization_id, roles, access_level`. **Does not carry** `workflow_id`, `form_schema`, `description`, `launch_workflow_id`, `default_launch_params`, `allowed_query_params`.
**DTOs:** `FormCreate` (`forms.py:218`) — `name, description, workflow_id, launch_workflow_id, default_launch_params, allowed_query_params, form_schema, access_level, organization_id`. `FormUpdate` (`forms.py:232`) — same set plus `is_active, clear_roles`, minus required-ness. **Neither has `role_ids` or `id`.**
**Endpoints:** `POST /api/forms` (`forms.py:283`), `PATCH /api/forms/{id}` (`forms.py:441`), `PUT /api/forms/{id}` (`forms.py:565`, legacy), `DELETE /api/forms/{id}` (`forms.py:583`).

| Q | Answer |
|---|---|
| Field parity | Manifest is a **partial** view: the content (workflow_id, form_schema, etc.) lives in `forms/{uuid}.form.yaml` and is indexed server-side when that file is written through `/api/files/write` — **not** through the manifest path. So for manifest-only changes (access_level, roles, name, organization_id), PATCH is enough. |
| Aliases/casing | None. |
| Nested entities | `form_schema` is a nested model but lives in the `.form.yaml` file, not the manifest. Out of scope for the manifest PATCH. |
| UI-managed fields | `workflow_id`, `form_schema`, `description`, `launch_workflow_id`, etc. — watcher doesn't touch these from `.bifrost/forms.yaml`. The `.form.yaml` per-file path handles them. |
| UUID-on-create | **No.** `FormCreate` has no `id` field; server generates via ORM default. `_resolve_form` (`manifest_import.py:1995`) writes UUID directly and **only runs for org-scoped forms** — global forms come entirely from the file indexer. |
| `_resolve_*` rules | `_resolve_form` is almost a no-op for global forms and a minimal upsert for org-scoped ones (name + access_level + organization_id + roles). Replicable client-side trivially. |

**Rating: Yellow.** PATCH handles metadata cleanly. New-form creation is awkward: `FormCreate` requires `workflow_id` not to be None in many flows and the manifest doesn't know it — but in practice the watcher shouldn't be creating forms via `.bifrost/forms.yaml`; forms are created via the UI or via the per-file path (which writes `.form.yaml` then registers the form). **Recommendation: watcher treats `forms` manifest entries as PATCH-only; treat a new UUID in `.bifrost/forms.yaml` as an error unless the companion file already exists.**

---

### 5. Agents

**Manifest:** `ManifestAgent` (`manifest.py:89`) — `id, name, path, organization_id, roles, access_level, max_iterations, max_token_budget`. **Does not carry** `system_prompt`, `channels`, `tool_ids`, `delegated_agent_ids`, `knowledge_sources`, `system_tools`, `llm_model`, `llm_max_tokens`, `description`.
**DTOs:** `AgentCreate` (`agents.py:37`) — 14 fields including `system_prompt` (required), `channels`, `tool_ids`, etc. `AgentUpdate` (`agents.py:58`) — same fields as optional, plus `is_active, clear_roles, role_ids`.
**Endpoints:** `POST /api/agents` (`agents.py:292`), **`PUT /api/agents/{id}`** (`agents.py:536`, **not PATCH** — plan is wrong), `DELETE /api/agents/{id}` (`agents.py:719`).

| Q | Answer |
|---|---|
| Field parity | Same story as forms: the manifest is a partial view; content lives in `agents/{uuid}.agent.yaml`. Manifest covers registration metadata + `max_iterations` / `max_token_budget` which are also on `AgentUpdate`. All manifest fields have DTO equivalents. |
| Aliases/casing | None. |
| Nested entities | Tool/agent/knowledge associations are lists on `AgentUpdate`, not separate endpoints. They replace-by-set. |
| UI-managed fields | `system_prompt`, `tool_ids`, `channels`, `description`, etc. — if the watcher only sends manifest-carried fields, PUT preserves the rest *only if* PUT is partial-update-semantic. **Verify: is it PUT-as-PATCH here?** From `agents.py:536` onward the handler uses `if request.xxx is not None:` guards so it behaves as PATCH despite the HTTP verb. **Confirmed.** Watcher can safely send partial bodies. |
| UUID-on-create | **No.** `AgentCreate` has no `id` field; server assigns via `uuid4()` (`agents.py:327`). |
| `_resolve_*` rules | `_resolve_agent` (`manifest_import.py:2043`) is a minimal metadata upsert like `_resolve_form`. Role sync via `_sync_role_assignments`. |

**Rating: Yellow.** PUT-with-partial-body works, but the plan's mapping table says PATCH — **routing table needs to use PUT or the client gets 405**. Same new-agent issue as forms: the full content lives in the `.agent.yaml` file, so the manifest-only path should PATCH existing rows, not POST new ones.

---

### 6. Apps (Applications)

**Manifest:** `ManifestApp` (`manifest.py:101`) — `id, path, slug, name, description, dependencies, organization_id, roles, access_level`.
**DTOs:** `ApplicationCreate` (`applications.py:38`) — `name, description, icon, slug, access_level, role_ids, organization_id`. **No `dependencies`, no `path`, no `id`.** `ApplicationUpdate` (`applications.py:80`) — `name, slug, description, icon, scope, access_level, role_ids`. **No `dependencies`.**
**Endpoints:** `POST /api/applications` (`applications.py:621`), `PATCH /api/applications/{app_id}` (`applications.py:726`) — metadata only, `PUT /api/applications/{app_id}/draft` (`applications.py:842`) — app definition blob (separate concern), `DELETE /api/applications/{app_id}` (`applications.py:781`). **Dependencies: `PUT /api/applications/{app_id}/dependencies`** (`app_code_files.py:660`) — body is `dict[str, str]`.

| Q | Answer |
|---|---|
| Field parity | `role_ids` on manifest is `roles` — renamed. `dependencies` on manifest has **no slot on PATCH**; needs a separate PUT call. `path` on manifest has no DTO equivalent — derived from `slug` server-side. `icon` is DTO-only (UI-managed). |
| Aliases/casing | `roles` (manifest) vs `role_ids` (DTO). Watcher must translate. |
| Nested entities | None on manifest (the definition blob / files live in their own endpoints). |
| UI-managed fields | `icon`, and the definition blob / embed secrets. |
| UUID-on-create | **No.** `ApplicationCreate` has no `id`. `_resolve_app` (`manifest_import.py:1671`) writes UUID directly via `Upsert`. |
| `_resolve_*` rules | `_resolve_app` does slug-first lookup, ID-realigns if needed, and writes `dependencies` along with metadata in one upsert. The per-entity REST path needs **two calls** for create-with-deps: `POST /api/applications` then `PUT /api/applications/{id}/dependencies`. Update path similarly: PATCH for metadata, separate PUT for deps. |

**Rating: Yellow.** Workable but requires the watcher to (a) remap `roles` ↔ `role_ids`, (b) route `dependencies` to a separate endpoint, (c) skip `path` on outbound (it's not writable). The plan's mapping table entry for apps is inaccurate — PATCH-draft is NOT the right endpoint.

---

### 7. Integrations

**Manifest:** `ManifestIntegration` (`manifest.py:152`) — `id, name, entity_id, entity_id_name, default_entity_id, list_entities_data_provider_id, config_schema (list), oauth_provider (nested), mappings (list)`.
**DTOs:** `IntegrationCreate` (`integrations.py:63`) — `name, config_schema, entity_id, entity_id_name, default_entity_id`. **No `list_entities_data_provider_id`, no `oauth_provider`, no `mappings`, no `id`.** `IntegrationUpdate` (`integrations.py:97`) — adds `list_entities_data_provider_id`, still **no `oauth_provider`, no `mappings`**.
**Endpoints:** `POST /api/integrations` (`integrations.py:653`), **`PUT /api/integrations/{id}`** (`integrations.py:814`, **not PATCH**), `DELETE /api/integrations/{id}` (`integrations.py:840`). Mappings: `POST /api/integrations/{id}/mappings` (`integrations.py:963`), `PUT /api/integrations/{id}/mappings/{mapping_id}` (`integrations.py:1133`), `DELETE /api/integrations/{id}/mappings/{mapping_id}` (`integrations.py:1241`). Batch upsert: `POST /api/integrations/{id}/mappings/batch` (`integrations.py:1176`). OAuth provider: **`GET /api/integrations/{id}/oauth` only** (`integrations.py:1271`) — no POST/PUT/DELETE. OAuth provider is configured via a completely different surface (`/api/oauth/connections` — `oauth_connections.py:396`). |

| Q | Answer |
|---|---|
| Field parity | Top-level integration fields map cleanly (with `list_entities_data_provider_id` update-only). **Nested `mappings`**: cannot be sent in the parent PUT — need separate child endpoints. **Nested `oauth_provider`**: there is **no REST endpoint** that sets the OAuth provider row for an integration from the manifest shape. `_resolve_integration` writes the `OAuthProvider` row directly. |
| Aliases/casing | None. |
| Nested entities | `config_schema` **is** accepted in PUT body (both Create and Update DTOs have it as a list). However the DTO version of `ConfigSchemaItem` has no `position` field, while `ManifestIntegrationConfigSchema` does. The DTO uses list order implicitly as position (`create_integration` in the repo passes `position=idx`). For PUT, the router presumably replaces config schema wholesale — but this **breaks the non-destructive upsert invariant** that `_resolve_integration` carefully preserves (see `manifest_import.py:1482–1523`), because FK-linked `Config` rows reference schema items via `config_schema_id`. **If the PUT handler deletes+reinserts schema items, any org-level Config values lose their FK link.** Needs inspection of `IntegrationsRepository.update_integration`; if it doesn't replicate the non-destructive pattern, this is **Red**. |
| UI-managed fields | `oauth_provider.client_secret` (never serialized; fine), `oauth_provider.client_id` can be `__NEEDS_SETUP__` sentinel, `mappings[].oauth_token_id` (set by UI after user does OAuth dance). Watcher must omit these when PATCH-ing mappings unless explicitly present. |
| UUID-on-create | **No.** `IntegrationCreate` has no `id`; `_resolve_integration` writes manifest UUID directly. |
| `_resolve_*` rules (critical) | `_resolve_integration` (`manifest_import.py:1426`) does three things the REST surface does NOT: **(a) non-destructive upsert of `config_schema` by natural key `(integration_id, key)`** preserving DB-assigned IDs so that FK-linked `Config` rows aren't cascade-deleted. **(b) upsert of `OAuthProvider` row** keyed on `uq_oauth_providers_integration_id`, skipping `client_id` when it's the `__NEEDS_SETUP__` sentinel so UI-set values aren't stomped; placeholder empty `encrypted_client_secret` on insert. **(c) upsert of `IntegrationMapping` by `(integration_id, organization_id)`** preserving UI-set `oauth_token_id` (only overwrites if manifest explicitly carries one). None of this logic exists on the per-entity REST surface today. |

**Rating: Red.** Three structural gaps that the per-entity REST path can't replicate without either new server work or the watcher reimplementing upsert-by-natural-key against the existing endpoints (which it can do for mappings via list-then-diff-then-POST/PUT/DELETE, but **cannot** do for `oauth_provider` since no mutation endpoint exists, and **cannot safely** do for `config_schema` if the PUT handler is destructive).

---

### 8. Configs

**Manifest:** `ManifestConfig` (`manifest.py:165`) — `id, integration_id, key, config_type, description, organization_id, value`.
**DTOs:** `SetConfigRequest` (`config.py:40`) — `key, value, type, description, organization_id`. **No `integration_id`.** `UpdateConfigRequest` (`config.py:49`) — same fields as optional. **No `integration_id`.** Note there's also `ConfigCreate` / `ConfigUpdate` in the CRUD pattern (`config.py:71`, `76`) but the routers use the request models above.
**Endpoints:** `POST /api/config` (`config.py:333`), **`PUT /api/config/{id}`** (`config.py:379`, **not PATCH**), `DELETE /api/config/{id}` (`config.py:419`).

| Q | Answer |
|---|---|
| Field parity | **`integration_id` is manifest-only** — there is no way to set or change the integration_id / config_schema_id linkage through the public REST endpoints. This is precisely the field that cascades-from-integration-schema, and the `_resolve_integration` flow is what sets it (via IntegrationConfigSchema FK). Additionally, `ConfigRepository.set_config` (`config.py:149`) wraps `value` in a `{"value": ...}` JSONB envelope — manifest carries the raw value. Watcher must match server's envelope format. |
| Aliases/casing | Manifest has `config_type`, DTO has `type`. Rename. |
| Nested entities | None. |
| UI-managed fields | User-set values for integration configs with `type="secret"` — `_resolve_config` (`manifest_import.py:1627`) skips overwriting a non-null existing value when both manifest and DB are SECRET. REST `UpdateConfigRequest` has a docstring claim that omitting `value` preserves existing (`config.py:56`) — confirmed by `update_config_by_id` logic — so the watcher is fine here as long as it omits `value` for secrets. |
| UUID-on-create | **No.** `SetConfigRequest` has no `id`; server generates. POST is upsert-by-(org_id, key) not insert-by-id. Delete-then-recreate-with-same-UUID will produce a different UUID, breaking manifest references. |
| `_resolve_*` rules | `_resolve_config` (`manifest_import.py:1604`) upserts by natural key `(key, integration_id, org_id)`, realigns IDs, writes `integration_id` and `config_schema_id`. Stale-entity sweep skips configs with `config_schema_id` set because those are managed via integration cascade. This **is not replicable** via REST: there's no way to tell POST/PUT that this config belongs to integration X schema item Y. |

**Rating: Red** for configs that belong to integrations (manifest has `integration_id` set). **Yellow** for standalone org/global configs (no `integration_id`). Configs tied to integration schemas cannot round-trip through the public REST endpoints — that linkage is server-internal.

---

### 9. Tables

**Manifest:** `ManifestTable` (`manifest.py:176`) — `id, name, description, organization_id, application_id, table_schema (alias='schema')`.
**DTOs:** `TableCreate` (`tables.py:39`) — `name, description, schema, organization_id`. **No `application_id`, no `id`.** `TableUpdate` (`tables.py:48`) — `description, schema`. **No `name`, no `application_id`, no `organization_id`.**
**Endpoints:** `POST /api/tables` (`tables.py:460`), `PATCH /api/tables/{id}` (`tables.py:547`), `DELETE /api/tables/{id}` (`tables.py:571`).

| Q | Answer |
|---|---|
| Field parity | Manifest's `application_id` has **no DTO slot** — neither Create nor Update. `_resolve_table` writes it directly. **`name` is not on TableUpdate** — so renaming a table is impossible via the public endpoint. `_resolve_table` (`manifest_import.py:1740`) freely writes name. |
| Aliases/casing | `ManifestTable.table_schema` serializes as `schema` (alias match with DTO). Both sides use `schema`. Match is clean. |
| Nested entities | None. |
| UI-managed fields | None (tables are entirely schema-declarative). |
| UUID-on-create | **No.** `TableCreate` has no `id`. `_resolve_table` writes manifest UUID directly. |
| `_resolve_*` rules | `_resolve_table` uses natural-key `(name, organization_id)` then ID. **Supports ID realignment** (CASCADE ON UPDATE across Document rows). This is impossible to replicate via REST. Also writes `application_id` — also impossible via REST. |

**Rating: Red.** Rename, application_id changes, and ID realignment are all unsupported by the public surface. Only description+schema edits can round-trip cleanly.

---

### 10. Events (event sources + subscriptions)

**Manifest:** `ManifestEventSource` (`manifest.py:204`) — `id, name, source_type, organization_id, is_active, cron_expression, timezone, schedule_enabled, adapter_name, webhook_integration_id, webhook_config, subscriptions (list)`.
`ManifestEventSubscription` (`manifest.py:192`) — `id, target_type, workflow_id, agent_id, event_type, filter_expression, input_mapping, is_active`.
**DTOs:** `EventSourceCreate` (`events.py:84`) — `name, source_type, organization_id, webhook (nested WebhookSourceConfig), schedule (nested ScheduleSourceConfig)`. **No `is_active` (server sets True), no `id`.** `EventSourceUpdate` (`events.py:116`) — `name, is_active, organization_id, webhook, schedule`.
`EventSubscriptionCreate` (`events.py:151`) — `target_type, workflow_id, agent_id, event_type, filter_expression, input_mapping`. **No `id`, no `is_active`.** `EventSubscriptionUpdate` (`events.py:184`) — `event_type, filter_expression, is_active, input_mapping`. **Does not allow updating `target_type`, `workflow_id`, `agent_id`.**
**Endpoints:** `POST /api/events/sources` (`events.py:341`), `PATCH /api/events/sources/{id}` (`events.py:500`), `DELETE /api/events/sources/{id}` (`events.py:581`). Subscriptions: `POST /api/events/sources/{id}/subscriptions` (`events.py:670`), `PATCH /api/events/sources/{id}/subscriptions/{sub_id}` (`events.py:738`), `DELETE` (`events.py:799`).

| Q | Answer |
|---|---|
| Field parity | **Shape mismatch:** the manifest flattens webhook/schedule fields onto the event source (`cron_expression`, `timezone`, `adapter_name`, `webhook_config` directly on `ManifestEventSource`); the DTOs wrap them in nested `webhook: WebhookSourceConfig` and `schedule: ScheduleSourceConfig`. Watcher must translate flat → nested on outbound. `schedule_enabled` on manifest maps to `schedule.enabled`. `webhook_integration_id` maps to `webhook.integration_id`. `webhook_config` maps to `webhook.config`. Translatable but not 1:1. Subscription side: cannot change `target_type`, `workflow_id`, `agent_id` via PATCH — **must delete + recreate** to change the target. |
| Aliases/casing | Structural (flat vs nested) rather than alias-based. |
| Nested entities | Subscriptions are their own resource; parent PATCH cannot update them. Watcher must diff `subscriptions` list client-side and issue N POST/PATCH/DELETE on the subscription sub-endpoints. |
| UI-managed fields | Webhook subscription external state (`external_id`, `expires_at`, `state`) — set by adapter at create time, not round-tripped through manifest. The manifest only carries what the user controls. |
| UUID-on-create | **No.** Neither `EventSourceCreate` nor `EventSubscriptionCreate` accept `id`. `_resolve_event_source` (`manifest_import.py:1833`) writes manifest UUID directly via ON CONFLICT upserts. **Critical gap** for subscriptions: manifest carries subscription UUIDs that won't match server-assigned ones after recreate. |
| `_resolve_*` rules | `_resolve_event_source` (a) upserts EventSource by ID (b) upserts ScheduleSource or WebhookSource by `event_source_id` (c) resolves subscription `workflow_id` via portable ref (UUID / `path::func` / workflow name — `_resolve_workflow_ref` in `manifest_import.py:1093`) (d) skips subscriptions whose referenced workflow wasn't imported. The portable-ref resolution is **CLI-manifest-specific** — the REST endpoints require a real UUID. Watcher would have to resolve refs client-side using its store. |

**Rating: Red.** Four problems: flat-vs-nested translation (workable), no UUID-on-create (breaks delete-then-recreate), `target_type`/`workflow_id`/`agent_id` unchangeable via PATCH (forces delete+recreate), portable-ref resolution. The plan already calls out subscriptions as having their own endpoints (line 329) but under-estimates the complexity.

---

## Summary Table

| Entity | Verb (actual) | UUID-on-create | Field parity | Nested | Special `_resolve_*` rules | Rating |
|---|---|---|---|---|---|---|
| organizations | PATCH | No | Partial (DTO extras) | — | ID/name upsert | **Yellow** |
| roles | PATCH (PUT legacy) | No | Partial (DTO extras) | — | ID/name upsert | **Yellow** |
| workflows | PATCH | N/A | Full for metadata | Roles via separate endpoints | Natural-key on `(path, func)` | **Yellow** |
| forms | PATCH (PUT legacy) | No | Manifest is partial; content in .form.yaml | — | Org-scoped minimal upsert | **Yellow** |
| agents | **PUT** (not PATCH) | No | Same as forms | Associations replace-by-set | Minimal upsert | **Yellow** |
| apps | PATCH + `PUT /dependencies` | No | `roles` ↔ `role_ids` rename; no `dependencies` on PATCH; `path` not writable | Definition+files are separate | Slug-first lookup, ID-realign | **Yellow** |
| integrations | **PUT** (not PATCH) | No | Missing `oauth_provider` REST surface | config_schema and mappings need non-destructive upsert; oauth_provider has no mutation endpoint | Non-destructive config_schema upsert preserves FK; oauth_provider upsert with sentinel-skip; mapping upsert preserves UI-set `oauth_token_id` | **Red** |
| configs | **PUT** (not PATCH) | No | `integration_id` is manifest-only | — | Natural-key upsert; FK to IntegrationConfigSchema | **Red** (for integration-owned configs) / Yellow (standalone) |
| tables | PATCH | No | `application_id` + `name` not on PATCH | — | ID realignment with cascade | **Red** |
| events | PATCH + sub-endpoints | No | Flat-vs-nested translation; PATCH can't change sub-target | Subscriptions separate child endpoints | Portable-ref workflow_id; schedule/webhook sub-row upsert | **Red** |

---

## Decision Gate

Per the plan's rubric (lines 577–583):

- **Green (4/10):** none.
- **Yellow (6/10):** `organizations`, `roles`, `workflows`, `forms`, `agents`, `apps`.
- **Red (4/10):** `integrations`, `configs` (when integration-owned), `tables`, `events`.

The Red count is **four out of ten entity types**, covering exactly the entity shapes where the old `_resolve_*` methods do the most non-trivial translation work. Critically:

1. **Integrations** have no REST surface at all for `oauth_provider`, and their `config_schema` relies on non-destructive upsert semantics that aren't exposed publicly.
2. **Configs** owned by integration schemas cannot round-trip because `integration_id` / `config_schema_id` are never in the DTOs.
3. **Tables** can't round-trip rename or `application_id` changes through PATCH.
4. **Events** need per-subscription child-endpoint orchestration, flat-to-nested translation, and portable-ref resolution client-side.

Every Yellow entity also has a UUID-on-create gap (server generates UUIDs, so delete-then-recreate with the same UUID is impossible across the board). This breaks one documented watcher edge case (plan lines 374–375) uniformly — it's not an exotic concern limited to a couple of types.

### Bottom-line recommendation: **Pause Task 1; open the pivot conversation.**

The plan's "Task 2 removed — endpoints already exist" claim (plan line 35) holds for the Yellow set only. The Red set needs either:

- **Server additions** (OAuth provider CRUD, config integration_id writability, table application_id + name on PATCH, subscription target-change), plus a convention that `POST` accepts client-supplied UUIDs for every entity. That's easily four small PRs before Task 1 is viable.
- **OR** the watcher reimplements `_resolve_*` logic client-side (non-destructive schema upsert, portable-ref resolution, flat-nested translation, mapping-by-natural-key) against the existing endpoints — except for the parts that simply don't have endpoints (`oauth_provider`), which would still need server work.

Both options contradict the plan's stated goal of avoiding "two parallel model-translation layers."

The plan's own escape hatch (lines 585–589) — **"retire `.bifrost/` from the watch path entirely"** — is the lower-friction direction. Recommendation: invoke that pivot. Watch stops touching `.bifrost/*.yaml`; entity mutations move to an explicit `bifrost api` / `bifrost import` surface; `.bifrost/` becomes an export artifact. The tactical `delete_removed_entities=False` stopgap (plan line 34) addresses the urgent disappearing-entity bug without requiring the redesign at all.

If the team still wants the gatekeeper redesign, the smaller viable scope is: **apply it only to the Yellow entities** (orgs/roles/workflows/forms/agents/apps) and continue routing integrations/configs/tables/events through `POST /api/files/manifest/import` with `delete_removed_entities=False`. That's a mixed-mode architecture — less pure than the plan envisions but achievable incrementally.

---

## Appendix: files consulted

- `/home/jack/GitHub/bifrost/api/bifrost/manifest.py` — manifest models + parsing (lines 48–234).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/organizations.py` — OrganizationCreate/Update (81, 86).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/users.py` — RoleCreate/Update (165, 173).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/workflows.py` — WorkflowUpdateRequest (261).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/forms.py` — FormCreate/FormUpdate (218, 232).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/agents.py` — AgentCreate/AgentUpdate (37, 58).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/applications.py` — ApplicationCreate/Update (38, 80).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/integrations.py` — IntegrationCreate/Update, IntegrationMappingCreate/Update (63, 97, 135, 170), ConfigSchemaItem (25).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/config.py` — SetConfigRequest / UpdateConfigRequest (40, 49).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/tables.py` — TableCreate/Update (39, 48).
- `/home/jack/GitHub/bifrost/api/src/models/contracts/events.py` — EventSourceCreate/Update, EventSubscriptionCreate/Update (84, 116, 151, 184).
- `/home/jack/GitHub/bifrost/api/src/routers/organizations.py`, `roles.py`, `workflows.py`, `forms.py`, `agents.py`, `applications.py`, `app_code_files.py`, `integrations.py`, `config.py`, `tables.py`, `events.py` — verified endpoint verbs and path shapes.
- `/home/jack/GitHub/bifrost/api/src/services/manifest_import.py` — all `_resolve_*` methods (893, 933, 1015, 1426, 1604, 1671, 1740, 1833, 1995, 2043); `_resolve_workflow_ref` (1093); `_sync_role_assignments` (973); `_resolve_deletions` (1185).
- `/home/jack/GitHub/bifrost/api/src/models/orm/config.py` — Config model, `config_schema_id` FK (line 53).
