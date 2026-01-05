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
- `list_workflows` - List all registered workflows
- `get_workflow` - Get detailed metadata for a specific workflow
- `get_workflow_schema` - Documentation about workflow decorators and structure
- `list_integrations` - Show available integrations and auth status
- `list_forms` - List all forms with URLs
- `get_form_schema` - Documentation about form structure and field types
- `get_data_provider_schema` - Documentation about data provider decorators
- `list_data_providers` - List available data providers
- `list_apps` - List App Builder applications
- `get_app` - Get detailed app definition
- `get_app_schema` - Documentation about app structure and components
- `search_knowledge` - Search the Bifrost knowledge base

### Creation Tools (Auto-Validating)
- `create_workflow` - Create workflow, tool, or data provider (validates automatically)
- `create_form` - Create a form (validates automatically)

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

## Development Process

1. **Read the schema** - Use appropriate schema tool to understand structure
2. **Explore patterns** - Use `list_files` and `read_file` to see existing examples
3. **Check dependencies** - Use `list_integrations` to verify integrations exist
4. **Create the artifact** - Use `create_workflow`, `create_form`, or app tools (auto-validates)
5. **Test** - Use `execute_workflow` for workflows/tools, verify apps render correctly

**Creation tools auto-validate. Always test execution before declaring something ready.**

## App Builder Tool Hierarchy

Apps are managed at three levels:

### App Level
- `list_apps` - List all apps
- `get_app` - Get app metadata and structure
- `update_app` - Update app settings
- `publish_app` - Publish app for users

### Page Level
- `create_page` - Add a new page to an app
- `get_page` - Get page definition
- `update_page` - Update page settings/layout
- `delete_page` - Remove a page

### Component Level
- `list_components` - List components on a page
- `create_component` - Add component to a page
- `get_component` - Get component details
- `update_component` - Update component props/settings
- `delete_component` - Remove component
- `move_component` - Reposition component

## App Layout Properties

### Component Width
All components support a `width` property:
- `"auto"` (default) - Natural size
- `"full"` - Full width of container
- `"1/2"`, `"1/3"`, `"1/4"`, `"2/3"`, `"3/4"` - Fractional widths

### Layout autoSize
Row layouts have an `autoSize` property:
- `false` (default) - Children expand equally to fill space (flex-1)
- `true` - Children keep their natural size

Example for right-aligned button group:
```json
{
  "type": "row",
  "justify": "end",
  "autoSize": true,
  "gap": 8,
  "children": [
    {"type": "button", "props": {"label": "Cancel", "variant": "outline"}},
    {"type": "button", "props": {"label": "Save"}}
  ]
}
```

## Required Testing Workflow

Before declaring any artifact complete, you MUST test it:

### Workflow/Tool/Data Provider Testing
1. Create via `create_workflow` (auto-validates)
2. Verify it appears in list tools (`list_workflows` or `list_data_providers`)
3. Execute with sample data via `execute_workflow`
4. Verify the result matches expectations

### Form Testing
1. Create via `create_form` (auto-validates)
2. Verify referenced `workflow_id` exists and works

### App Testing
1. Use granular tools (`create_page`, `create_component`)
2. Verify all `loadingWorkflows` exist and work
3. Test component layout (use `width` and `autoSize` for proper alignment)

DO NOT report success until all applicable tests pass.

## Decorators and IDs

Always include a generated UUID for decorator `id` parameters:

```python
@workflow(id="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
async def my_workflow(name: str) -> dict:
    '''What this workflow does.'''
    return {"result": "value"}

@tool(id="b2c3d4e5-f6a7-8901-bcde-f12345678901")
async def my_tool(query: str) -> dict:
    '''Tool description for AI agents.'''
    return {"answer": "..."}

@data_provider(id="c3d4e5f6-a7b8-9012-cdef-123456789012")
async def get_options() -> list[dict]:
    '''Returns options for dropdowns.'''
    return [{"label": "Option", "value": "opt"}]
```

## Workspace Structure

```
workspace/
├── apps/                   # App Builder applications (by company/org)
│   ├── global/             # Global apps (available to all orgs)
│   └── <company>/          # Company-specific apps
├── features/               # Feature-based organization (primary work area)
│   └── <feature-name>/
│       ├── workflows/
│       ├── services/
│       ├── forms/
│       └── models.py
├── shared/                 # Cross-feature resources
│   ├── data_providers/
│   ├── utilities/
│   └── services/
└── modules/                # Auto-generated SDKs (DO NOT EDIT)
```

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
