"""
App Builder MCP Tools - Application Level

Tools for listing, creating, getting, updating, publishing apps,
plus schema documentation.

Applications use code-based files (TSX/TypeScript) stored in file_index table.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastmcp.tools.tool import ToolResult

from src.core.pubsub import publish_app_draft_update, publish_app_published
from src.services.mcp_server.tool_result import error_result, success_result

logger = logging.getLogger(__name__)


async def list_apps(context: Any) -> ToolResult:
    """List all applications with file summaries."""
    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.app_storage import AppStorageService

    logger.info("MCP list_apps called")

    try:
        async with get_db_context() as db:
            query = select(Application)

            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query.order_by(Application.name))
            apps = result.scalars().all()

            apps_data = []
            for app in apps:
                app_storage = AppStorageService()
                preview_files = await app_storage.list_files(str(app.id), "preview")
                count = len(preview_files)

                apps_data.append({
                    "id": str(app.id),
                    "name": app.name,
                    "slug": app.slug,
                    "description": app.description,
                    "status": "published" if app.is_published else "draft",
                    "is_published": app.is_published,
                    "has_unpublished_changes": app.has_unpublished_changes,
                    "file_count": count,
                    "url": f"/apps/{app.slug}",
                })

            display_text = f"Found {len(apps_data)} application(s)"
            return success_result(display_text, {"apps": apps_data, "count": len(apps_data)})

    except Exception as e:
        logger.exception(f"Error listing apps via MCP: {e}")
        return error_result(f"Error listing apps: {str(e)}")


async def create_app(
    context: Any,
    name: str,
    description: str | None = None,
    slug: str | None = None,
    scope: str = "organization",
    organization_id: str | None = None,
) -> ToolResult:
    """
    Create a new application with scaffold files.

    Args:
        name: Application name (required)
        description: Application description
        slug: URL slug (auto-generated from name if not provided)
        scope: 'global' (visible to all orgs) or 'organization' (default)
        organization_id: Override context.org_id when scope='organization'

    Returns:
        ToolResult with app details
    """
    import re
    from uuid import UUID, uuid4

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.file_storage import FileStorageService

    logger.info(f"MCP create_app called with name={name}, scope={scope}")

    if not name:
        return error_result("name is required")

    if scope not in ("global", "organization"):
        return error_result("scope must be 'global' or 'organization'")

    effective_org_id: UUID | None = None
    if scope == "global":
        effective_org_id = None
    else:
        if organization_id:
            try:
                effective_org_id = UUID(organization_id)
            except ValueError:
                return error_result(f"organization_id '{organization_id}' is not a valid UUID")
        elif context.org_id:
            effective_org_id = UUID(str(context.org_id)) if isinstance(context.org_id, str) else context.org_id
        else:
            return error_result("organization_id is required when scope='organization' and no context org_id is set")

    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    try:
        async with get_db_context() as db:
            query = select(Application).where(Application.slug == slug)
            if effective_org_id:
                query = query.where(Application.organization_id == effective_org_id)
            else:
                query = query.where(Application.organization_id.is_(None))

            existing = await db.execute(query)
            if existing.scalar_one_or_none():
                return error_result(f"Application with slug '{slug}' already exists")

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

            # Write scaffold files via FileStorageService
            file_storage = FileStorageService(db)

            layout_source = '''import { Outlet } from "bifrost";

export default function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <Outlet />
    </div>
  );
}
'''
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
            await file_storage.write_file(
                path=f"apps/{slug}/_layout.tsx",
                content=layout_source.encode("utf-8"),
                updated_by="system",
            )
            await file_storage.write_file(
                path=f"apps/{slug}/pages/index.tsx",
                content=index_source.encode("utf-8"),
                updated_by="system",
            )

            await db.commit()

            display_text = f"Created application: {app.name}"
            return success_result(display_text, {
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "file_count": 2,
                "url": f"/apps/{app.slug}",
            })

    except Exception as e:
        logger.exception(f"Error creating app via MCP: {e}")
        return error_result(f"Error creating app: {str(e)}")


async def get_app(
    context: Any,
    app_id: str | None = None,
    app_slug: str | None = None,
) -> ToolResult:
    """
    Get application metadata and file list.

    Returns app info and a summary of files.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.app_storage import AppStorageService

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

            if not context.is_platform_admin and context.org_id:
                query = query.where(
                    (Application.organization_id == context.org_id)
                    | (Application.organization_id.is_(None))
                )

            result = await db.execute(query)
            app = result.scalar_one_or_none()

            if not app:
                return error_result(f"Application not found: {app_id or app_slug}")

            # List files from S3 preview
            app_storage = AppStorageService()
            preview_files = await app_storage.list_files(str(app.id), "preview")

            app_data = {
                "id": str(app.id),
                "name": app.name,
                "slug": app.slug,
                "description": app.description,
                "is_published": app.is_published,
                "has_unpublished_changes": app.has_unpublished_changes,
                "url": f"/apps/{app.slug}",
                "files": [
                    {"path": p}
                    for p in sorted(preview_files)
                ],
            }

            display_text = f"Application: {app.name}"
            return success_result(display_text, app_data)

    except Exception as e:
        logger.exception(f"Error getting app via MCP: {e}")
        return error_result(f"Error getting app: {str(e)}")


