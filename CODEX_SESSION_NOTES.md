# Codex Session Notes

**Last updated:** 2026-03-25

This file is a Codex-friendly distillation of the top-level `CLAUDE.md`,
selected `.claude/` behavior, and the current integration-session context.
It exists so future sessions do not need to reconstruct operating assumptions
from Claude-specific config files.

## Scope

These notes describe how to work in the `bifrost` repo, not the separate
workflow/content repos.

## Repo State

- Repo: `~/mtg-bifrost/bifrost`
- Active branch at time of writing: `feat/autotask-cove-integrations`
- The platform is FastAPI + React and is developed primarily through Docker
- `.bifrost/*.yaml` manifests are first-class source files for integrations,
  workflows, forms, apps, and related entities

## Core Operating Rules

### Development Environment

- Treat Docker as the normal development environment
- Start the stack with `./debug.sh`
- Access the app through `http://localhost:3000`
- Do not assume host-level Python or frontend processes are the intended path
- Hot reload is expected; do not restart the whole stack for normal file edits

### Testing and Verification

- Use `./test.sh` for backend tests rather than host `pytest`
- If full Docker-backed test execution is unavailable, at minimum run targeted
  syntax/import sanity checks and say so explicitly
- Standard quality gates from `CLAUDE.md` remain:
  - backend: `pyright`, `ruff check`
  - frontend: `npm run generate:types`, `npm run tsc`, `npm run lint`

### File and Architecture Rules

- Cross-feature workspace logic belongs in top-level `shared/`, not in thin HTTP handlers
- The repo no longer has `api/shared/`; Docker and local tooling should reference `shared/`
- Frontend API types should be generated, not handwritten
- S3/RepoStorage is the source of truth for repo content in the platform
- For manifests and git sync, use non-destructive upsert patterns for
  integrations, config schema, and mappings
- The fork currently carries committed `.bifrost/*.yaml`, but upstream treats
  `.bifrost/` as generated/system-managed workspace state
- See `docs/plans/2026-03-26-upstream-convergence-plan.md` before doing more
  repo-model work around manifests or dev image workflows
- See `docs/plans/2026-03-26-feature-branch-closeout-plan.md` for the merge
  path from `feat/autotask-cove-integrations` back to fork `main`

## Useful `.claude` Behavior That Matters

### Environment Detection Hook

The hook at `.claude/hooks/bifrost-detect.sh` tries to detect:

- whether local Bifrost source exists
- whether the `bifrost` CLI is installed
- whether local Bifrost credentials are present
- whether a Bifrost MCP server is configured
- Python version / install command hints

That detection is Claude-specific, but the practical takeaway is:

- future sessions should quickly determine whether they have local source,
  working platform credentials, and a usable CLI before assuming SDK-first
  workflows are available

### Build Skill Guidance

The main reusable ideas from `.claude/skills/bifrost-build/SKILL.md` are:

- prefer local-repo discovery over remote platform discovery when source is
  available
- fetch platform docs once per session if needed and reuse them
- treat `.bifrost/*.yaml` as the main discovery surface for local work
- generate UUIDs before writing cross-referenced manifest entities
- rely on `bifrost watch` only when intentionally using SDK/watch workflows

For this repo specifically, those ideas are secondary to the repo-level Docker
and test rules above.

## Integration Work Pattern Used In This Session

For first-class vendor integrations, the working pattern has been:

1. `modules/{vendor}.py`
   - focused async `httpx` client
   - auth handling
   - normalized customer/entity helpers
   - `get_client(scope: str | None = None)` that reads Bifrost integration config
2. `features/{vendor}/workflows/data_providers.py`
   - returns sorted `{value, label}` options for org mapping
3. `features/{vendor}/workflows/sync_*.py`
   - lists vendor entities
   - matches or creates Bifrost orgs
   - upserts `IntegrationMapping`
4. `.bifrost/integrations.yaml`
   - add integration entry and config schema
5. `.bifrost/workflows.yaml`
   - add workflow + data provider metadata
6. `api/tests/unit/test_{vendor}_integration.py`
   - config contract
   - sorting/normalization
   - sync behavior

## Current Integration Coverage

As of this note, `integrations.yaml` includes:

- CIPP
- Microsoft CSP
- Microsoft
- GoToConnect
- DNSFilter
- Meraki
- VIPRE
- Quoter
- ConnectSecure
- Pax8
- Huntress
- HaloPSA
- AutoElevate
- NinjaOne
- Cove Data Protection
- Datto SaaS Protection
- Google Workspace Reseller
- Google Workspace
- Datto RMM
- Datto Networking
- IT Glue
- Keeper MSP

## Current Architectural Decisions Worth Preserving

### Keeper

- Keeper is integrated as `Keeper MSP` through Commander Service Mode over HTTP
- Keeper is treated as a system Bifrost manages, not as Bifrost's primary
  secrets backend

### Microsoft

- `Microsoft CSP` and `Microsoft` are intentionally separate integrations
- `Microsoft CSP` is the partner-side delegated OAuth connection for Partner
  Center, tenant discovery, GDAP, and consent workflows
- `Microsoft` is the Bifrost customer-tenant app identity used for Graph and
  Exchange after tenants are linked and consented
- The Microsoft CSP app expects both integrations to be configured; one does not
  replace the other
- Preferred security model: `Microsoft` should be a dedicated Bifrost Entra app
  / service-principal style identity, while `Microsoft CSP` remains the
  delegated partner-admin connection
- Detailed rationale is in
  `docs/plans/2026-03-26-microsoft-integration-boundaries.md`
- Additional service-account guidance is in
  `docs/plans/2026-03-26-microsoft-service-account-model.md`
- For Bifrost runtime secrets, prefer an external store such as Azure Key Vault
- See `docs/plans/2026-03-25-keeper-msp-integration-design-note.md`

### Vendor Order-Lifecycle Research

Current conclusion:

- Amazon Business is the cleanest fit for order / shipment / delivery events
- Dell appears workable but requires partner onboarding and webhook setup
- TD SYNNEX is clearly workable for StreamOne cloud orders, but physical-order
  shipment tracking is not verified from public API docs
- LuxSci remains deferred pending business relevance

See `docs/plans/2026-03-25-order-lifecycle-vendor-api-research.md`

## Operational Constraints Observed In This Session

- Docker was not available in the execution environment, so `./test.sh` could
  not be run here
- local `pytest` was blocked by missing dependencies such as `pytest_asyncio`
- in that constrained environment, lightweight validation used:
  - `python3 -m py_compile`
  - YAML parse checks
  - import sanity checks with adjusted `sys.path`

Future sessions should still prefer the full Docker-backed validation path when
available.

## Suggested Start-of-Session Checklist

1. Read this file
2. Check branch and `git status`
3. Check whether Docker and `./test.sh` are usable
4. Read any note in `docs/plans/` that matches the feature area being touched
5. Confirm whether the task is:
   - platform/repo work in `bifrost`
   - community contribution work in `bifrost-workspace-community`
   - external integration research in `~/agents/integrations`

## When In Doubt

- prefer repository source over stale handoff assumptions
- prefer focused vendor clients over committing large generated SDKs unless the
  broader surface is actually needed
- document architectural calls in normal repo docs, not only in ephemeral chat
