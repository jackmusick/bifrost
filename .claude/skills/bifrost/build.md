---
name: build
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

## Development Mode

**Auto-detect:** If a `.bifrost/` directory exists in the workspace, you are in **SDK-First** mode. Otherwise, use **MCP-Only** mode. Only ask the user if the situation is ambiguous.

### SDK-First (Local Development)

Best for: developers who want git history, local testing, code review before deploying.

**Requirements:** Git repository, Bifrost SDK installed, GitHub sync configured in platform.

**Discovery: ALWAYS read local `.bifrost/*.yaml` files first.** These are the source of truth — the platform is synced FROM them. Never call MCP discovery tools (`list_workflows`, `list_integrations`, `list_forms`, etc.) when the same data is in local YAML.

| To find... | Read this file | NOT this MCP tool |
|---|---|---|
| Registered workflows/tools/data_providers | `.bifrost/workflows.yaml` | ~~list_workflows~~ |
| Integration config + data provider refs | `.bifrost/integrations.yaml` | ~~list_integrations~~ |
| Forms and their linked workflows | `.bifrost/forms.yaml` + `forms/*.form.yaml` | ~~list_forms~~ |
| Agents and their tool assignments | `.bifrost/agents.yaml` + `agents/*.agent.yaml` | ~~list_agents~~ |
| Organizations | `.bifrost/organizations.yaml` | ~~list_organizations~~ |
| Tables | `.bifrost/tables.yaml` | ~~list_tables~~ |
| Event sources and subscriptions | `.bifrost/events.yaml` | ~~list_event_sources~~ |
| Apps | `.bifrost/apps.yaml` + `apps/*/app.yaml` | ~~list_apps~~ |

**When to use MCP tools in SDK-First mode:**
- `execute_workflow` — to test a workflow on the platform
- `get_execution` — to check execution logs
- `get_workflow_schema`, `get_sdk_schema` — to look up SDK docs
- `list_workflows` etc. — ONLY to verify platform state diverged from local (post-sync debugging)

**Creation flow:**
1. Write workflow/form/agent files locally in the git repo
2. Add entries to `.bifrost/*.yaml` manifest files
3. Test workflows locally with `bifrost run <file> <function> --params '{...}'`
4. Iterate until happy with the result
5. `git add && git commit && git push` to push to GitHub
6. `bifrost sync` to sync with the platform (runs preflight, pulls/pushes changes)
7. If conflicts: show them, help user resolve with `bifrost sync --resolve`
8. If preflight errors: fix issues (syntax, broken refs) and re-sync
9. Verify deployment with MCP tools (`execute_workflow`, `get_execution`)

### MCP-Only (Remote Development)

Best for: quick iterations, non-developers, working without a local git repo.

**Discovery: Use MCP tools** (`list_workflows`, `list_integrations`, etc.) since there are no local files.

**Flow:**
1. Understand the goal
2. Read SDK docs via `get_workflow_schema`, `get_sdk_schema`
3. Create artifact via MCP (`create_workflow`, `create_form`, `create_app`)
4. Test via `execute_workflow` or access preview URL
5. Check logs via `get_execution` if issues
6. Iterate with `patch_content` or `replace_content`

## Workspace Structure (SDK-First)

The git repo mirrors the platform's `_repo/` storage in S3:

```
my-workspace/
  .bifrost/                        # Manifest (configuration as code)
    organizations.yaml
    roles.yaml
    workflows.yaml                 # Workflow identity, org, roles, runtime config
    forms.yaml                     # Form identity, org, roles
    agents.yaml                    # Agent identity, org, roles
    apps.yaml                      # App identity, org, roles
    integrations.yaml              # Integration definitions + config schema
    configs.yaml                   # Config values (secrets redacted)
    tables.yaml                    # Table schema declarations
    events.yaml                    # Event sources + subscriptions
    knowledge.yaml                 # Namespace declarations
  workflows/
    onboard_user.py                # Workflow code
    ticket_classifier.py
  forms/
    {uuid}.form.yaml               # Form definition (fields, workflow ref)
  agents/
    {uuid}.agent.yaml              # Agent definition (prompt, tools, channels)
  apps/
    my-dashboard/
      app.json                     # App metadata
      pages/index.tsx              # App code files
  modules/
    shared/utils.py                # Shared Python modules
```

