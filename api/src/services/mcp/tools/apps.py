"""
App Builder MCP Tools - Application Level

Tools for listing, creating, getting, updating, publishing apps,
plus schema documentation and validation.
"""

import json
import logging
from typing import Any

from src.services.mcp.tool_decorator import system_tool
from src.services.mcp.tool_registry import ToolCategory

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

            if not apps:
                return "No applications found."

            lines = ["# Applications\n"]
            for app in apps:
                # Get page count
                page_count_query = (
                    select(func.count())
                    .select_from(AppPage)
                    .where(
                        AppPage.application_id == app.id,
                        AppPage.is_draft == True,  # noqa: E712
                    )
                )
                page_count = await db.execute(page_count_query)
                count = page_count.scalar() or 0

                status = "Published" if app.live_version > 0 else "Draft only"
                lines.append(f"## {app.name}")
                lines.append(f"- **ID:** {app.id}")
                lines.append(f"- **Slug:** {app.slug}")
                lines.append(f"- **Status:** {status}")
                lines.append(f"- **Pages:** {count}")
                if app.live_version:
                    lines.append(f"- **Live Version:** v{app.live_version}")
                lines.append(f"- **Draft Version:** v{app.draft_version}")
                if app.description:
                    lines.append(f"- **Description:** {app.description}")
                lines.append(f"- **URL:** /apps/{app.slug}")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error listing apps via MCP: {e}")
        return f"Error listing apps: {str(e)}"


@system_tool(
    id="create_app",
    name="Create Application",
    description="Create a new App Builder application. Creates app metadata and optional home page. Use create_page and create_component for content.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
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
) -> str:
    """
    Create a new application with optional home page.

    Args:
        name: Application name (required)
        description: Application description
        slug: URL slug (auto-generated from name if not provided)
        create_home_page: Create a blank home page (default: True)

    Returns:
        Success message with app details, or error message
    """
    import re
    from uuid import uuid4

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application

    logger.info(f"MCP create_app called with name={name}")

    if not name:
        return "Error: name is required"

    # Generate slug from name if not provided
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    try:
        async with get_db_context() as db:
            # Check for duplicate slug within same org
            query = select(Application).where(Application.slug == slug)
            if context.org_id:
                query = query.where(Application.organization_id == context.org_id)
            else:
                query = query.where(Application.organization_id.is_(None))

            existing = await db.execute(query)
            if existing.scalar_one_or_none():
                return f"Error: Application with slug '{slug}' already exists"

            # Create application
            app = Application(
                id=uuid4(),
                name=name,
                slug=slug,
                description=description,
                organization_id=context.org_id,
                draft_version=1,
                live_version=0,
                created_by=str(context.user_id),
            )
            db.add(app)
            await db.flush()

            page_count = 0
            if create_home_page:
                # Create blank home page with column layout
                page = AppPage(
                    id=uuid4(),
                    application_id=app.id,
                    page_id="home",
                    title="Home",
                    path="/",
                    is_draft=True,
                    version=1,
                    root_layout_type="column",
                    root_layout_config={"gap": 16, "padding": 24},
                    page_order=0,
                )
                db.add(page)
                page_count = 1

            await db.commit()

            return (
                f"Application '{name}' created!\n\n"
                f"**ID:** {app.id}\n"
                f"**Slug:** {app.slug}\n"
                f"**Pages:** {page_count}\n"
                f"**URL:** /apps/{app.slug}\n\n"
                f"Use `create_page` to add pages or `get_page` to view the home page."
            )

    except Exception as e:
        logger.exception(f"Error creating app via MCP: {e}")
        return f"Error creating app: {str(e)}"


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
        return "Error: Either app_id or app_slug is required"

    try:
        async with get_db_context() as db:
            query = select(Application)

            if app_id:
                try:
                    query = query.where(Application.id == UUID(app_id))
                except ValueError:
                    return f"Error: Invalid app_id format: {app_id}"
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
                return f"Application not found: {app_id or app_slug}"

            lines = [f"# {app.name}\n"]
            lines.append(f"**ID:** {app.id}")
            lines.append(f"**Slug:** {app.slug}")
            if app.description:
                lines.append(f"**Description:** {app.description}")
            lines.append(f"**Live Version:** v{app.live_version}")
            lines.append(f"**Draft Version:** v{app.draft_version}")
            lines.append(f"**URL:** /apps/{app.slug}")
            lines.append("")

            # Show navigation config if present
            if app.navigation:
                lines.append("## Navigation Config")
                lines.append("```json")
                lines.append(json.dumps(app.navigation, indent=2))
                lines.append("```")
                lines.append("")

            # List pages (summaries only)
            pages_query = (
                select(AppPage)
                .where(
                    AppPage.application_id == app.id,
                    AppPage.is_draft == True,  # noqa: E712
                )
                .order_by(AppPage.page_order)
            )
            pages_result = await db.execute(pages_query)
            pages = pages_result.scalars().all()

            if pages:
                lines.append("## Pages\n")
                lines.append("| Page ID | Title | Path | Has Workflow |")
                lines.append("|---------|-------|------|--------------|")
                for page in pages:
                    has_wf = "Y" if page.launch_workflow_id else ""
                    lines.append(
                        f"| {page.page_id} | {page.title} | {page.path} | {has_wf} |"
                    )
                lines.append("")
                lines.append(
                    "*Use `get_page` to see component details for a specific page.*"
                )
            else:
                lines.append("No pages defined yet.")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting app via MCP: {e}")
        return f"Error getting app: {str(e)}"


