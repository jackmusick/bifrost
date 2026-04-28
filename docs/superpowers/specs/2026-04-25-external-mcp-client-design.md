# External MCP Client (RFC)

**Date:** 2026-04-25 · **Status:** Draft

Bifrost serves MCP via `mcp_server/`. This proposes the symmetric **client** capability: register external MCP servers as integrations and let Bifrost agents call their tools.

## First question: is this already on your roadmap?

Asking before describing the design — if you've already got something in flight or have a different shape in mind, point me at it and I'll align rather than duplicate.

## Problem

`resolve_agent_tools()` in `agent_helpers.py` builds an agent's toolset from three sources: system tools, workflows, delegated agents. All in-process. There's no path to call a tool hosted on an external MCP server.

The MCP ecosystem has produced a lot of useful servers in the last six months (M365 Admin, Slack, Atlassian, Salesforce, plus vendor and homegrown ones). An operator today has to mirror each as Bifrost workflows — which doesn't scale, a 77-tool server is 77 mirrored workflows — or skip Bifrost and use Claude Desktop / Code directly. SpireTech has a concrete forcing example: an MCP server fronting HaloPSA with granular per-integration permissions. We want Bifrost agents to call it without standing up a parallel agent stack.

## Design

**Data model — extends existing tables, no parallel infra:**

```sql
ALTER TABLE integrations
  ADD COLUMN kind VARCHAR(50) NOT NULL DEFAULT 'standard';
-- 'standard' (today's behavior) | 'external_mcp'

CREATE TABLE external_mcp_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    qualified_name VARCHAR(511) NOT NULL,    -- e.g. 'halopsa.list_tickets'
    description TEXT,
    input_schema JSONB NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (integration_id, name)
);
```

OAuth credentials reuse `oauth_providers`. Base URL goes in `configs`. Per-agent grants either reuse `agent.tools` if it can be made polymorphic, or add a small association table.

**Code surface (~1.5k LOC):** new `api/src/services/mcp_client/` (Streamable-HTTP client wrapper, catalog sync, dispatch, registration validation), a new ORM + alembic migration, ~30 lines added to `resolve_agent_tools()` for a fourth source, ~40 lines in `agent_executor.py` to branch dispatch on tool kind, new endpoints under `/integrations` for catalog refresh, plus `ExternalMcpForm.tsx` and a tweak to `AgentToolPicker.tsx`.

**Run-time flow:** LLM emits `tool_use` with `name="halopsa.list_tickets"`, executor sees the qualified-name prefix, dispatches via the MCP client (which gets a token from `oauth_provider`'s existing client_credentials helper, reuses it until expiry, posts the tool call), result is normalized to the same envelope as a workflow tool result. Errors become tool-call errors, not fatal run errors.

**Audit:** each call logs `(agent_run_id, integration_id, tool_name, status, duration)` via the same path workflow tools use, with `tool_kind="external_mcp"`.

## Access control — two layers, either can deny

| Layer | Question | Where |
|---|---|---|
| Bifrost | Can THIS agent invoke THIS tool? | per-agent grant, checked at `resolve_agent_tools` time |
| Remote MCP server | Can THIS credential perform THIS scope? | the remote's own policy — returns 403 / tool error |

A misconfiguration on either side is caught by the other. The remote server is treated as untrusted (responses validated against declared schema, size capped, timeouts enforced) but its tool definitions are trusted for naming/schema.

## Non-goals

Streamable HTTP only (no SSE/stdio). No tool-call streaming back through the LLM. No per-user OAuth-on-behalf-of (integration credentials are shared across agents that use it, same as today). Bifrost is a consumer, not a registry/proxy of other MCP servers.

## Security highlights

Encrypted-at-rest credentials reuse `oauth_providers.encrypted_client_secret` — no new crypto path. Token refresh via the existing `oauth_token_refresh` scheduler. Optional `MCP_CLIENT_ALLOWED_HOSTS` env var to restrict outbound destinations. Default 256 KB result cap, 30 s wall-clock per call (overridable per-integration via `configs`). Touches the executor, agent helpers, and audit log → expects manual sensitive-paths review per CONTRIBUTING.md.

## Migration / compat

`kind` defaults to `'standard'`, existing integrations unchanged. `external_mcp_tools` is purely additive. API responses gain a `kind` field; clients that ignore unknown fields are unaffected. Reversible.

## Alternatives considered

- **Mirror each remote tool as a workflow.** Doesn't scale; remote tool changes become workflow PRs.
- **Single dispatcher tool** (`mcp_call(server, tool, args)`). Collapses N tool schemas into one, LLM can't reason about specific tools at planning time, breaks per-tool grants.
- **Delegate to Anthropic's `mcp_servers=` parameter on `messages.create`.** Requires public exposure of every MCP server, locks tool dispatch into Anthropic's infra, bypasses Bifrost's grant gate. Could be a future per-integration fall-back option for operators who don't want to host the client.

## Open questions

1. `kind` column shape — plain VARCHAR vs normalized table vs JSON metadata. I'd default to plain.
2. Per-org vs per-deployment registration — `integration.organization_id` (existing) seems right but want to confirm for multi-tenant deployments.
3. Catalog refresh — manual button + ~24h scheduled, per-integration or global?
4. Polymorphic `agent.tools` vs new association table — depends on whether the existing `Tool` model already wants a discriminator.
5. Tool name namespacing — `<integration.name>.<tool>` (proposed) vs `<integration.id>:<tool>` (rename-stable, uglier).

## Delivery

Single feature PR, branch + tests + UI together. Smaller incremental review can happen by section if you'd prefer it that way, but I'd rather not split it into 4 PRs over 2 weeks unless you specifically want it that way.

## Asking for

Direction on (a) is this already planned, (b) overall approach, (c) any of the open questions you have strong opinions on. If green-lit I'll start the implementation against `upstream/main`.