### Manifest is Configuration as Code

The `.bifrost/*.yaml` files declare **all platform entities**, their UUIDs, org bindings, roles, and runtime config. Entity files (forms, agents, workflows) contain the **portable definition** only.

| Data | Location | Examples |
|------|----------|---------|
| Entity identity | `.bifrost/*.yaml` | id, path, function_name, type |
| Org/role binding | `.bifrost/*.yaml` | organization_id, roles, access_level |
| Runtime config | `.bifrost/*.yaml` | endpoint_enabled, timeout_seconds |
| Portable definition | Entity file | form fields, agent prompt, workflow code |
| Cross-references | Entity file | workflow UUID in form, tool UUIDs in agent |

## UUID Generation (CRITICAL for SDK-First)

**All entity UUIDs must be generated BEFORE writing files.** When creating related entities, generate UUIDs upfront so cross-references are valid at write time.

Example: creating a workflow + form + agent that uses it:

```python
import uuid
wf_id = str(uuid.uuid4())   # Generate first
form_id = str(uuid.uuid4())
agent_id = str(uuid.uuid4())
```

Then use these IDs in all files:
1. Write `workflows/my_workflow.py` with the code
2. Write `.bifrost/workflows.yaml` with `id: {wf_id}`
3. Write `forms/{form_id}.form.yaml` with `workflow_id: {wf_id}`
4. Write `.bifrost/forms.yaml` with `id: {form_id}`
5. Write `agents/{agent_id}.agent.yaml` with `tool_ids: [{wf_id}]`
6. Write `.bifrost/agents.yaml` with `id: {agent_id}`

**Preflight catches missing IDs as a safety net**, but generating upfront avoids errors.

## Entity YAML Formats

### Workflow Manifest Entry (`.bifrost/workflows.yaml`)

```yaml
workflows:
  onboard_user:                    # Key = human-readable name
    id: "f8a1b3c2-..."
    path: workflows/onboard_user.py
    function_name: onboard_user
    type: workflow                 # workflow | tool | data_provider
    organization_id: "9a3f2b1c-..."  # null for global
    roles: ["b7e2a4d1-..."]
    access_level: role_based       # role_based | authenticated | public
    endpoint_enabled: false
    timeout_seconds: 1800
```

Workflow code is a standard `.py` file with `@workflow`/`@tool`/`@data_provider` decorators.

### Form (`forms/{uuid}.form.yaml`)

```yaml
name: Onboarding Form
description: New employee onboarding request
workflow_id: "f8a1b3c2-..."        # UUID reference to workflow
launch_workflow_id: null           # Optional startup workflow
form_schema:
  fields:
    - name: employee_name
      type: text
      label: Employee Name
      required: true
    - name: department
      type: select
      label: Department
      options:
        - { label: Engineering, value: Engineering }
        - { label: Sales, value: Sales }
    - name: license_type
      type: select
      label: M365 License
      default_value: E3
      options:
        - { label: E1, value: E1 }
        - { label: E3, value: E3 }
        - { label: E5, value: E5 }
```

**Form manifest entry** (`.bifrost/forms.yaml`):
```yaml
forms:
  Onboarding Form:
    id: "d2e5f8a1-..."
    path: forms/d2e5f8a1-....form.yaml
    organization_id: "9a3f2b1c-..."
    roles: ["b7e2a4d1-..."]
```

### Agent (`agents/{uuid}.agent.yaml`)

```yaml
name: Support Agent
description: Handles tier 1 support tickets
system_prompt: You are a helpful support agent...
channels:
  - chat
llm_model: claude-sonnet-4-5-20250929
llm_temperature: 0.7
llm_max_tokens: 4096
tool_ids:                          # Workflow UUIDs this agent can call
  - "a2b4c6d8-..."
  - "e1f2a3b4-..."
delegated_agent_ids: []            # Other agents it can delegate to
knowledge_sources:                 # Knowledge namespace names
  - tickets
system_tools:                      # Built-in tools
  - http
```

