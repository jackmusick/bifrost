"""
Bifrost MCP Server

MCP server for Bifrost platform capabilities with dual-mode support:
- Internal mode: Uses Claude Agent SDK's in-process MCP for Coding Agent
- External mode: Uses FastMCP for HTTP access (Claude Desktop, etc.)

Architecture:
    - MCPContext: Holds user/org context for permission-scoped tool execution
    - BifrostMCPServer: Creates MCP servers with registered tools
    - Supports both SDK in-process (internal) and FastMCP HTTP (external)

Usage:
    # For Coding Agent (SDK in-process)
    server = BifrostMCPServer(context)
    sdk_server = server.get_sdk_server()
    options = ClaudeAgentOptions(mcp_servers={"bifrost": sdk_server})

    # For external access (FastMCP HTTP)
    server = BifrostMCPServer(context)
    fastmcp_server = server.get_fastmcp_server()
    app = fastmcp_server.http_app()
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

if TYPE_CHECKING:
    from fastmcp import FastMCP  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

# Claude Agent SDK for internal MCP (Coding Agent)
try:
    from claude_agent_sdk import create_sdk_mcp_server, tool as sdk_tool  # type: ignore

    HAS_CLAUDE_SDK = True
except ImportError:
    HAS_CLAUDE_SDK = False

    def create_sdk_mcp_server(*args: Any, **kwargs: Any) -> Any:
        """Stub when SDK not installed."""
        raise ImportError(
            "claude-agent-sdk is required for coding mode. "
            "Install it with: pip install claude-agent-sdk"
        )

    def sdk_tool(**kwargs: Any) -> Any:
        """Stub decorator when SDK not installed."""
        def decorator(func: Any) -> Any:
            return func
        return decorator

# FastMCP for external HTTP access - runtime import check
HAS_FASTMCP = False
_FastMCP: type["FastMCP"] | None = None  # Runtime class holder
_Icon: type | None = None  # MCP Icon type

try:
    from fastmcp import FastMCP as _FastMCPClass  # type: ignore[import-not-found]
    from mcp.types import Icon as _IconClass  # type: ignore[import-not-found]
    _FastMCP = _FastMCPClass
    _Icon = _IconClass
    HAS_FASTMCP = True
except ImportError:
    pass

# Bifrost branding
BIFROST_ICON_URL = "https://bifrostintegrations.blob.core.windows.net/public/logo.svg"
BIFROST_WEBSITE_URL = "https://docs.gobifrost.com"


@dataclass
class MCPContext:
    """
    Context for MCP tool execution.

    Provides user and organization scope for permission-aware tool execution.
    All MCP tools receive this context to enforce access control.
    """

    user_id: UUID | str
    org_id: UUID | str | None = None
    is_platform_admin: bool = False
    user_email: str = ""
    user_name: str = ""

    # System tools enabled for this context (from agent.system_tools)
    enabled_system_tools: list[str] = field(default_factory=list)

    # Knowledge namespaces accessible to this user (from agent.knowledge_sources)
    accessible_namespaces: list[str] = field(default_factory=list)


# =============================================================================
# Tool Implementations (shared between SDK and FastMCP)
# =============================================================================

async def _execute_workflow_impl(
    context: MCPContext,
    workflow_name: str,
    inputs: dict[str, Any] | None = None,
) -> str:
    """Execute a workflow and return results."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    if not workflow_name:
        return "Error: workflow_name is required"

    inputs = inputs or {}
    logger.info(f"MCP execute_workflow: {workflow_name} with inputs: {inputs}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflow = await repo.get_by_name(workflow_name)

            if not workflow:
                return f"Error: Workflow '{workflow_name}' not found. Use list_workflows to see available workflows."

            result = await execute_tool(
                workflow_id=str(workflow.id),
                workflow_name=workflow.name,
                parameters=inputs,
                user_id=str(context.user_id),
                user_email=context.user_email or "mcp@bifrost.local",
                user_name=context.user_name or "MCP User",
                org_id=str(context.org_id) if context.org_id else None,
                is_platform_admin=context.is_platform_admin,
            )

            if result.status.value == "Success":
                import json
                result_str = json.dumps(result.result, indent=2, default=str) if result.result else "null"
                return (
                    f"✓ Workflow '{workflow_name}' executed successfully!\n\n"
                    f"**Duration:** {result.duration_ms}ms\n\n"
                    f"**Result:**\n```json\n{result_str}\n```"
                )
            else:
                return (
                    f"✗ Workflow '{workflow_name}' failed!\n\n"
                    f"**Status:** {result.status.value}\n"
                    f"**Error:** {result.error or 'Unknown error'}\n\n"
                    f"**Error Type:** {result.error_type or 'Unknown'}"
                )

    except Exception as e:
        logger.exception(f"Error executing workflow via MCP: {e}")
        return f"Error executing workflow: {str(e)}"


async def _list_workflows_impl(
    context: MCPContext,
    query: str | None = None,
    category: str | None = None,
) -> str:
    """List all registered workflows."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP list_workflows called with query={query}, category={category}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflows = await repo.search(query=query, category=category, limit=100)
            total_count = await repo.count_active()

            if not workflows:
                return (
                    "No workflows found.\n\n"
                    "If you've created a workflow file in `/tmp/bifrost/workspace`, "
                    "wait a moment for the file watcher to detect and register it.\n\n"
                    "Workflows are Python files with the `.workflow.py` extension that "
                    "use the `@workflow` decorator."
                )

            lines = ["# Registered Workflows\n"]
            lines.append(f"Showing {len(workflows)} of {total_count} total workflows\n")

            for workflow in workflows:
                lines.append(f"## {workflow.name}")
                if workflow.description:
                    lines.append(f"{workflow.description}")

                meta_parts = []
                if workflow.category:
                    meta_parts.append(f"Category: {workflow.category}")
                if workflow.is_tool:
                    meta_parts.append("Tool: Yes")
                if workflow.schedule:
                    meta_parts.append(f"Schedule: {workflow.schedule}")
                if workflow.endpoint_enabled:
                    meta_parts.append("Endpoint: Enabled")

                if meta_parts:
                    lines.append(f"- {' | '.join(meta_parts)}")
                if workflow.file_path:
                    lines.append(f"- File: `{workflow.file_path}`")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing workflows via MCP: {e}")
        return f"Error listing workflows: {str(e)}"


async def _list_integrations_impl(context: MCPContext) -> str:
    """List all available integrations."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.integrations import Integration, IntegrationMapping

    logger.info("MCP list_integrations called")

    try:
        async with get_db_context() as db:
            if context.is_platform_admin or not context.org_id:
                result = await db.execute(
                    select(Integration)
                    .where(Integration.is_deleted.is_(False))
                    .order_by(Integration.name)
                )
                integrations = result.scalars().all()
            else:
                result = await db.execute(
                    select(Integration)
                    .join(IntegrationMapping)
                    .where(IntegrationMapping.organization_id == context.org_id)
                    .where(Integration.is_deleted.is_(False))
                    .order_by(Integration.name)
                )
                integrations = result.scalars().all()

            if not integrations:
                return (
                    "No integrations are currently configured.\n\n"
                    "To use integrations in workflows, they must first be set up "
                    "in the Bifrost admin panel."
                )

            lines = ["# Available Integrations\n"]
            for integration in integrations:
                lines.append(f"## {integration.name}")
                if integration.has_oauth_config:
                    lines.append("- **Auth:** OAuth configured")
                if integration.entity_id_name:
                    lines.append(f"- **Entity:** {integration.entity_id_name}")
                lines.append("")

            lines.append("\n## Usage in Workflows\n")
            lines.append("```python")
            lines.append("from bifrost import integrations")
            lines.append("")
            lines.append('integration = await integrations.get("IntegrationName")')
            lines.append("if integration and integration.oauth:")
            lines.append("    access_token = integration.oauth.access_token")
            lines.append("```")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing integrations via MCP: {e}")
        return f"Error listing integrations: {str(e)}"


async def _list_forms_impl(context: MCPContext) -> str:
    """List all forms."""
    from src.core.database import get_db_context
    from src.repositories.forms import FormRepository

    logger.info("MCP list_forms called")

    try:
        async with get_db_context() as db:
            repo = FormRepository(db)

            # Get forms based on context
            if context.is_platform_admin:
                forms = await repo.list_all(limit=100)
            elif context.org_id:
                forms = await repo.list_by_organization(str(context.org_id), limit=100)
            else:
                forms = []

            if not forms:
                return "No forms found."

            lines = ["# Forms\n"]
            for form in forms:
                lines.append(f"## {form.name}")
                if form.description:
                    lines.append(f"{form.description}")
                lines.append(f"- URL: `/forms/{form.id}`")
                if form.workflow_id:
                    lines.append(f"- Linked workflow: {form.workflow_id}")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing forms via MCP: {e}")
        return f"Error listing forms: {str(e)}"


async def _get_form_schema_impl(context: MCPContext) -> str:
    """Get form schema documentation."""
    return """# Form Schema Documentation

Forms in Bifrost are defined using a JSON schema with the following structure:

## Form Definition

```json
{
  "name": "Example Form",
  "description": "Form description",
  "fields": [...],
  "workflow_id": "optional-workflow-uuid"
}
```

## Field Types

### Text Field
```json
{
  "name": "username",
  "type": "text",
  "label": "Username",
  "required": true,
  "placeholder": "Enter username"
}
```

### Select Field
```json
{
  "name": "country",
  "type": "select",
  "label": "Country",
  "options": [
    {"value": "us", "label": "United States"},
    {"value": "uk", "label": "United Kingdom"}
  ]
}
```

### Number Field
```json
{
  "name": "age",
  "type": "number",
  "label": "Age",
  "min": 0,
  "max": 150
}
```

### Boolean Field
```json
{
  "name": "subscribe",
  "type": "boolean",
  "label": "Subscribe to newsletter",
  "default": false
}
```

### Date Field
```json
{
  "name": "birthday",
  "type": "date",
  "label": "Birthday"
}
```

## Common Field Properties

- `name`: Field identifier (required)
- `type`: Field type (required)
- `label`: Display label
- `required`: Whether field is required
- `default`: Default value
- `placeholder`: Placeholder text
- `description`: Help text
"""


async def _validate_form_schema_impl(context: MCPContext, form_json: str) -> str:
    """Validate a form JSON structure."""
    import json

    try:
        form_data = json.loads(form_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {str(e)}"

    errors = []

    # Check required fields
    if "name" not in form_data:
        errors.append("Missing required field: 'name'")
    if "fields" not in form_data:
        errors.append("Missing required field: 'fields'")
    elif not isinstance(form_data.get("fields"), list):
        errors.append("'fields' must be an array")

    # Validate each field
    valid_types = {"text", "number", "select", "boolean", "date", "textarea", "email", "password"}
    if isinstance(form_data.get("fields"), list):
        for i, fld in enumerate(form_data["fields"]):
            if not isinstance(fld, dict):
                errors.append(f"Field {i}: must be an object")
                continue
            if "name" not in fld:
                errors.append(f"Field {i}: missing 'name'")
            if "type" not in fld:
                errors.append(f"Field {i}: missing 'type'")
            elif fld["type"] not in valid_types:
                errors.append(f"Field {i}: invalid type '{fld['type']}'. Valid types: {', '.join(valid_types)}")

    if errors:
        return "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)

    return "✓ Form schema is valid!"


async def _create_form_impl(
    context: MCPContext,
    name: str,
    workflow_id: str,
    fields: list[dict[str, Any]],
    description: str | None = None,
    launch_workflow_id: str | None = None,
) -> str:
    """Create a new form with fields linked to a workflow.

    Args:
        context: MCP context with user permissions
        name: Form name (1-200 chars)
        workflow_id: UUID of workflow to execute on form submit
        fields: Array of field definitions
        description: Optional form description
        launch_workflow_id: Optional UUID of workflow to run before form display

    Returns:
        Formatted confirmation with form ID/URL
    """
    from datetime import datetime
    from uuid import UUID as UUID_TYPE

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models import Form as FormORM
    from src.models import FormSchema
    from src.repositories.workflows import WorkflowRepository
    from src.routers.forms import _form_schema_to_fields, _write_form_to_file

    logger.info(f"MCP create_form called: name={name}, workflow_id={workflow_id}")

    # Validate inputs
    if not name:
        return "Error: name is required"
    if not workflow_id:
        return "Error: workflow_id is required"
    if not fields:
        return "Error: fields array is required"
    if len(name) > 200:
        return "Error: name must be 200 characters or less"

    # Validate workflow_id is a valid UUID
    try:
        UUID_TYPE(workflow_id)
    except ValueError:
        return f"Error: workflow_id '{workflow_id}' is not a valid UUID"

    # Validate launch_workflow_id if provided
    if launch_workflow_id:
        try:
            UUID_TYPE(launch_workflow_id)
        except ValueError:
            return f"Error: launch_workflow_id '{launch_workflow_id}' is not a valid UUID"

    try:
        async with get_db_context() as db:
            # Verify workflow exists
            workflow_repo = WorkflowRepository(db)
            workflow = await workflow_repo.get(UUID_TYPE(workflow_id))
            if not workflow:
                return f"Error: Workflow '{workflow_id}' not found. Use list_workflows to see available workflows."

            # Verify launch workflow if provided
            if launch_workflow_id:
                launch_workflow = await workflow_repo.get(UUID_TYPE(launch_workflow_id))
                if not launch_workflow:
                    return f"Error: Launch workflow '{launch_workflow_id}' not found."

            # Validate form schema
            try:
                FormSchema.model_validate({"fields": fields})
            except Exception as e:
                return f"Error validating form schema: {str(e)}"

            # Create form record
            now = datetime.utcnow()
            org_id = UUID_TYPE(str(context.org_id)) if context.org_id else None

            form = FormORM(
                name=name,
                description=description,
                workflow_id=workflow_id,
                launch_workflow_id=launch_workflow_id,
                access_level="role_based",
                organization_id=org_id,
                is_active=True,
                created_by=context.user_email or "mcp@bifrost.local",
                created_at=now,
                updated_at=now,
            )

            db.add(form)
            await db.flush()  # Get the form ID

            # Convert form_schema to FormField records
            field_records = _form_schema_to_fields({"fields": fields}, form.id)
            for field in field_records:
                db.add(field)

            await db.flush()

            # Reload form with fields eager-loaded
            result = await db.execute(
                select(FormORM)
                .options(selectinload(FormORM.fields))
                .where(FormORM.id == form.id)
            )
            form = result.scalar_one()

            # Write to file system (dual-write pattern)
            try:
                file_path = await _write_form_to_file(form, db)
                form.file_path = file_path
                await db.flush()
            except Exception as e:
                logger.error(f"Failed to write form file for {form.id}: {e}", exc_info=True)
                # Continue - database write succeeded

            logger.info(f"Created form {form.id}: {form.name}")

            return (
                f"✓ Form '{name}' created successfully!\n\n"
                f"**Form ID:** {form.id}\n"
                f"**URL:** `/forms/{form.id}`\n"
                f"**Linked Workflow:** {workflow.name}\n"
                f"**Fields:** {len(fields)}\n"
                + (f"**Launch Workflow:** {launch_workflow.name}\n" if launch_workflow_id else "")
                + (f"**File Path:** {form.file_path}\n" if form.file_path else "")
            )

    except Exception as e:
        logger.exception(f"Error creating form via MCP: {e}")
        return f"Error creating form: {str(e)}"


async def _get_form_impl(
    context: MCPContext,
    form_id: str | None = None,
    form_name: str | None = None,
) -> str:
    """Get detailed information about a specific form.

    Args:
        context: MCP context with user permissions
        form_id: Form UUID (preferred)
        form_name: Form name (alternative to ID)

    Returns:
        Formatted markdown with form details
    """
    from uuid import UUID as UUID_TYPE

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models import Form as FormORM
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP get_form called: form_id={form_id}, form_name={form_name}")

    if not form_id and not form_name:
        return "Error: Either form_id or form_name is required"

    try:
        async with get_db_context() as db:
            # Build query
            query = select(FormORM).options(selectinload(FormORM.fields))

            if form_id:
                try:
                    uuid_id = UUID_TYPE(form_id)
                except ValueError:
                    return f"Error: '{form_id}' is not a valid UUID"
                query = query.where(FormORM.id == uuid_id)
            else:
                query = query.where(FormORM.name == form_name)

            # Apply org scoping for non-admins
            if not context.is_platform_admin and context.org_id:
                from sqlalchemy import or_
                org_uuid = UUID_TYPE(str(context.org_id))
                query = query.where(
                    or_(
                        FormORM.organization_id == org_uuid,
                        FormORM.organization_id.is_(None)  # Global forms
                    )
                )

            result = await db.execute(query)
            form = result.scalar_one_or_none()

            if not form:
                identifier = form_id or form_name
                return f"Error: Form '{identifier}' not found. Use list_forms to see available forms."

            # Get workflow names
            workflow_repo = WorkflowRepository(db)
            workflow_name = None
            launch_workflow_name = None

            if form.workflow_id:
                try:
                    workflow = await workflow_repo.get(UUID_TYPE(form.workflow_id))
                    workflow_name = workflow.name if workflow else None
                except Exception:
                    pass

            if form.launch_workflow_id:
                try:
                    launch_workflow = await workflow_repo.get(UUID_TYPE(form.launch_workflow_id))
                    launch_workflow_name = launch_workflow.name if launch_workflow else None
                except Exception:
                    pass

            # Build output
            lines = [f"# {form.name}\n"]

            if form.description:
                lines.append(f"{form.description}\n")

            lines.append("## Details\n")
            lines.append(f"- **ID:** `{form.id}`")
            lines.append(f"- **URL:** `/forms/{form.id}`")
            lines.append(f"- **Active:** {'Yes' if form.is_active else 'No'}")
            lines.append(f"- **Access Level:** {form.access_level or 'role_based'}")

            if form.organization_id:
                lines.append(f"- **Organization:** `{form.organization_id}`")
            else:
                lines.append("- **Scope:** Global")

            lines.append("")
            lines.append("## Linked Workflows\n")
            if workflow_name:
                lines.append(f"- **Submit Workflow:** {workflow_name} (`{form.workflow_id}`)")
            else:
                lines.append(f"- **Submit Workflow ID:** `{form.workflow_id}`")

            if form.launch_workflow_id:
                if launch_workflow_name:
                    lines.append(f"- **Launch Workflow:** {launch_workflow_name} (`{form.launch_workflow_id}`)")
                else:
                    lines.append(f"- **Launch Workflow ID:** `{form.launch_workflow_id}`")

            # Fields
            if form.fields:
                lines.append("")
                lines.append(f"## Fields ({len(form.fields)})\n")

                # Sort by position
                sorted_fields = sorted(form.fields, key=lambda f: f.position)

                for field in sorted_fields:
                    required_marker = " **(required)**" if field.required else ""
                    lines.append(f"### {field.label or field.name}{required_marker}")
                    lines.append(f"- **Name:** `{field.name}`")
                    lines.append(f"- **Type:** `{field.type}`")

                    if field.placeholder:
                        lines.append(f"- **Placeholder:** {field.placeholder}")
                    if field.help_text:
                        lines.append(f"- **Help:** {field.help_text}")
                    if field.default_value is not None:
                        lines.append(f"- **Default:** `{field.default_value}`")
                    if field.options:
                        import json
                        lines.append(f"- **Options:** `{json.dumps(field.options)}`")
                    if field.data_provider_id:
                        lines.append(f"- **Data Provider:** `{field.data_provider_id}`")

                    lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting form via MCP: {e}")
        return f"Error getting form: {str(e)}"


async def _update_form_impl(
    context: MCPContext,
    form_id: str,
    name: str | None = None,
    description: str | None = None,
    workflow_id: str | None = None,
    launch_workflow_id: str | None = None,
    fields: list[dict[str, Any]] | None = None,
    is_active: bool | None = None,
) -> str:
    """Update an existing form.

    Args:
        context: MCP context with user permissions
        form_id: Form UUID (required)
        name: New form name
        description: New description
        workflow_id: New workflow UUID
        launch_workflow_id: New launch workflow UUID
        fields: New field definitions (replaces all fields)
        is_active: Enable/disable the form

    Returns:
        Formatted confirmation
    """
    from datetime import datetime
    from uuid import UUID as UUID_TYPE

    from sqlalchemy import delete, select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models import Form as FormORM, FormField as FormFieldORM
    from src.models import FormSchema
    from src.repositories.workflows import WorkflowRepository
    from src.routers.forms import _form_schema_to_fields, _update_form_file

    logger.info(f"MCP update_form called: form_id={form_id}")

    if not form_id:
        return "Error: form_id is required"

    # Validate form_id is a valid UUID
    try:
        uuid_id = UUID_TYPE(form_id)
    except ValueError:
        return f"Error: '{form_id}' is not a valid UUID"

    try:
        async with get_db_context() as db:
            # Get existing form
            result = await db.execute(
                select(FormORM)
                .options(selectinload(FormORM.fields))
                .where(FormORM.id == uuid_id)
            )
            form = result.scalar_one_or_none()

            if not form:
                return f"Error: Form '{form_id}' not found. Use list_forms to see available forms."

            # Check access for non-admins
            if not context.is_platform_admin:
                if form.organization_id:
                    if context.org_id and str(form.organization_id) != str(context.org_id):
                        return "Error: You don't have permission to update this form."
                # Global forms can only be updated by admins
                if form.organization_id is None:
                    return "Error: Only platform admins can update global forms."

            old_file_path = form.file_path
            updates_made = []

            # Apply updates
            if name is not None:
                if len(name) > 200:
                    return "Error: name must be 200 characters or less"
                form.name = name
                updates_made.append("name")

            if description is not None:
                form.description = description
                updates_made.append("description")

            if workflow_id is not None:
                try:
                    UUID_TYPE(workflow_id)
                except ValueError:
                    return f"Error: workflow_id '{workflow_id}' is not a valid UUID"

                workflow_repo = WorkflowRepository(db)
                workflow = await workflow_repo.get(UUID_TYPE(workflow_id))
                if not workflow:
                    return f"Error: Workflow '{workflow_id}' not found."
                form.workflow_id = workflow_id
                updates_made.append("workflow_id")

            if launch_workflow_id is not None:
                if launch_workflow_id == "":
                    # Clear launch workflow
                    form.launch_workflow_id = None
                    updates_made.append("launch_workflow_id (cleared)")
                else:
                    try:
                        UUID_TYPE(launch_workflow_id)
                    except ValueError:
                        return f"Error: launch_workflow_id '{launch_workflow_id}' is not a valid UUID"

                    workflow_repo = WorkflowRepository(db)
                    launch_workflow = await workflow_repo.get(UUID_TYPE(launch_workflow_id))
                    if not launch_workflow:
                        return f"Error: Launch workflow '{launch_workflow_id}' not found."
                    form.launch_workflow_id = launch_workflow_id
                    updates_made.append("launch_workflow_id")

            if is_active is not None:
                form.is_active = is_active
                updates_made.append(f"is_active ({is_active})")

            if fields is not None:
                # Validate new fields
                try:
                    FormSchema.model_validate({"fields": fields})
                except Exception as e:
                    return f"Error validating form schema: {str(e)}"

                # Delete existing fields
                await db.execute(
                    delete(FormFieldORM).where(FormFieldORM.form_id == form.id)
                )

                # Add new fields
                field_records = _form_schema_to_fields({"fields": fields}, form.id)
                for field in field_records:
                    db.add(field)

                updates_made.append(f"fields ({len(fields)} fields)")

            if not updates_made:
                return "No updates provided. Specify at least one field to update."

            form.updated_at = datetime.utcnow()
            await db.flush()

            # Reload form with fields
            result = await db.execute(
                select(FormORM)
                .options(selectinload(FormORM.fields))
                .where(FormORM.id == form.id)
            )
            form = result.scalar_one()

            # Update file
            try:
                new_file_path = await _update_form_file(form, old_file_path, db)
                form.file_path = new_file_path
                await db.flush()
            except Exception as e:
                logger.error(f"Failed to update form file for {form.id}: {e}", exc_info=True)

            logger.info(f"Updated form {form.id}: {', '.join(updates_made)}")

            return (
                f"✓ Form '{form.name}' updated successfully!\n\n"
                f"**Form ID:** {form.id}\n"
                f"**Updates:** {', '.join(updates_made)}\n"
                + (f"**File Path:** {form.file_path}\n" if form.file_path else "")
            )

    except Exception as e:
        logger.exception(f"Error updating form via MCP: {e}")
        return f"Error updating form: {str(e)}"


async def _search_knowledge_impl(
    context: MCPContext,
    query: str,
    namespace: str | None = None,
    limit: int = 5,
) -> str:
    """Search the knowledge base.

    Args:
        context: MCP context with user permissions
        query: Search query text
        namespace: Optional specific namespace to search (must be accessible)
        limit: Maximum number of results
    """
    from src.core.database import get_db_context
    from src.repositories.knowledge import KnowledgeRepository
    from src.services.embeddings import get_embedding_client

    logger.info(f"MCP search_knowledge called with query={query}, namespace={namespace}")

    if not query:
        return "Error: query is required"

    # Validate namespace access
    accessible = context.accessible_namespaces
    if not accessible:
        return "No knowledge sources available. No agents with knowledge access configured."

    if namespace:
        if namespace not in accessible:
            return f"Access denied: namespace '{namespace}' is not accessible."
        namespaces_to_search = [namespace]
    else:
        namespaces_to_search = accessible

    try:
        async with get_db_context() as db:
            # Generate query embedding
            embedding_client = await get_embedding_client(db)
            query_embedding = await embedding_client.embed_single(query)

            # Search knowledge store
            repo = KnowledgeRepository(db)
            results = await repo.search(
                query_embedding=query_embedding,
                namespace=namespaces_to_search,
                organization_id=context.org_id if context.org_id else None,
                limit=limit,
                fallback=True,
            )

            if not results:
                return f"No results found for query: '{query}'"

            lines = [f"# Knowledge Search Results for '{query}'\n"]
            for i, doc in enumerate(results, 1):
                lines.append(f"## Result {i}")
                if doc.namespace:
                    lines.append(f"**Namespace:** {doc.namespace}")
                if doc.score:
                    lines.append(f"**Relevance:** {doc.score:.2%}")
                lines.append(f"\n{doc.content}\n")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error searching knowledge via MCP: {e}")
        return f"Error searching knowledge: {str(e)}"


# =============================================================================
# File Operation Tool Implementations
# =============================================================================


async def _read_file_impl(context: MCPContext, path: str) -> str:
    """Read a file from the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP read_file called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        result = await file_operations.read_file(path)
        if result.encoding == "base64":
            return f"Binary file ({result.size} bytes). Base64 content available but too large to display."
        return result.content or ""
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error reading file via MCP: {e}")
        return f"Error reading file: {str(e)}"


async def _write_file_impl(context: MCPContext, path: str, content: str) -> str:
    """Write content to a file in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP write_file called with path={path}")

    if not path:
        return "Error: path is required"
    if content is None:
        return "Error: content is required"

    try:
        result = await file_operations.write_file(path, content)
        return f"✓ File written successfully: {path} ({result.size} bytes)"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error writing file via MCP: {e}")
        return f"Error writing file: {str(e)}"


async def _list_files_impl(context: MCPContext, directory: str = "") -> str:
    """List files and directories in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP list_files called with directory={directory}")

    try:
        items = file_operations.list_directory(directory or "")

        if not items:
            return f"No files found in: {directory or '/'}"

        lines = [f"# Files in {directory or '/'}\n"]
        for item in items:
            icon = "📁" if item.type.value == "folder" else "📄"
            size_str = f" ({item.size} bytes)" if item.type.value == "file" and item.size else ""
            lines.append(f"- {icon} `{item.name}`{size_str}")

        return "\n".join(lines)
    except FileNotFoundError:
        return f"Error: Directory not found: {directory}"
    except Exception as e:
        logger.exception(f"Error listing files via MCP: {e}")
        return f"Error listing files: {str(e)}"


async def _delete_file_impl(context: MCPContext, path: str) -> str:
    """Delete a file or directory from the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP delete_file called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        file_operations.delete_path(path)
        return f"✓ Deleted: {path}"
    except FileNotFoundError:
        return f"Error: Path not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.exception(f"Error deleting file via MCP: {e}")
        return f"Error deleting file: {str(e)}"


async def _search_files_impl(
    context: MCPContext,
    query: str,
    pattern: str = "**/*",
    case_sensitive: bool = False,
) -> str:
    """Search for text patterns across files in the workspace."""
    from src.services.editor import search as search_module
    from src.services.editor.search import SearchRequest

    logger.info(f"MCP search_files called with query={query}, pattern={pattern}")

    if not query:
        return "Error: query is required"

    try:
        request = SearchRequest(
            query=query,
            include_pattern=pattern,
            case_sensitive=case_sensitive,
            max_results=50,
        )
        response = search_module.search_files(request)
        results = response.results

        if not results:
            return f"No matches found for: '{query}'"

        lines = [f"# Search Results for '{query}'\n"]
        lines.append(f"Found {len(results)} matches\n")

        for result in results[:20]:  # Limit to 20 results in output
            lines.append(f"## {result.file_path}:{result.line}")
            lines.append("```")
            lines.append(result.match_text.strip())
            lines.append("```\n")

        if len(results) > 20:
            lines.append(f"... and {len(results) - 20} more matches")

        return "\n".join(lines)
    except Exception as e:
        logger.exception(f"Error searching files via MCP: {e}")
        return f"Error searching files: {str(e)}"


async def _create_folder_impl(context: MCPContext, path: str) -> str:
    """Create a new folder in the workspace."""
    from src.services.editor import file_operations

    logger.info(f"MCP create_folder called with path={path}")

    if not path:
        return "Error: path is required"

    try:
        file_operations.create_folder(path)
        return f"✓ Folder created: {path}"
    except FileExistsError:
        return f"Folder already exists: {path}"
    except Exception as e:
        logger.exception(f"Error creating folder via MCP: {e}")
        return f"Error creating folder: {str(e)}"


# =============================================================================
# Workflow and Execution Tool Implementations
# =============================================================================


async def _validate_workflow_impl(context: MCPContext, file_path: str) -> str:
    """Validate a workflow Python file."""
    import ast
    from pathlib import Path

    logger.info(f"MCP validate_workflow called with file_path={file_path}")

    if not file_path:
        return "Error: file_path is required"

    try:
        workspace_path = Path("/tmp/bifrost/workspace")
        full_path = workspace_path / file_path.lstrip("/")

        if not full_path.exists():
            return f"Error: File not found: {file_path}"

        content = full_path.read_text()
        errors = []

        # Check syntax
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append(f"Syntax error on line {e.lineno}: {e.msg}")
            return "# Validation Failed\n\n" + "\n".join(f"- {e}" for e in errors)

        # Check for @workflow decorator
        if "@workflow" not in content:
            errors.append("Missing @workflow decorator")

        # Check for bifrost import
        if "from bifrost" not in content and "import bifrost" not in content:
            errors.append("Missing bifrost import (e.g., from bifrost import workflow)")

        # Check for async def
        if "async def" not in content:
            errors.append("Workflow function should be async (use 'async def')")

        if errors:
            return "# Validation Issues\n\n" + "\n".join(f"- {e}" for e in errors)

        return "✓ Workflow syntax is valid!"

    except Exception as e:
        logger.exception(f"Error validating workflow via MCP: {e}")
        return f"Error validating workflow: {str(e)}"


async def _get_workflow_schema_impl(context: MCPContext) -> str:
    """Get documentation about workflow structure and SDK features."""
    return """# Workflow Schema Documentation

## Basic Workflow Structure

```python
from bifrost import workflow

@workflow(
    name="My Workflow",
    description="What this workflow does",
    category="automation",  # Optional: group related workflows
)
async def my_workflow(param1: str, param2: int = 10):
    # Workflow logic here
    return {"result": "value"}
```

## Decorator Properties

- `name`: Display name for the workflow (required)
- `description`: Human-readable description
- `category`: Group workflows by category
- `schedule`: Cron expression for scheduled execution (e.g., "0 9 * * *")
- `is_tool`: Enable as MCP tool for AI agents (default: False)
- `endpoint_enabled`: Enable REST API endpoint (default: False)

## SDK Modules

### AI Module
```python
from bifrost import ai

response = await ai.chat("Hello, how are you?")
structured = await ai.chat("Extract name", response_model=MyModel)
```

### HTTP Module
```python
from bifrost import http

response = await http.get("https://api.example.com/data")
data = await http.post("https://api.example.com", json={"key": "value"})
```

### Integrations Module
```python
from bifrost import integrations

integration = await integrations.get("MyIntegration")
if integration and integration.oauth:
    token = integration.oauth.access_token
```

### Config Module
```python
from bifrost import config

api_key = await config.get("MY_API_KEY")
await config.set("MY_SETTING", "value")
```

### Knowledge Module
```python
from bifrost import knowledge

results = await knowledge.search("my query", limit=5)
await knowledge.store(key="doc1", content="Document content")
```

## Parameter Types

Supported parameter types for workflow functions:
- `str` - Text input
- `int` - Integer number
- `float` - Decimal number
- `bool` - True/False
- `dict` - JSON object
- `list` - JSON array
- `Optional[T]` - Optional parameter with None default

## Return Values

Workflows can return:
- `dict` - JSON object (most common)
- `list` - JSON array
- `str` - Plain text
- HTML string (for rich display in UI)
- `None` - No output
"""


async def _get_workflow_impl(
    context: MCPContext,
    workflow_id: str | None = None,
    workflow_name: str | None = None,
) -> str:
    """Get detailed metadata for a specific workflow."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP get_workflow called with id={workflow_id}, name={workflow_name}")

    if not workflow_id and not workflow_name:
        return "Error: Either workflow_id or workflow_name is required"

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)

            if workflow_id:
                workflow = await repo.get_by_id(workflow_id)
            else:
                workflow = await repo.get_by_name(workflow_name or "")

            if not workflow:
                return "Error: Workflow not found"

            lines = [f"# {workflow.name}\n"]
            if workflow.description:
                lines.append(f"{workflow.description}\n")

            lines.append("## Properties\n")
            lines.append(f"- **ID:** `{workflow.id}`")
            lines.append(f"- **File:** `{workflow.file_path}`")
            if workflow.category:
                lines.append(f"- **Category:** {workflow.category}")
            lines.append(f"- **Is Tool:** {'Yes' if workflow.is_tool else 'No'}")
            lines.append(f"- **Endpoint Enabled:** {'Yes' if workflow.endpoint_enabled else 'No'}")
            if workflow.schedule:
                lines.append(f"- **Schedule:** `{workflow.schedule}`")

            if workflow.parameters_schema:
                lines.append("\n## Parameters\n")
                for param in workflow.parameters_schema:
                    param_name = param.get("name", "unknown")
                    param_type = param.get("type", "string")
                    required = "required" if param.get("required") else "optional"
                    lines.append(f"- `{param_name}`: {param_type} ({required})")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting workflow via MCP: {e}")
        return f"Error getting workflow: {str(e)}"


async def _list_executions_impl(
    context: MCPContext,
    workflow_name: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List recent workflow executions."""
    from src.core.database import get_db_context
    from src.repositories.executions import ExecutionRepository

    logger.info(f"MCP list_executions called with workflow={workflow_name}, status={status}")

    try:
        async with get_db_context() as db:
            repo = ExecutionRepository(db)

            # Build filters
            filters: dict[str, Any] = {}
            if workflow_name:
                filters["workflow_name"] = workflow_name
            if status:
                filters["status"] = status

            executions = await repo.list_executions(
                filters=filters,
                limit=limit,
                user_id=str(context.user_id) if not context.is_platform_admin else None,
                org_id=str(context.org_id) if context.org_id else None,
            )

            if not executions:
                return "No executions found."

            lines = ["# Recent Executions\n"]
            for ex in executions:
                status_icon = "✓" if ex.status.value == "Success" else "✗" if ex.status.value == "Failed" else "⏳"
                lines.append(f"## {status_icon} {ex.workflow_name or 'Unknown'}")
                lines.append(f"- **ID:** `{ex.id}`")
                lines.append(f"- **Status:** {ex.status.value}")
                if ex.duration_ms:
                    lines.append(f"- **Duration:** {ex.duration_ms}ms")
                if ex.created_at:
                    lines.append(f"- **Started:** {ex.created_at.isoformat()}")
                if ex.error:
                    lines.append(f"- **Error:** {ex.error[:100]}...")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing executions via MCP: {e}")
        return f"Error listing executions: {str(e)}"


async def _get_execution_impl(context: MCPContext, execution_id: str) -> str:
    """Get details and logs for a specific workflow execution."""
    import json as json_module

    from src.core.database import get_db_context
    from src.repositories.executions import ExecutionRepository

    logger.info(f"MCP get_execution called with id={execution_id}")

    if not execution_id:
        return "Error: execution_id is required"

    try:
        async with get_db_context() as db:
            repo = ExecutionRepository(db)
            execution = await repo.get_execution(execution_id)

            if not execution:
                return f"Error: Execution not found: {execution_id}"

            # Check access
            if not context.is_platform_admin and str(execution.user_id) != str(context.user_id):
                return "Error: Access denied"

            lines = [f"# Execution: {execution.workflow_name or 'Unknown'}\n"]

            status_icon = "✓" if execution.status.value == "Success" else "✗" if execution.status.value == "Failed" else "⏳"
            lines.append(f"## Status: {status_icon} {execution.status.value}\n")

            lines.append("## Details\n")
            lines.append(f"- **ID:** `{execution.id}`")
            if execution.duration_ms:
                lines.append(f"- **Duration:** {execution.duration_ms}ms")
            if execution.created_at:
                lines.append(f"- **Started:** {execution.created_at.isoformat()}")
            if execution.completed_at:
                lines.append(f"- **Completed:** {execution.completed_at.isoformat()}")

            if execution.error:
                lines.append(f"\n## Error\n```\n{execution.error}\n```")

            if execution.result:
                result_str = json_module.dumps(execution.result, indent=2, default=str)
                lines.append(f"\n## Result\n```json\n{result_str}\n```")

            # Get logs
            logs = await repo.get_execution_logs(execution_id)
            if logs:
                lines.append("\n## Logs\n")
                for log in logs[-20:]:  # Last 20 logs
                    lines.append(f"[{log.level}] {log.message}")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting execution via MCP: {e}")
        return f"Error getting execution: {str(e)}"


# =============================================================================
# SDK Tool Wrappers (for Claude Agent SDK in-process MCP)
# =============================================================================

def _create_sdk_tools(context: MCPContext, enabled_tools: set[str] | None) -> list[Callable[..., Any]]:
    """Create SDK-compatible tools for the given context."""
    tools: list[Callable[..., Any]] = []

    # Tool definitions with SDK decorator
    if enabled_tools is None or "execute_workflow" in enabled_tools:
        @sdk_tool(
            name="execute_workflow",
            description="Execute a Bifrost workflow by name and return the results. Use this to test workflows you've written.",
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_name": {"type": "string", "description": "Name of the workflow to execute"},
                    "inputs": {"type": "object", "description": "Input parameters for the workflow"},
                },
                "required": ["workflow_name"],
            },
        )
        async def execute_workflow(args: dict[str, Any]) -> dict[str, Any]:
            result = await _execute_workflow_impl(context, args.get("workflow_name", ""), args.get("inputs"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(execute_workflow)

    if enabled_tools is None or "list_workflows" in enabled_tools:
        @sdk_tool(
            name="list_workflows",
            description="List workflows registered in Bifrost. Use this to verify a workflow you created was successfully discovered and registered.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search query to filter workflows"},
                    "category": {"type": "string", "description": "Optional category to filter workflows"},
                },
                "required": [],
            },
        )
        async def list_workflows(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_workflows_impl(context, args.get("query"), args.get("category"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_workflows)

    if enabled_tools is None or "list_integrations" in enabled_tools:
        @sdk_tool(
            name="list_integrations",
            description="List available integrations that can be used in workflows.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def list_integrations(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_integrations_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_integrations)

    if enabled_tools is None or "list_forms" in enabled_tools:
        @sdk_tool(
            name="list_forms",
            description="List all forms with their URLs for viewing in the platform.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def list_forms(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_forms_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_forms)

    if enabled_tools is None or "get_form_schema" in enabled_tools:
        @sdk_tool(
            name="get_form_schema",
            description="Get documentation about form structure, field types, and examples.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def get_form_schema(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_form_schema_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_form_schema)

    if enabled_tools is None or "validate_form_schema" in enabled_tools:
        @sdk_tool(
            name="validate_form_schema",
            description="Validate a form JSON structure before saving.",
            input_schema={
                "type": "object",
                "properties": {
                    "form_json": {"type": "string", "description": "JSON string of the form to validate"},
                },
                "required": ["form_json"],
            },
        )
        async def validate_form_schema(args: dict[str, Any]) -> dict[str, Any]:
            result = await _validate_form_schema_impl(context, args.get("form_json", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(validate_form_schema)

    # Form CRUD operations (not enabled for coding agent by default - uses file system)
    if enabled_tools is not None and "create_form" in enabled_tools:
        @sdk_tool(
            name="create_form",
            description="Create a new form with fields linked to a workflow.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Form name (1-200 chars)"},
                    "workflow_id": {"type": "string", "description": "UUID of workflow to execute on form submit"},
                    "fields": {
                        "type": "array",
                        "description": "Array of field definitions",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string", "enum": ["text", "email", "number", "select", "checkbox", "textarea", "radio", "datetime", "file"]},
                                "label": {"type": "string"},
                                "required": {"type": "boolean"},
                                "placeholder": {"type": "string"},
                                "help_text": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "object"}}
                            },
                            "required": ["name", "type", "label"]
                        }
                    },
                    "description": {"type": "string", "description": "Optional form description"},
                    "launch_workflow_id": {"type": "string", "description": "Optional UUID of workflow to run before form display"}
                },
                "required": ["name", "workflow_id", "fields"],
            },
        )
        async def create_form(args: dict[str, Any]) -> dict[str, Any]:
            result = await _create_form_impl(
                context,
                args.get("name", ""),
                args.get("workflow_id", ""),
                args.get("fields", []),
                args.get("description"),
                args.get("launch_workflow_id"),
            )
            return {"content": [{"type": "text", "text": result}]}
        tools.append(create_form)

    if enabled_tools is None or "get_form" in enabled_tools:
        @sdk_tool(
            name="get_form",
            description="Get detailed information about a specific form including all fields.",
            input_schema={
                "type": "object",
                "properties": {
                    "form_id": {"type": "string", "description": "Form UUID"},
                    "form_name": {"type": "string", "description": "Form name (alternative to ID)"},
                },
                "required": [],
            },
        )
        async def get_form(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_form_impl(context, args.get("form_id"), args.get("form_name"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_form)

    if enabled_tools is not None and "update_form" in enabled_tools:
        @sdk_tool(
            name="update_form",
            description="Update an existing form's properties or fields.",
            input_schema={
                "type": "object",
                "properties": {
                    "form_id": {"type": "string", "description": "Form UUID (required)"},
                    "name": {"type": "string", "description": "New form name"},
                    "description": {"type": "string", "description": "New description"},
                    "workflow_id": {"type": "string", "description": "New workflow UUID"},
                    "launch_workflow_id": {"type": "string", "description": "New launch workflow UUID (empty string to clear)"},
                    "fields": {"type": "array", "description": "New field definitions (replaces all fields)"},
                    "is_active": {"type": "boolean", "description": "Enable/disable the form"},
                },
                "required": ["form_id"],
            },
        )
        async def update_form(args: dict[str, Any]) -> dict[str, Any]:
            result = await _update_form_impl(
                context,
                args.get("form_id", ""),
                args.get("name"),
                args.get("description"),
                args.get("workflow_id"),
                args.get("launch_workflow_id"),
                args.get("fields"),
                args.get("is_active"),
            )
            return {"content": [{"type": "text", "text": result}]}
        tools.append(update_form)

    if enabled_tools is None or "search_knowledge" in enabled_tools:
        @sdk_tool(
            name="search_knowledge",
            description="Search the Bifrost knowledge base for documentation and examples.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "namespace": {"type": "string", "description": "Optional namespace to search (default: all accessible)"},
                    "limit": {"type": "integer", "description": "Maximum results to return (default: 5)"},
                },
                "required": ["query"],
            },
        )
        async def search_knowledge(args: dict[str, Any]) -> dict[str, Any]:
            result = await _search_knowledge_impl(
                context,
                args.get("query", ""),
                args.get("namespace"),
                args.get("limit", 5),
            )
            return {"content": [{"type": "text", "text": result}]}
        tools.append(search_knowledge)

    # File Operations (not enabled for coding agent by default - uses local file access)
    if enabled_tools is not None and "read_file" in enabled_tools:
        @sdk_tool(
            name="read_file",
            description="Read a file from the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file (relative to workspace)"},
                },
                "required": ["path"],
            },
        )
        async def read_file(args: dict[str, Any]) -> dict[str, Any]:
            result = await _read_file_impl(context, args.get("path", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(read_file)

    if enabled_tools is not None and "write_file" in enabled_tools:
        @sdk_tool(
            name="write_file",
            description="Write content to a file in the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file (relative to workspace)"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        )
        async def write_file(args: dict[str, Any]) -> dict[str, Any]:
            result = await _write_file_impl(context, args.get("path", ""), args.get("content", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(write_file)

    if enabled_tools is not None and "list_files" in enabled_tools:
        @sdk_tool(
            name="list_files",
            description="List files and directories in the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path (default: root)"},
                },
                "required": [],
            },
        )
        async def list_files(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_files_impl(context, args.get("directory", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_files)

    if enabled_tools is not None and "delete_file" in enabled_tools:
        @sdk_tool(
            name="delete_file",
            description="Delete a file or directory from the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                },
                "required": ["path"],
            },
        )
        async def delete_file(args: dict[str, Any]) -> dict[str, Any]:
            result = await _delete_file_impl(context, args.get("path", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(delete_file)

    if enabled_tools is not None and "search_files" in enabled_tools:
        @sdk_tool(
            name="search_files",
            description="Search for text patterns across files in the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or regex pattern"},
                    "pattern": {"type": "string", "description": "File glob pattern (default: **/*)", "default": "**/*"},
                    "case_sensitive": {"type": "boolean", "description": "Case sensitive search", "default": False},
                },
                "required": ["query"],
            },
        )
        async def search_files(args: dict[str, Any]) -> dict[str, Any]:
            result = await _search_files_impl(
                context, args.get("query", ""), args.get("pattern", "**/*"), args.get("case_sensitive", False)
            )
            return {"content": [{"type": "text", "text": result}]}
        tools.append(search_files)

    if enabled_tools is not None and "create_folder" in enabled_tools:
        @sdk_tool(
            name="create_folder",
            description="Create a new folder in the Bifrost workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path for the new folder"},
                },
                "required": ["path"],
            },
        )
        async def create_folder(args: dict[str, Any]) -> dict[str, Any]:
            result = await _create_folder_impl(context, args.get("path", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(create_folder)

    # Workflow and Execution Tools
    if enabled_tools is None or "validate_workflow" in enabled_tools:
        @sdk_tool(
            name="validate_workflow",
            description="Validate a workflow Python file for syntax and decorator issues.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to workflow file (relative to workspace)"},
                },
                "required": ["file_path"],
            },
        )
        async def validate_workflow(args: dict[str, Any]) -> dict[str, Any]:
            result = await _validate_workflow_impl(context, args.get("file_path", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(validate_workflow)

    if enabled_tools is None or "get_workflow_schema" in enabled_tools:
        @sdk_tool(
            name="get_workflow_schema",
            description="Get documentation about workflow structure, decorators, and SDK features.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        async def get_workflow_schema(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_workflow_schema_impl(context)
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_workflow_schema)

    if enabled_tools is None or "get_workflow" in enabled_tools:
        @sdk_tool(
            name="get_workflow",
            description="Get detailed metadata for a specific workflow.",
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow UUID"},
                    "workflow_name": {"type": "string", "description": "Workflow name (alternative to ID)"},
                },
                "required": [],
            },
        )
        async def get_workflow(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_workflow_impl(context, args.get("workflow_id"), args.get("workflow_name"))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_workflow)

    if enabled_tools is None or "list_executions" in enabled_tools:
        @sdk_tool(
            name="list_executions",
            description="List recent workflow executions.",
            input_schema={
                "type": "object",
                "properties": {
                    "workflow_name": {"type": "string", "description": "Filter by workflow name"},
                    "status": {"type": "string", "description": "Filter by status (Success, Failed, Running)"},
                    "limit": {"type": "integer", "description": "Maximum results (default: 20)"},
                },
                "required": [],
            },
        )
        async def list_executions(args: dict[str, Any]) -> dict[str, Any]:
            result = await _list_executions_impl(
                context, args.get("workflow_name"), args.get("status"), args.get("limit", 20)
            )
            return {"content": [{"type": "text", "text": result}]}
        tools.append(list_executions)

    if enabled_tools is None or "get_execution" in enabled_tools:
        @sdk_tool(
            name="get_execution",
            description="Get details and logs for a specific workflow execution.",
            input_schema={
                "type": "object",
                "properties": {
                    "execution_id": {"type": "string", "description": "Execution UUID"},
                },
                "required": ["execution_id"],
            },
        )
        async def get_execution(args: dict[str, Any]) -> dict[str, Any]:
            result = await _get_execution_impl(context, args.get("execution_id", ""))
            return {"content": [{"type": "text", "text": result}]}
        tools.append(get_execution)

    return tools


