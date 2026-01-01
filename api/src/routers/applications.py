"""
Applications Router

Manage applications for the App Builder with draft/live versioning.
Uses OrgScopedRepository for standardized org scoping.

Applications follow the same scoping pattern as configs:
- organization_id = NULL: Global application (platform-wide)
- organization_id = UUID: Organization-scoped application
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.core.org_filter import OrgFilterType, resolve_org_filter
from src.models.contracts.applications import (
    ApplicationCreate,
    ApplicationDefinition,
    ApplicationDraftSave,
    ApplicationListResponse,
    ApplicationPublic,
    ApplicationPublishRequest,
    ApplicationRollbackRequest,
    ApplicationUpdate,
    VersionHistoryEntry,
    VersionHistoryResponse,
)
from src.models.orm.applications import Application
from src.repositories.org_scoped import OrgScopedRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications", tags=["Applications"])

# Maximum number of versions to keep in history
MAX_VERSION_HISTORY = 10


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
        """Get application by slug with cascade scoping."""
        query = select(self.model).where(self.model.slug == slug)
        query = self.filter_cascade(query)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_slug_strict(self, slug: str) -> Application | None:
        """Get application by slug strictly in current org scope (no fallback)."""
        query = select(self.model).where(
            self.model.slug == slug,
            self.model.organization_id == self.org_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_application(
        self,
        data: ApplicationCreate,
        created_by: str,
    ) -> Application:
        """Create a new application."""
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
            live_version=0,
            draft_version=1,
            version_history=[],
        )
        self.session.add(application)
        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Created application '{data.slug}' in org {self.org_id}")
        return application

    async def update_application(
        self,
        slug: str,
        data: ApplicationUpdate,
    ) -> Application | None:
        """Update application metadata."""
        application = await self.get_by_slug_strict(slug)
        if not application:
            return None

        if data.name is not None:
            application.name = data.name
        if data.description is not None:
            application.description = data.description
        if data.icon is not None:
            application.icon = data.icon

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Updated application '{slug}'")
        return application

    async def delete_application(self, slug: str) -> bool:
        """Delete an application."""
        application = await self.get_by_slug_strict(slug)
        if not application:
            return False

        await self.session.delete(application)
        await self.session.flush()

        logger.info(f"Deleted application '{slug}'")
        return True

    async def save_draft(
        self,
        slug: str,
        definition: dict[str, Any],
    ) -> Application | None:
        """Save draft definition."""
        application = await self.get_by_slug_strict(slug)
        if not application:
            return None

        application.draft_definition = definition
        application.draft_version = application.draft_version + 1

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Saved draft for application '{slug}' (v{application.draft_version})")
        return application

    async def publish(
        self,
        slug: str,
        published_by: str,
        message: str | None = None,
    ) -> Application | None:
        """Publish draft to live."""
        application = await self.get_by_slug_strict(slug)
        if not application:
            return None

        if application.draft_definition is None:
            raise ValueError("No draft definition to publish")

        # Save current live version to history before overwriting
        if application.live_definition is not None and application.live_version > 0:
            history_entry = {
                "version": application.live_version,
                "definition": application.live_definition,
                "published_at": application.published_at.isoformat() if application.published_at else None,
                "published_by": None,  # We don't track who published previous versions
                "message": None,
            }
            # Prepend to history and trim to max size
            history = [history_entry] + (application.version_history or [])
            application.version_history = history[:MAX_VERSION_HISTORY]

        # Publish draft to live
        application.live_definition = application.draft_definition
        application.live_version = application.draft_version
        application.published_at = datetime.utcnow()

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Published application '{slug}' (v{application.live_version})")
        return application

    async def rollback(
        self,
        slug: str,
        version: int,
    ) -> Application | None:
        """Rollback to a previous version from history."""
        application = await self.get_by_slug_strict(slug)
        if not application:
            return None

        # Find version in history
        history = application.version_history or []
        target_entry = None
        for entry in history:
            if entry.get("version") == version:
                target_entry = entry
                break

        if not target_entry:
            raise ValueError(f"Version {version} not found in history")

        # Save current live version to history before overwriting
        if application.live_definition is not None and application.live_version > 0:
            history_entry = {
                "version": application.live_version,
                "definition": application.live_definition,
                "published_at": application.published_at.isoformat() if application.published_at else None,
                "published_by": None,
                "message": None,
            }
            # Prepend to history and trim to max size
            history = [history_entry] + history
            application.version_history = history[:MAX_VERSION_HISTORY]

        # Restore from history
        application.live_definition = target_entry["definition"]
        application.live_version = application.live_version + 1  # New version number
        application.published_at = datetime.utcnow()

        await self.session.flush()
        await self.session.refresh(application)

        logger.info(f"Rolled back application '{slug}' from v{version} to v{application.live_version}")
        return application


# =============================================================================
# Helper functions
# =============================================================================


def parse_scope(scope: str | None, default_org_id: UUID | None) -> UUID | None:
    """Parse scope parameter to target org ID."""
    if scope is None:
        return default_org_id
    if scope == "global":
        return None
    try:
        return UUID(scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scope: {scope}",
        )


async def get_application_or_404(
    ctx: Context,
    slug: str,
    scope: str | None = None,
) -> Application:
    """Get application by slug or raise 404."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)
    application = await repo.get_by_slug(slug)

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
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
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)

    try:
        application = await repo.create_application(data, created_by=user.email)
        return ApplicationPublic.model_validate(application)
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

    repo = ApplicationRepository(ctx.db, filter_org)
    applications = await repo.list_applications(filter_type)

    return ApplicationListResponse(
        applications=[ApplicationPublic.model_validate(a) for a in applications],
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
    application = await get_application_or_404(ctx, slug, scope)
    return ApplicationPublic.model_validate(application)


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
    """Update application metadata."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)
    application = await repo.update_application(slug, data)

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )

    return ApplicationPublic.model_validate(application)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete application",
)
async def delete_application(
    slug: str,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> None:
    """Delete an application."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)
    success = await repo.delete_application(slug)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )


