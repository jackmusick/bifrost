---
name: bifrost:build
description: Build Bifrost workflows, forms, and apps. Use when user wants to create, debug, or modify Bifrost artifacts. Supports SDK-first (local dev + git) and MCP-only modes.
---

# Bifrost Build

Create and debug Bifrost artifacts.

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

- **Local first.** Use Glob, Read, Grep for discovery. `.bifrost/*.yaml` manifests are the source of truth.
- **Write locally, sync to deploy.** Write files in the git repo. `bifrost watch` auto-syncs to the platform.
- **Never use MCP for discovery** (`list_*`), reading code (`list_content`, `search_content`), or docs when a local workspace exists.

### Before Building

1. **Which organization?** Ask the user which organization they're building for (natural language — don't dump a list of UUIDs). Confirm the org name, then look up the UUID from `.bifrost/organizations.yaml`.
2. **What triggers this?** (webhook, form, schedule, manual)
3. **If webhook:** Get sample payload from user
4. **What integrations?** Read `.bifrost/integrations.yaml`
5. **If migrating from Rewst:** Use `/rewst-migration` skill

#### Organization Context for CLI Commands

- **`bifrost run`**: Use `--org <UUID>` to execute in that org's context
- **`bifrost watch`/`sync`**: Files sync based on manifest bindings, not CLI flags — the manifest's org references in `.bifrost/*.yaml` determine where things land
- **`bifrost api`**: Authenticated API client for inspecting platform state (executions, workflows, etc.). Endpoints that need org context accept it as a parameter in the URL or body, same as the web UI

### Start Watch Mode

Before any build work, ensure `bifrost watch` is running. **The user (not the agent) should start watch** because the initial sync may present interactive conflict resolution (TUI).

```bash
pgrep -f 'bifrost watch' > /dev/null 2>&1 && echo "RUNNING" || echo "NOT RUNNING"
```

If not running, tell the user: "Please run `bifrost watch` in a terminal to start syncing." Wait for confirmation before writing files. Once watch is running, the agent writes files locally and watch auto-pushes them.

### Discovery: Read Local Files

| To find... | Read this file |
|---|---|
| Workflows/tools/data_providers | `.bifrost/workflows.yaml` |
| Forms and linked workflows | `.bifrost/forms.yaml` + `forms/*.form.yaml` |
| Agents and tool assignments | `.bifrost/agents.yaml` + `agents/*.agent.yaml` |
| Apps | `.bifrost/apps.yaml` + `apps/*/app.yaml` |
| Organizations | `.bifrost/organizations.yaml` |
| Integrations | `.bifrost/integrations.yaml` |
| Tables | `.bifrost/tables.yaml` |
| Events | `.bifrost/events.yaml` |

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
3. Add entries to `.bifrost/*.yaml` manifest files
4. Watch mode auto-syncs to platform
5. Test workflows: `bifrost run <file> --workflow <name> --org <UUID> --params '{...}'`
6. When happy: `git add && git commit && git push`

### CLI Commands Reference