**Agent manifest entry** (`.bifrost/agents.yaml`):
```yaml
agents:
  Support Agent:
    id: "c3d4e5f6-..."
    path: agents/c3d4e5f6-....agent.yaml
    organization_id: "9a3f2b1c-..."
    roles: ["b7e2a4d1-..."]
```

### App (`apps/{slug}/app.json`)

```json
{
  "id": "<uuid>",
  "name": "Dashboard",
  "slug": "my-dashboard",
  "description": "Client overview dashboard"
}
```

App pages and components are sibling files in the same directory.

## Sync Workflow (SDK-First)

### Creating New Entities

1. Generate UUID(s) for all new entities
2. Write entity files (workflow `.py`, form `.form.yaml`, agent `.agent.yaml`)
3. Add entries to `.bifrost/*.yaml` manifest files with the UUIDs
4. `git add . && git commit -m "Add onboarding workflow and form"`
5. `git push`
6. `bifrost sync`

### What `bifrost sync` Does

1. **Preview** — fetches remote state, computes diff (pull/push), runs preflight
2. **Preflight validation** — checks syntax, linting, cross-references, manifest validity
3. **Execute** — if no conflicts, auto-syncs; if conflicts, shows them for resolution

### Preflight Checks

Preflight runs automatically during sync and validates:

| Check | Category | Severity | What it catches |
|-------|----------|----------|-----------------|
| Manifest parse | `manifest` | error | Invalid YAML, missing required fields |
| File existence | `manifest` | error | Manifest references file that doesn't exist |
| Python syntax | `syntax` | error | `SyntaxError` in `.py` files |
| Ruff linting | `lint` | warning | Style violations (non-blocking) |
| UUID references | `ref` | error | Form references non-existent workflow |
| Cross-references | `ref` | error | Broken org/role/integration refs in manifest |
| Orphan detection | `orphan` | warning | Forms referencing workflows not in manifest |
| Secret configs | `health` | warning | Config values that need manual setup |
| OAuth setup | `health` | warning | OAuth providers needing credentials |

**Errors block sync. Warnings are informational.**

### Resolving Conflicts

```bash
bifrost sync --preview                    # Preview only
bifrost sync --resolve workflows/billing.py=keep_remote
bifrost sync --resolve a.py=keep_local --resolve b.py=keep_remote
bifrost sync --confirm-orphans            # Acknowledge orphan warnings
```

## Before Building

Clarify with the user:
1. **Which organization?** Check `.bifrost/organizations.yaml` (SDK-First) or `list_organizations` (MCP-Only)
2. **What triggers this?** (webhook, form, schedule, manual)
3. **If webhook:** Get sample payload
4. **What integrations?** Check `.bifrost/integrations.yaml` (SDK-First) or `list_integrations` (MCP-Only)
5. **Error handling requirements?**
6. **If migrating from Rewst:** Use `/rewst-migration` skill for cutover guidance

## MCP Tools Reference

> **SDK-First mode:** Skip the Discovery tools below — read `.bifrost/*.yaml` files instead. Use MCP only for Execution, Events, and SDK docs.

### Discovery (MCP-Only mode, or post-sync verification)
- `list_workflows` - List workflows (filter by query, category, type)
- `get_workflow` - Get workflow metadata by ID or name
- `get_workflow_schema` - Workflow decorator documentation
- `get_sdk_schema` - Full SDK documentation
- `list_integrations` - Available integrations and auth status
- `list_forms` - List forms with URLs
- `get_form_schema` - Form structure documentation
- `list_apps` - List App Builder applications
- `get_app_schema` - App structure documentation
- `get_data_provider_schema` - Data provider patterns
- `get_agent_schema` - Agent structure and channels
- `list_event_sources` - List event sources (webhooks, schedules)
- `get_event_source` - Get event source details
- `list_webhook_adapters` - List available webhook adapters