async def update_app(
    context: Any,
    app_id: str,
    name: str | None = None,
    description: str | None = None,
) -> ToolResult:
    """
    Update application metadata.

    Args:
        app_id: Application UUID (required)
        name: New application name
        description: New description

    Returns:
        ToolResult with updated fields
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

            if not updates_made:
                return error_result("No updates specified")

            await db.commit()

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


async def publish_app(context: Any, app_id: str) -> ToolResult:
    """Publish all draft files to live.

    Builds a published_snapshot from current file_index entries and
    sets it on the application.
    """
    from uuid import UUID

    from sqlalchemy import select

    from src.core.database import get_db_context
    from src.models.orm.applications import Application
    from src.services.app_storage import AppStorageService

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

            # Publish via AppStorageService: copy preview → live in S3
            app_storage = AppStorageService()
            published_count = await app_storage.publish(str(app.id))

            if published_count == 0:
                return error_result("No files found to publish")

            # Update app metadata
            preview_files = await app_storage.list_files(str(app.id), "preview")
            app.published_snapshot = {f: "" for f in preview_files}
            app.published_at = datetime.now(timezone.utc)

            await db.commit()

            await publish_app_published(
                app_id=app_id,
                user_id=str(context.user_id),
                user_name=context.user_name or context.user_email or "Unknown",
                new_version_id=app_id,
            )

            display_text = f"Published application: {app.name} ({published_count} files)"
            return success_result(display_text, {
                "success": True,
                "id": str(app.id),
                "name": app.name,
                "is_published": True,
                "files_published": published_count,
            })

    except Exception as e:
        logger.exception(f"Error publishing app via MCP: {e}")
        return error_result(f"Error publishing app: {str(e)}")


async def get_app_schema(context: Any) -> ToolResult:  # noqa: ARG001
    """Get application schema documentation for code-based apps."""
    from src.models.contracts.applications import (
        ApplicationCreate,
        ApplicationUpdate,
    )
    from src.services.mcp_server.schema_utils import models_to_markdown

    app_models = models_to_markdown([
        (ApplicationCreate, "ApplicationCreate (for creating apps)"),
        (ApplicationUpdate, "ApplicationUpdate (for updating apps)"),
    ], "Application Models")

    # Documentation for code-based apps
    overview = r"""# App Builder Schema Documentation

Applications in Bifrost use a code-based approach with TypeScript/TSX files.

## App Builder Tool Hierarchy

Apps are managed at two levels:

### App Level
- `list_apps` - List all applications with file counts
- `get_app` - Get app metadata and file list
- `update_app` - Update app settings (name, description)
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

## Workflow Hooks

**CRITICAL: Always use workflow IDs, not names.**

```tsx
// CORRECT - use the workflow UUID
const { data } = useWorkflowQuery("ef8cf1f2-b451-47f4-aee8-336f7cb21d33");

// WRONG - names don't work
const { data } = useWorkflowQuery("list_csp_tenants");
```

Get workflow IDs using `list_workflows` before building the app.

Two hooks are available:
- `useWorkflowQuery` — for loading data (runs automatically on mount)
- `useWorkflowMutation` — for user-triggered actions (runs when you call `execute()`)

### useWorkflowQuery

Declarative data fetching. Executes automatically on mount, re-executes when params change.

