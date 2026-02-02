# Bifrost Integrations Platform

## What This Is

Bifrost is an MSP automation platform that enables writing Python workflows, building apps/forms/agents, and deploying them to customers. It provides a code-first infrastructure where Python code works locally with the SDK installed, with special handling only for workflow files decorated with `@workflow`.

## Core Value

Multi-tenant automation: write code once, share and customize across organizations, while maintaining isolation and security boundaries.

## Requirements

### Validated

<!-- Shipped and confirmed valuable - inferred from existing codebase -->

- ✓ Workflow execution engine with process isolation — existing
- ✓ Python SDK for workflows (`from bifrost import workflow, files, tables, etc.`) — existing
- ✓ Organization-scoped entities (workflows, forms, agents, apps) — existing
- ✓ Role-based access control with cascade scoping — existing
- ✓ GitHub sync for code deployment — existing
- ✓ Form builder with workflow integration — existing
- ✓ Agent builder with tool assignment — existing
- ✓ App builder with code editor — existing
- ✓ Scheduled workflow execution (cron) — existing
- ✓ Real-time execution updates via WebSocket — existing
- ✓ OAuth integrations (credentials, tokens) — existing
- ✓ Config/secrets management per organization — existing
- ✓ File storage (S3-backed with workspace indexing) — existing
- ✓ Virtual import system for user modules — existing
- ✓ MCP server integration — existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Organization-scoped modules (workspace_files need org_id)
- [ ] Cascade filtering for modules (org-specific → global fallback)
- [ ] One scope per GitHub repo enforcement
- [ ] Redis cache restructure for scoped modules

### Out of Scope

- Builder Workbench UI (unified editor) — deferred to future milestone, not blocked by scoping work
- Name-based portable references — can be done after scoping, separate migration
- Prescriptive folder structure enforcement — nice-to-have, not required for multi-tenancy

## Context

**The Problem:**
`workspace_files` (which stores modules) has no `organization_id` column. This means:
- Modules are always global — two orgs can't have their own `halopsa.py`
- Virtual importer has no cascade logic for modules
- GitHub sync has logical issues with scope (uniqueness is path-only)

**Technical Environment:**
- FastAPI backend (Python 3.11), React frontend (TypeScript)
- PostgreSQL, Redis, RabbitMQ, S3 (MinIO locally)
- Existing org-scoped pattern in OrgScopedRepository for workflows/forms/apps/agents
- Virtual import system loads modules from Redis cache

**Existing Patterns to Follow:**
- `OrgScopedRepository` already implements cascade scoping (org → global)
- Workflows, Forms, Agents, Apps all have `organization_id` with NULL = global
- `bifrost.files` SDK operates via `/api/files/*` endpoints

## Constraints

- **Backward Compatibility**: Existing modules must continue working (NULL org_id = global)
- **Migration Safety**: Data migration must not break existing references
- **SDK Transparency**: `bifrost.files` SDK should not require code changes in user workflows

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Add org_id to workspace_files, not create separate modules table | Follow existing pattern, minimize schema changes | — Pending |
| Cascade order: org-specific first, global fallback | Matches existing behavior in other entities | — Pending |
| One repo = one scope | Simplifies sync logic, avoids path collision | — Pending |

---
*Last updated: 2026-02-02 after initialization*
