# External-User Model — corrected design, unwind/redo record, and forward plan

> **Status: EXECUTED 2026-06-11.** The canonical description of the final
> model lives in `api/src/repositories/README.md` ("External users live at
> gate 3 only"). This doc records what changed and what comes next.
>
> Client-specific material (the portal solution that drove this work) lives
> OUTSIDE this repo, in Obsidian under `Projects/Bifrost/Clients/`. Nothing
> in this repo names the client; the generic driver is "reproducing a
> complex external-client application on Solutions."

## The corrected mental model (stated 2026-06-11)

The platform has ONE authentication/authorization/RBAC enforcement layer:
**the API layer, for direct user calls.** That is where a real, untrusted
user principal is checked.

**The workflow engine runs as a SUPERUSER (the fixed sentinel).** It is
trusted. It carries the caller's identity as an "on-behalf-of"
ExecutionContext **not as an authz mechanism** but as material the engine
uses to voluntarily self-filter — so cascade/scope resolution inside a
workflow returns the right thing for that caller. `is_external` on the
ExecutionContext is just one more fact a workflow developer can use to
self-filter; it is NEVER the platform auto-restricting SDK results inside a
workflow.

**Org scoping is org→global, keyed on the effective caller's ORG. Period.**
It never subtracts the global tier based on user properties — a global
entity is shared, not secret-by-user. The original implementation violated
this (an external-aware cascade), which silently broke explicit role grants
on global entities: the row vanished before the role check could run.

## What shipped (commit "External-user model: revert cascade restrictions…")

- **Cascade fully reverted to pure org→global** for every principal. All
  external-aware scope code removed (repo primitive, org_filter sentinel,
  per-repo copies, MCP scope helper, inline router/websocket gates, listing
  restrictions, and the lint rules that enforced the wrong invariant).
- **Access tiers (SharePoint-style)** are the external lever, at the
  access-level check only:
  - `authenticated` → UI label "Everyone except external users" (stored
    value unchanged; externals excluded — this rule predates the redo and
    was kept).
  - `everyone` (NEW) → any signed-in user including externals. Enum member
    on forms/agents/apps (+ plain string on workflows), PG migration
    `20260611_everyone_access`, validators, MCP tool access, UI dropdowns.
    Replaces the earlier `available_to_external` flag idea — the tier IS
    the flag.
  - `role_based` → grants externals exactly what it grants anyone with the
    role, including on GLOBAL entities (restored capability).
  - `private` (agents) → owner-only, unchanged.
- **Solution workflows**: the own-install carve-out (EXT-3/W3) was removed.
  A solution marks its external-facing workflows `access_level: everyone`
  explicitly.
- **Carve-outs for surfaces with no grant axis**: knowledge content is
  403'd for externals on every direct surface (CLI knowledge endpoints, MCP
  search_knowledge, knowledge-sources reads) — their agents/workflows still
  ground on KB via the engine; decrypted global secrets (config/OAuth/SDK
  integrations) stay denied to direct external callers.
- **Kept**: the genuine cross-tenant fixes the adversarial passes surfaced
  (the free-org_id integrations endpoint deletion; the embed→form binding
  that closed cross-tenant code execution; embed-cookie middleware), the
  `is_external` claim mint/plumbing, the MCP agent-discovery org-scoping
  fix, principal-derived repo construction on SDK routes.

Verification: pyright/ruff clean; 4417 unit + 1450 e2e backend green
(external suite 22/22, incl. everyone-tier end-to-end through a solution
install and a global-role-grant proof); client tsc/lint/vitest green; types
regenerated.

## NEXT: wrap up the external-client portal (the real test of Solutions)

The portal is the thing that will find holes in the Solutions architecture —
and probably in Tables. Sequence:

1. **Ship this branch first** (PR timing is Jack's call — security-relevant,
   wants real review). The portal work depends on the `everyone` tier
   existing server-side.
2. **Re-cut the portal solution under the new model** (workspace lives
   outside this repo): mark the workflows the portal app function-calls as
   an external user with `access_level: everyone`; internal/admin workflows
   stay `role_based`/`authenticated`. Bump the solution version and deploy
   to the client install. In-workflow grant checks (per-facility/doc-type)
   remain the SOLUTION's job — the engine self-filters off the
   ExecutionContext; the platform does not.
3. **Full persona re-drive** with the corrected isolation criteria: external
   users reach only everyone-tier/role-granted entities (org or global);
   authenticated-tier entities are invisible; direct KB surfaces 403; row
   data flows only through table policies (verify, not assume). Note what
   the pure cascade now SHOWS externals in listings (global tool/table
   NAMES are visible by design) and flag anything uncomfortable.
4. **Tables follow-ups the portal will stress** (file issues as found):
   - The claims-resolver list-flatten gap: `preserve.py` does
     `row.get(select)` and doesn't flatten list columns; the flattened
     side-table in the portal is a workaround. Fix platform-side, retire
     the workaround, re-test the per-facility union case.
   - The data global-fallback gate question: tables/configs honoring
     `global_repo_access` like the module loader does (flag already on the
     execution context; README calls data fallback "ungated today").
   - Policy ergonomics under real use (policies referencing `is_external`,
     debugging denied rows, validation UX).
5. **Remaining solutions shakeout items** (tracked in the solutions plan):
   watch-in-solution-workspace refusal, the open UI/UX findings.
6. **Handoff**: refresh the client handoff bundle (runbook gains the
   `everyone` tier + migration step) — bundle and runbook live outside this
   repo.

## Note on pre-existing public-repo mentions

The 2026-05-21 table-policies spec/plan on `main` reference the client by
acronym (merged before the no-client-content rule). Decide separately:
forward-edit those docs to genericize, or accept (acronym only, no
identifying detail).
