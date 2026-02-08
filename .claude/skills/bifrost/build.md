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

Ask the user which development mode they prefer:

### Option 1: SDK-First (Local Development)

Best for: developers who want git history, local testing, code review before deploying.

**Requirements:** Git repository, Bifrost SDK installed, GitHub sync configured in platform.

**Flow:**
1. Write workflow code locally in the git repo
2. Test locally with `bifrost run <file> <function> --params '{...}'`
3. Iterate until happy with the result
4. `git add && git commit && git push` to push to GitHub
5. `bifrost sync` to tell the platform to pull from GitHub
6. If conflicts: show them, help user resolve with `bifrost sync --resolve`
7. Verify deployment with MCP tools (`list_workflows`, `execute_workflow`)
8. For forms/apps: switch to MCP tools (these are platform-only artifacts)

**Limitations:** Forms and apps cannot be developed locally. After syncing workflows, use MCP tools to create forms and apps that reference them.

### Option 2: MCP-Only (Remote Development)

Best for: quick iterations, non-developers, working without a local git repo.

**Flow:**
1. Understand the goal
2. Read SDK docs via `get_workflow_schema`, `get_sdk_schema`
3. Create artifact via MCP (`create_workflow`, `create_form`, `create_app`)
4. Test via `execute_workflow` or access preview URL
5. Check logs via `get_execution` if issues
6. Iterate with `patch_content` or `replace_content`

### Per-Artifact Switching

Even in SDK-first mode, some artifacts require MCP:

| Artifact | SDK-First | MCP-Only |
|----------|-----------|----------|
| Workflow | Local dev + sync | `create_workflow` |
| Data Provider | Local dev + sync | `create_workflow` |
| Tool | Local dev + sync | `create_workflow` |
| Form | MCP only | `create_form` |
| App | MCP only | `create_app` |

When the user needs a form or app in SDK-first mode: "Forms and apps are platform artifacts - I'll create these using the MCP tools against your synced workflows."

## Before Building

Clarify with the user:
1. **Which organization?** Use `list_organizations` to show options, or "global" for platform-wide
2. **What triggers this?** (webhook, form, schedule, manual)
3. **If webhook:** Get sample payload
4. **What integrations?** Use `list_integrations` to verify availability
5. **Error handling requirements?**
6. **If migrating from Rewst:** Use `/rewst-migration` skill for cutover guidance

## MCP Tools Reference

### Discovery
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

## Development Process

1. **Read the schema** - Use appropriate schema tool to understand structure
2. **Check dependencies** - Use `list_integrations` to verify integrations exist
3. **Create the artifact** - Use creation tools (auto-validates)
4. **Test** - Use `execute_workflow` for workflows, preview URL for apps
5. **Iterate** - Use editing tools to refine

**Creation tools auto-validate. Always test execution before declaring something ready.**

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