# =============================================================================
# FastMCP Tool Registration (for external HTTP access)
# =============================================================================


def _get_context_from_token() -> MCPContext:
    """
    Get MCPContext from authenticated FastMCP token.

    This extracts user information from the validated JWT token set by
    FastMCP's authentication middleware. Used by tool execution to get
    the actual authenticated user instead of the default startup context.

    Returns:
        MCPContext populated with authenticated user's information

    Raises:
        ToolError: If no authenticated user (token missing or invalid)
    """
    from fastmcp.exceptions import ToolError  # type: ignore[import-not-found]
    from fastmcp.server.dependencies import get_access_token  # type: ignore[import-not-found]

    token = get_access_token()
    if token is None:
        raise ToolError("Authentication required")

    return MCPContext(
        user_id=token.claims.get("user_id", ""),
        org_id=token.claims.get("org_id"),
        is_platform_admin=token.claims.get("is_superuser", False),
        user_email=token.claims.get("email", ""),
        user_name=token.claims.get("name", ""),
    )


async def _get_context_with_namespaces() -> MCPContext:
    """
    Get MCPContext with accessible knowledge namespaces.

    This extends the basic token context with accessible namespaces
    queried from the database based on user's agent access.

    Returns:
        MCPContext with accessible_namespaces populated
    """
    from src.core.database import get_db_context
    from src.services.mcp.tool_access import MCPToolAccessService
    from fastmcp.server.dependencies import get_access_token  # type: ignore[import-not-found]
    from fastmcp.exceptions import ToolError  # type: ignore[import-not-found]

    token = get_access_token()
    if token is None:
        raise ToolError("Authentication required")

    user_roles = token.claims.get("roles", [])
    is_superuser = token.claims.get("is_superuser", False)

    # Query accessible namespaces from agents
    accessible_namespaces: list[str] = []
    try:
        async with get_db_context() as db:
            service = MCPToolAccessService(db)
            result = await service.get_accessible_tools(
                user_roles=user_roles,
                is_superuser=is_superuser,
            )
            accessible_namespaces = result.accessible_namespaces
    except Exception as e:
        logger.warning(f"Failed to get accessible namespaces: {e}")

    return MCPContext(
        user_id=token.claims.get("user_id", ""),
        org_id=token.claims.get("org_id"),
        is_platform_admin=is_superuser,
        user_email=token.claims.get("email", ""),
        user_name=token.claims.get("name", ""),
        accessible_namespaces=accessible_namespaces,
    )


