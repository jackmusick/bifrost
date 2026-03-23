"""
Applications Router

Manage applications for the App Builder with draft/live versioning.
Uses OrgScopedRepository for standardized org scoping.

Applications follow the same scoping pattern as configs:
- organization_id = NULL: Global application (platform-wide)
- organization_id = UUID: Organization-scoped application

Applications use code-based files (TSX/TypeScript) stored in app_files table.
File operations are handled through the app_files router.
"""

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.core.auth import Context, CurrentUser
from src.core.org_filter import OrgFilterType, resolve_org_filter
from src.core.pubsub import publish_app_draft_update, publish_app_published
from src.models.contracts.applications import (
    ApplicationCreate,
    ApplicationDefinition,
    ApplicationDraftSave,
    ApplicationListResponse,
    ApplicationPublic,
    ApplicationPublishRequest,
    ApplicationRollbackRequest,
    ApplicationUpdate,
)
from src.models.orm.app_roles import AppRole
from src.models.orm.applications import Application
from src.core.exceptions import AccessDeniedError
from src.repositories.org_scoped import OrgScopedRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["Applications"])


# =============================================================================
# Known components available in the app builder runtime
# =============================================================================

KNOWN_APP_COMPONENTS = {
    # React
    "React", "Fragment",
    # Routing
    "Outlet", "Link", "NavLink", "Navigate", "RequireRole",
    # Layout
    "Card", "CardHeader", "CardFooter", "CardTitle", "CardAction", "CardDescription", "CardContent",
    # Forms
    "Button", "Input", "Label", "Textarea", "Checkbox", "Switch",
    "Select", "SelectContent", "SelectGroup", "SelectItem", "SelectLabel", "SelectTrigger", "SelectValue", "SelectSeparator",
    "RadioGroup", "RadioGroupItem", "Combobox", "MultiCombobox", "TagsInput", "Slider",
    # Display
    "Badge", "Avatar", "AvatarImage", "AvatarFallback", "Alert", "AlertTitle", "AlertDescription",
    "Skeleton", "Progress",
    # Navigation
    "Tabs", "TabsList", "TabsTrigger", "TabsContent",
    "Pagination", "PaginationContent", "PaginationEllipsis", "PaginationItem", "PaginationLink", "PaginationNext", "PaginationPrevious",
    # Feedback
    "Dialog", "DialogClose", "DialogContent", "DialogDescription", "DialogFooter", "DialogHeader", "DialogTitle", "DialogTrigger",
    "AlertDialog", "AlertDialogTrigger", "AlertDialogContent", "AlertDialogHeader", "AlertDialogFooter", "AlertDialogTitle", "AlertDialogDescription", "AlertDialogAction", "AlertDialogCancel",
    "Tooltip", "TooltipContent", "TooltipProvider", "TooltipTrigger",
    "Popover", "PopoverContent", "PopoverTrigger", "PopoverAnchor",
    "HoverCard", "HoverCardContent", "HoverCardTrigger",
    "Sheet", "SheetClose", "SheetContent", "SheetDescription", "SheetFooter", "SheetHeader", "SheetTitle", "SheetTrigger",
    "Command", "CommandDialog", "CommandEmpty", "CommandGroup", "CommandInput", "CommandItem", "CommandList", "CommandSeparator", "CommandShortcut",
    "ContextMenu", "ContextMenuCheckboxItem", "ContextMenuContent", "ContextMenuGroup", "ContextMenuItem", "ContextMenuLabel", "ContextMenuPortal", "ContextMenuRadioGroup", "ContextMenuRadioItem", "ContextMenuSeparator", "ContextMenuShortcut", "ContextMenuSub", "ContextMenuSubContent", "ContextMenuSubTrigger", "ContextMenuTrigger",
    # Data Display
    "Table", "TableHeader", "TableBody", "TableFooter", "TableHead", "TableRow", "TableCell", "TableCaption",
    # Calendar/Date
    "Calendar", "DateRangePicker",
    # Accordion/Collapsible
    "Accordion", "AccordionContent", "AccordionItem", "AccordionTrigger",
    "Collapsible", "CollapsibleContent", "CollapsibleTrigger",
    # Toggle
    "Toggle", "ToggleGroup", "ToggleGroupItem",
    # Separator
    "Separator",
    # DropdownMenu
    "DropdownMenu", "DropdownMenuCheckboxItem", "DropdownMenuContent", "DropdownMenuGroup", "DropdownMenuItem", "DropdownMenuLabel", "DropdownMenuPortal", "DropdownMenuRadioGroup", "DropdownMenuRadioItem", "DropdownMenuSeparator", "DropdownMenuShortcut", "DropdownMenuSub", "DropdownMenuSubContent", "DropdownMenuSubTrigger", "DropdownMenuTrigger",
}

