"""
Form MCP Tools

Tools for listing, creating, validating, and managing forms.
"""

import logging
from typing import Any
from uuid import UUID

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

# MCPContext is imported where needed to avoid circular imports

logger = logging.getLogger(__name__)


@system_tool(
    id="list_forms",
    name="List Forms",
    description="List all forms with their URLs.",
    category=ToolCategory.FORM,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_forms(context: Any) -> str:
    """List all forms."""
    import json

    from src.core.database import get_db_context
    from src.core.org_filter import OrgFilterType
    from src.repositories.forms import FormRepository

    logger.info("MCP list_forms called")

    try:
        async with get_db_context() as db:
            # Determine filter type and org_id based on context
            if context.is_platform_admin:
                # Platform admins see all forms
                filter_type = OrgFilterType.ALL
                org_id = None
            elif context.org_id:
                # Org users see their org's forms + global forms
                filter_type = OrgFilterType.ORG_PLUS_GLOBAL
                org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
            else:
                # No org context - only global forms
                filter_type = OrgFilterType.GLOBAL_ONLY
                org_id = None

            repo = FormRepository(db, org_id)
            forms = await repo.list_forms(filter_type, active_only=True)

            return json.dumps({
                "forms": [
                    {
                        "id": str(form.id),
                        "name": form.name,
                        "description": form.description,
                        "workflow_id": form.workflow_id,
                        "url": f"/forms/{form.id}",
                    }
                    for form in forms
                ],
                "count": len(forms),
            })

    except Exception as e:
        logger.exception(f"Error listing forms via MCP: {e}")
        return json.dumps({"error": f"Error listing forms: {str(e)}"})


@system_tool(
    id="get_form_schema",
    name="Get Form Schema",
    description="Get documentation about form structure and field types.",
    category=ToolCategory.FORM,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_form_schema(context: Any) -> str:
    """Get form schema documentation."""
    return """# Form Schema Documentation

Forms in Bifrost are defined using a JSON schema with the following structure:

## Form Definition

```json
{
  "name": "Example Form",
  "description": "Form description",
  "workflow_id": "optional-workflow-uuid",
  "form_schema": {
    "fields": [
      {
        "name": "field_name",
        "type": "text",
        "label": "Field Label",
        "required": true
      }
    ]
  }
}
```

**Important:** Fields must be nested inside `form_schema.fields`, not at the top level.

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

### Textarea Field
```json
{
  "name": "description",
  "type": "textarea",
  "label": "Description",
  "placeholder": "Enter details...",
  "help_text": "Provide a detailed description"
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
- `type`: Field type (required) - text, textarea, number, select, boolean, date, email, password
- `label`: Display label
- `required`: Whether field is required (default: false)
- `default`: Default value
- `placeholder`: Placeholder text
- `help_text`: Help text shown below the field

## Complete Example

```json
{
  "name": "User Registration",
  "description": "Register a new user account",
  "workflow_id": "abc123-workflow-uuid",
  "form_schema": {
    "fields": [
      {
        "name": "email",
        "type": "email",
        "label": "Email Address",
        "required": true,
        "placeholder": "user@example.com"
      },
      {
        "name": "full_name",
        "type": "text",
        "label": "Full Name",
        "required": true
      },
      {
        "name": "notes",
        "type": "textarea",
        "label": "Additional Notes",
        "required": false,
        "help_text": "Any additional information"
      }
    ]
  }
}
```
"""


@system_tool(
    id="create_form",
    name="Create Form",
    description="Create a new form with fields linked to a workflow.",
    category=ToolCategory.FORM,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
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
            "launch_workflow_id": {"type": "string", "description": "Optional UUID of workflow to run before form display"},
            "scope": {
                "type": "string",
                "enum": ["global", "organization"],
                "description": "Resource scope: 'global' (visible to all orgs) or 'organization' (default)",
            },
            "organization_id": {
                "type": "string",
                "description": "Organization UUID (overrides context.org_id when scope='organization')",
            },
        },
        "required": ["name", "workflow_id", "fields"],
    },
)
async def create_form(
    context: Any,
    name: str,
    workflow_id: str,
    fields: list[dict[str, Any]],
    description: str | None = None,
    launch_workflow_id: str | None = None,
    scope: str = "organization",
    organization_id: str | None = None,
) -> str:
    """Create a new form with fields linked to a workflow.

    Args:
        context: MCP context with user permissions
        name: Form name (1-200 chars)
        workflow_id: UUID of workflow to execute on form submit
        fields: Array of field definitions
        description: Optional form description
        launch_workflow_id: Optional UUID of workflow to run before form display
        scope: 'global' (visible to all orgs) or 'organization' (default)
        organization_id: Override context.org_id when scope='organization'

    Returns:
        JSON with form details
    """
    import json
    from datetime import datetime
    from uuid import UUID as UUID_TYPE

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models import Form as FormORM
    from src.models import FormSchema
    from src.repositories.workflows import WorkflowRepository
    from src.routers.forms import _form_schema_to_fields, _write_form_to_file

    logger.info(f"MCP create_form called: name={name}, workflow_id={workflow_id}, scope={scope}")

    # Validate inputs
    if not name:
        return json.dumps({"error": "name is required"})
    if not workflow_id:
        return json.dumps({"error": "workflow_id is required"})
    if not fields:
        return json.dumps({"error": "fields array is required"})
    if len(name) > 200:
        return json.dumps({"error": "name must be 200 characters or less"})

    # Validate scope parameter
    if scope not in ("global", "organization"):
        return json.dumps({"error": "scope must be 'global' or 'organization'"})

    # Determine effective organization_id based on scope
    effective_org_id: UUID_TYPE | None = None
    if scope == "global":
        # Global resources have no organization_id
        effective_org_id = None
    else:
        # Organization scope: use provided organization_id or fall back to context.org_id
        if organization_id:
            try:
                effective_org_id = UUID_TYPE(organization_id)
            except ValueError:
                return json.dumps({"error": f"organization_id '{organization_id}' is not a valid UUID"})
        elif context.org_id:
            effective_org_id = UUID_TYPE(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
        else:
            return json.dumps({"error": "organization_id is required when scope='organization' and no context org_id is set"})

    # Validate workflow_id is a valid UUID
    try:
        UUID_TYPE(workflow_id)
    except ValueError:
        return json.dumps({"error": f"workflow_id '{workflow_id}' is not a valid UUID"})

    # Validate launch_workflow_id if provided
    if launch_workflow_id:
        try:
            UUID_TYPE(launch_workflow_id)
        except ValueError:
            return json.dumps({"error": f"launch_workflow_id '{launch_workflow_id}' is not a valid UUID"})

    try:
        async with get_db_context() as db:
            # Verify workflow exists
            workflow_repo = WorkflowRepository(db)
            workflow = await workflow_repo.get(UUID_TYPE(workflow_id))
            if not workflow:
                return json.dumps({"error": f"Workflow '{workflow_id}' not found. Use list_workflows to see available workflows."})

            # Verify launch workflow if provided
            launch_workflow = None
            if launch_workflow_id:
                launch_workflow = await workflow_repo.get(UUID_TYPE(launch_workflow_id))
                if not launch_workflow:
                    return json.dumps({"error": f"Launch workflow '{launch_workflow_id}' not found."})

            # Validate form schema
            try:
                FormSchema.model_validate({"fields": fields})
            except Exception as e:
                return json.dumps({"error": f"Error validating form schema: {str(e)}"})

            # Create form record
            now = datetime.utcnow()

            form = FormORM(
                name=name,
                description=description,
                workflow_id=workflow_id,
                launch_workflow_id=launch_workflow_id,
                access_level="role_based",
                organization_id=effective_org_id,
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

            return json.dumps({
                "success": True,
                "id": str(form.id),
                "name": form.name,
                "url": f"/forms/{form.id}",
                "workflow_id": workflow_id,
                "workflow_name": workflow.name,
                "field_count": len(fields),
                "launch_workflow_id": launch_workflow_id,
                "launch_workflow_name": launch_workflow.name if launch_workflow else None,
                "file_path": form.file_path,
            })

    except Exception as e:
        logger.exception(f"Error creating form via MCP: {e}")
        return json.dumps({"error": f"Error creating form: {str(e)}"})


@system_tool(
    id="get_form",
    name="Get Form",
    description="Get detailed information about a specific form including all fields.",
    category=ToolCategory.FORM,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "form_id": {"type": "string", "description": "Form UUID"},
            "form_name": {"type": "string", "description": "Form name (alternative to ID)"},
        },
        "required": [],
    },
)
async def get_form(
    context: Any,
    form_id: str | None = None,
    form_name: str | None = None,
) -> str:
    """Get detailed information about a specific form.

    Args:
        context: MCP context with user permissions
        form_id: Form UUID (preferred)
        form_name: Form name (alternative to ID)

    Returns:
        JSON with form details
    """
    import json
    from uuid import UUID as UUID_TYPE

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models import Form as FormORM
    from src.repositories.workflows import WorkflowRepository

    logger.info(f"MCP get_form called: form_id={form_id}, form_name={form_name}")

    if not form_id and not form_name:
        return json.dumps({"error": "Either form_id or form_name is required"})

    try:
        async with get_db_context() as db:
            # Build query
            query = select(FormORM).options(selectinload(FormORM.fields))

            if form_id:
                try:
                    uuid_id = UUID_TYPE(form_id)
                except ValueError:
                    return json.dumps({"error": f"'{form_id}' is not a valid UUID"})
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
                return json.dumps({"error": f"Form '{identifier}' not found. Use list_forms to see available forms."})

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

            # Sort fields by position
            sorted_fields = sorted(form.fields, key=lambda f: f.position) if form.fields else []

            return json.dumps({
                "id": str(form.id),
                "name": form.name,
                "description": form.description,
                "url": f"/forms/{form.id}",
                "is_active": form.is_active,
                "access_level": form.access_level or "role_based",
                "organization_id": str(form.organization_id) if form.organization_id else None,
                "workflow_id": form.workflow_id,
                "workflow_name": workflow_name,
                "launch_workflow_id": form.launch_workflow_id,
                "launch_workflow_name": launch_workflow_name,
                "fields": [
                    {
                        "name": field.name,
                        "type": field.type,
                        "label": field.label,
                        "required": field.required,
                        "placeholder": field.placeholder,
                        "help_text": field.help_text,
                        "default_value": field.default_value,
                        "options": field.options,
                        "data_provider_id": field.data_provider_id,
                        "position": field.position,
                    }
                    for field in sorted_fields
                ],
            })

    except Exception as e:
        logger.exception(f"Error getting form via MCP: {e}")
        return json.dumps({"error": f"Error getting form: {str(e)}"})


