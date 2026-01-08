"""
App Builder MCP Tools - Application Level

Tools for listing, creating, getting, updating, publishing apps,
plus schema documentation and validation.
"""

import json
import logging
from typing import Any

from src.core.pubsub import publish_app_draft_update, publish_app_published
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory

logger = logging.getLogger(__name__)


@system_tool(
    id="list_apps",
    name="List Applications",
    description="List all App Builder applications with page counts and URLs.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_apps(context: Any) -> str:
    """List all applications with page summaries."""
    from sqlalchemy import func, select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application

    logger.info("MCP list_apps called")

    try:
        async with get_db_context() as db:
            # Query apps with page count
            query = select(Application)

            # Non-admins can only see their org's apps + global apps
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query.order_by(Application.name))
            apps = result.scalars().all()

            apps_data = []
            for app in apps:
                # Get page count from draft version
                count = 0
                if app.draft_version_id:
                    page_count_query = (
                        select(func.count())
                        .select_from(AppPage)
                        .where(
                            AppPage.application_id == app.id,
                            AppPage.version_id == app.draft_version_id,
                        )
                    )
                    page_count = await db.execute(page_count_query)
                    count = page_count.scalar() or 0

                apps_data.append({
                    "id": str(app.id),
                    "name": app.name,
                    "slug": app.slug,
                    "description": app.description,
                    "status": "published" if app.is_published else "draft",
                    "page_count": count,
                    "active_version_id": str(app.active_version_id) if app.active_version_id else None,
                    "draft_version_id": str(app.draft_version_id) if app.draft_version_id else None,
                    "url": f"/apps/{app.slug}",
                })

            return json.dumps({"apps": apps_data, "count": len(apps_data)})

    except Exception as e:
        logger.exception(f"Error listing apps via MCP: {e}")
        return json.dumps({"error": f"Error listing apps: {str(e)}"})


@system_tool(
    id="create_app",
    name="Create Application",
    description="Create a new App Builder application. Creates app metadata and optional home page. Use create_page and create_component for content.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Application name"},
            "description": {
                "type": "string",
                "description": "Application description",
            },
            "slug": {
                "type": "string",
                "description": "URL slug (auto-generated from name if not provided)",
            },
            "create_home_page": {
                "type": "boolean",
                "description": "Create blank home page (default: true)",
            },
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
        "required": ["name"],
    },
)
async def create_app(
    context: Any,
    name: str,
    description: str | None = None,
    slug: str | None = None,
    create_home_page: bool = True,
    scope: str = "organization",
    organization_id: str | None = None,
) -> str:
    """
    Create a new application with optional home page.

    Args:
        name: Application name (required)
        description: Application description
        slug: URL slug (auto-generated from name if not provided)
        create_home_page: Create a blank home page (default: True)
        scope: 'global' (visible to all orgs) or 'organization' (default)
        organization_id: Override context.org_id when scope='organization'

    Returns:
        Success message with app details, or error message
    """
    import re
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, AppVersion, Application

    logger.info(f"MCP create_app called with name={name}, scope={scope}")

    if not name:
        return json.dumps({"error": "name is required"})

    # Validate scope parameter
    if scope not in ("global", "organization"):
        return json.dumps({"error": "scope must be 'global' or 'organization'"})

    # Determine effective organization_id based on scope
    effective_org_id: UUID | None = None
    if scope == "global":
        # Global resources have no organization_id
        effective_org_id = None
    else:
        # Organization scope: use provided organization_id or fall back to context.org_id
        if organization_id:
            try:
                effective_org_id = UUID(organization_id)
            except ValueError:
                return json.dumps({"error": f"organization_id '{organization_id}' is not a valid UUID"})
        elif context.org_id:
            effective_org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
        else:
            return json.dumps({"error": "organization_id is required when scope='organization' and no context org_id is set"})

    # Generate slug from name if not provided
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    try:
        async with get_db_context() as db:
            # Check for duplicate slug within same org scope
            query = select(Application).where(Application.slug == slug)
            if effective_org_id:
                query = query.where(Application.organization_id == effective_org_id)
            else:
                query = query.where(Application.organization_id.is_(None))

            existing = await db.execute(query)
            if existing.scalar_one_or_none():
                return json.dumps({"error": f"Application with slug '{slug}' already exists"})

            # Create application
            app = Application(
                id=uuid4(),
                name=name,
                slug=slug,
                description=description,
                organization_id=effective_org_id,
                created_by=str(context.user_id),
            )
            db.add(app)
            await db.flush()

            # Create initial draft version
            draft_version = AppVersion(
                application_id=app.id,
            )
            db.add(draft_version)
            await db.flush()

            # Link app to draft version
            app.draft_version_id = draft_version.id
            await db.flush()  # Ensure draft_version_id is persisted

            page_count = 0
            if create_home_page:
                # Create blank home page with column layout
                page = AppPage(
                    id=uuid4(),
                    application_id=app.id,
                    page_id="home",
                    title="Home",
                    path="/",
                    version_id=draft_version.id,
                    root_layout_type="column",
                    root_layout_config={"gap": 16, "padding": 24},
                    page_order=0,
                )
                db.add(page)
                page_count = 1

            await db.commit()

            return json.dumps({
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "draft_version_id": str(draft_version.id),
                "page_count": page_count,
                "url": f"/apps/{app.slug}",
            })

    except Exception as e:
        logger.exception(f"Error creating app via MCP: {e}")
        return json.dumps({"error": f"Error creating app: {str(e)}"})