def _map_type_to_json_schema(param_type: str) -> str:
    """Map workflow parameter type to JSON Schema type."""
    type_map = {
        "string": "string",
        "str": "string",
        "int": "integer",
        "integer": "integer",
        "float": "number",
        "number": "number",
        "bool": "boolean",
        "boolean": "boolean",
        "json": "object",
        "dict": "object",
        "object": "object",
        "list": "array",
        "array": "array",
    }
    return type_map.get(param_type.lower(), "string")


async def _execute_workflow_tool_impl(
    context: MCPContext,
    workflow_id: str,
    workflow_name: str,
    **inputs: Any,
) -> str:
    """Execute a specific workflow tool by ID."""
    from src.core.database import get_db_context
    from src.repositories.workflows import WorkflowRepository
    from src.services.execution.service import execute_tool

    logger.info(f"MCP workflow tool '{workflow_name}' ({workflow_id}) called with inputs: {inputs}")

    try:
        async with get_db_context() as db:
            repo = WorkflowRepository(db)
            workflow = await repo.get_by_id(workflow_id)

            if not workflow:
                return f"Error: Workflow '{workflow_name}' not found."

            result = await execute_tool(
                workflow_id=workflow_id,
                workflow_name=workflow.name,
                parameters=inputs,
                user_id=str(context.user_id),
                user_email=context.user_email or "mcp@bifrost.local",
                user_name=context.user_name or "MCP User",
                org_id=str(context.org_id) if context.org_id else None,
                is_platform_admin=context.is_platform_admin,
            )

            if result.status.value == "Success":
                import json
                result_str = json.dumps(result.result, indent=2, default=str) if result.result else "null"
                return (
                    f"✓ '{workflow_name}' executed successfully!\n\n"
                    f"**Duration:** {result.duration_ms}ms\n\n"
                    f"**Result:**\n```json\n{result_str}\n```"
                )
            else:
                return (
                    f"✗ '{workflow_name}' failed!\n\n"
                    f"**Status:** {result.status.value}\n"
                    f"**Error:** {result.error or 'Unknown error'}\n\n"
                    f"**Error Type:** {result.error_type or 'Unknown'}"
                )

    except Exception as e:
        logger.exception(f"Error executing workflow tool via MCP: {e}")
        return f"Error executing workflow: {str(e)}"


