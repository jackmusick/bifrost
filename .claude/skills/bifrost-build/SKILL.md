---
name: bifrost:build
description: Build Bifrost workflows, forms, and apps. Use when user wants to create, debug, or modify Bifrost artifacts. Supports SDK-first (local dev + git) and MCP-only modes.
---

# Bifrost Build

Create and debug Bifrost artifacts.

When local practice and upstream expectations diverge, align the build or test pattern to upstream first. Do not preserve drift by expanding local harness assumptions unless that surface is part of the upstream-supported workflow.

## First: Check Prerequisites

```bash
echo "SDK: $BIFROST_SDK_INSTALLED | Login: $BIFROST_LOGGED_IN | MCP: $BIFROST_MCP_CONFIGURED"
echo "Source: $BIFROST_HAS_SOURCE | Path: $BIFROST_SOURCE_PATH | URL: $BIFROST_DEV_URL"
```

**If SDK or Login is false/empty:** Direct user to run `/bifrost:setup` first.

## Step 1: Download Platform Docs (Once Per Session)

All platform reference (SDK, forms, agents, apps, tables, manifest YAML formats) is in a single document. Fetch it once and grep locally.

**SDK-First:**
```bash
mkdir -p /tmp/bifrost-docs
bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt
```

**MCP-Only:** Call `get_docs` tool, save the result to `/tmp/bifrost-docs/llms.txt`.

Then use `Grep/Read` on `/tmp/bifrost-docs/llms.txt` whenever you need reference.

## Step 2: Detect Development Mode

**Auto-detect:** If a `.bifrost/` directory exists in the workspace, use **SDK-First**. Otherwise, **MCP-Only**. Only ask the user if ambiguous.

## SDK-First Mode

### Principles

- **Local first.** Use Glob, Read, and Grep for discovery when source is available.
- **Treat `.bifrost/` as generated workspace metadata.** It is useful for discovery and transitional sync workflows, but it is not a safe long-term source-of-truth assumption in this fork.
- **Write locally, sync intentionally.** Prefer entity files and normal source code as the primary authored surface. If a local watch/sync flow still requires manifest updates for new entities, keep them minimal and expect regeneration/import to overwrite them.
- **Never use MCP for discovery** (`list_*`), reading code (`list_content`, `search_content`), or docs when a local workspace exists.

### Before Building

1. **What triggers this?** (webhook, form, schedule, manual)
2. **If webhook:** Get sample payload from user
3. **What existing entities already cover this space?** Check source files first, then inspect generated `.bifrost/` manifests only as needed
4. **If migrating from Rewst:** Use `/rewst-migration` skill

### Start Watch Mode

Before any build work, ensure `bifrost watch` is running:

```bash
pgrep -f 'bifrost watch' > /dev/null 2>&1 && echo "RUNNING" || echo "NOT RUNNING"
```

If not running, start it as a background Bash task: `bifrost watch`

### Discovery: Read Local Files

| To find... | Read this file |
|---|---|
| Workflows/tools/data_providers | source files first, then `.bifrost/workflows.yaml` if needed |
| Forms and linked workflows | `forms/*.form.yaml`, then `.bifrost/forms.yaml` if needed |
| Agents and tool assignments | `agents/*.agent.yaml`, then `.bifrost/agents.yaml` if needed |
| Apps | `apps/*/app.yaml`, then `.bifrost/apps.yaml` if needed |
| Organizations | platform data first, `.bifrost/organizations.yaml` only if present |
| Integrations | source + platform config, then `.bifrost/integrations.yaml` if needed |
| Tables | `.bifrost/tables.yaml` if present |
| Events | `.bifrost/events.yaml` if present |

For YAML field formats, grep `/tmp/bifrost-docs/llms.txt` for `ManifestWorkflow`, `ManifestForm`, etc.

### UUID Generation (CRITICAL)

**Generate ALL entity UUIDs BEFORE writing files.** Cross-references must be valid at write time.

```python
import uuid
wf_id = str(uuid.uuid4())
form_id = str(uuid.uuid4())
agent_id = str(uuid.uuid4())
```

Then use these IDs in all files — workflow code, manifest entries, form/agent YAML cross-references.

### Creation Flow

1. Generate UUIDs for all new entities
2. Write entity files (workflow `.py`, form `.form.yaml`, agent `.agent.yaml`, app `.tsx`)
3. If the chosen local sync path still requires manifest entries for new entities, update the generated `.bifrost/*.yaml` files minimally and expect later regeneration/import
4. Sync through `bifrost watch`, `bifrost push`, or `bifrost sync` as appropriate for the current workspace flow
5. Test workflows: `bifrost run <file> --workflow <name> --org <UUID> --params '{...}'`
6. When happy: `git add && git commit && git push`

### CLI Commands Reference