@system_tool(
    id="get_app",
    name="Get Application",
    description="Get application metadata and page list (does NOT include component details - use get_page for that).",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string", "description": "Application UUID"},
            "app_slug": {
                "type": "string",
                "description": "Application slug (alternative to ID)",
            },
        },
        "required": [],
    },
)
async def get_app(
    context: Any,
    app_id: str | None = None,
    app_slug: str | None = None,
) -> str:
    """
    Get application metadata and page list.

    Does NOT return full component trees - use get_page for that.
    This provides enough info to know what pages exist without token bloat.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application

    logger.info(f"MCP get_app called with id={app_id}, slug={app_slug}")

    if not app_id and not app_slug:
        return json.dumps({"error": "Either app_id or app_slug is required"})

    try:
        async with get_db_context() as db:
            query = select(Application)

            if app_id:
                try:
                    query = query.where(Application.id == UUID(app_id))
                except ValueError:
                    return json.dumps({"error": f"Invalid app_id format: {app_id}"})
            else:
                query = query.where(Application.slug == app_slug)

            # Non-admins can only see their org's apps + global
            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return json.dumps({"error": f"Application not found: {app_id or app_slug}"})

            # List pages from draft version (summaries only)
            pages = []
            if app.draft_version_id:
                pages_query = (
                    select(AppPage)
                    .where(
                        AppPage.application_id == app.id,
                        AppPage.version_id == app.draft_version_id,
                    )
                    .order_by(AppPage.page_order)
                )
                pages_result = await db.execute(pages_query)
                pages = list(pages_result.scalars().all())

            return json.dumps({
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "description": app.description,
                "active_version_id": str(app.active_version_id) if app.active_version_id else None,
                "draft_version_id": str(app.draft_version_id) if app.draft_version_id else None,
                "url": f"/apps/{app.slug}",
                "navigation": app.navigation,
                "pages": [
                    {
                        "page_id": page.page_id,
                        "title": page.title,
                        "path": page.path,
                        "has_launch_workflow": page.launch_workflow_id is not None,
                        "version_id": str(page.version_id) if page.version_id else None,
                    }
                    for page in pages
                ],
            })

    except Exception as e:
        logger.exception(f"Error getting app via MCP: {e}")
        return json.dumps({"error": f"Error getting app: {str(e)}"})


@system_tool(
    id="update_app",
    name="Update Application",
    description="Update application metadata (name, description, navigation). Does NOT update pages - use page tools for that.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string", "description": "Application UUID (required)"},
            "name": {"type": "string", "description": "New application name"},
            "description": {"type": "string", "description": "New description"},
            "navigation": {
                "type": "string",
                "description": "Navigation config as JSON string",
            },
        },
        "required": ["app_id"],
    },
)
async def update_app(
    context: Any,
    app_id: str,
    name: str | None = None,
    description: str | None = None,
    navigation: dict[str, Any] | None = None,
    global_data_sources: list[dict[str, Any]] | None = None,
    global_variables: dict[str, Any] | None = None,
) -> str:
    """
    Update application metadata only.

    Does NOT update pages or components - use page/component tools for that.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application

    logger.info(f"MCP update_app called with id={app_id}")

    if not app_id:
        return json.dumps({"error": "app_id is required"})

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            # Non-admins can only update their org's apps
            if not context.is_platform_admin and context.org_id:
                query = query.where(Application.organization_id == context.org_id)

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            updates_made = []

            if name is not None:
                app.name = name
                updates_made.append("name")

            if description is not None:
                app.description = description
                updates_made.append("description")

            if navigation is not None:
                app.navigation = navigation
                updates_made.append("navigation")

            if global_data_sources is not None:
                app.global_data_sources = global_data_sources
                updates_made.append("global_data_sources")

            if global_variables is not None:
                app.global_variables = global_variables
                updates_made.append("global_variables")

            if not updates_made:
                return json.dumps({"error": "No updates specified"})

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="app",
                entity_id=app_id,
            )

            return json.dumps({
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "updates": updates_made,
            })

    except Exception as e:
        logger.exception(f"Error updating app via MCP: {e}")
        return json.dumps({"error": f"Error updating app: {str(e)}"})