@system_tool(
    id="update_app",
    name="Update Application",
    description="Update application metadata (name, description, navigation). Does NOT update pages - use page tools for that.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
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
        return "Error: app_id is required"

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            # Non-admins can only update their org's apps
            if not context.is_platform_admin and context.org_id:
                query = query.where(Application.organization_id == context.org_id)

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return f"Application not found: {app_id}"

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
                return "No updates specified"

            app.draft_version += 1
            await db.commit()

            return (
                f"Application '{app.name}' updated!\n\n"
                f"**Updates:** {', '.join(updates_made)}\n"
                f"**Draft Version:** v{app.draft_version}"
            )

    except Exception as e:
        logger.exception(f"Error updating app via MCP: {e}")
        return f"Error updating app: {str(e)}"


@system_tool(
    id="publish_app",
    name="Publish Application",
    description="Publish all draft pages and components to live.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_id": {"type": "string", "description": "Application UUID"},
        },
        "required": ["app_id"],
    },
)
async def publish_app(context: Any, app_id: str) -> str:
    """Publish all draft pages and components to live."""
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppPage, Application
    from src.services.app_builder_service import AppBuilderService

    logger.info(f"MCP publish_app called with id={app_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return f"Error: Invalid app_id format: {app_id}"

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            if not context.is_platform_admin and context.org_id:
                query = query.where(Application.organization_id == context.org_id)

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return f"Application not found: {app_id}"

            # Get draft pages
            pages_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.is_draft == True,  # noqa: E712
            )
            pages_result = await db.execute(pages_query)
            draft_pages = list(pages_result.scalars().all())

            if not draft_pages:
                return "Error: No draft pages to publish"

            # Delete existing live pages
            live_query = select(AppPage).where(
                AppPage.application_id == app_uuid,
                AppPage.is_draft == False,  # noqa: E712
            )
            live_result = await db.execute(live_query)
            for live_page in live_result.scalars().all():
                await db.delete(live_page)

            # Copy each draft page to live
            service = AppBuilderService(db)
            for draft_page in draft_pages:
                await service.copy_page_to_live(draft_page)

            # Update app version
            app.live_version = app.draft_version
            app.published_at = datetime.utcnow()

            await db.commit()

            return (
                f"Application '{app.name}' published!\n\n"
                f"**Live Version:** v{app.live_version}\n"
                f"**Pages Published:** {len(draft_pages)}"
            )

    except Exception as e:
        logger.exception(f"Error publishing app via MCP: {e}")
        return f"Error publishing app: {str(e)}"


