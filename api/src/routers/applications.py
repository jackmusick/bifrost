"""
Applications Router

Manage applications for the App Builder with draft/live versioning.
Uses OrgScopedRepository for standardized org scoping.

Applications follow the same scoping pattern as configs:
- organization_id = NULL: Global application (platform-wide)
- organization_id = UUID: Organization-scoped application

NOTE: This router handles app-level operations. Page and component operations
are in separate routers (app_pages.py, app_components.py).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
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
from src.models.orm.applications import AppComponent, AppPage, AppVersion, Application
from src.repositories.org_scoped import OrgScopedRepository
from src.services.app_builder_service import AppBuilderService
from src.services.authorization import AuthorizationService
from src.services.workflow_role_service import sync_app_roles_to_workflows

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["Applications"])


# =============================================================================
# Repository
# =============================================================================


class ApplicationRepository(OrgScopedRepository[Application]):
    """Repository for application operations."""

    model = Application

    async def list_applications(
        self,
        filter_type: OrgFilterType = OrgFilterType.ORG_PLUS_GLOBAL,
    ) -> list[Application]:
        """List applications with specified filter type."""
        query = select(self.model)
        query = self.apply_filter(query, filter_type, self.org_id)
        query = query.order_by(self.model.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Application | None:
        """Get application by slug with cascade scoping: org-specific > global.

        Uses get_one_cascade() to avoid MultipleResultsFound when the same
        slug exists in both org scope and global scope.
        """
        query = select(self.model).where(self.model.slug == slug)
        return await self.get_one_cascade(query)

    async def get_by_id(self, id: UUID) -> Application | None:
        """Get application by UUID with cascade scoping: org-specific > global.

        Uses get_one_cascade() to avoid MultipleResultsFound when the same
        ID exists in both org scope and global scope.
        """
        query = select(self.model).where(self.model.id == id)
        return await self.get_one_cascade(query)

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
            navigation={},
            permissions={},
            access_level=data.access_level,
        )
        self.session.add(application)
        await self.session.flush()

        # Create initial draft version
        draft_version = AppVersion(application_id=application.id)
        self.session.add(draft_version)
        await self.session.flush()

        # Link app to draft version
        application.draft_version_id = draft_version.id
        await self.session.flush()  # Ensure draft_version_id is persisted

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
        slug: str,
        data: ApplicationUpdate,
        updated_by: str,
        is_platform_admin: bool = False,
    ) -> Application | None:
        """Update application metadata and access control."""
        # Use cascade lookup to find global or org-scoped apps
        application = await self.get_by_slug(slug)
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

        logger.info(f"Updated application '{slug}'")
        return application

    async def delete_application(self, slug: str) -> bool:
        """Delete an application (cascade deletes pages and components)."""
        # Use cascade lookup to find global or org-scoped apps
        application = await self.get_by_slug(slug)
        if not application:
            return False

        await self.session.delete(application)
        await self.session.flush()

        logger.info(f"Deleted application '{slug}'")
        return True

    async def publish(
        self,
        app_id: UUID,
        published_by: str,
        message: str | None = None,
    ) -> Application | None:
        """
        Publish draft to live.

        Creates a new version from the draft and sets it as the active version.
        """
        application = await self.get_by_id(app_id)
        if not application:
            return None

        if not application.draft_version_id:
            raise ValueError("Application has no draft version to publish")

        # Verify there are pages in the draft version
        pages_query = select(AppPage).where(
            AppPage.application_id == app_id,
            AppPage.version_id == application.draft_version_id,
        )
        result = await self.session.execute(pages_query)
        draft_pages = list(result.scalars().all())

        if not draft_pages:
            raise ValueError("No draft pages to publish")

        # Use versioning-based publish
        service = AppBuilderService(self.session)
        new_version = await service.publish_with_versioning(application)

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(
            f"Published application {app_id} with version {new_version.id} "
            f"by user {published_by}"
        )
        return application


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
        active_version_id=application.active_version_id,
        draft_version_id=application.draft_version_id,
        published_at=application.published_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
        created_by=application.created_by,
        is_published=application.is_published,
        has_unpublished_changes=application.has_unpublished_changes,
        access_level=application.access_level,
        role_ids=role_ids,
        navigation=application.navigation,
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

    Fetches the application without org filtering, then uses AuthorizationService
    to check access. This allows platform admins to access any app regardless
    of their current org context.

    Returns:
        Application if found and accessible

    Raises:
        HTTPException 404 if not found
        HTTPException 403 if access denied
    """
    # Fetch app directly by slug without org filter
    query = select(Application).where(Application.slug == slug)
    result = await ctx.db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )

    # Check access using AuthorizationService
    auth = AuthorizationService(ctx.db, ctx)
    if not await auth.can_access_app(application):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this application",
        )

    return application


