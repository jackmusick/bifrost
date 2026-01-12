---
name: bifrost-vibecode-debugger
description: "Debug and improve the Bifrost vibe coding experience. Use this skill when working on Bifrost platform development in Claude Code where you have access to Bifrost source code. Helps identify system bugs vs documentation issues, fix the right thing, and ensure end users have a smooth MCP-only experience."
---

# Bifrost Vibecode Debugger

You are debugging and improving the Bifrost vibe coding experience. You have access to both the **Bifrost MCP server** (like end users) and the **Bifrost source code** (unlike end users).

## Your Mission

End users will build Bifrost artifacts using only MCP tools and documentation. Your job is to:

1. Build things using MCP tools exactly as an end user would
2. When things break, identify WHY and fix the right thing
3. Ensure end users won't hit the same issues

## Critical: Two Types of Failures

### Type 1: System Bug
**The Bifrost backend has an actual bug.**

Example: You create a workflow, and it throws a timezone exception because a database column has the wrong type.

**Action: Fix the source code**
1. Stop the current task
2. Find the bug in Bifrost source code
3. Fix it
4. Restart services: `docker compose restart bifrost-server` (or relevant service)
5. Verify the fix
6. Resume original task

### Type 2: Documentation/Schema Misled You
**You called the MCP tool incorrectly because the docs or schema were wrong or unclear.**

Example: You include a `priority` field when creating a workflow because `get_workflow_schema` mentioned it, but that field doesn't actually exist.