# =============================================================================
# Definition Endpoints
# =============================================================================


@router.get(
    "/{slug}/definition",
    response_model=ApplicationDefinition,
    summary="Get live definition",
)
async def get_live_definition(
    slug: str,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """Get the live (published) definition of an application."""
    application = await get_application_or_404(ctx, slug, scope)

    return ApplicationDefinition(
        definition=application.live_definition,
        version=application.live_version,
        is_live=True,
    )


@router.get(
    "/{slug}/draft",
    response_model=ApplicationDefinition,
    summary="Get draft definition",
)
async def get_draft_definition(
    slug: str,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """Get the draft definition of an application."""
    application = await get_application_or_404(ctx, slug, scope)

    return ApplicationDefinition(
        definition=application.draft_definition,
        version=application.draft_version,
        is_live=False,
    )


@router.put(
    "/{slug}/draft",
    response_model=ApplicationDefinition,
    summary="Save draft definition",
)
async def save_draft(
    slug: str,
    data: ApplicationDraftSave,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationDefinition:
    """Save a new draft definition."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)

    application = await repo.save_draft(slug, data.definition)
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{slug}' not found",
        )

    return ApplicationDefinition(
        definition=application.draft_definition,
        version=application.draft_version,
        is_live=False,
    )


# =============================================================================
# Publish/Rollback Endpoints
# =============================================================================


@router.post(
    "/{slug}/publish",
    response_model=ApplicationPublic,
    summary="Publish draft to live",
)
async def publish_application(
    slug: str,
    ctx: Context,
    user: CurrentUser,
    data: ApplicationPublishRequest | None = None,
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """Publish the draft definition to live."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)

    try:
        message = data.message if data else None
        application = await repo.publish(slug, user.email, message)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application '{slug}' not found",
            )
        return ApplicationPublic.model_validate(application)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/{slug}/rollback",
    response_model=ApplicationPublic,
    summary="Rollback to previous version",
)
async def rollback_application(
    slug: str,
    data: ApplicationRollbackRequest,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> ApplicationPublic:
    """Rollback to a previous version from history."""
    target_org_id = parse_scope(scope, ctx.org_id)
    repo = ApplicationRepository(ctx.db, target_org_id)

    try:
        application = await repo.rollback(slug, data.version)
        if not application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application '{slug}' not found",
            )
        return ApplicationPublic.model_validate(application)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# Version History Endpoint
# =============================================================================


@router.get(
    "/{slug}/history",
    response_model=VersionHistoryResponse,
    summary="Get version history",
)
async def get_version_history(
    slug: str,
    ctx: Context,
    user: CurrentUser,
    scope: str | None = Query(default=None),
) -> VersionHistoryResponse:
    """Get the version history of an application."""
    application = await get_application_or_404(ctx, slug, scope)

    history_entries = []
    for entry in application.version_history or []:
        published_at = entry.get("published_at")
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)
        elif published_at is None:
            published_at = application.created_at  # Fallback

        history_entries.append(
            VersionHistoryEntry(
                version=entry.get("version", 0),
                definition=entry.get("definition", {}),
                published_at=published_at,
                published_by=entry.get("published_by"),
                message=entry.get("message"),
            )
        )

    return VersionHistoryResponse(
        history=history_entries,
        current_live_version=application.live_version,
        current_draft_version=application.draft_version,
    )