async def get_application_by_id_or_404(
    ctx: Context,
    app_id: UUID,
    scope: str | None = None,  # noqa: ARG001 - kept for API compatibility
) -> Application:
    """Get application by UUID with access control.

    Fetches the application without org filtering, then uses AuthorizationService
    to check access. This allows platform admins to access any app regardless
    of their current org context.

    Returns:
        Application if found and accessible

    Raises:
        HTTPException 404 if not found
        HTTPException 403 if access denied
    """
    # Fetch app directly by ID without org filter
    query = select(Application).where(Application.id == app_id)
    result = await ctx.db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )

    # Check access using AuthorizationService
    auth = AuthorizationService(ctx.db, ctx)
    if not await auth.can_access_app(application):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this application",
        )

    return application


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
    repo = ApplicationRepository(ctx.db, target_org_id)

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
    _user: CurrentUser,
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

    repo = ApplicationRepository(ctx.db, filter_org)
    applications = await repo.list_applications(filter_type)

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
    _user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """Get application metadata by slug."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(ctx.db, target_org_id)
    application = await get_application_or_404(ctx, slug, scope)
    return await application_to_public(application, repo)


@router.patch(
    "/{slug}",
    response_model=ApplicationPublic,
    summary="Update application metadata",
)
async def update_application(
    slug: str,
    data: ApplicationUpdate,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """Update application metadata and access control."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(ctx.db, target_org_id)
    application = await repo.update_application(
        slug,
        data,
        updated_by=ctx.user.email,
        is_platform_admin=user.is_platform_admin,
    )

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )

    # Sync app roles to workflows if role_ids changed
    # Only sync draft pages/components (live sync happens on publish)
    if data.role_ids is not None and application.draft_version_id:
        draft_pages_query = select(AppPage).where(
            AppPage.application_id == application.id,
            AppPage.version_id == application.draft_version_id,
        )
        draft_pages_result = await ctx.db.execute(draft_pages_query)
        draft_pages = list(draft_pages_result.scalars().all())

        draft_components: list[AppComponent] = []
        for page in draft_pages:
            comp_query = select(AppComponent).where(AppComponent.page_id == page.id)
            comp_result = await ctx.db.execute(comp_query)
            draft_components.extend(comp_result.scalars().all())

        await sync_app_roles_to_workflows(
            db=ctx.db,
            app_id=application.id,
            pages=draft_pages,
            components=draft_components,
            assigned_by=user.email,
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
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete application",
)
async def delete_application(
    slug: str,
    ctx: Context,
    _user: CurrentUser,
    scope: str | None = Query(default=None),
) -> None:
    """Delete an application."""
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(ctx.db, target_org_id)
    success = await repo.delete_application(slug)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
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
    _user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """
    Get the current draft definition.

    Returns the draft pages and components serialized as JSON.
    """
    app = await get_application_by_id_or_404(ctx, app_id, scope)
    service = AppBuilderService(ctx.db)
    export_data = await service.export_application(app, version_id=app.draft_version_id)
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
    _user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """
    Save a new draft definition.

    Replaces all existing draft pages and components with the provided definition.
    """
    app = await get_application_by_id_or_404(ctx, app_id, scope)
    service = AppBuilderService(ctx.db)
    await service.update_draft_definition(app, data.definition)
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

    Copies all draft pages and components to live versions.
    Also syncs workflow_roles for execution authorization.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(ctx.db, target_org_id)

    try:
        message = data.message if data else None
        application = await repo.publish(app_id, user.email, message)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application '{app_id}' not found",
            )

        # Sync workflow roles for the newly published live pages/components
        # Query pages by the active version (set by publish)
        if not application.active_version_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Publish completed but no active version found",
            )

        live_pages_query = select(AppPage).where(
            AppPage.application_id == app_id,
            AppPage.version_id == application.active_version_id,
        )
        live_pages_result = await ctx.db.execute(live_pages_query)
        live_pages = list(live_pages_result.scalars().all())

        # Get all components for these live pages (components belong to page by FK)
        live_components: list[AppComponent] = []
        for page in live_pages:
            comp_query = select(AppComponent).where(
                AppComponent.page_id == page.id,
            )
            comp_result = await ctx.db.execute(comp_query)
            live_components.extend(comp_result.scalars().all())

        # Sync app roles to referenced workflows - additive
        await sync_app_roles_to_workflows(
            db=ctx.db,
            app_id=app_id,
            pages=live_pages,
            components=live_components,
            assigned_by=user.email,
        )

        # Emit event for real-time updates
        await publish_app_published(
            app_id=str(app_id),
            user_id=str(user.user_id),
            user_name=user.name or user.email or "Unknown",
            new_version_id=str(application.active_version_id),
        )

        return await application_to_public(application, repo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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
    _user: CurrentUser,
    version_id: UUID | None = Query(default=None, description="Version UUID to export (defaults to draft)"),
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """
    Export full application to JSON for GitHub sync/portability.

    Returns the complete application structure including all pages and components.
    Pass version_id to export a specific version, or omit to export draft.

    The export format uses typed PageDefinition models and includes `_export`
    metadata for portable workflow refs resolution during import.
    """
    application = await get_application_by_id_or_404(ctx, app_id, scope)

    service = AppBuilderService(ctx.db)
    export_data = await service.export_application(application, version_id)

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
    _user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """
    Rollback the application's active (live) version to a previous version.

    Sets the specified version as the new active version.
    The draft version remains unchanged.
    """
    target_org_id = _resolve_target_org_safe(ctx, scope)
    repo = ApplicationRepository(ctx.db, target_org_id)
    application = await get_application_by_id_or_404(ctx, app_id, scope)

    service = AppBuilderService(ctx.db)

    try:
        await service.rollback_to_version(application, data.version_id)
        await ctx.db.flush()
        await ctx.db.refresh(application)
        logger.info(f"Rolled back application {app_id} to version {data.version_id}")
        return await application_to_public(application, repo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