# =============================================================================
# WorkflowTool - FastMCP Tool subclass for dynamic workflow parameters
# =============================================================================

# Only define WorkflowTool when FastMCP is available
_WorkflowTool: type | None = None

if HAS_FASTMCP:
    from fastmcp.tools import Tool as _FastMCPTool  # type: ignore[import-not-found]
    from fastmcp.tools.tool import ToolResult as _ToolResult  # type: ignore[import-not-found]

    class WorkflowTool(_FastMCPTool):
        """
        MCP Tool that executes a Bifrost workflow.

        Subclasses FastMCP's Tool to:
        1. Accept JSON Schema directly via `parameters` field
        2. Override `run()` to delegate to workflow execution

        This bypasses FastMCP's function signature inspection, allowing
        dynamic parameter schemas from workflow `parameters_schema`.

        The execution context is retrieved dynamically from the authenticated
        token at runtime via _get_context_from_token().
        """

        workflow_id: str
        workflow_name: str

        model_config = {"arbitrary_types_allowed": True}

        async def run(self, arguments: dict[str, Any]) -> "_ToolResult":
            """Execute the workflow with the given arguments."""
            try:
                context = _get_context_from_token()
            except Exception as e:
                return _ToolResult(content=f"Error: Authentication required - {e}")

            result = await _execute_workflow_tool_impl(
                context,
                self.workflow_id,
                self.workflow_name,
                **arguments,
            )
            return _ToolResult(content=result)

    _WorkflowTool = WorkflowTool


