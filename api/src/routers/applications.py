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
from src.models.orm.applications import AppFile, AppVersion, Application
from src.core.exceptions import AccessDeniedError
from src.repositories.org_scoped import OrgScopedRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["Applications"])


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

        # Scaffold initial files for new apps
        await self._scaffold_code_files(draft_version.id)

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

        # Handle navigation updates
        if data.navigation is not None:
            application.navigation = data.navigation.model_dump(exclude_none=True)

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

        Creates a new version from the draft and sets it as the active version.
        """
        application = await self.get_by_id(app_id)
        if not application:
            return None

        if not application.draft_version_id:
            raise ValueError("Application has no draft version to publish")

        # Verify there are files in the draft version
        from sqlalchemy.orm import selectinload
        draft_version_query = (
            select(AppVersion)
            .where(AppVersion.id == application.draft_version_id)
            .options(selectinload(AppVersion.files))
        )
        result = await self.session.execute(draft_version_query)
        draft_version = result.scalar_one_or_none()

        if not draft_version or not draft_version.files:
            raise ValueError("No files in draft version to publish")

        # Create new version with files copied from draft
        await self._publish_version(application, draft_version)

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(
            f"Published application {app_id} with version {application.active_version_id} "
            f"by user {published_by}"
        )
        return application

    async def _scaffold_code_files(self, version_id: UUID) -> None:
        """Create initial scaffold files for a code engine app.

        Creates:
        - _layout: Root layout wrapper
        - pages/index: Home page
        """
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
            app_version_id=version_id,
            path="_layout.tsx",
            source=layout_source,
        )
        self.session.add(layout_file)

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
            app_version_id=version_id,
            path="pages/index.tsx",
            source=index_source,
        )
        self.session.add(index_file)

        await self.session.flush()
        logger.info(f"Scaffolded initial code files for version {version_id}")

    async def _publish_version(
        self,
        application: Application,
        draft_version: AppVersion,
    ) -> None:
        """
        Create a new published version by copying files from the draft version.

        Sets the new version as the active version and updates published_at.
        """
        from datetime import datetime

        # Create new version for the published copy
        new_version = AppVersion(application_id=application.id)
        self.session.add(new_version)
        await self.session.flush()

        # Copy all files from draft to new version
        for draft_file in draft_version.files:
            new_file = AppFile(
                app_version_id=new_version.id,
                path=draft_file.path,
                source=draft_file.source,
                compiled=draft_file.compiled,
            )
            self.session.add(new_file)

        # Update application to point to new active version
        application.active_version_id = new_version.id
        application.published_at = datetime.utcnow()

        await self.session.flush()

    async def get_files_for_version(
        self,
        version_id: UUID,
    ) -> list[AppFile]:
        """Get all files for a specific version."""
        from sqlalchemy.orm import selectinload

        version_query = (
            select(AppVersion)
            .where(AppVersion.id == version_id)
            .options(selectinload(AppVersion.files))
        )
        result = await self.session.execute(version_query)
        version = result.scalar_one_or_none()

        if not version:
            return []
        return list(version.files)

    async def export_application(
        self,
        application: Application,
        version_id: UUID | None = None,
    ) -> dict:
        """
        Export application data for API response or GitHub sync.

        Returns a dictionary with application metadata and files.
        """
        # Use draft version if no specific version requested
        target_version_id = version_id or application.draft_version_id
        files_data: list[dict] = []

        if target_version_id:
            files = await self.get_files_for_version(target_version_id)
            for file in sorted(files, key=lambda f: f.path):
                file_dict: dict = {"path": file.path, "source": file.source}
                if file.compiled:
                    file_dict["compiled"] = file.compiled
                files_data.append(file_dict)

        role_ids = await self.get_role_ids(application.id)

        return {
            "id": str(application.id),
            "name": application.name,
            "slug": application.slug,
            "description": application.description,
            "icon": application.icon,
            "organization_id": str(application.organization_id) if application.organization_id else None,
            "active_version_id": str(application.active_version_id) if application.active_version_id else None,
            "draft_version_id": str(application.draft_version_id) if application.draft_version_id else None,
            "published_at": application.published_at.isoformat() if application.published_at else None,
            "created_at": application.created_at.isoformat() if application.created_at else None,
            "updated_at": application.updated_at.isoformat() if application.updated_at else None,
            "created_by": application.created_by,
            "is_published": application.is_published,
            "has_unpublished_changes": application.has_unpublished_changes,
            "access_level": application.access_level,
            "role_ids": [str(rid) for rid in role_ids],
            "navigation": application.navigation,
            "files": files_data,
        }

    async def update_draft_files(
        self,
        application: Application,
        files_data: list[dict],
    ) -> None:
        """
        Replace all files in the draft version with the provided files.

        Args:
            application: The application to update
            files_data: List of file dictionaries with 'path', 'source', and optional 'compiled'
        """
        if not application.draft_version_id:
            raise ValueError("Application has no draft version")

        # Delete existing files
        from sqlalchemy import delete as sql_delete
        await self.session.execute(
            sql_delete(AppFile).where(AppFile.app_version_id == application.draft_version_id)
        )

        # Create new files
        for file_dict in files_data:
            new_file = AppFile(
                app_version_id=application.draft_version_id,
                path=file_dict["path"],
                source=file_dict["source"],
                compiled=file_dict.get("compiled"),
            )
            self.session.add(new_file)

        await self.session.flush()

    async def rollback_to_version(
        self,
        application: Application,
        version_id: UUID,
    ) -> None:
        """
        Rollback the application's active version to a previous version.

        Validates that the version belongs to this application.
        """
        # Verify version exists and belongs to this application
        version_query = select(AppVersion).where(
            AppVersion.id == version_id,
            AppVersion.application_id == application.id,
        )
        result = await self.session.execute(version_query)
        version = result.scalar_one_or_none()

        if not version:
            raise ValueError(f"Version {version_id} not found for this application")

        # Cannot rollback to draft version
        if version_id == application.draft_version_id:
            raise ValueError("Cannot rollback to draft version")

        # Update active version
        application.active_version_id = version_id
        await self.session.flush()


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
    export_data = await repo.export_application(app, version_id=app.draft_version_id)
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
            new_version_id=str(application.active_version_id) if application.active_version_id else "",
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