# Note: Lucide icons (lucide-react) are all valid - hundreds of icons available.
# We skip checking those to avoid false positives.

# All names available via `import { ... } from "bifrost"` in app code.
# Built from: React exports, platform scope (scope.ts), UI components,
# utility functions (utils.ts), and date-fns.
KNOWN_BIFROST_EXPORTS = KNOWN_APP_COMPONENTS | {
    # Platform hooks (from scope.ts / createPlatformScope)
    "useWorkflowQuery", "useWorkflowMutation",
    "useUser", "useAppState",
    "useNavigate", "useParams", "useSearchParams",
    "useLocation", "useMatch", "useResolvedPath", "useOutletContext",
    # Platform functions
    "navigate",
    # React hooks and utilities (spread via ...React in runtime)
    "useState", "useEffect", "useCallback", "useMemo", "useRef",
    "useContext", "useReducer", "useLayoutEffect", "useId",
    "useTransition", "useDeferredValue", "useSyncExternalStore",
    "useInsertionEffect", "useDebugValue", "useImperativeHandle",
    # React component utilities
    "Fragment", "Suspense", "lazy", "memo", "forwardRef",
    "createContext", "createRef", "createElement", "cloneElement",
    "isValidElement", "Children", "StrictMode",
    # Utility functions (from ...utils spread)
    "cn", "formatDate", "formatDateShort", "formatTime",
    "formatRelativeTime", "formatBytes", "formatNumber",
    "formatCost", "formatDuration",
    # Third-party utilities available in scope
    "clsx", "twMerge", "format",
}


class AppValidationIssue(BaseModel):
    severity: str  # "error" or "warning"
    file: str
    message: str
    line: int | None = None


class AppValidationResponse(BaseModel):
    valid: bool
    errors: list[AppValidationIssue] = []
    warnings: list[AppValidationIssue] = []


# =============================================================================
# Repository
# =============================================================================


