"""
Table MCP Tools

Tools for listing, getting, creating, and updating tables.
Tables are flexible document stores scoped to global, organization, or application level.
"""

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="list_tables",
    name="List Tables",
    description="List tables in the platform. Platform admin only.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["global", "organization", "application"],
                "description": "Filter by scope: 'global' (platform-wide), 'organization' (org-specific), 'application' (app-specific)",
            },
        },
        "required": [],
    },
)
async def list_tables(
    context: Any,
    scope: str | None = None,
) -> str:
    """List tables with org filtering for non-admins."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.tables import Table

    logger.info(f"MCP list_tables called with scope={scope}")

    try:
        async with get_db_context() as db:
            query = select(Table)

            # Non-admins can only see their org's tables + global tables
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Table.organization_id == context.org_id)
                    | (Table.organization_id.is_(None))
                )

            # Apply scope filter if provided
            if scope == "global":
                query = query.where(Table.organization_id.is_(None))
                query = query.where(Table.application_id.is_(None))
            elif scope == "organization":
                query = query.where(Table.organization_id.isnot(None))
                query = query.where(Table.application_id.is_(None))
            elif scope == "application":
                query = query.where(Table.application_id.isnot(None))

            result = await db.execute(query.order_by(Table.name))
            tables = result.scalars().all()

            tables_data = []
            for table in tables:
                # Determine scope
                if table.application_id:
                    table_scope = "application"
                elif table.organization_id:
                    table_scope = "organization"
                else:
                    table_scope = "global"

                tables_data.append({
                    "id": str(table.id),
                    "name": table.name,
                    "description": table.description,
                    "scope": table_scope,
                    "organization_id": str(table.organization_id) if table.organization_id else None,
                    "application_id": str(table.application_id) if table.application_id else None,
                    "created_at": table.created_at.isoformat() if table.created_at else None,
                })

            return json.dumps({"tables": tables_data, "count": len(tables_data)})

    except Exception as e:
        logger.exception(f"Error listing tables via MCP: {e}")
        return json.dumps({"error": f"Error listing tables: {str(e)}"})


@system_tool(
    id="get_table",
    name="Get Table",
    description="Get table details including schema by ID. Platform admin only.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "table_id": {"type": "string", "description": "Table UUID"},
        },
        "required": [],
    },
)
async def get_table(
    context: Any,
    table_id: str | None = None,
) -> str:
    """Get table details including schema."""
    from sqlalchemy import func, select

    from src.core.database import get_db_context
    from src.models.orm.tables import Document, Table

    logger.info(f"MCP get_table called with id={table_id}")

    if not table_id:
        return json.dumps({"error": "table_id is required"})

    try:
        table_uuid = UUID(table_id)
    except ValueError:
        return json.dumps({"error": f"Invalid table_id format: {table_id}"})

    try:
        async with get_db_context() as db:
            query = select(Table).where(Table.id == table_uuid)

            # Non-admins can only see their org's tables + global
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Table.organization_id == context.org_id)
                    | (Table.organization_id.is_(None))
                )

            result = await db.execute(query)
            table = result.scalar_one_or_none()

            if not table:
                return json.dumps({"error": f"Table not found: {table_id}"})

            # Get document count
            count_query = (
                select(func.count())
                .select_from(Document)
                .where(Document.table_id == table_uuid)
            )
            count_result = await db.execute(count_query)
            document_count = count_result.scalar() or 0

            # Determine scope
            if table.application_id:
                table_scope = "application"
            elif table.organization_id:
                table_scope = "organization"
            else:
                table_scope = "global"

            # Extract columns from schema if available
            columns = []
            if table.schema and isinstance(table.schema, dict):
                columns = table.schema.get("columns", [])

            return json.dumps({
                "id": str(table.id),
                "name": table.name,
                "description": table.description,
                "scope": table_scope,
                "organization_id": str(table.organization_id) if table.organization_id else None,
                "application_id": str(table.application_id) if table.application_id else None,
                "schema": table.schema,
                "columns": columns,
                "document_count": document_count,
                "created_at": table.created_at.isoformat() if table.created_at else None,
                "updated_at": table.updated_at.isoformat() if table.updated_at else None,
                "created_by": table.created_by,
            })

    except Exception as e:
        logger.exception(f"Error getting table via MCP: {e}")
        return json.dumps({"error": f"Error getting table: {str(e)}"})


@system_tool(
    id="get_table_schema",
    name="Get Table Schema Documentation",
    description="Get documentation about table structure, column types, and scope options.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_table_schema(context: Any) -> str:
    """Return markdown documentation about table structure."""
    return """# Table Schema Documentation

Tables in Bifrost are flexible document stores, similar to Dataverse or Airtable.
They store JSON documents with optional schema hints for validation and UI.

## Table Scope

Tables can be scoped at three levels:

| Scope | organization_id | application_id | Visibility |
|-------|-----------------|----------------|------------|
| **global** | NULL | NULL | All organizations |
| **organization** | UUID | NULL | Single organization |
| **application** | UUID | UUID | Single application |