| Command | Purpose |
|---------|---------|
| `bifrost watch` | Primary dev command — starts interactive watch session, syncs file changes on save |
| `bifrost sync` | One-shot bidirectional sync — **interactive TUI, user must run manually** |
| `bifrost run <file> -w <name> --org <UUID>` | Execute workflow in specific org context |
| `bifrost api <METHOD> <path>` | Bifrost platform API client ONLY — inspect executions, validate apps, check platform state. NOT for third-party APIs. |
| `bifrost push` | One-shot upload — **interactive TUI, user must run manually** |
| `bifrost pull` | One-shot download — **interactive TUI, user must run manually** |
### Platform Operations

| Need | Command |
|------|---------|
| Run a workflow | `bifrost api POST /api/workflows/{id}/execute '{"workflow_id":"...","input_data":{...},"sync":true}'` |
| Check execution logs | `bifrost api GET /api/executions/{id}` |
| List executions | `bifrost api GET /api/executions` |
| Verify platform state | `bifrost api GET /api/workflows` (only for debugging sync divergence) |
| Validate an app | `bifrost api POST /api/applications/{id}/validate` |
| Download platform docs | `bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt` |

### `bifrost api` Boundaries (CRITICAL)

`bifrost api` is ONLY for the Bifrost platform API. It does NOT proxy to third-party integration APIs.

- **Valid**: `/api/executions/{id}`, `/api/workflows`, `/api/applications/{id}/validate`, `/api/llms.txt`
- **Invalid**: `/Client/237` (HaloPSA), `/companies` (Pax8), or any non-`/api/` path

**If you don't know whether an endpoint exists, check first:**
1. Download the docs if not already cached: `bifrost api GET /api/llms.txt > /tmp/bifrost-docs/llms.txt`
2. Grep for the endpoint: `grep -i "endpoint_name" /tmp/bifrost-docs/llms.txt`
3. If it's not documented, it doesn't exist — do NOT guess URL patterns

**To call a third-party integration API** (HaloPSA, Pax8, NinjaOne, etc.):
- Write a small test workflow using the SDK module and run it with `bifrost run`
- Never try to route integration API calls through `bifrost api`

### MCP Tools (creation and events only)

| Need | Tool |
|------|------|
| Create a form | `create_form` |
| Create an app | `create_app` |
| Create an agent | `create_agent` |
| Event triggers | `create_event_source`, `create_event_subscription` |
| RAG search | `search_knowledge` |
| Validate an app | `validate_app` or `bifrost api POST /api/applications/{id}/validate` |
| App dependencies | `get_app_dependencies`, `update_app_dependencies` |

### Syncing

**`bifrost watch` handles all syncing.** The agent NEVER runs sync commands directly.

#### NEVER run these commands from the agent (CRITICAL)

`bifrost sync`, `bifrost push`, and `bifrost pull` all launch an **interactive TUI** for conflict resolution. They will hang or fail when run non-interactively. The agent must NEVER execute these commands.

#### Sync rules

1. **Before writing any files**, verify `bifrost watch` is running:
   ```bash
   pgrep -f 'bifrost watch' > /dev/null 2>&1 && echo "RUNNING" || echo "NOT RUNNING"
   ```
2. **If watch is running**: Write files locally. Only touch `.bifrost/*.yaml` for new entities when the current watch/import flow requires it, and treat those edits as transitional metadata rather than durable authored source.
3. **If watch is NOT running**: Tell the user: "Please run `bifrost watch` in a terminal first." **Do NOT write files or attempt to sync until the user confirms watch is running.**
4. **If the user asks to sync manually** (push/pull/sync): Tell them to run the command themselves in their terminal since it requires interactive TUI input.
5. **GitHub/git-integrated deployment is deprecated.** Use normal local git for source control, and use `bifrost watch`, `bifrost sync`, or explicit platform image deploys as appropriate.

#### What about deploying without watch?

If the user doesn't want to run watch and asks to deploy, tell them to run `bifrost sync` or `bifrost push` in their own terminal. The agent cannot do this for them.

Preflight (runs automatically in watch): manifest YAML, file existence, Python syntax, ruff linting, UUID cross-references, orphan detection.

### Manifest Transition Rule

- Do not build new workflow habits around hand-authoring `.bifrost/*.yaml`.
- In this fork, `.bifrost/` may still appear in local watch/sync workflows, but the platform treats it as generated/system-managed state.
- Prefer source files, platform APIs, and CLI sync operations over manual manifest editing whenever possible.
- See `docs/plans/2026-03-27-manifest-transition-guidance.md` before doing more repo-model work.

### Workflow Policy Rule

- Do not treat workflow parameter defaults as the durable home for operational policy.
- Use workflow parameters for execution-time overrides and one-off runs.
- Put persistent operator-managed policy into Bifrost-managed configuration, ideally through an app-owned configuration surface.
- Preferred pattern:
  - workflow reads policy from `bifrost.config`
  - app provides the operator UI to view/edit that policy
  - workflow parameters remain available to override config temporarily