@system_tool(
    id="publish_app",
    name="Publish Application",
    description="Publish all draft pages and components to live.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string", "description": "Application UUID"},
        },
        "required": ["app_id"],
    },
)
async def publish_app(context: Any, app_id: str) -> str:
    """Publish all draft pages and components to live.

    Creates a new version by copying all pages from the draft version,
    then sets this new version as the active (live) version.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP publish_app called with id={app_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return json.dumps({"error": f"Invalid app_id format: {app_id}"})

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            if not context.is_platform_admin and context.org_id:
                query = query.where(Application.organization_id == context.org_id)

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return json.dumps({"error": f"Application not found: {app_id}"})

            if not app.draft_version_id:
                return json.dumps({"error": "Application has no draft version to publish"})

            # Count draft pages for reporting
            pages_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.version_id == app.draft_version_id,
            )
            pages_result = await db.execute(pages_query)
            draft_pages = list(pages_result.scalars().all())

            if not draft_pages:
                return json.dumps({"error": "No draft pages to publish"})

            # Use versioning-based publish (copies draft to new version)
            service = AppBuilderService(db)
            new_version = await service.publish_with_versioning(app)

            await db.commit()

            # Emit event for real-time updates
            await publish_app_published(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                new_version_id=str(new_version.id),
            )

            return json.dumps({
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "active_version_id": str(new_version.id),
                "draft_version_id": str(app.draft_version_id),
                "pages_published": len(draft_pages),
            })

    except Exception as e:
        logger.exception(f"Error publishing app via MCP: {e}")
        return json.dumps({"error": f"Error publishing app: {str(e)}"})


@system_tool(
    id="get_app_schema",
    name="Get App Schema",
    description="Get documentation about App Builder application structure, components, expressions, and actions.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_app_schema(context: Any) -> str:
    """Get application schema documentation."""
    return """# App Builder Schema Documentation

Applications in Bifrost are defined using a JSON schema with pages, layouts, and components.

## App Builder Tool Hierarchy

Apps are managed at three levels with granular MCP tools for 99% token savings on single-component edits:

### App Level
- `list_apps` - List all applications with page summaries
- `get_app` - Get app metadata and page list (NOT full component trees)
- `update_app` - Update app settings (name, description, navigation, global config)
- `publish_app` - Publish all draft pages and components to live

### Page Level
- `create_page` - Add a new page to an app with optional layout
- `get_page` - Get page definition with full component tree
- `update_page` - Update page settings or replace layout
- `delete_page` - Remove a page and all its components

### Component Level
- `list_components` - List components in a page (type, parent, order only)
- `create_component` - Add a component to a page
- `get_component` - Get a single component with full props
- `update_component` - Update component props or settings
- `delete_component` - Remove a component and all its children
- `move_component` - Reposition a component to new parent/order

**Workflow**: Use `get_app` to see pages, then `get_page` for the page you need,
then component tools for granular edits. Avoid fetching full app definitions.

**Note:** Each create/update operation validates automatically. There is no separate validate tool.

---