## Creating Tables

Use `create_table` to create a new table:

```json
{
  "name": "Customers",
  "scope": "organization",
  "organization_id": "org-uuid",
  "columns": [
    {"name": "name", "type": "string", "required": true},
    {"name": "email", "type": "string"},
    {"name": "status", "type": "string", "enum": ["active", "inactive"]}
  ]
}
```

## Column Types

Supported column types for schema hints:

| Type | Description | Options |
|------|-------------|---------|
| `string` | Text value | `minLength`, `maxLength`, `pattern`, `enum` |
| `number` | Numeric value | `minimum`, `maximum` |
| `integer` | Whole number | `minimum`, `maximum` |
| `boolean` | True/false | - |
| `date` | ISO date string | - |
| `datetime` | ISO datetime string | - |
| `json` | Nested JSON object | - |
| `array` | List of values | `items` (type of array elements) |

## Column Properties

Each column can have these properties:

```json
{
  "name": "status",
  "type": "string",
  "required": true,
  "description": "Customer status",
  "default": "active",
  "enum": ["active", "inactive", "pending"]
}
```

## Documents

Documents are JSON records stored in tables. Each document has:
- `id`: Unique identifier (auto-generated UUID or custom string)
- `data`: The actual document data (JSONB)
- `created_at`, `updated_at`: Timestamps
- `created_by`, `updated_by`: User tracking

## Schema Enforcement

The schema field is optional and provides hints for:
- Form field generation
- UI validation
- API validation (when enabled)

Documents can contain any JSON data regardless of schema.
The schema is not strictly enforced at the database level.

## Multi-tenancy

When listing or getting tables:
- **Platform admins**: See all tables
- **Regular users**: See global tables + their organization's tables

When creating tables:
- Set `scope` to 'global', 'organization', or 'application'
- Provide `organization_id` for org-scoped tables
- Provide `application_id` (and `organization_id`) for app-scoped tables

## Example: Full Table Definition

```json
{
  "name": "Support Tickets",
  "description": "Customer support tickets",
  "scope": "organization",
  "organization_id": "abc-123",
  "columns": [
    {"name": "title", "type": "string", "required": true, "maxLength": 200},
    {"name": "description", "type": "string"},
    {"name": "priority", "type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
    {"name": "status", "type": "string", "enum": ["open", "in_progress", "resolved", "closed"], "default": "open"},
    {"name": "assignee_id", "type": "string"},
    {"name": "tags", "type": "array", "items": {"type": "string"}},
    {"name": "metadata", "type": "json"}
  ]
}
```
"""


@system_tool(
    id="create_table",
    name="Create Table",
    description="Create a new table with specified scope. Requires platform admin for global scope.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Table name"},
            "description": {"type": "string", "description": "Table description"},
            "scope": {
                "type": "string",
                "enum": ["global", "organization", "application"],
                "description": "Table scope: 'global' (platform-wide), 'organization' (org-specific), 'application' (app-specific)",
            },
            "organization_id": {
                "type": "string",
                "description": "Organization UUID (required for 'organization' and 'application' scope)",
            },
            "application_id": {
                "type": "string",
                "description": "Application UUID (required for 'application' scope)",
            },
            "columns": {
                "type": "array",
                "description": "Column definitions for the table schema",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "required": {"type": "boolean"},
                        "description": {"type": "string"},
                        "default": {},
                        "enum": {"type": "array"},
                    },
                },
            },
        },
        "required": ["name"],
    },
)
async def create_table(
    context: Any,
    name: str,
    description: str | None = None,
    scope: str = "organization",
    organization_id: str | None = None,
    application_id: str | None = None,
    columns: list[dict[str, Any]] | None = None,
) -> str:
    """Create a new table with explicit scope."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.tables import Table

    logger.info(f"MCP create_table called with name={name}, scope={scope}")

    if not name:
        return json.dumps({"error": "name is required"})

    # Validate scope parameters
    if scope == "organization":
        if not organization_id:
            # Default to context org_id for non-admins
            if context.org_id:
                organization_id = str(context.org_id)
            else:
                return json.dumps({"error": "organization_id is required for organization scope"})
    elif scope == "application":
        if not application_id:
            return json.dumps({"error": "application_id is required for application scope"})
        if not organization_id:
            return json.dumps({"error": "organization_id is required for application scope"})
    elif scope == "global":
        # Global tables can only be created by platform admins
        if not context.is_platform_admin:
            return json.dumps({"error": "Only platform admins can create global tables"})
        organization_id = None
        application_id = None

    # Parse UUIDs
    org_uuid: UUID | None = None
    app_uuid: UUID | None = None

    if organization_id:
        try:
            org_uuid = UUID(organization_id)
        except ValueError:
            return json.dumps({"error": f"Invalid organization_id format: {organization_id}"})

    if application_id:
        try:
            app_uuid = UUID(application_id)
        except ValueError:
            return json.dumps({"error": f"Invalid application_id format: {application_id}"})

    # Non-admins can only create tables in their own org
    if not context.is_platform_admin and context.org_id:
        if org_uuid and org_uuid != context.org_id:
            return json.dumps({"error": "Cannot create tables in other organizations"})

    try:
        async with get_db_context() as db:
            # Check for duplicate name within same scope
            query = select(Table).where(Table.name == name)
            if org_uuid:
                query = query.where(Table.organization_id == org_uuid)
            else:
                query = query.where(Table.organization_id.is_(None))

            if app_uuid:
                query = query.where(Table.application_id == app_uuid)
            else:
                query = query.where(Table.application_id.is_(None))

            existing = await db.execute(query)
            if existing.scalar_one_or_none():
                return json.dumps({"error": f"Table with name '{name}' already exists in this scope"})

            # Build schema from columns
            schema: dict[str, Any] | None = None
            if columns:
                schema = {"columns": columns}

            # Create table
            table = Table(
                id=uuid4(),
                name=name,
                description=description,
                organization_id=org_uuid,
                application_id=app_uuid,
                schema=schema,
                created_by=str(context.user_id),
            )
            db.add(table)
            await db.commit()

            return json.dumps({
                "success": True,
                "id": str(table.id),
                "name": table.name,
                "scope": scope,
                "organization_id": str(org_uuid) if org_uuid else None,
                "application_id": str(app_uuid) if app_uuid else None,
            })

    except Exception as e:
        logger.exception(f"Error creating table via MCP: {e}")
        return json.dumps({"error": f"Error creating table: {str(e)}"})


