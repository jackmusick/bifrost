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
                # Create blank home page - layout will be created via create_page MCP tool
                # or added when components are first added
                page = AppPage(
                    id=uuid4(),
                    application_id=app.id,
                    page_id="home",
                    title="Home",
                    path="/",
                    version_id=draft_version.id,
                    page_order=0,
                )
                db.add(page)

                # Create root layout component
                from src.models.orm.applications import AppComponent
                root_layout = AppComponent(
                    id=uuid4(),
                    page_id=page.id,
                    component_id="layout_root",
                    parent_id=None,
                    type="column",
                    props={"gap": 16, "padding": 24},
                    component_order=0,
                )
                db.add(root_layout)
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
                # Validate navigation through Pydantic model with strict checking
                from pydantic import ValidationError

                from src.models.contracts.app_components import NavigationConfig

                try:
                    # Use strict=True to catch type mismatches
                    validated_nav = NavigationConfig.model_validate(navigation, strict=True)
                    app.navigation = validated_nav.model_dump(exclude_none=True)
                    updates_made.append("navigation")
                except ValidationError as e:
                    return json.dumps({
                        "error": f"Invalid navigation configuration: {e}"
                    })

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
async def get_app_schema(context: Any) -> str:  # noqa: ARG001
    """Get application schema documentation generated from Pydantic models."""
    from src.models.contracts.applications import (
        ApplicationCreate,
        ApplicationUpdate,
        AppPageCreate,
        AppPageUpdate,
        AppComponentCreate,
        AppComponentUpdate,
        AppComponentMove,
    )
    from src.models.contracts.app_components import (
        # Container components
        RowComponent,
        ColumnComponent,
        CardComponent,
        ModalComponent,
        TabsComponent,
        FormGroupComponent,
        # Leaf components
        HeadingComponent,
        TextComponent,
        ButtonComponent,
        StatCardComponent,
        DataTableComponent,
        TextInputComponent,
        SelectComponent,
        FormEmbedComponent,
    )
    from src.services.mcp_server.schema_utils import models_to_markdown

    # Generate model documentation
    app_models = models_to_markdown([
        (ApplicationCreate, "ApplicationCreate (for creating apps)"),
        (ApplicationUpdate, "ApplicationUpdate (for updating apps)"),
    ], "Application Models")

    page_models = models_to_markdown([
        (AppPageCreate, "AppPageCreate (for creating pages)"),
        (AppPageUpdate, "AppPageUpdate (for updating pages)"),
    ], "Page Models")

    component_models = models_to_markdown([
        (AppComponentCreate, "AppComponentCreate (for creating components)"),
        (AppComponentUpdate, "AppComponentUpdate (for updating components)"),
        (AppComponentMove, "AppComponentMove (for moving components)"),
    ], "Component Models")

    # Component types - unified model with flat props
    container_components = models_to_markdown([
        (RowComponent, "RowComponent (horizontal layout)"),
        (ColumnComponent, "ColumnComponent (vertical layout)"),
        (CardComponent, "CardComponent (container with header)"),
        (ModalComponent, "ModalComponent (dialog container)"),
        (TabsComponent, "TabsComponent (tabbed container)"),
        (FormGroupComponent, "FormGroupComponent (form field group)"),
    ], "Container Components (can have children)")

    leaf_components = models_to_markdown([
        (HeadingComponent, "HeadingComponent (h1-h6)"),
        (TextComponent, "TextComponent (body text)"),
        (ButtonComponent, "ButtonComponent (clickable button)"),
        (StatCardComponent, "StatCardComponent (metric display)"),
        (DataTableComponent, "DataTableComponent (data table)"),
        (TextInputComponent, "TextInputComponent (text field)"),
        (SelectComponent, "SelectComponent (dropdown)"),
        (FormEmbedComponent, "FormEmbedComponent (embedded form)"),
    ], "Leaf Components (no children)")

    # Conceptual documentation
    overview = """# App Builder Schema Documentation

Applications in Bifrost are defined using a JSON schema with pages, layouts, and components.

## App Builder Tool Hierarchy

Apps are managed at three levels:

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
then component tools for granular edits.

---

"""

    component_types_doc = """
## Component Model (Unified Flat Props)

All components use a unified model where props are FLAT on the component (not nested under a 'props' key).

When creating/updating components via MCP tools, pass props in the `props` dict:
```json
{
    "component_id": "my-heading",
    "type": "heading",
    "props": {
        "text": "Welcome",
        "level": 1
    }
}
```

When reading components (from get_page), props are returned FLAT on the component:
```json
{
    "id": "my-heading",
    "type": "heading",
    "text": "Welcome",
    "level": 1
}
```

See the component type documentation above for all available properties per type.

## Available Component Types

### Container Components (can have children)
| Type | Description |
|------|-------------|
| row | Horizontal flex container (layout) |
| column | Vertical flex container (layout) |
| grid | CSS grid container (layout) |
| card | Container with optional header/title |
| modal | Dialog/modal container |
| tabs | Tabbed container |
| tab-item | Single tab within tabs |
| form-group | Group form fields with label |

### Leaf Components (no children)
| Type | Description |
|------|-------------|
| heading | Display heading text (h1-h6) |
| text | Display text content |
| html | Render raw HTML content |
| divider | Horizontal dividing line |
| spacer | Vertical spacing |
| button | Clickable button with actions |
| stat-card | Metric display with label and value |
| image | Display images |
| badge | Status indicator |
| progress | Progress bar |
| data-table | Data table with sorting/filtering |
| file-viewer | Document/image viewer |
| text-input | Text input field |
| number-input | Number input field |
| select | Dropdown selection |
| checkbox | Boolean toggle |
| form-embed | Embed a Bifrost form |

## Expression Syntax

Use `{{ expression }}` for dynamic content:
- `{{ page.variable }}` - Page variables
- `{{ component.id.value }}` - Component values
- `{{ workflow.dataSourceId.result }}` - Workflow results
- `{{ $user.name }}` - Current user info

## Action Types

| Action | Description |
|--------|-------------|
| navigate | Navigate to another page |
| openModal | Open a modal component |
| closeModal | Close current modal |
| runWorkflow | Execute a workflow |
| setValue | Set a component or page variable |
| openUrl | Open external URL |

"""

    return overview + app_models + "\n\n" + page_models + "\n\n" + component_models + "\n\n" + props_models + "\n\n" + component_types_doc


# End of apps.py