## Page Structure

Each page has a path, title, layout, and optional launch workflow for data loading:

```json
{
  "id": "dashboard",
  "title": "Dashboard",
  "path": "/",
  "launchWorkflowId": "get_dashboard_stats",
  "launchWorkflowDataSourceId": "stats",
  "layout": {
    "type": "column",
    "gap": 16,
    "children": [...]
  }
}
```

## Data Loading with Launch Workflows

Pages load data through launch workflows, not data sources. This is the standard pattern:

1. Set `launchWorkflowId` to a workflow UUID - executes when the page mounts
2. Set `launchWorkflowDataSourceId` to a key name (e.g., "stats", "customers")
3. Access results via `{{ workflow.<dataSourceId> }}`

**Example:**
```json
{
  "launchWorkflowId": "abc-123-workflow-uuid",
  "launchWorkflowDataSourceId": "customers"
}
```
Then use `{{ workflow.customers }}` to access the data directly.

**Important:** All data loading now goes through workflows, accessed via `{{ workflow.<key> }}`

## Layout Types

- **column**: Vertical flex container (children stack vertically)
- **row**: Horizontal flex container (children side by side)
- **grid**: CSS grid with configurable columns

Layout properties:
- `gap`: INTEGER - Space between children in pixels (e.g., 16, not "16px"). Defaults: column=16, row=8, grid=16. Set to 0 for no gap.
- `padding`: INTEGER - Internal padding in pixels (e.g., 24, not "24px"). Default: 0. Single value only (not CSS multi-value).
- `align`: ENUM - Cross-axis alignment: "start", "center", "end", "stretch"
- `justify`: ENUM - Main-axis alignment: "start", "center", "end", "between", "around"
- `columns`: INTEGER - Number of grid columns (grid type only)
- `distribute`: ENUM - How children fill available space: "natural" (default), "equal", "fit"
- `maxWidth`: ENUM - Constrains layout width: "sm" (384px), "md" (448px), "lg" (512px), "xl" (576px), "2xl" (672px), "full"/"none" (no limit)
- `maxHeight`: INTEGER - Container height limit in pixels (enables scrolling when content overflows)
- `overflow`: ENUM - Behavior when content exceeds bounds: "visible", "auto", "scroll", "hidden"
- `sticky`: ENUM - Pin container to edge when scrolling: "top", "bottom"
- `stickyOffset`: INTEGER - Distance from edge in pixels when sticky is set
- `className`: STRING - Custom Tailwind or CSS classes
- `style`: OBJECT - Inline CSS styles as object (use camelCase: backgroundColor, maxHeight)

**IMPORTANT**: Integer properties (gap, padding, columns, maxHeight, stickyOffset) must be numbers, NOT strings with "px" suffix.

## Layout Distribution

Control how children fill available space with the `distribute` property:

- `"natural"` (default): Children keep their natural size
- `"equal"`: Children expand equally (flex-1 behavior)
- `"fit"`: Children fit their content

**Example: Page header with action button (natural)**
```json
{
  "type": "row",
  "justify": "between",
  "align": "center",
  "children": [
    {"id": "title", "type": "heading", "props": {"text": "Customers", "level": 1}},
    {"id": "add-btn", "type": "button", "props": {"label": "Add Customer"}}
  ]
}
```

**Example: Right-aligned button group**
```json
{
  "type": "row",
  "justify": "end",
  "children": [
    {"id": "cancel", "type": "button", "props": {"label": "Cancel", "variant": "outline"}},
    {"id": "save", "type": "button", "props": {"label": "Save"}}
  ]
}
```

**Example: Equal-width columns (use distribute: "equal")**
```json
{
  "type": "row",
  "distribute": "equal",
  "children": [
    {"id": "firstName", "type": "text-input", "props": {"fieldId": "firstName", "label": "First Name"}},
    {"id": "lastName", "type": "text-input", "props": {"fieldId": "lastName", "label": "Last Name"}}
  ]
}
```

## Scrollable Containers

Create scrollable areas by setting `maxHeight` and `overflow`:

**Example: Scrollable sidebar**
```json
{
  "type": "column",
  "maxHeight": 400,
  "overflow": "auto",
  "gap": 16,
  "children": [...]
}
```

## Custom Styling

