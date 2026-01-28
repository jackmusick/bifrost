"""
App Builder MCP Tools - Application Level

Tools for listing, creating, getting, updating, publishing apps,
plus schema documentation.

Applications use code-based files (TSX/TypeScript) stored in app_files table.
"""

import logging
from typing import Any

from mcp.types import CallToolResult

from src.core.pubsub import publish_app_draft_update, publish_app_published
from src.services.mcp_server.tool_decorator import system_tool
from src.services.mcp_server.tool_registry import ToolCategory
from src.services.mcp_server.tool_result import error_result, success_result

logger = logging.getLogger(__name__)


@system_tool(
    id="list_apps",
    name="List Applications",
    description="List all App Builder applications with file counts and URLs.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def list_apps(context: Any) -> CallToolResult:
    """List all applications with file summaries."""
    from sqlalchemy import func, select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info("MCP list_apps called")

    try:
        async with get_db_context() as db:
            # Query apps with file count
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
                # Get file count from draft version
                count = 0
                if app.draft_version_id:
                    file_count_query = (
                        select(func.count())
                        .select_from(AppFile)
                        .where(AppFile.app_version_id == app.draft_version_id)
                    )
                    file_count = await db.execute(file_count_query)
                    count = file_count.scalar() or 0

                apps_data.append({
                    "id": str(app.id),
                    "name": app.name,
                    "slug": app.slug,
                    "description": app.description,
                    "status": "published" if app.is_published else "draft",
                    "file_count": count,
                    "active_version_id": str(app.active_version_id) if app.active_version_id else None,
                    "draft_version_id": str(app.draft_version_id) if app.draft_version_id else None,
                    "url": f"/apps/{app.slug}",
                })

            display_text = f"Found {len(apps_data)} application(s)"
            return success_result(display_text, {"apps": apps_data, "count": len(apps_data)})

    except Exception as e:
        logger.exception(f"Error listing apps via MCP: {e}")
        return error_result(f"Error listing apps: {str(e)}")


@system_tool(
    id="create_app",
    name="Create Application",
    description="Create a new App Builder application with scaffold files.",
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
    scope: str = "organization",
    organization_id: str | None = None,
) -> CallToolResult:
    """
    Create a new application with scaffold files.

    Args:
        name: Application name (required)
        description: Application description
        slug: URL slug (auto-generated from name if not provided)
        scope: 'global' (visible to all orgs) or 'organization' (default)
        organization_id: Override context.org_id when scope='organization'

    Returns:
        CallToolResult with app details
    """
    import re
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, AppVersion, Application

    logger.info(f"MCP create_app called with name={name}, scope={scope}")

    if not name:
        return error_result("name is required")

    # Validate scope parameter
    if scope not in ("global", "organization"):
        return error_result("scope must be 'global' or 'organization'")

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
                return error_result(f"organization_id '{organization_id}' is not a valid UUID")
        elif context.org_id:
            effective_org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
        else:
            return error_result("organization_id is required when scope='organization' and no context org_id is set")

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
                return error_result(f"Application with slug '{slug}' already exists")

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
            await db.flush()

            # Create scaffold files
            # Root layout - wraps all pages
            layout_source = '''import { Outlet } from "bifrost";

export default function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <Outlet />
    </div>
  );
}
'''
            layout_file = AppFile(
                app_version_id=draft_version.id,
                path="_layout.tsx",
                source=layout_source,
            )
            db.add(layout_file)

            # Home page
            index_source = '''export default function HomePage() {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-4">Welcome</h1>
      <p className="text-muted-foreground">
        Start building your app by editing this page or adding new files.
      </p>
    </div>
  );
}
'''
            index_file = AppFile(
                app_version_id=draft_version.id,
                path="pages/index.tsx",
                source=index_source,
            )
            db.add(index_file)

            await db.commit()

            display_text = f"Created application: {app.name}"
            return success_result(display_text, {
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "draft_version_id": str(draft_version.id),
                "file_count": 2,
                "url": f"/apps/{app.slug}",
            })

    except Exception as e:
        logger.exception(f"Error creating app via MCP: {e}")
        return error_result(f"Error creating app: {str(e)}")


@system_tool(
    id="get_app",
    name="Get Application",
    description="Get application metadata and file list.",
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
) -> CallToolResult:
    """
    Get application metadata and file list.

    Returns app info and a summary of files in the draft version.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, Application

    logger.info(f"MCP get_app called with id={app_id}, slug={app_slug}")

    if not app_id and not app_slug:
        return error_result("Either app_id or app_slug is required")

    try:
        async with get_db_context() as db:
            query = select(Application)

            if app_id:
                try:
                    query = query.where(Application.id == UUID(app_id))
                except ValueError:
                    return error_result(f"Invalid app_id format: {app_id}")
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
                return error_result(f"Application not found: {app_id or app_slug}")

            # List files from draft version
            files = []
            if app.draft_version_id:
                files_query = (
                    select(AppFile)
                    .where(AppFile.app_version_id == app.draft_version_id)
                    .order_by(AppFile.path)
                )
                files_result = await db.execute(files_query)
                files = list(files_result.scalars().all())

            app_data = {
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "description": app.description,
                "active_version_id": str(app.active_version_id) if app.active_version_id else None,
                "draft_version_id": str(app.draft_version_id) if app.draft_version_id else None,
                "url": f"/apps/{app.slug}",
                "navigation": app.navigation,
                "files": [
                    {
                        "id": str(f.id),
                        "path": f.path,
                        "has_compiled": f.compiled is not None,
                    }
                    for f in files
                ],
            }

            display_text = f"Application: {app.name}"
            return success_result(display_text, app_data)

    except Exception as e:
        logger.exception(f"Error getting app via MCP: {e}")
        return error_result(f"Error getting app: {str(e)}")


@system_tool(
    id="update_app",
    name="Update Application",
    description="Update application metadata (name, description, navigation).",
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
) -> CallToolResult:
    """
    Update application metadata.

    Args:
        app_id: Application UUID (required)
        name: New application name
        description: New description
        navigation: Navigation configuration dict

    Returns:
        CallToolResult with updated fields
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application

    logger.info(f"MCP update_app called with id={app_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return error_result(f"Invalid app_id format: {app_id}")

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return error_result(f"Application not found: {app_id}")

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

                from src.models.contracts.applications import NavigationConfig

                try:
                    # Use strict=True to catch type mismatches
                    validated_nav = NavigationConfig.model_validate(navigation, strict=True)
                    app.navigation = validated_nav.model_dump(exclude_none=True)
                    updates_made.append("navigation")
                except ValidationError as e:
                    return error_result(f"Invalid navigation configuration: {e}")

            if not updates_made:
                return error_result("No updates specified")

            await db.commit()

            # Emit event for real-time updates
            await publish_app_draft_update(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                entity_type="app",
                entity_id=app_id,
            )

            display_text = f"Updated application: {app.name} ({', '.join(updates_made)})"
            return success_result(display_text, {
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "updates": updates_made,
            })

    except Exception as e:
        logger.exception(f"Error updating app via MCP: {e}")
        return error_result(f"Error updating app: {str(e)}")


@system_tool(
    id="publish_app",
    name="Publish Application",
    description="Publish all draft files to live.",
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
async def publish_app(context: Any, app_id: str) -> CallToolResult:
    """Publish all draft files to live.

    Creates a new version by copying all files from the draft version,
    then sets this new version as the active (live) version.
    """
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.database import get_db_context
    from src.models.orm.applications import AppFile, AppVersion, Application

    logger.info(f"MCP publish_app called with id={app_id}")

    try:
        app_uuid = UUID(app_id)
    except ValueError:
        return error_result(f"Invalid app_id format: {app_id}")

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.id == app_uuid)

            if not context.is_platform_admin and context.org_id:
                query = query.where(Application.organization_id == context.org_id)

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return error_result(f"Application not found: {app_id}")

            if not app.draft_version_id:
                return error_result("Application has no draft version to publish")

            # Get draft version with files
            draft_version_query = (
                select(AppVersion)
                .where(AppVersion.id == app.draft_version_id)
                .options(selectinload(AppVersion.files))
            )
            draft_result = await db.execute(draft_version_query)
            draft_version = draft_result.scalar_one_or_none()

            if not draft_version or not draft_version.files:
                return error_result("No files in draft version to publish")

            # Create new version for the published copy
            new_version = AppVersion(application_id=app.id)
            db.add(new_version)
            await db.flush()

            # Copy all files from draft to new version
            for draft_file in draft_version.files:
                new_file = AppFile(
                    app_version_id=new_version.id,
                    path=draft_file.path,
                    source=draft_file.source,
                    compiled=draft_file.compiled,
                )
                db.add(new_file)

            # Update application to point to new active version
            app.active_version_id = new_version.id
            app.published_at = datetime.utcnow()

            await db.commit()

            # Emit event for real-time updates
            await publish_app_published(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                new_version_id=str(new_version.id),
            )

            display_text = f"Published application: {app.name} ({len(draft_version.files)} files)"
            return success_result(display_text, {
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "active_version_id": str(new_version.id),
                "draft_version_id": str(app.draft_version_id),
                "files_published": len(draft_version.files),
            })

    except Exception as e:
        logger.exception(f"Error publishing app via MCP: {e}")
        return error_result(f"Error publishing app: {str(e)}")


@system_tool(
    id="get_app_schema",
    name="Get App Schema",
    description="Get documentation about App Builder application structure and code-based files.",
    category=ToolCategory.APP_BUILDER,
    default_enabled_for_coding_agent=True,
    is_restricted=True,
    input_schema={"type": "object", "properties": {}, "required": []},
)
async def get_app_schema(context: Any) -> CallToolResult:  # noqa: ARG001
    """Get application schema documentation for code-based apps."""
    from src.models.contracts.applications import (
        AppFileCreate,
        AppFileUpdate,
        ApplicationCreate,
        ApplicationUpdate,
    )
    from src.services.mcp_server.schema_utils import models_to_markdown

    # Generate model documentation
    app_models = models_to_markdown([
        (ApplicationCreate, "ApplicationCreate (for creating apps)"),
        (ApplicationUpdate, "ApplicationUpdate (for updating apps)"),
    ], "Application Models")

    file_models = models_to_markdown([
        (AppFileCreate, "AppFileCreate (for creating files)"),
        (AppFileUpdate, "AppFileUpdate (for updating files)"),
    ], "File Models")

    # Documentation for code-based apps
    overview = """# App Builder Schema Documentation

Applications in Bifrost use a code-based approach with TypeScript/TSX files.

## App Builder Tool Hierarchy

Apps are managed at two levels:

### App Level
- `list_apps` - List all applications with file counts
- `get_app` - Get app metadata and file list
- `update_app` - Update app settings (name, description, navigation)
- `publish_app` - Publish all draft files to live

### File Level
- `code_list_files` - List all files in an app
- `code_get_file` - Get a specific file's content
- `code_create_file` - Create a new file
- `code_update_file` - Update a file's content
- `code_delete_file` - Delete a file

**Workflow**: Use `get_app` to see files, then file tools for editing.

---

## File Structure

Applications use a file-based structure:

```
_layout.tsx          # Root layout wrapper (required)
_providers.tsx       # Optional providers wrapper
pages/
  index.tsx          # Home page (/)
  about.tsx          # About page (/about)
  clients/
    index.tsx        # Clients list (/clients)
    [id].tsx         # Client detail (/clients/:id)
components/
  Button.tsx         # Shared components
  Card.tsx
modules/
  api.ts             # Utility modules
  utils.ts
```

## File Path Conventions

- Root files: `_layout.tsx`, `_providers.tsx` only
- Pages: `pages/*.tsx` - automatically become routes
- Components: `components/*.tsx` - reusable UI
- Modules: `modules/*.ts` - utilities and helpers
- Dynamic routes: `[param].tsx` syntax

## CRITICAL: No Import Statements

**App files must NOT contain import statements.** The Bifrost runtime automatically provides all necessary modules in scope:

- **React hooks**: `useState`, `useEffect`, `useMemo`, `useCallback`, etc.
- **Bifrost hooks**: `useWorkflow`, `useUser`, `useNavigate`, `useLocation`, `useParams`
- **Routing**: `Outlet`, `Link`
- **UI components**: `Button`, `Card`, `Table`, `Select`, `Badge`, `Input`, `Skeleton`, etc.
- **Icons**: All lucide-react icons (`Loader2`, `RefreshCw`, `Check`, `X`, `Building2`, etc.)
- **Utilities**: `cn` (for className merging)

If you add import statements, you will get: `Cannot use import statement outside a module`

## useWorkflow Hook

**CRITICAL: Always use workflow IDs, not names.**

```tsx
// CORRECT - use the workflow UUID
const workflow = useWorkflow("ef8cf1f2-b451-47f4-aee8-336f7cb21d33");

// WRONG - names don't work
const workflow = useWorkflow("list_csp_tenants");
```

Get workflow IDs using `list_workflows` before building the app.

The hook returns: `{ result, loading, error, execute }`

## Layout Pattern

The root `_layout.tsx` must use `<Outlet />` for routing:

```tsx
// _layout.tsx - CORRECT
export default function RootLayout() {
  return (
    <div className="h-full bg-background overflow-hidden">
      <Outlet />
    </div>
  );
}
```

**Do NOT use `{children}` prop pattern** - it doesn't work with Bifrost routing.

## Scrolling and Layout

For pages with scrollable content, use flex layout with overflow control:

```tsx
// Page with scrollable table
export default function MyPage() {
  return (
    <div className="flex flex-col h-full p-6 overflow-hidden">
      {/* Header - fixed */}
      <div className="shrink-0 mb-4">
        <h1>Title</h1>
      </div>

      {/* Content - scrollable */}
      <Card className="flex flex-col min-h-0 flex-1">
        <CardHeader className="shrink-0">...</CardHeader>
        <CardContent className="flex-1 min-h-0 overflow-auto">
          <Table>...</Table>
        </CardContent>
      </Card>
    </div>
  );
}
```

Key classes:
- `h-full overflow-hidden` on layout root
- `flex flex-col h-full overflow-hidden` on page root
- `shrink-0` on fixed headers
- `flex-1 min-h-0 overflow-auto` on scrollable content

## Example Page

```tsx
// pages/index.tsx - NO IMPORTS NEEDED
export default function ClientsPage() {
  // Use workflow ID, not name
  const clientsWorkflow = useWorkflow("a1b2c3d4-0001-0001-0001-000000000001");

  useEffect(() => {
    clientsWorkflow.execute();
  }, []);

  if (clientsWorkflow.loading) {
    return (
      <div className="p-8">
        <Skeleton className="h-8 w-48 mb-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const clients = clientsWorkflow.result?.clients || [];

  return (
    <div className="flex flex-col h-full p-6 overflow-hidden">
      <h1 className="text-2xl font-bold mb-4 shrink-0">Clients</h1>
      <Card className="flex flex-col min-h-0 flex-1">
        <CardContent className="flex-1 min-h-0 overflow-auto p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map(client => (
                <TableRow key={client.id}>
                  <TableCell>{client.name}</TableCell>
                  <TableCell>{client.email}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
```

"""

    schema_doc = overview + app_models + "\n\n" + file_models
    return success_result("App Builder schema documentation", {"schema": schema_doc})


# End of apps.py