# =============================================================================
# Workflow Tool Name Management
# =============================================================================

# Module-level mapping: tool_name -> workflow_id (populated during registration)
_TOOL_NAME_TO_WORKFLOW_ID: dict[str, str] = {}
# Reverse mapping: workflow_id -> tool_name
_WORKFLOW_ID_TO_TOOL_NAME: dict[str, str] = {}


def _normalize_tool_name(name: str) -> str:
    """
    Convert workflow name to valid MCP tool name (snake_case).

    Examples:
        "Review Tickets" -> "review_tickets"
        "get-user-data" -> "get_user_data"
        "ProcessOrder123" -> "processorder123"
    """
    import re

    name = name.lower().strip()
    # Replace spaces, hyphens, and multiple underscores with single underscore
    name = re.sub(r"[\s\-]+", "_", name)
    # Remove any non-alphanumeric characters except underscores
    name = re.sub(r"[^a-z0-9_]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Remove leading/trailing underscores
    name = name.strip("_")
    return name


def _generate_short_suffix(length: int = 3) -> str:
    """Generate a short random alphanumeric suffix for duplicate tool names."""
    import secrets
    import string

    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def get_workflow_id_for_tool(tool_name: str) -> str | None:
    """
    Get workflow UUID for a registered MCP tool name.

    Args:
        tool_name: The MCP tool name (e.g., "review_tickets")

    Returns:
        Workflow UUID string or None if not found
    """
    return _TOOL_NAME_TO_WORKFLOW_ID.get(tool_name)


def get_registered_tool_name(workflow_id: str) -> str | None:
    """
    Get the registered MCP tool name for a workflow ID.

    Args:
        workflow_id: The workflow UUID string

    Returns:
        Tool name string or None if not registered
    """
    return _WORKFLOW_ID_TO_TOOL_NAME.get(workflow_id)


async def _notify_duplicate_workflow_names(duplicates: dict[str, list]) -> None:
    """
    Create admin notification when duplicate workflow names are detected.

    This alerts platform admins that multiple workflows have the same
    normalized name, which may cause confusion for LLM tool selection.
    """
    from src.models.contracts.notifications import NotificationCategory, NotificationCreate
    from src.services.notification_service import NotificationService

    try:
        notification_service = NotificationService()

        # Check if notification already exists (deduplication)
        existing = await notification_service.find_admin_notification_by_title(
            title="Duplicate Workflow Names in MCP Tools",
            category=NotificationCategory.SYSTEM,
        )
        if existing:
            logger.debug("Duplicate workflow name notification already exists, skipping")
            return

        # Build description with duplicate details
        details = []
        for name, workflows in duplicates.items():
            workflow_names = [w.name for w in workflows]
            details.append(f"'{name}': {', '.join(workflow_names)}")

        await notification_service.create_notification(
            user_id="system",
            request=NotificationCreate(
                category=NotificationCategory.SYSTEM,
                title="Duplicate Workflow Names in MCP Tools",
                description=(
                    f"Multiple workflows share the same normalized name. "
                    f"Consider renaming for clarity: {'; '.join(details)}"
                ),
            ),
            for_admins=True,
        )
        logger.info(f"Created admin notification for {len(duplicates)} duplicate workflow names")

    except Exception as e:
        # Don't fail tool registration if notification fails
        logger.warning(f"Failed to create duplicate workflow name notification: {e}")


async def _register_workflow_tools(mcp: "FastMCP", context: MCPContext) -> int:
    """
    Register workflow tools with FastMCP server using human-readable names.

    Creates WorkflowTool instances for each workflow with is_tool=True,
    passing the parameters_schema directly as JSON Schema. This bypasses
    FastMCP's function signature inspection.

    Tool names are normalized from workflow names (e.g., "Review Tickets" -> "review_tickets").
    Duplicate names get a short random suffix (e.g., "review_tickets_x7k").

    Returns:
        Number of workflow tools registered
    """
    global _TOOL_NAME_TO_WORKFLOW_ID, _WORKFLOW_ID_TO_TOOL_NAME

    if not HAS_FASTMCP or _WorkflowTool is None:
        logger.warning("FastMCP not available, skipping workflow tool registration")
        return 0

    from src.core.database import get_db_context
    from src.services.tool_registry import ToolRegistry

    try:
        async with get_db_context() as db:
            registry = ToolRegistry(db)
            tools = await registry.get_all_tools()

            # Clear previous mappings (in case of re-registration)
            _TOOL_NAME_TO_WORKFLOW_ID = {}
            _WORKFLOW_ID_TO_TOOL_NAME = {}

            # Group workflows by normalized name to detect duplicates
            name_groups: dict[str, list] = {}
            for tool in tools:
                normalized = _normalize_tool_name(tool.name)
                # Handle edge case: empty normalized name falls back to workflow ID
                if not normalized:
                    normalized = str(tool.id)
                name_groups.setdefault(normalized, []).append(tool)

            # Detect duplicates and notify admins
            duplicates = {name: wfs for name, wfs in name_groups.items() if len(wfs) > 1}
            if duplicates:
                await _notify_duplicate_workflow_names(duplicates)
                logger.warning(
                    f"Found {len(duplicates)} duplicate workflow names: "
                    f"{list(duplicates.keys())}"
                )

            # Assign unique tool names and register
            count = 0
            for base_name, workflows in name_groups.items():
                for i, tool in enumerate(workflows):
                    workflow_id = str(tool.id)
                    workflow_name = tool.name
                    description = tool.description or f"Execute the {workflow_name} workflow"

                    # First workflow gets clean name, duplicates get suffix
                    if i == 0:
                        tool_name = base_name
                    else:
                        tool_name = f"{base_name}_{_generate_short_suffix()}"

                    # Store mapping for middleware lookups
                    _TOOL_NAME_TO_WORKFLOW_ID[tool_name] = workflow_id
                    _WORKFLOW_ID_TO_TOOL_NAME[workflow_id] = tool_name

                    # Build JSON Schema from parameters_schema
                    properties: dict[str, Any] = {}
                    required: list[str] = []
                    for param in tool.parameters_schema:
                        param_name = param.get("name")
                        if not param_name:
                            continue

                        param_type = param.get("type", "string")
                        json_type = _map_type_to_json_schema(param_type)

                        properties[param_name] = {
                            "type": json_type,
                            "description": param.get("label") or param.get("description") or param_name,
                        }

                        if param.get("required", False):
                            required.append(param_name)

                    # Create WorkflowTool with human-readable name
                    # Context is retrieved dynamically from authenticated token at runtime
                    workflow_tool = _WorkflowTool(
                        name=tool_name,  # Human-readable name instead of UUID
                        description=description,
                        workflow_id=workflow_id,
                        workflow_name=workflow_name,
                        parameters={
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        },
                    )

                    # Add to FastMCP server
                    try:
                        mcp.add_tool(workflow_tool)
                        count += 1
                        logger.debug(
                            f"Registered workflow tool: {tool_name} "
                            f"(workflow: {workflow_name}, id: {workflow_id})"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to register workflow tool {workflow_name}: {e}")

            logger.info(f"Registered {count} workflow tools with FastMCP")
            return count

    except Exception as e:
        logger.exception(f"Error registering workflow tools: {e}")
        return 0


def _register_fastmcp_tools(mcp: "FastMCP", context: MCPContext, enabled_tools: set[str] | None) -> None:
    """
    Register system tools with a FastMCP server.

    Note: The `context` parameter is used for SDK mode (where context is fixed per-session).
    For FastMCP HTTP mode, tools use _get_context_from_token() to get the authenticated
    user's context per-request. This is determined at runtime based on whether we're
    in an authenticated FastMCP request (token available) or SDK mode (token not available).
    """
    def _get_context() -> MCPContext:
        """Get context from token if available (FastMCP), otherwise use provided context (SDK)."""
        try:
            return _get_context_from_token()
        except Exception:
            # Not in FastMCP request context, use provided context (SDK mode)
            return context

    if enabled_tools is None or "execute_workflow" in enabled_tools:
        @mcp.tool(
            name="execute_workflow",
            description="Execute a Bifrost workflow by name and return the results.",
        )
        async def execute_workflow(workflow_name: str, inputs: dict[str, Any] | None = None) -> str:
            return await _execute_workflow_impl(_get_context(), workflow_name, inputs)

    if enabled_tools is None or "list_workflows" in enabled_tools:
        @mcp.tool(
            name="list_workflows",
            description="List workflows registered in Bifrost.",
        )
        async def list_workflows(query: str | None = None, category: str | None = None) -> str:
            return await _list_workflows_impl(_get_context(), query, category)

    if enabled_tools is None or "list_integrations" in enabled_tools:
        @mcp.tool(
            name="list_integrations",
            description="List available integrations that can be used in workflows.",
        )
        async def list_integrations() -> str:
            return await _list_integrations_impl(_get_context())

    if enabled_tools is None or "list_forms" in enabled_tools:
        @mcp.tool(
            name="list_forms",
            description="List all forms with their URLs.",
        )
        async def list_forms() -> str:
            return await _list_forms_impl(_get_context())

    if enabled_tools is None or "get_form_schema" in enabled_tools:
        @mcp.tool(
            name="get_form_schema",
            description="Get documentation about form structure and field types.",
        )
        async def get_form_schema() -> str:
            return await _get_form_schema_impl(_get_context())

    if enabled_tools is None or "validate_form_schema" in enabled_tools:
        @mcp.tool(
            name="validate_form_schema",
            description="Validate a form JSON structure before saving.",
        )
        async def validate_form_schema(form_json: str) -> str:
            return await _validate_form_schema_impl(_get_context(), form_json)

    # Form CRUD operations (for external access like Claude Desktop)
    if enabled_tools is None or "create_form" in enabled_tools:
        @mcp.tool(
            name="create_form",
            description="Create a new form with fields linked to a workflow.",
        )
        async def create_form(
            name: str,
            workflow_id: str,
            fields: list[dict[str, Any]],
            description: str | None = None,
            launch_workflow_id: str | None = None,
        ) -> str:
            return await _create_form_impl(
                _get_context(), name, workflow_id, fields, description, launch_workflow_id
            )

    if enabled_tools is None or "get_form" in enabled_tools:
        @mcp.tool(
            name="get_form",
            description="Get detailed information about a specific form including all fields.",
        )
        async def get_form(form_id: str | None = None, form_name: str | None = None) -> str:
            return await _get_form_impl(_get_context(), form_id, form_name)

    if enabled_tools is None or "update_form" in enabled_tools:
        @mcp.tool(
            name="update_form",
            description="Update an existing form's properties or fields.",
        )
        async def update_form(
            form_id: str,
            name: str | None = None,
            description: str | None = None,
            workflow_id: str | None = None,
            launch_workflow_id: str | None = None,
            fields: list[dict[str, Any]] | None = None,
            is_active: bool | None = None,
        ) -> str:
            return await _update_form_impl(
                _get_context(), form_id, name, description, workflow_id, launch_workflow_id, fields, is_active
            )

    if enabled_tools is None or "search_knowledge" in enabled_tools:
        @mcp.tool(
            name="search_knowledge",
            description="Search the Bifrost knowledge base.",
        )
        async def search_knowledge(query: str, namespace: str | None = None, limit: int = 5) -> str:
            context = await _get_context_with_namespaces()
            return await _search_knowledge_impl(context, query, namespace, limit)

    # File Operations (for external access like Claude Desktop)
    if enabled_tools is None or "read_file" in enabled_tools:
        @mcp.tool(
            name="read_file",
            description="Read a file from the Bifrost workspace.",
        )
        async def read_file(path: str) -> str:
            return await _read_file_impl(_get_context(), path)

    if enabled_tools is None or "write_file" in enabled_tools:
        @mcp.tool(
            name="write_file",
            description="Write content to a file in the Bifrost workspace.",
        )
        async def write_file(path: str, content: str) -> str:
            return await _write_file_impl(_get_context(), path, content)

    if enabled_tools is None or "list_files" in enabled_tools:
        @mcp.tool(
            name="list_files",
            description="List files and directories in the Bifrost workspace.",
        )
        async def list_files(directory: str = "") -> str:
            return await _list_files_impl(_get_context(), directory)

    if enabled_tools is None or "delete_file" in enabled_tools:
        @mcp.tool(
            name="delete_file",
            description="Delete a file or directory from the Bifrost workspace.",
        )
        async def delete_file(path: str) -> str:
            return await _delete_file_impl(_get_context(), path)

    if enabled_tools is None or "search_files" in enabled_tools:
        @mcp.tool(
            name="search_files",
            description="Search for text patterns across files in the Bifrost workspace.",
        )
        async def search_files(query: str, pattern: str = "**/*", case_sensitive: bool = False) -> str:
            return await _search_files_impl(_get_context(), query, pattern, case_sensitive)

    if enabled_tools is None or "create_folder" in enabled_tools:
        @mcp.tool(
            name="create_folder",
            description="Create a new folder in the Bifrost workspace.",
        )
        async def create_folder(path: str) -> str:
            return await _create_folder_impl(_get_context(), path)

    # Workflow and Execution Tools
    if enabled_tools is None or "validate_workflow" in enabled_tools:
        @mcp.tool(
            name="validate_workflow",
            description="Validate a workflow Python file for syntax and decorator issues.",
        )
        async def validate_workflow(file_path: str) -> str:
            return await _validate_workflow_impl(_get_context(), file_path)

    if enabled_tools is None or "get_workflow_schema" in enabled_tools:
        @mcp.tool(
            name="get_workflow_schema",
            description="Get documentation about workflow structure, decorators, and SDK features.",
        )
        async def get_workflow_schema() -> str:
            return await _get_workflow_schema_impl(_get_context())

    if enabled_tools is None or "get_workflow" in enabled_tools:
        @mcp.tool(
            name="get_workflow",
            description="Get detailed metadata for a specific workflow.",
        )
        async def get_workflow(workflow_id: str | None = None, workflow_name: str | None = None) -> str:
            return await _get_workflow_impl(_get_context(), workflow_id, workflow_name)

    if enabled_tools is None or "list_executions" in enabled_tools:
        @mcp.tool(
            name="list_executions",
            description="List recent workflow executions.",
        )
        async def list_executions(
            workflow_name: str | None = None, status: str | None = None, limit: int = 20
        ) -> str:
            return await _list_executions_impl(_get_context(), workflow_name, status, limit)

    if enabled_tools is None or "get_execution" in enabled_tools:
        @mcp.tool(
            name="get_execution",
            description="Get details and logs for a specific workflow execution.",
        )
        async def get_execution(execution_id: str) -> str:
            return await _get_execution_impl(_get_context(), execution_id)


# =============================================================================
# BifrostMCPServer
# =============================================================================

class BifrostMCPServer:
    """
    Bifrost MCP Server with dual-mode support.

    Creates MCP servers with tools registered based on user context and
    permissions. Supports both:
    - SDK mode: In-process MCP for Claude Agent SDK (Coding Agent)
    - FastMCP mode: HTTP server for external access (Claude Desktop)

    Usage:
        # Create server with context
        context = MCPContext(user_id=user.id, org_id=user.org_id)
        server = BifrostMCPServer(context)

        # For SDK in-process use (Coding Agent)
        sdk_server = server.get_sdk_server()
        options = ClaudeAgentOptions(mcp_servers={"bifrost": sdk_server})

        # For FastMCP HTTP use (external)
        fastmcp_server = server.get_fastmcp_server()
    """

    def __init__(
        self,
        context: MCPContext,
        *,
        name: str = "bifrost",
    ):
        """
        Initialize Bifrost MCP server.

        Args:
            context: MCP context with user/org information
            name: Server name (default: "bifrost")
        """
        self.context = context
        self._name = name

        # Determine enabled tools
        self._enabled_tools: set[str] | None = None
        if context.enabled_system_tools:
            self._enabled_tools = set(context.enabled_system_tools)

        # SDK server (lazy initialized)
        self._sdk_server: Any = None

        # FastMCP server (lazy initialized)
        self._fastmcp: Any = None

    def get_sdk_server(self) -> Any:
        """
        Get Claude Agent SDK compatible MCP server.

        The SDK server is cached for reuse across multiple calls.

        Returns:
            MCP server instance for ClaudeAgentOptions.mcp_servers
        """
        if self._sdk_server is None:
            tools = _create_sdk_tools(self.context, self._enabled_tools)
            self._sdk_server = create_sdk_mcp_server(
                name=self._name,
                version="1.0.0",
                tools=tools,
            )
            logger.info(f"Created SDK MCP server with {len(tools)} tools")
        return self._sdk_server

    def get_fastmcp_server(self, auth: Any = None) -> "FastMCP":
        """
        Get FastMCP server for HTTP access.

        The server is cached for reuse. If auth is provided, a new server
        is created with authentication enabled.

        Args:
            auth: Optional authentication provider (e.g., token verifier).
                  If provided, creates a new server with auth.

        Returns:
            FastMCP server instance
        """
        if not HAS_FASTMCP:
            raise ImportError(
                "fastmcp is required for external MCP access. "
                "Install it with: pip install 'fastmcp>=2.0,<3'"
            )

        # Build icon list for branding
        icons = []
        if _Icon is not None:
            icons = [
                _Icon(
                    src=BIFROST_ICON_URL,
                    mimeType="image/svg+xml",
                    sizes=["any"],
                )
            ]

        # If auth is provided, always create a new server with auth
        if auth is not None:
            assert _FastMCP is not None
            mcp = _FastMCP(
                self._name,
                auth=auth,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            _register_fastmcp_tools(mcp, self.context, self._enabled_tools)
            tool_count = len(self._enabled_tools) if self._enabled_tools else 18
            logger.info(f"Created FastMCP server with {tool_count} tools and auth")
            return mcp

        # Otherwise use cached server
        if self._fastmcp is None:
            assert _FastMCP is not None  # For type checker; HAS_FASTMCP check above ensures this
            self._fastmcp = _FastMCP(
                self._name,
                website_url=BIFROST_WEBSITE_URL,
                icons=icons,
            )
            _register_fastmcp_tools(self._fastmcp, self.context, self._enabled_tools)
            tool_count = len(self._enabled_tools) if self._enabled_tools else 18
            logger.info(f"Created FastMCP server with {tool_count} tools")
        return self._fastmcp

    def get_tool_names(self) -> list[str]:
        """Get list of registered tool names (prefixed for SDK use)."""
        all_tools = [
            "execute_workflow", "list_workflows", "list_integrations",
            "list_forms", "get_form_schema", "validate_form_schema", "search_knowledge",
            # File operations
            "read_file", "write_file", "list_files", "delete_file", "search_files", "create_folder",
            # Workflow and execution tools
            "validate_workflow", "get_workflow_schema", "get_workflow", "list_executions", "get_execution",
        ]
        if self._enabled_tools:
            tools = [t for t in all_tools if t in self._enabled_tools]
        else:
            tools = all_tools
        return [f"mcp__{self._name}__{t}" for t in tools]


# Factory function for creating user-scoped MCP servers
async def create_user_mcp_server(
    user_id: UUID | str,
    org_id: UUID | str | None = None,
    is_platform_admin: bool = False,
    enabled_tools: list[str] | None = None,
    user_email: str = "",
    user_name: str = "",
) -> BifrostMCPServer:
    """
    Create an MCP server scoped to a user's permissions.

    Args:
        user_id: User ID
        org_id: Organization ID (optional)
        is_platform_admin: Whether user is platform admin
        enabled_tools: List of enabled tool IDs (None = all)
        user_email: User email for context
        user_name: User name for context

    Returns:
        BifrostMCPServer configured for this user
    """
    context = MCPContext(
        user_id=user_id,
        org_id=org_id,
        is_platform_admin=is_platform_admin,
        enabled_system_tools=enabled_tools or [],
        user_email=user_email,
        user_name=user_name,
    )
    return BifrostMCPServer(context)