@system_tool(
    id="update_table",
    name="Update Table",
    description="Update table properties including name, description, scope, and columns.",
    category=ToolCategory.DATA_PROVIDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "table_id": {"type": "string", "description": "Table UUID (required)"},
            "name": {"type": "string", "description": "New table name"},
            "description": {"type": "string", "description": "New description"},
            "scope": {
                "type": "string",
                "enum": ["global", "organization", "application"],
                "description": "New scope (changing scope affects visibility)",
            },
            "organization_id": {
                "type": "string",
                "description": "New organization UUID (for scope changes)",
            },
            "columns": {
                "type": "array",
                "description": "Updated column definitions (replaces existing)",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "required": {"type": "boolean"},
                        "description": {"type": "string"},
                    },
                },
            },
        },
        "required": ["table_id"],
    },
)
async def update_table(
    context: Any,
    table_id: str,
    name: str | None = None,
    description: str | None = None,
    scope: str | None = None,
    organization_id: str | None = None,
    columns: list[dict[str, Any]] | None = None,
) -> str:
    """Update table properties."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.tables import Table

    logger.info(f"MCP update_table called with id={table_id}")

    if not table_id:
        return json.dumps({"error": "table_id is required"})

    try:
        table_uuid = UUID(table_id)
    except ValueError:
        return json.dumps({"error": f"Invalid table_id format: {table_id}"})

    try:
        async with get_db_context() as db:
            query = select(Table).where(Table.id == table_uuid)

            # Non-admins can only update their org's tables
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Table.organization_id == context.org_id)
                    | (Table.organization_id.is_(None))
                )

            result = await db.execute(query)
            table = result.scalar_one_or_none()

            if not table:
                return json.dumps({"error": f"Table not found: {table_id}"})

            updates_made = []

            if name is not None:
                table.name = name
                updates_made.append("name")

            if description is not None:
                table.description = description
                updates_made.append("description")

            # Handle scope changes
            if scope is not None:
                # Validate scope change permissions
                if scope == "global" and not context.is_platform_admin:
                    return json.dumps({"error": "Only platform admins can set global scope"})

                if scope == "global":
                    table.organization_id = None
                    table.application_id = None
                    updates_made.append("scope")
                elif scope == "organization":
                    if organization_id:
                        try:
                            table.organization_id = UUID(organization_id)
                        except ValueError:
                            return json.dumps({"error": f"Invalid organization_id format: {organization_id}"})
                    elif not table.organization_id:
                        # Default to context org_id
                        if context.org_id:
                            table.organization_id = context.org_id
                        else:
                            return json.dumps({"error": "organization_id required for organization scope"})
                    table.application_id = None
                    updates_made.append("scope")
                elif scope == "application":
                    return json.dumps({"error": "Cannot change to application scope via update_table. Create a new table instead."})

            if columns is not None:
                if table.schema is None:
                    table.schema = {}
                table.schema = {**table.schema, "columns": columns}
                updates_made.append("columns")

            if not updates_made:
                return json.dumps({"error": "No updates specified"})

            await db.commit()

            # Determine current scope
            if table.application_id:
                current_scope = "application"
            elif table.organization_id:
                current_scope = "organization"
            else:
                current_scope = "global"

            return json.dumps({
                "success": True,
                "id": str(table.id),
                "name": table.name,
                "scope": current_scope,
                "updates": updates_made,
            })

    except Exception as e:
        logger.exception(f"Error updating table via MCP: {e}")
        return json.dumps({"error": f"Error updating table: {str(e)}"})