Apply custom classes and inline styles to layouts:

**Example: Custom styled container**
```json
{
  "type": "column",
  "className": "bg-blue-50 rounded-lg shadow-lg",
  "style": {"maxHeight": "500px", "overflowY": "auto"},
  "children": [...]
}
```

## Form Page Layouts (IMPORTANT)

For pages containing forms (create/edit pages), ALWAYS use `maxWidth: "lg"` on the root column layout.
This prevents forms from stretching uncomfortably wide on large screens.

**Example: Create/Edit page layout**
```json
{
  "id": "create",
  "title": "New Customer",
  "path": "/new",
  "layout": {
    "type": "column",
    "maxWidth": "lg",
    "gap": 16,
    "padding": 24,
    "children": [
      {"id": "h1", "type": "heading", "props": {"text": "New Customer", "level": 1}},
      {"id": "form-card", "type": "card", "props": {
        "children": [
          {"id": "name", "type": "text-input", "props": {"fieldId": "name", "label": "Company Name", "required": true}},
          {"id": "email", "type": "text-input", "props": {"fieldId": "email", "label": "Email"}},
          {"id": "actions", "type": "row", "props": {"justify": "end", "gap": 8, "children": [
            {"id": "cancel", "type": "button", "props": {"label": "Cancel", "variant": "outline", "actionType": "navigate", "navigateTo": "/"}},
            {"id": "save", "type": "button", "props": {"label": "Save", "actionType": "submit", "workflowId": "create_customer"}}
          ]}}
        ]
      }}
    ]
  }
}
```

## Component Width Property

All components support a `width` property for responsive layouts:

| Value | Description |
|-------|-------------|
| `"auto"` | Natural size (default) |
| `"full"` | Full width of container |
| `"1/2"` | 50% width |
| `"1/3"` | 33.33% width |
| `"1/4"` | 25% width |
| `"2/3"` | 66.67% width |
| `"3/4"` | 75% width |

**Example: Two-column form layout**
```json
{
  "type": "row",
  "gap": 16,
  "children": [
    {"id": "firstName", "type": "text-input", "width": "1/2", "props": {"fieldId": "firstName", "label": "First Name"}},
    {"id": "lastName", "type": "text-input", "width": "1/2", "props": {"fieldId": "lastName", "label": "Last Name"}}
  ]
}
```

**Example: Sidebar layout**
```json
{
  "type": "row",
  "gap": 24,
  "children": [
    {"id": "main", "type": "card", "width": "2/3", "props": {"title": "Main Content", "children": [...]}},
    {"id": "sidebar", "type": "card", "width": "1/3", "props": {"title": "Sidebar", "children": [...]}}
  ]
}
```

## Repeating Components

Render a component multiple times by iterating over an array using the `repeatFor` property:

**Example: Render a card for each client**
```json
{
  "id": "client-cards",
  "type": "card",
  "repeatFor": {
    "items": "{{ workflow.clients }}",
    "itemKey": "id",
    "as": "client"
  },
  "props": {
    "title": "{{ client.name }}",
    "children": [
      {"id": "email", "type": "text", "props": {"text": "{{ client.email }}", "label": "Email"}},
      {"id": "status", "type": "badge", "props": {"text": "{{ client.status }}"}}
    ]
  }
}
```

Properties:
- `items`: Expression that evaluates to an array
- `itemKey`: Property name used for React keys (must be unique per item)
- `as`: Variable name to access each item in child expressions

## Component Grid Spanning

Components can span multiple columns in grid layouts using the `gridSpan` property:

**Example: Component spanning 2 columns**
```json
{
  "type": "grid",
  "columns": 3,
  "gap": 16,
  "children": [
    {"id": "item1", "type": "card", "props": {"title": "Item 1"}},
    {"id": "item2", "type": "card", "props": {"title": "Item 2"}},
    {"id": "item3", "type": "card", "gridSpan": 2, "props": {"title": "Wide Item - Spans 2 Columns"}},
    {"id": "item4", "type": "card", "props": {"title": "Item 4"}}
  ]
}
```

## Component Styling

All components support custom styling through `className` and `style` properties:

**Example: Styled component**
```json
{
  "id": "custom-text",
  "type": "text",
  "className": "text-blue-500 font-bold",
  "style": {"padding": "20px", "backgroundColor": "#f0f0f0"},
  "props": {"text": "Custom styled text"}
}
```

## Page-Level CSS

Add custom CSS to pages using the `styles` property:

**Example: Page with custom styles**
```json
{
  "page_id": "dashboard",
  "title": "Dashboard",
  "path": "/",
  "styles": ".custom-sidebar { position: sticky; top: 0; height: 100vh; overflow-y: auto; }",
  "layout": {...}
}
```

## Component Types

### Display Components

**heading** - Page/section headings
```json
{"id": "h1", "type": "heading", "props": {"text": "Welcome", "level": 1}}
```

**text** - Text content with optional label
```json
{"id": "t1", "type": "text", "props": {"text": "Description here", "label": "Details"}}
```

**badge** - Status badges
```json
{"id": "b1", "type": "badge", "props": {"text": "Active", "variant": "default"}}
```
Variants: default, secondary, destructive, outline

**stat-card** - Dashboard statistics
```json
{
  "id": "sc1",
  "type": "stat-card",
  "loadingWorkflows": ["workflow-uuid"],
  "props": {
    "title": "Total Users",
    "value": "{{ workflow.stats.result.userCount }}",
    "icon": "users",
    "trend": {"value": "+12%", "direction": "up"}
  }
}
```
- `loadingWorkflows`: Array of workflow IDs - shows skeleton while any are executing

**image** - Images with sizing
```json
{"id": "img1", "type": "image", "props": {"src": "{{ workflow.profile.result.avatar }}", "alt": "Avatar", "maxWidth": 100}}
```

**card** - Container with optional header
```json
{"id": "c1", "type": "card", "props": {"title": "Section", "children": [...]}}
```

**divider** - Horizontal/vertical line separator
**spacer** - Empty space with configurable size

### Data Components

**data-table** - Full-featured data table
```json
{
  "id": "table1",
  "type": "data-table",
  "props": {
    "dataSource": "customers",
    "cacheKey": "customers-table",
    "columns": [
      {"key": "name", "header": "Name", "sortable": true},
      {"key": "status", "header": "Status", "type": "badge"}
    ],
    "searchable": true,
    "paginated": true,
    "rowActions": [
      {
        "label": "",
        "icon": "Eye",
        "onClick": {"type": "navigate", "navigateTo": "/customers/{{ row.id }}"}
      },
      {
        "label": "Edit",
        "icon": "Pencil",
        "onClick": {"type": "navigate", "navigateTo": "/customers/{{ row.id }}/edit"}
      }
    ]
  }
}
```
- `cacheKey`: Persist table data across page navigations (shows refresh button)
- Row actions: Use empty `label` + `icon` for icon-only buttons with tooltip

**tabs** - Tabbed content sections
```json
{
  "id": "tabs1",
  "type": "tabs",
  "props": {
    "defaultTab": "overview",
    "items": [
      {"id": "overview", "label": "Overview", "content": {"type": "column", "children": [...]}},
      {"id": "settings", "label": "Settings", "content": {"type": "column", "children": [...]}}
    ]
  }
}
```

### Form Input Components

**text-input** - Text field
```json
{"id": "ti1", "type": "text-input", "props": {"fieldId": "name", "label": "Name", "required": true}}
```

**number-input** - Number field with min/max
```json
{"id": "ni1", "type": "number-input", "props": {"fieldId": "quantity", "label": "Qty", "min": 1, "max": 100}}
```

**select** - Dropdown (static or data-driven)
```json
{
  "id": "sel1",
  "type": "select",
  "props": {
    "fieldId": "status",
    "label": "Status",
    "options": [
      {"value": "active", "label": "Active"},
      {"value": "inactive", "label": "Inactive"}
    ]
  }
}
```

**checkbox** - Boolean checkbox
```json
{"id": "cb1", "type": "checkbox", "props": {"fieldId": "agree", "label": "I agree to terms"}}
```

### Interactive Components

**button** - Action trigger
```json
{
  "id": "btn1",
  "type": "button",
  "props": {
    "label": "Save",
    "actionType": "submit",
    "workflowId": "save_data",
    "variant": "default"
  }
}
```
Action types: navigate, workflow, submit, custom
Variants: default, destructive, outline, secondary, ghost, link