@system_tool(
    id="get_app_schema",
    name="Get App Schema",
    description="Get documentation about App Builder application structure, components, expressions, and actions.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
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

---

## Application Definition

```json
{
  "name": "My Application",
  "description": "Application description",
  "version": "1.0.0",
  "pages": [...],
  "navigation": {...},
  "permissions": {...}
}
```

## Page Definition

Each page has a path, title, layout, and optional data sources:

```json
{
  "id": "dashboard",
  "title": "Dashboard",
  "path": "/",
  "dataSources": [
    {
      "id": "stats",
      "type": "workflow",
      "workflowId": "get_dashboard_stats"
    }
  ],
  "layout": {
    "type": "column",
    "gap": 16,
    "children": [...]
  }
}
```

## Layout Types

- **column**: Vertical flex container (children stack vertically)
- **row**: Horizontal flex container (children side by side)
- **grid**: CSS grid with configurable columns

Layout properties:
- `gap`: Space between children (pixels)
- `padding`: Internal padding (pixels)
- `align`: Cross-axis alignment (start, center, end, stretch)
- `justify`: Main-axis alignment (start, center, end, between, around)
- `columns`: Number of grid columns (grid type only)
- `autoSize`: When true, children keep natural size (see below)

## Layout autoSize Property

Row layouts have an `autoSize` property that controls how children are sized:
- `false` (default) - Children expand equally to fill available space (flex-1)
- `true` - Children keep their natural size

Use `autoSize: true` when you need precise control over button/element positioning.

**Example: Right-aligned button group**
```json
{
  "type": "row",
  "justify": "end",
  "autoSize": true,
  "gap": 8,
  "children": [
    {"id": "cancel", "type": "button", "props": {"label": "Cancel", "variant": "outline"}},
    {"id": "save", "type": "button", "props": {"label": "Save"}}
  ]
}
```

**Example: Left and right button groups**
```json
{
  "type": "row",
  "justify": "between",
  "autoSize": true,
  "children": [
    {"id": "back", "type": "button", "props": {"label": "Back", "variant": "ghost"}},
    {
      "type": "row",
      "autoSize": true,
      "gap": 8,
      "children": [
        {"id": "cancel", "type": "button", "props": {"label": "Cancel", "variant": "outline"}},
        {"id": "next", "type": "button", "props": {"label": "Next"}}
      ]
    }
  ]
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
    "value": "{{ data.stats.userCount }}",
    "icon": "users",
    "trend": {"value": "+12%", "direction": "up"}
  }
}
```
- `loadingWorkflows`: Array of workflow IDs - shows skeleton while any are executing

**image** - Images with sizing
```json
{"id": "img1", "type": "image", "props": {"src": "{{ data.user.avatar }}", "alt": "Avatar", "maxWidth": 100}}
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
- `{{ data.customers }}` - Data from data source
- `{{ workflow.result.id }}` - Last workflow result
- `{{ row.id }}` - Current row in table actions

Comparisons: `{{ user.role == 'admin' }}`
Logic: `{{ isActive && hasPermission }}`

## Data Sources

```json
{
  "dataSources": [
    {"id": "customers", "type": "workflow", "workflowId": "get_customers"},
    {"id": "categories", "type": "data-provider", "dataProviderId": "get_categories"},
    {"id": "config", "type": "static", "data": {"theme": "dark"}}
  ]
}
```

Types: workflow, data-provider, api, static, computed

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
      "dataSources": [
        {"id": "customers", "type": "workflow", "workflowId": "list_customers"}
      ],
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
"""


@system_tool(
    id="validate_app_schema",
    name="Validate App Schema",
    description="Validate an App Builder application JSON structure before saving.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={
        "type": "object",
        "properties": {
            "app_definition": {
                "type": "string",
                "description": "JSON string of the application definition to validate",
            },
        },
        "required": ["app_definition"],
    },
)
async def validate_app_schema(context: Any, app_definition: str) -> str:
    """Validate an application JSON structure."""
    try:
        app_data = json.loads(app_definition)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {str(e)}"

    errors: list[str] = []

    # Check required top-level fields
    if "name" not in app_data:
        errors.append("Missing required field: 'name'")

    if "pages" not in app_data:
        errors.append("Missing required field: 'pages'")
    elif not isinstance(app_data.get("pages"), list):
        errors.append("'pages' must be an array")
    elif len(app_data.get("pages", [])) == 0:
        errors.append("'pages' must have at least one page")

    # Validate each page
    valid_layout_types = {"row", "column", "grid"}
    valid_component_types = {
        "heading",
        "text",
        "html",
        "card",
        "divider",
        "spacer",
        "button",
        "stat-card",
        "image",
        "badge",
        "progress",
        "data-table",
        "tabs",
        "file-viewer",
        "modal",
        "text-input",
        "number-input",
        "select",
        "checkbox",
        "form-embed",
        "form-group",
    }

    def validate_layout(layout: dict[str, Any], path: str) -> None:
        """Recursively validate layout structure."""
        if not isinstance(layout, dict):
            errors.append(f"{path}: layout must be an object")
            return

        layout_type = layout.get("type")
        if (
            layout_type not in valid_layout_types
            and layout_type not in valid_component_types
        ):
            errors.append(f"{path}: invalid type '{layout_type}'")
            return

        if layout_type in valid_layout_types:
            # It's a layout container
            children = layout.get("children", [])
            if not isinstance(children, list):
                errors.append(f"{path}: 'children' must be an array")
            else:
                for i, child in enumerate(children):
                    validate_layout(child, f"{path}.children[{i}]")
        else:
            # It's a component
            if "props" not in layout and layout_type not in {"divider", "spacer"}:
                errors.append(f"{path}: component missing 'props'")

    pages = app_data.get("pages", [])
    if isinstance(pages, list):
        for i, page in enumerate(pages):
            if not isinstance(page, dict):
                errors.append(f"pages[{i}]: must be an object")
                continue

            if "id" not in page:
                errors.append(f"pages[{i}]: missing 'id'")
            if "title" not in page:
                errors.append(f"pages[{i}]: missing 'title'")
            if "path" not in page:
                errors.append(f"pages[{i}]: missing 'path'")
            if "layout" not in page:
                errors.append(f"pages[{i}]: missing 'layout'")
            elif isinstance(page.get("layout"), dict):
                validate_layout(page["layout"], f"pages[{i}].layout")

            # Validate data sources if present
            data_sources = page.get("dataSources", [])
            if not isinstance(data_sources, list):
                errors.append(f"pages[{i}].dataSources: must be an array")
            else:
                valid_ds_types = {
                    "workflow",
                    "data-provider",
                    "api",
                    "static",
                    "computed",
                }
                for j, ds in enumerate(data_sources):
                    if not isinstance(ds, dict):
                        errors.append(f"pages[{i}].dataSources[{j}]: must be an object")
                        continue
                    if "id" not in ds:
                        errors.append(f"pages[{i}].dataSources[{j}]: missing 'id'")
                    if "type" not in ds:
                        errors.append(f"pages[{i}].dataSources[{j}]: missing 'type'")
                    elif ds["type"] not in valid_ds_types:
                        errors.append(
                            f"pages[{i}].dataSources[{j}]: invalid type '{ds['type']}'. "
                            f"Valid: {', '.join(sorted(valid_ds_types))}"
                        )

    if errors:
        return "Validation errors:\n" + "\n".join(f"- {e}" for e in errors)

    return "Application schema is valid!"