| Property | Type | Description |
|----------|------|-------------|
| `data` | `T \| null` | The workflow result data (null until completed) |
| `isLoading` | `boolean` | True while the workflow is executing |
| `isError` | `boolean` | True if the workflow failed |
| `error` | `string \| null` | Error message if workflow failed |
| `logs` | `StreamingLog[]` | Streaming logs array (updates in real-time) |
| `refetch` | `() => Promise<T>` | Re-execute the workflow |
| `executionId` | `string \| null` | Current execution ID |
| `status` | `string \| null` | Execution status |

Options (third parameter): `{ enabled?: boolean }` — set `enabled: false` to skip automatic execution.

### useWorkflowMutation

Imperative execution. Does nothing until `execute()` is called. `execute()` returns `Promise<T>` with the actual result.

| Property | Type | Description |
|----------|------|-------------|
| `execute` | `(params?) => Promise<T>` | Execute the workflow. Returns the result directly. |
| `isLoading` | `boolean` | True while the workflow is executing |
| `isError` | `boolean` | True if the last execution failed |
| `error` | `string \| null` | Error message from last execution |
| `data` | `T \| null` | Result data from last execution |
| `logs` | `StreamingLog[]` | Streaming logs array (updates in real-time) |
| `reset` | `() => void` | Reset data, error, and loading state |
| `executionId` | `string \| null` | Current execution ID |
| `status` | `string \| null` | Execution status |

### Usage Patterns

**Pattern 1: Load data on mount (`useWorkflowQuery`)**

Best for workflows that load data when the page loads.

```tsx
const { data, isLoading, error } = useWorkflowQuery("workflow-id", { limit: 10 });

if (isLoading) return <Skeleton />;
if (error) return <Alert>{error}</Alert>;

return <CustomerList data={data} />;
```

**Pattern 2: Button-triggered action (`useWorkflowMutation`)**

Best for user-triggered actions like create, update, delete.

```tsx
const { execute, isLoading } = useWorkflowMutation("create-item-workflow");

const handleCreate = async () => {
  try {
    const result = await execute({ name: "New Item" });
    setItems(prev => [...prev, result.item]);
    setDialogOpen(false);
  } catch (err) {
    console.error("Failed:", err.message);
  }
};

<Button onClick={handleCreate} disabled={isLoading}>
  {isLoading ? <Loader2 className="animate-spin" /> : "Create"}
</Button>
```

**Pattern 3: Sequential/batch calls (`useWorkflowMutation`)**

Each `execute()` call is independent — safe to call in a loop.

```tsx
const { execute } = useWorkflowMutation("process-item-workflow");

const handleBatch = async () => {
  const results = [];
  for (const item of items) {
    const result = await execute({ id: item.id });
    results.push(result);
  }
  setProcessed(results);
};
```

**Pattern 4: Conditional loading (`useWorkflowQuery` with `enabled`)**

Delay execution until a condition is met.

```tsx
const params = useParams();
const { data, isLoading } = useWorkflowQuery(
  "get-customer-workflow",
  { id: params.id },
  { enabled: !!params.id }
);
```

### Guidelines

- Use `useWorkflowQuery` for **reading/loading data** (GET-like operations)
- Use `useWorkflowMutation` for **user-triggered actions and writes** (POST/PUT/DELETE-like operations)
- No `useEffect` needed for handling results — `useWorkflowQuery` auto-executes, and `useWorkflowMutation.execute()` returns results directly as a Promise

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

    schema_doc = overview + app_models
    return success_result("App Builder schema documentation", {"schema": schema_doc})


# Tool metadata for registration
TOOLS = [
    ("list_apps", "List Applications", "List all App Builder applications with file counts and URLs."),
    ("create_app", "Create Application", "Create a new App Builder application with scaffold files."),
    ("get_app", "Get Application", "Get application metadata and file list."),
    ("update_app", "Update Application", "Update application metadata (name, description)."),
    ("publish_app", "Publish Application", "Publish all draft files to live."),
    ("get_app_schema", "Get App Schema", "Get documentation about App Builder application structure and code-based files."),
]


def register_tools(mcp: Any, get_context_fn: Any) -> None:
    """Register all apps tools with FastMCP."""
    from src.services.mcp_server.generators.fastmcp_generator import register_tool_with_context

    tool_funcs = {
        "list_apps": list_apps,
        "create_app": create_app,
        "get_app": get_app,
        "update_app": update_app,
        "publish_app": publish_app,
        "get_app_schema": get_app_schema,
    }

    for tool_id, name, description in TOOLS:
        register_tool_with_context(mcp, tool_funcs[tool_id], tool_id, description, get_context_fn)