- Examples of policy that should not be hard-coded into workflow defaults:
  - excluded organization lists
  - standard admin rosters
  - special-case allowed admin lists
  - rollout target lists

## MCP-Only Mode

Best for: quick iterations, non-developers, no local git repo.

1. Call `get_docs` to get platform reference
2. Use `list_workflows`, `list_integrations`, etc. for discovery
3. Write via `replace_content`, register with `register_workflow`. For forms/apps: `create_form`, `create_app`.
4. Test via `execute_workflow` or preview URL
5. Check logs via `get_execution`
6. Iterate with `patch_content` / `replace_content`

Prefer `patch_content` for surgical edits. Use `replace_content` for full file rewrites.

## Building Apps

### Design Workflow

Before writing any app code, design what you're building.

**New app:**
1. Ask: "What should this app feel like? Any products you'd like it inspired by?"
2. If a product is named, **describe the specific visual patterns** that define it — not abstract qualities ("clean", "modern") but concrete observations: "full-height dark sidebar with icon+label nav items, content area with a sticky toolbar row above the main editor, right panel for live preview with a simulated email client frame, generous whitespace between sections, muted borders instead of heavy dividers."
3. Write a visual spec for each key screen: what elements exist, their spatial relationships, which are fixed vs. scrollable, where the visual weight sits, how the eye flows. This is the design — get it right before writing code.
4. Plan `styles.css` for visual identity — color palette, typography scale, spacing rhythm, dark mode variants.
5. Decide what's a custom component vs. pre-included shadcn. shadcn is for standard interactions (settings forms, confirmation dialogs, data tables). Custom components are for the interactions that define the app's identity — a project management app needs a custom kanban board, not a `<Table>`; an email tool needs a simulated inbox, not a textarea in a split pane.
6. Then start building.

**Existing app:**
1. Read existing `styles.css` and `components/` first
2. Match established design patterns

### Critical App Rules

1. **Imports:** `import { Button, useWorkflowQuery, useState } from "bifrost"` — everything from one import
2. **Root layout:** `_layout.tsx` uses `<Outlet />`, NOT `{children}`
3. **Workflow hooks:** Always use UUIDs, never names — `useWorkflowQuery("uuid-here")`
4. **Fixed-height container:** Your app renders in a fixed-height box — manage your own scrolling
5. **Custom CSS:** `styles.css` at app root, dark mode via `.dark` selector
6. **Dependencies:** Declare npm packages in `app.yaml` (max 20, loaded from esm.sh)
7. **Custom components:** Components in `components/` are auto-injected — do NOT write import statements for them. Just use `<MyComponent />` directly. Only import from `"bifrost"` or npm package names.

For component lists, hooks API, CSS examples, sandbox constraints — grep `/tmp/bifrost-docs/llms.txt`.

### App Workflow (SDK-First)

1. Write files in `apps/{slug}/`
2. If the current local sync path requires it, reconcile the generated app manifest metadata
3. `bifrost watch` syncs file changes (auto-validates app dirs after each push)
4. Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`
5. Validate with `bifrost push apps/{slug} --validate`

### App Workflow (MCP-Only)

1. `create_app(name="My App")` — scaffolds `_layout.tsx` + `pages/index.tsx`
2. Edit with `patch_content` / `replace_content`
3. Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`
4. Validate with `validate_app(app_id)`

## Testing

- **Workflows (local):** `bifrost run <file> --workflow <name> --params '{...}'`
- **Workflows (remote):** `bifrost api POST /api/workflows/{id}/execute '{"workflow_id":"...","input_data":{...},"sync":true}'`
- **Forms:** `$BIFROST_DEV_URL/forms/{form_id}`
- **Apps:** Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`, publish with `publish_app`, live at `$BIFROST_DEV_URL/apps/{slug}`
- **Webhooks:** `curl -X POST $BIFROST_DEV_URL/api/hooks/{source_id} -H 'Content-Type: application/json' -d '{...}'`
- **Logs:** `bifrost api GET /api/executions/{id}`

## Debugging

1. Check execution logs: `bifrost api GET /api/executions/{id}`
2. Check `bifrost watch` output for sync errors
3. Verify platform state: `bifrost api GET /api/workflows` (only if sync divergence suspected)

### When Errors Suggest System Bugs

**If BIFROST_HAS_SOURCE is true:**
> "This appears to be a backend bug ({error description}). I have access to the Bifrost source code at $BIFROST_SOURCE_PATH. Would you like me to debug and fix this on the backend?"

**If BIFROST_HAS_SOURCE is false:**
> "This appears to be a backend bug ({error description}). Please report this to the platform team with these details: {error details}"

## Session Summary

At end of session, provide:

```markdown
## Session Summary

### Completed
- [What was built/accomplished]

### System Bugs Fixed (if source available)
- [Bug] -> [Fix] -> [File]

### Notes for Future Sessions
- [Relevant context]
```