class ApplicationRepository(OrgScopedRepository[Application]):
    """
    Repository for application operations.

    Applications use the CASCADE scoping pattern for org users:
    - Org-specific applications + global (NULL org_id) applications

    Role-based access control:
    - Applications with access_level="role_based" require user to have a role assigned
    - Applications with access_level="authenticated" are accessible to any authenticated user
    """

    model = Application
    role_table = AppRole
    role_entity_id_column = "app_id"

    async def list_applications(self) -> list[Application]:
        """
        List applications with cascade scoping and role-based access.

        Uses the base class scoping and role checking automatically.

        Returns:
            List of Application ORM objects
        """
        # Build base query with cascade scoping
        query = select(self.model)
        query = self._apply_cascade_scope(query)
        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        entities = list(result.scalars().all())

        # Filter by role access for non-superusers with role-based entities
        if not self.is_superuser:
            accessible = []
            for entity in entities:
                if await self._can_access_entity(entity):
                    accessible.append(entity)
            return accessible

        return entities

    async def list_all_in_scope(
        self,
        filter_type: OrgFilterType = OrgFilterType.ALL,
    ) -> list[Application]:
        """
        List all applications in scope without role-based filtering.

        Used by platform admins who bypass role checks.
        Supports all filter types:
        - ALL: No org filter, show everything
        - GLOBAL_ONLY: Only applications with org_id IS NULL
        - ORG_ONLY: Only applications in the specific org (no global fallback)
        - ORG_PLUS_GLOBAL: Applications in the org + global applications

        Args:
            filter_type: How to filter by organization scope

        Returns:
            List of Application ORM objects
        """
        query = select(self.model)

        # Apply org filtering based on filter type
        if filter_type == OrgFilterType.ALL:
            # No org filter - show everything
            pass
        elif filter_type == OrgFilterType.GLOBAL_ONLY:
            # Only global applications (org_id IS NULL)
            query = query.where(self.model.organization_id.is_(None))
        elif filter_type == OrgFilterType.ORG_ONLY:
            # Only the specific org, NO global fallback
            if self.org_id is not None:
                query = query.where(self.model.organization_id == self.org_id)
            else:
                # Edge case: ORG_ONLY with no org_id - return nothing
                query = query.where(self.model.id == None)  # noqa: E711
        elif filter_type == OrgFilterType.ORG_PLUS_GLOBAL:
            # Cascade scope: org + global
            query = self._apply_cascade_scope(query)

        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, id: UUID) -> Application | None:
        """
        Get application by UUID with cascade scoping and role-based access check.

        Prioritizes org-specific over global to avoid MultipleResultsFound
        when the same ID exists in both scopes.

        Args:
            id: Application UUID

        Returns:
            Application if found and accessible, None otherwise
        """
        # Build query filtering by ID
        query = select(self.model).where(self.model.id == id)

        # Apply cascade scoping: prioritize org-specific, then global
        if self.org_id is not None:
            # Try org-specific first
            org_query = query.where(self.model.organization_id == self.org_id)
            result = await self.session.execute(org_query)
            entity = result.scalar_one_or_none()
            if entity:
                if await self._can_access_entity(entity):
                    return entity
                return None

        # Fall back to global
        global_query = query.where(self.model.organization_id.is_(None))
        result = await self.session.execute(global_query)
        entity = result.scalar_one_or_none()

        if entity and await self._can_access_entity(entity):
            return entity
        return None

    async def get_by_slug_global(self, slug: str) -> Application | None:
        """Check if any application exists with this slug (globally unique)."""
        query = select(self.model).where(self.model.slug == slug)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_role_ids(self, app_id: UUID) -> list[UUID]:
        """Get list of role IDs assigned to an application."""
        query = select(AppRole.role_id).where(AppRole.app_id == app_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_application(
        self,
        data: ApplicationCreate,
        created_by: str,
    ) -> Application:
        """Create a new application with access control settings."""
        # Check if application already exists in this scope
        existing = await self.get_by_slug_global(data.slug)
        if existing:
            raise ValueError(f"Application with slug '{data.slug}' already exists")

        application = Application(
            name=data.name,
            slug=data.slug,
            description=data.description,
            icon=data.icon,
            organization_id=self.org_id,
            created_by=created_by,
            access_level=data.access_level,
            repo_path=f"apps/{data.slug}",
        )
        self.session.add(application)
        await self.session.flush()

        # Scaffold initial files via FileStorageService
        await self._scaffold_code_files(application.slug)

        # Add role associations if role_based access
        if data.access_level == "role_based" and data.role_ids:
            for role_id in data.role_ids:
                app_role = AppRole(
                    app_id=application.id,
                    role_id=role_id,
                    assigned_by=created_by,
                )
                self.session.add(app_role)
            await self.session.flush()

        await self.session.refresh(application)

        logger.info(f"Created application '{data.slug}' in org {self.org_id} with access_level={data.access_level}")
        return application

    async def update_application(
        self,
        app_id: UUID,
        data: ApplicationUpdate,
        updated_by: str,
        is_platform_admin: bool = False,
    ) -> Application | None:
        """Update application metadata and access control by ID."""
        application = await self.get_by_id(app_id)
        if not application:
            return None

        if data.name is not None:
            application.name = data.name
        if data.description is not None:
            application.description = data.description
        if data.icon is not None:
            application.icon = data.icon
        if data.access_level is not None:
            application.access_level = data.access_level

        # Handle slug change with uniqueness check
        if data.slug is not None and data.slug != application.slug:
            # Check if new slug already exists in the same scope
            existing = await self.get_by_slug_global(data.slug)
            if existing and existing.id != application.id:
                raise ValueError(f"Application with slug '{data.slug}' already exists")
            application.slug = data.slug

        # Handle scope change (platform admin only)
        if data.scope is not None and is_platform_admin:
            if data.scope == "global":
                application.organization_id = None
            else:
                try:
                    application.organization_id = UUID(data.scope)
                except ValueError:
                    pass  # Invalid UUID, ignore

        # Update role associations if provided
        if data.role_ids is not None:
            # Delete existing role associations
            existing_roles_query = select(AppRole).where(AppRole.app_id == application.id)
            result = await self.session.execute(existing_roles_query)
            for existing_role in result.scalars().all():
                await self.session.delete(existing_role)

            # Add new role associations (deduplicate to avoid unique constraint violation)
            unique_role_ids = set(data.role_ids)
            for role_id in unique_role_ids:
                app_role = AppRole(
                    app_id=application.id,
                    role_id=role_id,
                    assigned_by=updated_by,
                )
                self.session.add(app_role)

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Updated application '{app_id}'")
        return application

    async def delete_application(self, app_id: UUID) -> bool:
        """Delete an application by ID (cascade deletes pages and components)."""
        application = await self.get_by_id(app_id)
        if not application:
            return False

        await self.session.delete(application)
        await self.session.flush()

        logger.info(f"Deleted application '{app_id}'")
        return True

    async def publish(
        self,
        app_id: UUID,
        published_by: str,
        message: str | None = None,
    ) -> Application | None:
        """
        Publish draft to live.

        Copies preview files to live in S3 via AppStorageService, then
        captures a published_snapshot for backwards compatibility.
        """
        application = await self.get_by_id(app_id)
        if not application:
            return None

        # Re-compile all files from _repo/ before publishing
        from src.services.app_storage import AppStorageService
        app_storage = AppStorageService()
        synced, compile_errors = await app_storage.sync_preview_compiled(
            str(app_id), application.repo_prefix
        )
        if compile_errors:
            logger.warning(f"Compile warnings during publish: {compile_errors}")

        # Now copy preview -> live
        published_count = await app_storage.publish(str(app_id))

        if published_count == 0:
            raise ValueError("No files found to publish")

        # Build snapshot for backwards compat
        preview_files = await app_storage.list_files(str(app_id), "preview")
        snapshot = {f: "" for f in preview_files}

        application.published_snapshot = snapshot
        application.published_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(
            f"Published application {app_id} "
            f"({published_count} files) by user {published_by}"
        )
        return application

    async def _scaffold_code_files(self, slug: str) -> None:
        """Create initial scaffold files for a new app via FileStorageService.

        Creates:
        - _layout.tsx: Root layout wrapper
        - pages/index.tsx: Home page
        """
        from src.services.file_storage import FileStorageService

        file_storage = FileStorageService(self.session)

        layout_source = '''import { Outlet } from "bifrost";

export default function RootLayout() {
  return (
    <div className="min-h-screen bg-background">
      <Outlet />
    </div>
  );
}
'''
        await file_storage.write_file(
            path=f"apps/{slug}/_layout.tsx",
            content=layout_source.encode("utf-8"),
            updated_by="system",
        )

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
            path=f"apps/{slug}/pages/index.tsx",
            content=index_source.encode("utf-8"),
            updated_by="system",
        )

        logger.info(f"Scaffolded initial code files for app {slug}")

    async def export_application(
        self,
        application: Application,
        version_id: UUID | None = None,  # noqa: ARG002 - kept for API compat
    ) -> dict:
        """
        Export application data for API response or GitHub sync.

        Returns a dictionary with application metadata and files from file_index.
        """
        from src.models.orm.file_index import FileIndex

        prefix = application.repo_prefix
        fi_result = await self.session.execute(
            select(FileIndex.path, FileIndex.content).where(
                FileIndex.path.startswith(prefix),
            ).order_by(FileIndex.path)
        )

        files_data: list[dict] = []
        for row in fi_result.all():
            rel_path = row.path[len(prefix):]
            files_data.append({"path": rel_path, "source": row.content or ""})

        role_ids = await self.get_role_ids(application.id)

        return {
            "id": str(application.id),
            "name": application.name,
            "slug": application.slug,
            "description": application.description,
            "icon": application.icon,
            "organization_id": str(application.organization_id) if application.organization_id else None,
            "published_at": application.published_at.isoformat() if application.published_at else None,
            "created_at": application.created_at.isoformat() if application.created_at else None,
            "updated_at": application.updated_at.isoformat() if application.updated_at else None,
            "created_by": application.created_by,
            "is_published": application.is_published,
            "has_unpublished_changes": application.has_unpublished_changes,
            "access_level": application.access_level,
            "role_ids": [str(rid) for rid in role_ids],
            "files": files_data,
        }

    async def update_draft_files(
        self,
        application: Application,
        files_data: list[dict],
    ) -> None:
        """
        Replace all files in the app with the provided files via FileStorageService.

        Args:
            application: The application to update
            files_data: List of file dictionaries with 'path' and 'source'
        """
        from src.services.file_storage import FileStorageService

        file_storage = FileStorageService(self.session)
        prefix = application.repo_prefix

        # Delete existing files
        from src.models.orm.file_index import FileIndex
        existing_result = await self.session.execute(
            select(FileIndex.path).where(
                FileIndex.path.startswith(prefix),
            )
        )
        for (path,) in existing_result.all():
            await file_storage.delete_file(path)

        # Write new files
        for file_dict in files_data:
            full_path = f"{prefix}{file_dict['path']}"
            source = file_dict.get("source", "")
            await file_storage.write_file(
                path=full_path,
                content=source.encode("utf-8"),
                updated_by="system",
            )

    async def rollback_to_version(
        self,
        application: Application,
        version_id: UUID,  # noqa: ARG002
    ) -> None:
        """
        Rollback is no longer supported with the unified file storage model.
        Published snapshots are immutable point-in-time captures.
        """
        raise ValueError("Version rollback is not supported. Use published snapshots instead.")