| Command | Purpose |
|---------|---------|
| `bifrost watch` | Primary dev command — starts interactive watch session, auto-syncs on save |
| `bifrost sync` | One-shot bidirectional sync with TUI conflict resolution |
| `bifrost run <file> -w <name> --org <UUID>` | Execute workflow in specific org context |
| `bifrost api <METHOD> <path>` | Authenticated API client — inspect executions, validate apps, check platform state |
| `bifrost push` | One-shot upload (alias for sync, use when watch isn't running) |
| `bifrost pull` | One-shot download (alias for sync) |

### Platform Operations

| Need | Command |
|------|---------|
| Run a workflow | `bifrost run <file> -w <name> --org <UUID> --params '{...}'` |
| Run a workflow (remote) | `bifrost api POST /api/workflows/{id}/execute '{"workflow_id":"...","input_data":{...},"sync":true}'` |
| Check execution logs | `bifrost api GET /api/executions/{id}` |
| List executions | `bifrost api GET /api/executions` |
| Verify platform state | `bifrost api GET /api/workflows` (only for debugging sync divergence) |
| Validate an app | `bifrost api POST /api/applications/{id}/validate` |

### MCP Tools (creation and events only)

| Need | Tool |
|------|------|
| Create a form | `create_form` |
| Create an app | `create_app` |
| Create an agent | `create_agent` |
| Event triggers | `create_event_source`, `create_event_subscription` |
| RAG search | `search_knowledge` |
| Validate an app | `validate_app` or `bifrost push --validate` |
| App dependencies | `get_app_dependencies`, `update_app_dependencies` |

### Syncing

**`bifrost watch` handles all syncing.** Do NOT run `bifrost push` or `bifrost git push` while watch is running — watch already pushes every file change automatically.

- `bifrost git push` is for git-integrated deployments (pull + push + entity import). Only use when the user explicitly requests it.
- `bifrost push` is a one-off direct upload. Only use when the user explicitly requests it or watch is not running.

Preflight (runs automatically in watch): manifest YAML, file existence, Python syntax, ruff linting, UUID cross-references, orphan detection.

### Git Source Control

When the user needs to deploy via git (not watch mode), use the `bifrost git` subcommands:

```bash
bifrost git fetch                     # regenerate manifest from DB, fetch remote
bifrost git status                    # show changed files, ahead/behind
bifrost git commit -m "description"   # regenerate manifest, stage, preflight, commit
bifrost git push                      # pull + push + import entities (deploy)
git pull                              # pull platform commits into local repo
bifrost git resolve path=keep_remote  # resolve merge conflicts
bifrost git diff <path>               # show file diff
bifrost git discard <path>            # discard working tree changes
```

Typical workflow: `bifrost git fetch` → `bifrost git commit -m "msg"` → `bifrost git push` → `git pull` (to get the platform's commits locally).

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
8. **Default exports:** Every custom component file in `components/` MUST have a default export
9. **Reserved names:** Never use `$`, `$deps`, `__defaultExport__`, `__exports__` as variable names (reserved by runtime)

For component lists, hooks API, CSS examples, sandbox constraints — grep `/tmp/bifrost-docs/llms.txt`.

### App Resilience Rules (MANDATORY)

These patterns are REQUIRED for every app. Skipping them leads to broken apps.

#### Loading & Error States (every data-fetching page)

```tsx
const { data, isLoading, isError, error } = useWorkflowQuery("uuid");
if (isLoading) return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin" /></div>;
if (isError) return <Alert variant="destructive"><AlertTitle>Error</AlertTitle><AlertDescription>{error ?? "Failed to load"}</AlertDescription></Alert>;
```

#### Null-safe Data Access

Always `data?.items?.map(...)`, never `data.items.map(...)`. Workflow queries return `null` before data loads.

#### Mutation Error Handling

Every `useWorkflowMutation` must handle errors with user feedback:

```tsx
const { execute, isLoading } = useWorkflowMutation("uuid");
const handleSubmit = async () => {
  const result = await execute(params);
  if (result.error) { toast.error(result.error); return; }
  toast.success("Saved");
};
```

#### Dependency Safety

- **Pre-included (no install needed):** `recharts`, `date-fns`, Lucide icons, `clsx`, `tailwind-merge`, `cn`, `format` (date-fns)
- **Testing unknown packages:** Open browser console on a running app and run:
  ```js
  import("https://esm.sh/PACKAGE@VERSION?deps=react@19.1.0,react-dom@19.1.0").then(m => console.log(Object.keys(m)))
  ```
- **Animations:** Always prefer Tailwind (`animate-in`, `transition-all`, `duration-200`) + CSS `@keyframes` in `styles.css` over JS animation libraries (complex dep trees, dual-React risk)
- **Always declare in `app.yaml` dependencies BEFORE importing**
- Failed ESM loads throw descriptive errors on property access — check browser console

#### Custom Component Rules

- Every custom component file MUST have a default export
- Verify `components/{Name}.tsx` exists before using `<Name />`
- Components CAN reference each other (the resolver handles this via topological sort)

### useAppState — Cross-Page State

Zustand-backed `[value, setValue]` tuple, like `useState` but persists across page navigations.

```tsx
const [selectedClient, setSelectedClient] = useAppState("selectedClient", null);
```

**Behavior:**
- Can store anything: primitives, objects, arrays, nested structures
- Scoped to the app session — cleared on browser refresh or switching apps
- NOT persistent storage — for permanent data, use workflows to save/load from DB

**Use cases:** Selected item between list/detail pages, filter/sort preferences, multi-step form data, shopping cart, sidebar collapse state.

**Example — list page sets, detail page reads:**
```tsx
// List page
const [, setSelectedClient] = useAppState("selectedClient", null);
<Button onClick={() => { setSelectedClient(client); navigate("/details"); }}>View</Button>

// Detail page
const [selectedClient] = useAppState("selectedClient", null);
if (!selectedClient) return <Navigate to="/" />;
```

### useUser — Role-Based Access

```tsx
const user = useUser();
// user.id: string
// user.email: string
// user.name: string
// user.roles: string[]
// user.hasRole("Admin"): boolean
// user.organizationId: string
```

**Prescribed patterns:**

Page-level guard (first line of component):
```tsx
if (!user.hasRole("Admin")) return <Navigate to="/" />;
```

Section-level guard:
```tsx
{user.hasRole("Manager") && <AdminPanel />}
```

Declarative guard component:
```tsx
<RequireRole role="Admin" fallback={<Navigate to="/" />}>
  <AdminPage />
</RequireRole>
```

Layout-level guard (protect all child routes):
```tsx
// In _layout.tsx
const user = useUser();
if (!user.hasRole("Admin")) return <Navigate to="/" />;
return <div className="flex h-full"><Sidebar /><Outlet /></div>;
```

### App Workflow (SDK-First)

1. Write files in `apps/{slug}/`
2. Add entry to `.bifrost/apps.yaml`
3. `bifrost watch` auto-syncs (auto-validates app dirs after each push)
4. Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`
5. Fix any validation errors shown in watch output

### App Workflow (MCP-Only)

1. `create_app(name="My App")` — scaffolds `_layout.tsx` + `pages/index.tsx`
2. Edit with `patch_content` / `replace_content`
3. Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`
4. Validate with `validate_app(app_id)`

### Post-Build Validation Checklist (REQUIRED)

After writing all app files, you MUST verify:

1. `_layout.tsx` exists and uses `<Outlet />`
2. `pages/index.tsx` exists
3. Every npm import matches an entry in `app.yaml` dependencies (pre-included packages exempt)
4. Every `useWorkflowQuery`/`useWorkflowMutation` uses a valid UUID from `.bifrost/workflows.yaml`
5. Every `<PascalCase />` JSX tag is either: a shadcn component, a Lucide icon, or a file in `components/`
6. Run validation: `bifrost api POST /api/applications/{id}/validate` (or MCP `validate_app`)
7. Review validation output — fix ALL errors before telling user it's ready
8. Open preview URL and verify pages render (or instruct user to check)

## Testing

- **Workflows (local):** `bifrost run <file> --workflow <name> --org <UUID> --params '{...}'`
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