### Creation (Auto-Validating)
- `create_workflow` - Create workflow, tool, or data provider
- `create_form` - Create a form linked to a workflow
- `create_app` - Create an App Builder application

### Editing
- `list_content` - List files by entity type
- `search_content` - Search code patterns
- `read_content_lines` - Read specific lines
- `patch_content` - Surgical string replacement
- `replace_content` - Replace entire file

### Events
- `list_event_subscriptions` - List subscriptions for an event source
- `create_event_source` - Create event source (webhook or schedule)
- `update_event_source` - Update event source
- `delete_event_source` - Delete event source
- `create_event_subscription` - Link event source to workflow
- `update_event_subscription` - Update subscription
- `delete_event_subscription` - Delete subscription

### Execution
- `execute_workflow` - Execute by workflow ID
- `list_executions` - List recent executions
- `get_execution` - Get execution details and logs

### Organization
- `list_organizations` - List all organizations
- `get_organization` - Get org details
- `list_tables` - List data tables

## Triggering Workflows

Three patterns for connecting triggers to workflows:

### Schedule
```
1. create_event_source(name="Daily Report", source_type="schedule", cron_expression="0 9 * * *", timezone="America/New_York")
2. create_event_subscription(source_id=<id>, workflow_id=<id>, input_mapping={"report_type": "daily"})
```

### Webhook
```
1. create_event_source(name="HaloPSA Tickets", source_type="webhook", adapter_name="generic")
   -> returns callback_url: /api/hooks/{source_id}
2. create_event_subscription(source_id=<id>, workflow_id=<id>, event_type="ticket.created")
3. Configure external service to POST to callback_url
```

### Form
```
1. Sync workflow to platform (bifrost sync or create_workflow)
2. create_form(name="New User", workflow_id=<id>, fields=[...])
   -> returns form URL
```

## Testing

- **Workflows (local):** `bifrost run <file> --workflow <name> --params '{...}'`
- **Workflows (remote):** `execute_workflow` with workflow ID, check `get_execution` for logs
- **Forms:** Access at `$BIFROST_DEV_URL/forms/{form_id}`, submit, check `list_executions`
- **Apps:** Preview at `$BIFROST_DEV_URL/apps/{slug}/preview`, publish with `publish_app`, then live at `$BIFROST_DEV_URL/apps/{slug}`
- **Events (schedule):** Wait for next cron tick, check `list_executions` for the subscribed workflow
- **Events (webhook):** `curl -X POST $BIFROST_DEV_URL/api/hooks/{source_id} -H 'Content-Type: application/json' -d '{...}'`, check `list_executions`

## Debugging

### MCP-First Debugging
1. Check execution logs via `get_execution`
2. Verify integrations with `list_integrations`
3. Test workflows with `execute_workflow`
4. Inspect workflow metadata with `get_workflow`

### When Errors Suggest System Bugs

If an error appears to be a backend bug (not user error or doc issue):

**If BIFROST_HAS_SOURCE is true:**
> "This appears to be a backend bug ({error description}). I have access to the Bifrost source code at $BIFROST_SOURCE_PATH. Would you like me to debug and fix this on the backend?"

**If BIFROST_HAS_SOURCE is false:**
> "This appears to be a backend bug ({error description}). Please report this to the platform team with these details: {error details}"

### Issue Categories
- **Documentation/Schema issue** -> Note for recommendation, work around, continue
- **System bug** -> Detect source access, offer to fix or escalate

## App URLs

- **Preview:** `$BIFROST_DEV_URL/apps/{slug}/preview`
- **Live (after `publish_app`):** `$BIFROST_DEV_URL/apps/{slug}`

## Session Summary

At end of session, provide:

```markdown
## Session Summary

### Completed
- [What was built/accomplished]

### System Bugs Fixed (if source available)
- [Bug] -> [Fix] -> [File]

### Documentation Recommendations
- [Tool/Schema]: [Issue] -> [Recommendation]

### Notes for Future Sessions
- [Relevant context]
```
