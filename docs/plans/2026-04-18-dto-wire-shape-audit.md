# DTO vs wire-shape audit

**Date:** 2026-04-18
**Status:** Follow-up to `2026-04-18-cli-mutation-surface-and-mcp-parity.md`
**Priority:** Medium — one concrete drift caught and patched; others may lurk.

## Context

The CLI mutation surface plan generates flags and payloads from `XxxCreate` / `XxxUpdate` Pydantic DTOs via `api/bifrost/dto_flags.py`'s `assemble_body`. This works **only when the internal DTO's field shapes match the REST endpoint's public request DTO**.

While verifying the plan, we hit a mismatch on **Configs**:

| | Internal DTO (`ConfigCreate`) | Public wire DTO (`SetConfigRequest`) |
|---|---|---|
| `value` | `dict` | `str` |

The router ignores `ConfigCreate` — it binds `SetConfigRequest`. But `assemble_body(ConfigCreate, ...)` sees `value: dict`, treats any CLI-passed string as JSON, and tries `json.loads("bar")` → `ValueError`. The MCP tool hit the same bug.

**Patch applied inline:** both CLI (`api/bifrost/commands/configs.py`) and MCP (`api/src/services/mcp_server/tools/configs.py`) bypass `assemble_body` for configs and build bodies manually (mirroring `SetConfigRequest`). This is a symptom fix, not a cure.

## The real issue

The `ConfigCreate` / `ConfigUpdate` internal DTOs are divergent from the public request/response contracts. Having two parallel contracts for the same endpoint — with different field types — is the drift that bit us.

Other entity DTOs may have the same problem. We haven't audited them.

## Proposed audit

For every `XxxCreate` / `XxxUpdate` listed in `DTO_EXCLUDES` (i.e. every entity the CLI/MCP mutation surface uses):

1. Find the REST route that accepts mutations for this entity.
2. Identify the Pydantic request model it binds (the `request: XxxRequest` argument).
3. Diff field-by-field: name, type, optionality, enum values, aliases.
4. Report any mismatch to this file.

Known entities to audit:
- [ ] Organizations (`OrganizationCreate` vs router request model)
- [ ] Roles (`RoleCreate` / `RoleUpdate`)
- [ ] Workflows (`WorkflowUpdateRequest` — already public, likely fine)
- [ ] Forms (`FormCreate` / `FormUpdate`)
- [ ] Agents (`AgentCreate` / `AgentUpdate`)
- [ ] Apps (`ApplicationCreate` / `ApplicationUpdate`)
- [ ] Integrations + mappings
- [x] Configs — **drift confirmed, patched inline**
- [ ] Tables (`TableCreate` / `TableUpdate` — Task 3 just extended `TableUpdate`, verify alignment)
- [ ] Events (`EventSourceCreate`, `EventSubscriptionCreate`, and Update variants)

## Proposed remediation, once audit is complete

For every mismatch:

- **Preferred**: reconcile to a single DTO. Delete the internal one if unused elsewhere, or rename the public one to match (contract-first) and remove the parallel.
- **If reconciliation is out of scope** (e.g. a rename would be an API break): extend `api/bifrost/dto_flags.py` with a registry of per-DTO wire overrides so `assemble_body` uses the public shape for flag generation and body assembly. This is only acceptable if the audit confirms the drift is a limited, closed set.

## Why this isn't urgent

- The Configs drift was caught by a test (`test_mcp_parity.py::test_configs_crud_roundtrip`) and patched.
- The CLI `configs create` command was shipped broken but is rarely used (`configs set` is the documented entry point and manually builds its body).
- The field-parity test (`test_dto_flags.py`) would catch a mismatch *only* if the internal DTO adds a field the wire shape lacks. It does not catch type-shape mismatches (dict vs str).

## Why this isn't zero-priority

Silent drift risks: a future field addition on the internal `OrganizationUpdate` (say) could introduce a type that `assemble_body` mangles in a way the existing tests don't exercise, ship broken, and only be caught when a user file an issue.