**modal** - Dialog with content
```json
{
  "id": "m1",
  "type": "modal",
  "props": {
    "title": "Add Item",
    "triggerLabel": "Add New",
    "content": {"type": "column", "children": [...]},
    "footerActions": [{"label": "Save", "actionType": "submit", "workflowId": "create_item"}]
  }
}
```

## Expressions

Use `{{ }}` syntax for dynamic values:

- `{{ user.name }}` - Current user's name
- `{{ user.email }}` - Current user's email
- `{{ user.role }}` - Current user's role
- `{{ variables.selectedId }}` - Page variable
- `{{ field.customerName }}` - Form field value
- `{{ workflow.<dataSourceId>.result }}` - Workflow result data (primary data access pattern)
- `{{ workflow.<dataSourceId>.result.id }}` - Access nested properties from workflow result
- `{{ workflow.lastResult }}` - Result from most recently executed workflow
- `{{ row.id }}` - Current row in table actions

Comparisons: `{{ user.role == 'admin' }}`
Logic: `{{ isActive && hasPermission }}`

## Data Sources (Legacy)

**Note:** The `dataSources` array is deprecated. Use launch workflows instead:

```json
{
  "launchWorkflowId": "workflow-uuid",
  "launchWorkflowDataSourceId": "customers"
}
```

Access data via `{{ workflow.customers.result }}` instead of `{{ data.customers }}`.

For backwards compatibility, the old pattern still works but should not be used for new pages.

## Navigation

```json
{
  "navigation": {
    "showSidebar": true,
    "sidebar": [
      {"id": "home", "label": "Dashboard", "icon": "home", "path": "/"},
      {"id": "users", "label": "Users", "icon": "users", "path": "/users"}
    ]
  }
}
```

## Actions

Button/table action types:
- **navigate**: Go to path `{"type": "navigate", "navigateTo": "/path"}`
- **workflow**: Execute workflow `{"type": "workflow", "workflowId": "...", "actionParams": {...}}`
- **submit**: Collect form fields and execute workflow
- **set-variable**: Update page variable

OnComplete actions (after workflow):
```json
{
  "onComplete": [
    {"type": "refresh-table", "dataSourceKey": "customers"},
    {"type": "navigate", "navigateTo": "/success"}
  ]
}
```

## Visibility & Disabled

Any component can have:
- `visible`: Expression to control visibility `"{{ user.role == 'admin' }}"`
- `disabled`: Expression for buttons `"{{ !field.name }}"`

## Loading States

Any component can specify `loadingWorkflows` to show a skeleton while workflows execute:
```json
{
  "id": "stats-card",
  "type": "stat-card",
  "loadingWorkflows": ["workflow-uuid-1", "workflow-uuid-2"],
  "props": {...}
}
```
The component shows a type-specific skeleton when any of the specified workflows are running.

## Complete Example

```json
{
  "name": "Customer Manager",
  "version": "1.0.0",
  "pages": [
    {
      "id": "list",
      "title": "Customers",
      "path": "/",
      "launchWorkflowId": "list_customers_workflow_uuid",
      "launchWorkflowDataSourceId": "customers",
      "layout": {
        "type": "column",
        "gap": 16,
        "padding": 24,
        "children": [
          {"id": "h1", "type": "heading", "props": {"text": "Customers", "level": 1}},
          {
            "id": "table",
            "type": "data-table",
            "props": {
              "dataSource": "customers",
              "columns": [
                {"key": "name", "header": "Name"},
                {"key": "email", "header": "Email"},
                {"key": "status", "header": "Status", "type": "badge"}
              ],
              "searchable": true,
              "onRowClick": {"type": "navigate", "navigateTo": "/customers/{{ row.id }}"}
            }
          }
        ]
      }
    }
  ],
  "navigation": {
    "showSidebar": true,
    "sidebar": [
      {"id": "list", "label": "Customers", "icon": "users", "path": "/"}
    ]
  }
}
```

**Key points:**
- Use `launchWorkflowId` + `launchWorkflowDataSourceId` instead of `dataSources`
- Access workflow results via `{{ workflow.customers.result }}`
- The `dataSource` prop in data-table references the `launchWorkflowDataSourceId`
"""