**Action: Recommend documentation updates**
1. Stop the current task
2. Identify exactly what was misleading
3. Note the specific file/tool that needs updating
4. Propose the fix (but don't necessarily implement it now)
5. Work around the issue to continue
6. At end of session, summarize all doc recommendations

This distinction matters because end users can't fix system bugs, but they WILL be misled by bad documentation.

## MCP Tools Reference

### Discovery Tools
- `list_workflows` - List all registered workflows (filter by query, category, or type)
- `get_workflow` - Get detailed metadata for a specific workflow
- `get_workflow_schema` - Documentation about workflow decorators and structure
- `get_sdk_schema` - Full SDK documentation (modules, decorators, error classes) - generated from source
- `list_integrations` - Show available integrations and auth status
- `list_forms` - List all forms with URLs
- `get_form_schema` - Documentation about form structure and field types
- `get_data_provider_schema` - Documentation about data provider patterns
- `list_apps` - List App Builder applications
- `get_app` - Get app metadata and page list (NOT full components)
- `get_app_schema` - Documentation about app structure and components
- `search_knowledge` - Search the Bifrost knowledge base

**Note:** Data providers are workflows with `type='data_provider'`. Use `list_workflows` to find them.

### Agent Tools
- `list_agents` - List all accessible agents
- `get_agent` - Get agent details by ID or name
- `create_agent` - Create a new AI agent with system prompt
- `update_agent` - Update agent properties
- `delete_agent` - Soft-delete an agent (deactivate)
- `get_agent_schema` - Documentation about agent structure and channels

### Organization Tools (Platform Admin Only)
- `list_organizations` - List all organizations in the platform
- `get_organization` - Get organization details by ID or slug
- `create_organization` - Create a new organization

### Table Tools
- `list_tables` - View tables (filtered by org for non-admins)
- `get_table` - Get table details and schema
- `create_table` - Create tables with explicit scope (platform admin only)
- `update_table` - Update table properties including scope (platform admin only)
- `get_table_schema` - Documentation about table structure and column types

### Creation Tools (Auto-Validating)
- `create_workflow` - Create workflow, tool, or data provider (validates automatically)
- `create_form` - Create a form (validates automatically, supports scope param)
- `create_app` - Create an app (validates automatically, supports scope param)

### App Builder Tools
See **App Builder Tool Hierarchy** section below for granular app management tools.

### File Operations
- `list_files` - List files and directories in workspace
- `read_file` - Read a file from workspace
- `write_file` - Write content to a file (for non-platform artifacts)
- `delete_file` - Delete a file or directory
- `search_files` - Search for text patterns across files
- `create_folder` - Create a new folder

### Execution Tools
- `execute_workflow` - Execute a workflow by ID
- `list_executions` - List recent executions
- `get_execution` - Get execution details and logs

## Artifact Types

| Artifact | Creation Method | Schema Tool | Notes |
|----------|-----------------|-------------|-------|
| Workflow | `create_workflow` | `get_workflow_schema` | Auto-validates |
| Tool | `create_workflow` | `get_workflow_schema` | Auto-validates |
| Data Provider | `create_workflow` | `get_data_provider_schema` | Auto-validates |
| Form | `create_form` | `get_form_schema` | Auto-validates |
| App | App-level tools | `get_app_schema` | See tool hierarchy |
| Agent | `create_agent` | `get_agent_schema` | Configure AI agents |

## Development Process

1. **Read the schema** - Use appropriate schema tool to understand structure
2. **Explore patterns** - Use `list_workflows` + `get_workflow` for workflow metadata, or `execute_workflow` to test behavior. File tools (`list_files`, `read_file`) are for YOUR workspace files, not for reading existing platform workflows.
3. **Check dependencies** - Use `list_integrations` to verify integrations exist
4. **Create the artifact** - Use `create_workflow`, `create_form`, or app tools (auto-validates)
5. **Test** - Use `execute_workflow` for workflows/tools, verify apps render correctly

**Important:** The `path` field in workflow metadata (e.g., `features/crm/workflows/clients.py`) is informational only - it shows where the workflow was registered from. Workflow source code is NOT accessible via MCP file tools.

**Creation tools auto-validate. Always test execution before declaring something ready.**

## App Builder Tool Hierarchy

Apps are built in pieces, NOT as a single JSON blob. This enables precise, targeted changes.

### App Level
- `list_apps` - List all apps with page counts
- `create_app` - Create app metadata (name, description)
- `get_app` - Get app metadata and page list (NOT full components)
- `update_app` - Update app settings (name, description, navigation)
- `publish_app` - Publish all draft pages to live (only when user requests)

### Page Level
- `create_page` - Add a new page to an app
- `get_page` - Get page with full component tree
- `update_page` - Update page settings/layout
- `delete_page` - Remove a page

### Component Level
- `list_components` - List components on a page (summaries only)
- `create_component` - Add component to a page
- `get_component` - Get component with full props
- `update_component` - Update component props/settings
- `delete_component` - Remove component
- `move_component` - Reposition component

### Draft Mode
Apps stay in draft until explicitly published. Preview at `/apps/{slug}?draft=true`.

**DO NOT publish automatically** - let users preview and test first.

## App Layout Properties

### Component Width
All components support a `width` property:
- `"auto"` (default) - Natural size
- `"full"` - Full width of container
- `"1/2"`, `"1/3"`, `"1/4"`, `"2/3"`, `"3/4"` - Fractional widths

### Layout Gap Defaults
Layouts have sensible gap defaults (set `gap: 0` explicitly for no gap):
- `column`: 16px default
- `row`: 8px default
- `grid`: 16px default

### Layout maxWidth
Constrains the max-width of layout containers. Use for form pages to prevent stretching:
- `"sm"` - 384px
- `"md"` - 448px
- `"lg"` - 512px (recommended for forms)
- `"xl"` - 576px
- `"2xl"` - 672px
- `"full"` / `"none"` - no constraint (default)

**IMPORTANT:** For pages with forms (create/edit pages), ALWAYS use `maxWidth: "lg"` on the root column layout.

### Advanced Layout Features (NEW)

**Scrollable Containers:**
```json
{
  "type": "column",
  "maxHeight": 400,
  "overflow": "auto",
  "children": [...]
}
```

**Sticky Positioning:**
```json
{
  "type": "row",
  "sticky": "top",
  "stickyOffset": 0,
  "children": [...]
}
```

**Custom Styling:**
```json
{
  "type": "card",
  "className": "bg-blue-50 rounded-lg shadow-md",
  "style": {"maxHeight": "300px", "overflowY": "auto"}
}
```

**Repeating Components:**
```json
{
  "type": "card",
  "repeatFor": {
    "items": "{{ workflow.clients }}",
    "itemKey": "id",
    "as": "client"
  },
  "props": {
    "title": "{{ client.name }}",
    "description": "{{ client.email }}"
  }
}
```

### Layout Distribution (NEW)
Controls how children fill available space:
- `distribute: "natural"` (default) - Children keep natural size (standard CSS flexbox)
- `distribute: "equal"` - Children expand equally (flex-1 behavior)
- `distribute: "fit"` - Children fit content, no stretch

**IMPORTANT:** `autoSize` is deprecated - use `distribute` instead.

Example for page header with action button:
```json
{
  "type": "row",
  "justify": "between",
  "align": "center",
  "children": [
    {"type": "heading", "props": {"text": "Customers", "level": 1}},
    {"type": "button", "props": {"label": "Add Customer"}}
  ]
}
```

Example for form page layout:
```json
{
  "type": "column",
  "maxWidth": "lg",
  "gap": 16,
  "children": [
    {"type": "heading", "props": {"text": "New Customer", "level": 1}},
    {"type": "card", "props": {"children": [/* form fields */]}}
  ]
}
```

## Required Testing Workflow

Before declaring any artifact complete, you MUST test it:

### Workflow/Tool Testing
1. Create via `create_workflow` (auto-validates)
2. Verify it appears in `list_workflows`
3. Execute with sample data via `execute_workflow`
4. Verify the result matches expectations

### Data Provider Testing
1. Create via `create_workflow` with type='data_provider' (auto-validates)
2. Verify it appears in `list_workflows` with type='data_provider'
3. Execute via `execute_workflow`
4. Verify output is `[{"label": "...", "value": "..."}]` format

### Form Testing
1. Create via `create_form` (auto-validates)
2. Verify referenced `workflow_id` exists and works

### App Building (Granular Approach)
Apps are built in pieces, NOT as a single JSON blob:
1. `create_app` - Create app metadata (name, description)
2. `create_page` - Add pages one at a time (auto-validates)
3. `create_component` - Add components to pages (auto-validates)
4. `update_component` - Modify individual components
5. Preview and test in draft mode at `/apps/{slug}?draft=true`
6. Only `publish_app` when user explicitly requests it

**DO NOT publish automatically** - let users preview and test first.

### App Testing
1. Verify all `launchWorkflowId` workflows exist and execute correctly
2. Test component layout (defaults should work for most cases)
3. Test in draft mode before publishing

DO NOT report success until all applicable tests pass.

## App Builder Data Loading

Pages load data via workflows, accessed through expressions:

- **`launchWorkflowId`**: Workflow to execute on page mount
- **`launchWorkflowDataSourceId`**: Key name for the result (defaults to workflow name)
- **Access data**: `{{ workflow.<dataSourceId> }}` (direct access - NO `.result` wrapper)
- **DataTable**: Use `dataSource` prop matching the `launchWorkflowDataSourceId`

### Example: List Page with DataTable

```json
{
  "launchWorkflowId": "list_clients",
  "launchWorkflowDataSourceId": "clientsList",
  "layout": {
    "type": "column",
    "children": [{
      "type": "data-table",
      "props": {
        "dataSource": "clientsList",
        "dataPath": "clients",
        "columns": [
          {"key": "name", "label": "Name"},
          {"key": "email", "label": "Email"}
        ]
      }
    }]
  }
}
```

The workflow result is stored under `workflow.clientsList`, and the DataTable reads from `workflow.clientsList.clients`.

## Decorators

Bifrost provides three decorator types:

```python
from bifrost import workflow, tool, data_provider

@workflow
async def my_workflow(name: str) -> dict:
    '''What this workflow does.'''
    return {"result": "value"}

@tool
async def my_tool(query: str) -> dict:
    '''Tool description for AI agents.'''
    return {"answer": "..."}

@data_provider
async def get_options() -> list[dict]:
    '''Returns options for dropdowns.'''
    return [{"label": "Option", "value": "opt"}]
```

Note: `@tool` is an alias for `@workflow(is_tool=True)`. Use `@tool` for cleaner code when creating AI agent tools.

## Workspace Structure

Files are organized in the root of the workspace (no `workspace/` prefix):

```
apps/                       # App Builder applications (by company/org)
├── global/                 # Global apps (available to all orgs)
└── <company>/              # Company-specific apps
features/                   # Feature-based organization (primary work area)
└── <feature-name>/
    ├── workflows/
    ├── services/
    ├── forms/
    └── models.py
shared/                     # Cross-feature resources
├── data_providers/
├── utilities/
└── services/
modules/                    # Auto-generated SDKs (DO NOT EDIT)
```

## Multi-tenancy Awareness

Before creating any resource (tables, apps, forms), ask the user:
1. **Which organization?** Use `list_organizations` to show available options
2. **Global or org-specific?** Clarify scope requirements

If user says "global", explain this makes the resource visible to all organizations.

### Scope Options
- `global` - Visible to all organizations
- `organization` - Visible only to the specified organization (requires `organization_id`)
- `application` - Scoped to a specific app (for tables only, requires `application_id`)

### Multi-tenancy Patterns

**When creating apps or forms:**
```python
# Organization-scoped (default)
create_app(name="My App", scope="organization", organization_id="org-123")

# Global (visible to all orgs)
create_app(name="Shared App", scope="global")
```

**When creating tables:**
```python
# Organization-scoped
create_table(name="Customers", scope="organization", organization_id="org-123")

# Global table
create_table(name="Reference Data", scope="global")

# App-scoped table
create_table(name="App Data", scope="application", application_id="app-456")
```

### Access Control Notes
- **Restricted tools** (org tools, create_table, update_table) are platform-admin only
- **Regular tools** (list_tables, get_table) respect org filtering for non-admins
- Non-admins only see resources in their organization

## Session Summary Template

At the end of each session, provide:

```markdown
## Session Summary

### Completed
- [What was built/accomplished]

### System Bugs Fixed
- [Bug description] → [Fix applied] → [File changed]

### Documentation Recommendations
- **Tool/File**: [get_workflow_schema / SKILL.md / etc.]
- **Issue**: [What was misleading or wrong]
- **Recommendation**: [Specific change to make]

### Notes for Future Sessions
- [Anything relevant for continuity]
```