@system_tool(
    id="update_form",
    name="Update Form",
    description="Update an existing form's properties or fields.",
    category=ToolCategory.FORM,
    default_enabled_for_coding_agent=False,
    is_restricted=True,
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
async def update_form(
    context: Any,
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
        JSON with update confirmation
    """
    import json
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
        return json.dumps({"error": "form_id is required"})

    # Validate form_id is a valid UUID
    try:
        uuid_id = UUID_TYPE(form_id)
    except ValueError:
        return json.dumps({"error": f"'{form_id}' is not a valid UUID"})

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
                return json.dumps({"error": f"Form '{form_id}' not found. Use list_forms to see available forms."})

            # Check access for non-admins
            if not context.is_platform_admin:
                if form.organization_id:
                    if context.org_id and str(form.organization_id) != str(context.org_id):
                        return json.dumps({"error": "You don't have permission to update this form."})
                # Global forms can only be updated by admins
                if form.organization_id is None:
                    return json.dumps({"error": "Only platform admins can update global forms."})

            old_file_path = form.file_path
            updates_made = []

            # Apply updates
            if name is not None:
                if len(name) > 200:
                    return json.dumps({"error": "name must be 200 characters or less"})
                form.name = name
                updates_made.append("name")

            if description is not None:
                form.description = description
                updates_made.append("description")

            if workflow_id is not None:
                try:
                    UUID_TYPE(workflow_id)
                except ValueError:
                    return json.dumps({"error": f"workflow_id '{workflow_id}' is not a valid UUID"})

                workflow_repo = WorkflowRepository(db)
                workflow = await workflow_repo.get(UUID_TYPE(workflow_id))
                if not workflow:
                    return json.dumps({"error": f"Workflow '{workflow_id}' not found."})
                form.workflow_id = workflow_id
                updates_made.append("workflow_id")

            if launch_workflow_id is not None:
                if launch_workflow_id == "":
                    # Clear launch workflow
                    form.launch_workflow_id = None
                    updates_made.append("launch_workflow_id")
                else:
                    try:
                        UUID_TYPE(launch_workflow_id)
                    except ValueError:
                        return json.dumps({"error": f"launch_workflow_id '{launch_workflow_id}' is not a valid UUID"})

                    workflow_repo = WorkflowRepository(db)
                    launch_workflow = await workflow_repo.get(UUID_TYPE(launch_workflow_id))
                    if not launch_workflow:
                        return json.dumps({"error": f"Launch workflow '{launch_workflow_id}' not found."})
                    form.launch_workflow_id = launch_workflow_id
                    updates_made.append("launch_workflow_id")

            if is_active is not None:
                form.is_active = is_active
                updates_made.append("is_active")

            if fields is not None:
                # Validate new fields
                try:
                    FormSchema.model_validate({"fields": fields})
                except Exception as e:
                    return json.dumps({"error": f"Error validating form schema: {str(e)}"})

                # Delete existing fields
                await db.execute(
                    delete(FormFieldORM).where(FormFieldORM.form_id == form.id)
                )

                # Add new fields
                field_records = _form_schema_to_fields({"fields": fields}, form.id)
                for field in field_records:
                    db.add(field)

                updates_made.append("fields")

            if not updates_made:
                return json.dumps({"error": "No updates provided. Specify at least one field to update."})

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

            return json.dumps({
                "success": True,
                "id": str(form.id),
                "name": form.name,
                "updates": updates_made,
                "file_path": form.file_path,
            })

    except Exception as e:
        logger.exception(f"Error updating form via MCP: {e}")
        return json.dumps({"error": f"Error updating form: {str(e)}"})
