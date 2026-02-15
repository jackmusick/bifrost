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

import io
import logging
import re
import tarfile
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.core.org_filter import OrgFilterType, resolve_org_filter, resolve_target_org
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
    "Outlet", "Link", "NavLink", "Navigate",
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

    async def get_by_slug(self, slug: str) -> Application | None:
        """
        Get application by slug with cascade scoping and role-based access check.

        Prioritizes org-specific over global to avoid MultipleResultsFound
        when the same slug exists in both scopes.

        Args:
            slug: Application slug

        Returns:
            Application if found and accessible, None otherwise
        """
        # Build query filtering by slug
        query = select(self.model).where(self.model.slug == slug)

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

    async def get_by_slug_strict(self, slug: str) -> Application | None:
        """Get application by slug strictly in current org scope (no fallback)."""
        query = select(self.model).where(
            self.model.slug == slug,
            self.model.organization_id == self.org_id,
        )
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
        existing = await self.get_by_slug_strict(data.slug)
        if existing:
            raise ValueError(f"Application with slug '{data.slug}' already exists")

        application = Application(
            name=data.name,
            slug=data.slug,
            description=data.description,
            icon=data.icon,
            organization_id=self.org_id,
            created_by=created_by,
            app_type=data.app_type,
            access_level=data.access_level,
        )
        self.session.add(application)
        await self.session.flush()

        # Scaffold initial files via FileStorageService (runtime apps only)
        if data.app_type != "static":
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
            existing = await self.get_by_slug_strict(data.slug)
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
            str(app_id), f"apps/{application.slug}/"
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

        prefix = f"apps/{application.slug}/"
        fi_result = await self.session.execute(
            select(FileIndex.path, FileIndex.content).where(
                FileIndex.path.startswith(prefix),
                ~FileIndex.path.endswith("/app.json"),
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
            "app_type": application.app_type,
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
        prefix = f"apps/{application.slug}/"

        # Delete existing files (except app.json)
        from src.models.orm.file_index import FileIndex
        existing_result = await self.session.execute(
            select(FileIndex.path).where(
                FileIndex.path.startswith(prefix),
                ~FileIndex.path.endswith("/app.json"),
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
        app_type=application.app_type,
        published_at=application.published_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
        created_by=application.created_by,
        is_published=application.is_published,
        has_unpublished_changes=application.has_unpublished_changes,
        access_level=application.access_level,
        role_ids=role_ids,
    )


def _resolve_target_org_safe(ctx: Context, scope: str | None) -> UUID | None:
    """Resolve target org ID with proper auth check, raising HTTPException on error."""
    try:
        return resolve_target_org(ctx.user, scope, ctx.org_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


async def get_application_or_404(
    ctx: Context,
    slug: str,
    scope: str | None = None,  # noqa: ARG001 - kept for API compatibility
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
        return await repo.can_access(slug=slug)
    except AccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )


async def get_application_by_id_or_404(
    ctx: Context,
    app_id: UUID,
    scope: str | None = None,  # noqa: ARG001 - kept for API compatibility
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
    scope: str | None = Query(
        default=None,
        description="Target scope: 'global' or org UUID. Defaults to current org.",
    ),
) -> ApplicationPublic:
    """Create a new application."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
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
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """Get application metadata by slug."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_or_404(ctx, slug, scope)
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
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """
    Get the current draft definition.

    Returns the draft files serialized as JSON.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    app = await get_application_by_id_or_404(ctx, app_id, scope)
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
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """
    Save a new draft definition.

    Replaces all existing draft files with the provided definition.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    app = await get_application_by_id_or_404(ctx, app_id, scope)

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
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """
    Publish the draft to live.

    Copies all draft files to a new live version.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
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
# Deploy Endpoint (Static Apps)
# =============================================================================


class DeployResponse(BaseModel):
    """Response from deploying a static app bundle."""
    files_uploaded: int
    mode: str  # "preview" or "live"


def _extract_bundle(content: bytes) -> dict[str, bytes]:
    """Extract and validate a .tar.gz app bundle.

    Returns normalized {relative_path: bytes} mapping.
    Raises HTTPException on invalid input.
    """
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty upload",
        )

    try:
        tar = tarfile.open(fileobj=io.BytesIO(content), mode="r:gz")
    except tarfile.TarError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tarball. Expected a .tar.gz archive.",
        )

    files: dict[str, bytes] = {}
    with tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Security: reject absolute paths and path traversal
            if member.name.startswith("/") or ".." in member.name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid path in archive: {member.name}",
                )
            f = tar.extractfile(member)
            if f:
                files[member.name] = f.read()

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive contains no files",
        )

    # Verify index.html exists (at root or inside a dist/ prefix)
    has_index = "index.html" in files or any(
        k.endswith("/index.html") or k == "dist/index.html" for k in files
    )
    if not has_index:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archive must contain an index.html file",
        )

    # Normalize paths: strip leading "dist/" prefix if present
    normalized: dict[str, bytes] = {}
    for path, data in files.items():
        clean = path.lstrip("/")
        if clean.startswith("dist/"):
            clean = clean[5:]
        normalized[clean] = data

    return normalized


@router.post(
    "/{app_id}/deploy",
    response_model=DeployResponse,
    summary="Deploy a static app bundle to preview",
)
async def deploy_static_app(
    app_id: UUID,
    ctx: Context,
    user: CurrentUser,
    bundle: UploadFile = File(..., description="Tarball (.tar.gz) of the built dist/ directory"),
) -> DeployResponse:
    """
    Upload a pre-built static app bundle to preview.

    Accepts a .tar.gz archive of the Vite build output (dist/ directory).
    The archive must contain an index.html at the root.

    Files go to **preview** storage — preview at /apps-v2/{slug}/preview/.
    Use POST /{app_id}/publish to copy preview → live.

    Only works for apps with app_type='static'.
    """
    application = await get_application_by_id_or_404(ctx, app_id)

    if application.app_type != "static":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deploy is only supported for static apps. This app has app_type='runtime'.",
        )

    raw = await bundle.read()
    normalized = _extract_bundle(raw)

    # Write files to S3 preview via AppStorageService
    from src.services.app_storage import AppStorageService
    app_storage = AppStorageService()

    for rel_path, data in normalized.items():
        await app_storage.write_preview_file(str(app_id), rel_path, data)

    logger.info(
        f"Deployed {len(normalized)} files to preview for static app {app_id} by {user.email}"
    )

    return DeployResponse(
        files_uploaded=len(normalized),
        mode="preview",
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
    prefix = f"apps/{app.slug}/"

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

    # Analyze each TSX/TS file
    for full_path, content in files.items():
        rel_path = full_path[len(prefix):]

        if not (rel_path.endswith(".tsx") or rel_path.endswith(".ts")):
            continue

        # Check for import statements (forbidden in app builder)
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            # Match import statements but not comments
            if re.match(r'^import\s+', stripped) and not stripped.startswith("//"):
                errors.append(AppValidationIssue(
                    severity="error",
                    file=rel_path,
                    message=f"Import statements are not allowed: {stripped[:80]}",
                    line=i,
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

        # Check for unknown components (JSX tags starting with uppercase)
        component_refs = set(re.findall(r'<([A-Z][a-zA-Z0-9]*)', content))
        for comp_name in component_refs:
            if comp_name not in KNOWN_APP_COMPONENTS:
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
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """
    Export full application to JSON for GitHub sync/portability.

    Returns the complete application structure including all files.
    Pass version_id to export a specific version, or omit to export draft.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_by_id_or_404(ctx, app_id, scope)
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
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """
    Rollback the application's active (live) version to a previous version.

    Sets the specified version as the new active version.
    The draft version remains unchanged.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(
        ctx.db,
        target_org_id,
        user_id=user.user_id,
        is_superuser=user.is_platform_admin,
    )
    application = await get_application_by_id_or_404(ctx, app_id, scope)

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