# =============================================================================
# Helper functions
# =============================================================================


async def application_to_public(
    application: Application,
    repo: "ApplicationRepository",
) -> ApplicationPublic:
    """Convert Application ORM to ApplicationPublic with role_ids."""
    role_ids = await repo.get_role_ids(application.id)
    return ApplicationPublic(
        id=application.id,
        name=application.name,
        slug=application.slug,
        description=application.description,
        icon=application.icon,
        organization_id=application.organization_id,
        published_at=application.published_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
        created_by=application.created_by,
        is_published=application.is_published,
        has_unpublished_changes=application.has_unpublished_changes,
        access_level=application.access_level,
        role_ids=role_ids,
    )


async def get_application_or_404(
    ctx: Context,
    slug: str,
) -> Application:
    """Get application by slug with access control.

    Uses ApplicationRepository for cascade scoping and role-based access.
    Returns 404 for both not found and access denied to avoid leaking
    existence information.

    Returns:
        Application if found and accessible

    Raises:
        HTTPException 404 if not found or access denied
    """
    repo = ApplicationRepository(
        session=ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        is_superuser=ctx.user.is_platform_admin,
    )
    try:
        if ctx.user.is_platform_admin:
            # Slugs are globally unique — super admins can resolve across orgs
            app = await repo.get_by_slug_global(slug)
            if not app:
                raise AccessDeniedError(f"Application '{slug}' not found")
            return app
        return await repo.can_access(slug=slug)
    except AccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )


async def get_application_by_id_or_404(
    ctx: Context,
    app_id: UUID,
) -> Application:
    """Get application by UUID with access control.

    Uses ApplicationRepository for cascade scoping and role-based access.
    Returns 404 for both not found and access denied to avoid leaking
    existence information.

    Returns:
        Application if found and accessible

    Raises:
        HTTPException 404 if not found or access denied
    """
    repo = ApplicationRepository(
        session=ctx.db,
        org_id=ctx.org_id,
        user_id=ctx.user.user_id,
        is_superuser=ctx.user.is_platform_admin,
    )
    try:
        return await repo.can_access(id=app_id)
    except AccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.post(
    "",
    response_model=ApplicationPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create an application",
)
async def create_application(
    data: ApplicationCreate,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationPublic:
    """Create a new application."""
    # Use organization_id from request body if explicitly provided, else default to current org
    if "organization_id" in (data.model_fields_set or set()):
        target_org_id = data.organization_id
    else:
        target_org_id = ctx.org_id
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )

    try:
        application = await repo.create_application(data, created_by=user.email)
        return await application_to_public(application, repo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application with slug '{data.slug}' already exists",
        )


@router.get(
    "",
    response_model=ApplicationListResponse,
    summary="List applications",
)
async def list_applications(
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(
        default=None,
        description="Filter scope: 'global' for global only, org UUID for specific org.",
    ),
) -> ApplicationListResponse:
    """List all applications in the current scope."""
    try:
        filter_type, filter_org = resolve_org_filter(ctx.user, scope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    repo = ApplicationRepository(
        ctx.db,
        filter_org,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )

    # Superusers use list_all_in_scope (respects filter_type, no role checks)
    # Regular users use list_applications (cascade scope + role checks)
    if user.is_platform_admin:
        applications = await repo.list_all_in_scope(filter_type)
    else:
        applications = await repo.list_applications()

    # Convert each application with role_ids
    public_apps = [await application_to_public(app, repo) for app in applications]

    return ApplicationListResponse(
        applications=public_apps,
        total=len(applications),
    )


@router.get(
    "/{slug}",
    response_model=ApplicationPublic,
    summary="Get application metadata",
)
async def get_application(
    slug: str,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationPublic:
    """Get application metadata by slug (globally unique)."""
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_or_404(ctx, slug)
    return await application_to_public(application, repo)


@router.patch(
    "/{app_id}",
    response_model=ApplicationPublic,
    summary="Update application metadata",
)
async def update_application(
    app_id: UUID,
    data: ApplicationUpdate,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationPublic:
    """Update application metadata and access control by ID."""
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )

    try:
        application = await repo.update_application(
            app_id,
            data,
            updated_by=ctx.user.email,
            is_platform_admin=user.is_platform_admin,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application with slug '{data.slug}' already exists",
        )

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(application.id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="app",
        entity_id=str(application.id),
    )

    return await application_to_public(application, repo)


@router.delete(
    "/{app_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete application",
)
async def delete_application(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
) -> None:
    """Delete an application by ID."""
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    success = await repo.delete_application(app_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )


# =============================================================================
# Draft Endpoints
# =============================================================================


@router.get(
    "/{app_id}/draft",
    response_model=ApplicationDefinition,
    summary="Get draft definition",
)
async def get_draft(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationDefinition:
    """
    Get the current draft definition.

    Returns the draft files serialized as JSON.
    """
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    app = await get_application_by_id_or_404(ctx, app_id)
    export_data = await repo.export_application(app)
    return ApplicationDefinition(
        definition=export_data,
        version=0,  # Legacy field - deprecated
        is_live=False,
    )


@router.put(
    "/{app_id}/draft",
    response_model=ApplicationDefinition,
    summary="Save draft definition",
)
async def save_draft(
    app_id: UUID,
    data: ApplicationDraftSave,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationDefinition:
    """
    Save a new draft definition.

    Replaces all existing draft files with the provided definition.
    """
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    app = await get_application_by_id_or_404(ctx, app_id)

    # Extract files from definition and update
    files_data = data.definition.get("files", [])
    await repo.update_draft_files(app, files_data)
    await ctx.db.flush()
    await ctx.db.refresh(app)
    return ApplicationDefinition(
        definition=data.definition,
        version=0,  # Legacy field - deprecated
        is_live=False,
    )


# =============================================================================
# Publish Endpoint
# =============================================================================


@router.post(
    "/{app_id}/publish",
    response_model=ApplicationPublic,
    summary="Publish draft to live",
)
async def publish_application(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
    data: ApplicationPublishRequest | None = None,
) -> ApplicationPublic:
    """
    Publish the draft to live.

    Copies all draft files to a new live version.
    """
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )

    try:
        message = data.message if data else None
        application = await repo.publish(app_id, user.email, message)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application '{app_id}' not found",
            )

        # Emit event for real-time updates
        await publish_app_published(
            app_id=str(app_id),
            user_id=str(user.user_id),
            user_name=user.name or user.email or "Unknown",
            new_version_id=application.published_at.isoformat() if application.published_at else "",
        )

        return await application_to_public(application, repo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Validate Endpoint
# =============================================================================


@router.post(
    "/{app_id}/validate",
    response_model=AppValidationResponse,
    summary="Validate application files",
)
async def validate_application(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
) -> AppValidationResponse:
    """
    Run static analysis on application files.

    Checks for: unknown components, workflow ID format/existence,
    bad imports, forbidden patterns, required file structure.
    """
    from src.models.orm.file_index import FileIndex
    from src.models.orm.workflows import Workflow

    app = await get_application_by_id_or_404(ctx, app_id)
    prefix = app.repo_prefix

    # Get all app files
    result = await ctx.db.execute(
        select(FileIndex.path, FileIndex.content).where(
            FileIndex.path.startswith(prefix)
        )
    )
    files = {row.path: row.content or "" for row in result.all()}

    errors: list[AppValidationIssue] = []
    warnings: list[AppValidationIssue] = []

    # Check required file structure
    layout_path = f"{prefix}_layout.tsx"
    index_path = f"{prefix}pages/index.tsx"

    if layout_path not in files:
        errors.append(AppValidationIssue(
            severity="error",
            file="_layout.tsx",
            message="Missing required _layout.tsx file",
        ))

    if index_path not in files:
        warnings.append(AppValidationIssue(
            severity="warning",
            file="pages/index.tsx",
            message="Missing pages/index.tsx (home page)",
        ))

    # Get declared dependencies and track referenced ones
    declared_deps = app.dependencies or {}
    referenced_deps: set[str] = set()

    # Build list of component files from the file index for cross-referencing
    component_files = {
        p[len(prefix) + len("components/"):].replace(".tsx", "").replace(".ts", "")
        for p in files
        if p.startswith(f"{prefix}components/") and (p.endswith(".tsx") or p.endswith(".ts"))
    }

    # Collect all compilable TSX/TS files
    compilable_files = []
    for full_path, content in files.items():
        rel_path = full_path[len(prefix):]
        if rel_path.endswith(".tsx") or rel_path.endswith(".ts"):
            compilable_files.append({"path": rel_path, "source": content, "full_path": full_path})

    # Compile all files via the server-side compiler
    if compilable_files:
        from src.services.app_compiler import AppCompilerService

        compiler = AppCompilerService()
        compile_inputs = [{"path": f["path"], "source": f["source"]} for f in compilable_files]
        compile_results = await compiler.compile_batch(compile_inputs)

        for comp_file, comp_result in zip(compilable_files, compile_results):
            rel_path = comp_file["path"]
            content = comp_file["source"]

            # Report compilation errors
            if not comp_result.success:
                errors.append(AppValidationIssue(
                    severity="error",
                    file=rel_path,
                    message=f"Compilation failed: {comp_result.error}",
                ))

            # Check for missing default export in pages and components
            if comp_result.success and comp_result.default_export is None:
                if rel_path.startswith("pages/") or rel_path.startswith("components/"):
                    errors.append(AppValidationIssue(
                        severity="error",
                        file=rel_path,
                        message="Missing default export. Pages and components must have a default export (e.g., export default function MyComponent() { ... })",
                    ))

            # Check _layout.tsx uses <Outlet /> not {children}
            if rel_path == "_layout.tsx":
                if "{children}" in content and "Outlet" not in content:
                    errors.append(AppValidationIssue(
                        severity="error",
                        file=rel_path,
                        message="Layout uses {children} but should use <Outlet /> for page routing. Replace {children} with <Outlet />.",
                    ))

            # Check for undefined bifrost imports
            bifrost_imports = re.findall(
                r'import\s+\{([^}]+)\}\s+from\s+["\']bifrost["\']',
                content,
            )
            for match in bifrost_imports:
                names = [n.strip().split(" as ")[0].strip() for n in match.split(",")]
                for name in names:
                    if name and name not in KNOWN_BIFROST_EXPORTS:
                        # PascalCase names could be Lucide icons — warn, don't error
                        if name[0].isupper():
                            warnings.append(AppValidationIssue(
                                severity="warning",
                                file=rel_path,
                                message=f"'{name}' is not a known bifrost export (could be a Lucide icon)",
                            ))
                        else:
                            errors.append(AppValidationIssue(
                                severity="error",
                                file=rel_path,
                                message=f"'{name}' is not available from 'bifrost'. Check spelling or see platform docs for available exports.",
                            ))

            # Check for forbidden patterns
            forbidden = [
                (r'\brequire\s*\(', "require() is not allowed"),
                (r'\bmodule\.exports\b', "module.exports is not allowed"),
            ]
            for pattern, msg in forbidden:
                for i, line in enumerate(content.split("\n"), 1):
                    if re.search(pattern, line) and not line.strip().startswith("//"):
                        errors.append(AppValidationIssue(
                            severity="error",
                            file=rel_path,
                            message=msg,
                            line=i,
                        ))

            # Extract external import references (non-bifrost) for dependency checking
            for match in re.finditer(
                r'^\s*import\s+.*?\s+from\s+["\']([^"\']+)["\']\s*;?\s*$',
                content,
                re.MULTILINE,
            ):
                pkg = match.group(1)
                if pkg != "bifrost":
                    referenced_deps.add(pkg)

            # Check for unknown components (JSX tags starting with uppercase)
            component_refs = set(re.findall(r'<([A-Z][a-zA-Z0-9]*)', content))
            for comp_name in component_refs:
                if comp_name not in KNOWN_APP_COMPONENTS and comp_name not in component_files:
                    # Could be a lucide icon (hundreds of them) or user-defined component
                    # Only warn, don't error
                    warnings.append(AppValidationIssue(
                        severity="warning",
                        file=rel_path,
                        message=f"Unknown component <{comp_name}> - verify it exists in the runtime",
                    ))

            # Check workflow IDs
            # Match useWorkflowQuery("...") and useWorkflowMutation("...")
            workflow_refs = re.findall(
                r'(?:useWorkflowQuery|useWorkflowMutation)\s*\(\s*["\']([^"\']+)["\']',
                content,
            )
            for wf_ref in workflow_refs:
                # Check UUID format
                try:
                    wf_uuid = UUID(wf_ref)
                except ValueError:
                    errors.append(AppValidationIssue(
                        severity="error",
                        file=rel_path,
                        message=f"Workflow reference '{wf_ref}' is not a valid UUID. Use workflow IDs, not names.",
                    ))
                    continue

                # Check workflow exists
                wf_result = await ctx.db.execute(
                    select(Workflow.id).where(
                        Workflow.id == wf_uuid,
                        Workflow.is_active == True,  # noqa: E712
                    )
                )
                if not wf_result.scalar_one_or_none():
                    errors.append(AppValidationIssue(
                        severity="error",
                        file=rel_path,
                        message=f"Workflow '{wf_ref}' not found or inactive",
                    ))

    # Check for missing/unused dependencies
    for dep in referenced_deps:
        if dep not in declared_deps:
            errors.append(AppValidationIssue(
                severity="error",
                file="dependencies",
                message=f"Missing dependency: '{dep}' is imported but not declared in app dependencies",
            ))
    for dep in declared_deps:
        if dep not in referenced_deps:
            warnings.append(AppValidationIssue(
                severity="warning",
                file="dependencies",
                message=f"Unused dependency: '{dep}' is declared but not imported by any file",
            ))

    return AppValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# =============================================================================
# Export/Import Endpoints
# =============================================================================


@router.get(
    "/{app_id}/export",
    response_model=ApplicationPublic,
    summary="Export application to JSON",
)
async def export_application(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
    version_id: UUID | None = Query(default=None, description="Version UUID to export (defaults to draft)"),
) -> ApplicationPublic:
    """
    Export full application to JSON for GitHub sync/portability.

    Returns the complete application structure including all files.
    Pass version_id to export a specific version, or omit to export draft.
    """
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_by_id_or_404(ctx, app_id)
    export_data = await repo.export_application(application, version_id)

    return ApplicationPublic.model_validate(export_data)


# =============================================================================
# Rollback Endpoint
# =============================================================================


@router.post(
    "/{app_id}/rollback",
    response_model=ApplicationPublic,
    summary="Rollback to a previous version",
)
async def rollback_application(
    app_id: UUID,
    data: ApplicationRollbackRequest,
    ctx: Context,
    user: CurrentUser,
) -> ApplicationPublic:
    """
    Rollback the application's active (live) version to a previous version.

    Sets the specified version as the new active version.
    The draft version remains unchanged.
    """
    repo = ApplicationRepository(
        ctx.db,
        ctx.org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_by_id_or_404(ctx, app_id)

    try:
        await repo.rollback_to_version(application, data.version_id)
        await ctx.db.flush()
        await ctx.db.refresh(application)
        logger.info(f"Rolled back application {app_id} to version {data.version_id}")
        return await application_to_public(application, repo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
