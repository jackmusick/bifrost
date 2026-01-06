"""
App Components Router

CRUD operations for individual application components.
Components are children of pages and can have parent components (tree structure).

Endpoints use UUID for internal APIs.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.core.pubsub import publish_app_draft_update
from src.models.contracts.applications import (
    AppComponentCreate,
    AppComponentListResponse,
    AppComponentMove,
    AppComponentResponse,
    AppComponentUpdate,
)
from src.models.orm.applications import AppPage, Application
from src.services.app_components_service import AppComponentsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/applications/{app_id}/pages/{page_id}/components",
    tags=["App Components"],
)


# =============================================================================
# Helper Functions
# =============================================================================


async def get_application_or_404(ctx: Context, app_id: UUID) -> Application:
    """Get application by UUID or raise 404."""
    query = select(Application).where(Application.id == app_id)
    result = await ctx.db.execute(query)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application '{app_id}' not found",
        )

    # Check org access
    if application.organization_id is not None and application.organization_id != ctx.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this application",
        )

    return application


async def get_draft_page_or_404(
    ctx: Context,
    app: Application,
    page_id: str,
) -> AppPage:
    """Get draft page by app and page_id or raise 404.

    Uses app's draft_version_id for version-based queries.
    """
    if not app.draft_version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application has no draft version",
        )

    query = select(AppPage).where(
        AppPage.application_id == app.id,
        AppPage.page_id == page_id,
        AppPage.version_id == app.draft_version_id,
    )
    result = await ctx.db.execute(query)
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page '{page_id}' not found",
        )

    return page


async def get_page_or_404(
    ctx: Context,
    app_id: UUID,
    page_id: str,
    version_id: UUID | None = None,
) -> AppPage:
    """Get page by app_id, page_id and version_id or raise 404.

    version_id is required for querying pages.
    """
    if version_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="version_id is required",
        )

    query = select(AppPage).where(
        AppPage.application_id == app_id,
        AppPage.page_id == page_id,
        AppPage.version_id == version_id,
    )
    result = await ctx.db.execute(query)
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page '{page_id}' not found",
        )

    return page


# =============================================================================
# Component CRUD Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AppComponentListResponse,
    summary="List components",
)
async def list_components(
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
    version_id: UUID | None = Query(default=None, description="Version ID to query components from"),
) -> AppComponentListResponse:
    """
    List all components for a page (summaries only).

    Returns component_id, type, parent_id, order - enough to decide what to fetch.

    Requires version_id to specify which version of the page to query.
    """
    # Verify app access
    app = await get_application_or_404(ctx, app_id)

    # Use draft_version_id if version_id not specified
    effective_version_id = version_id or app.draft_version_id
    page = await get_page_or_404(ctx, app_id, page_id, effective_version_id)

    service = AppComponentsService(ctx.db)
    components = await service.list_components(page.id)

    return AppComponentListResponse(
        components=components,
        total=len(components),
    )


@router.get(
    "/{component_id}",
    response_model=AppComponentResponse,
    summary="Get component",
)
async def get_component(
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    component_id: str = Path(..., description="Component ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
    version_id: UUID | None = Query(default=None, description="Version ID to query component from"),
) -> AppComponentResponse:
    """Get a single component with full props.

    Requires version_id to specify which version of the page to query.
    """
    # Verify app access
    app = await get_application_or_404(ctx, app_id)

    # Use draft_version_id if version_id not specified
    effective_version_id = version_id or app.draft_version_id
    page = await get_page_or_404(ctx, app_id, page_id, effective_version_id)

    service = AppComponentsService(ctx.db)
    component = await service.get_component(page.id, component_id)

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found",
        )

    return service.to_response(component)


@router.post(
    "",
    response_model=AppComponentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create component",
)
async def create_component(
    data: AppComponentCreate,
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppComponentResponse:
    """Create a new component."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    # Check for duplicate component_id
    service = AppComponentsService(ctx.db)
    existing = await service.get_component(page.id, data.component_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Component with ID '{data.component_id}' already exists",
        )

    try:
        component = await service.create_component(page.id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="component",
        entity_id=data.component_id,
        page_id=page_id,
    )

    logger.info(f"Created component '{data.component_id}' in page {page_id}")
    return service.to_response(component)


@router.patch(
    "/{component_id}",
    response_model=AppComponentResponse,
    summary="Update component",
)
async def update_component(
    data: AppComponentUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    component_id: str = Path(..., description="Component ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppComponentResponse:
    """Update component props and fields."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    service = AppComponentsService(ctx.db)
    component = await service.get_component(page.id, component_id)

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found",
        )

    component = await service.update_component(component, data)
    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="component",
        entity_id=component_id,
        page_id=page_id,
    )

    logger.info(f"Updated component '{component_id}' in page {page_id}")
    return service.to_response(component)


@router.delete(
    "/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete component",
)
async def delete_component(
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    component_id: str = Path(..., description="Component ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> None:
    """Delete a component and all its children."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    service = AppComponentsService(ctx.db)
    component = await service.get_component(page.id, component_id)

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found",
        )

    await service.delete_component(component)
    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="component",
        entity_id=component_id,
        page_id=page_id,
    )

    logger.info(f"Deleted component '{component_id}' from page {page_id}")


@router.post(
    "/{component_id}/move",
    response_model=AppComponentResponse,
    summary="Move component",
)
async def move_component(
    data: AppComponentMove,
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    component_id: str = Path(..., description="Component ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppComponentResponse:
    """Move a component to a new parent and/or position."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    service = AppComponentsService(ctx.db)
    component = await service.get_component(page.id, component_id)

    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component '{component_id}' not found",
        )

    try:
        component = await service.move_component(component, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="component",
        entity_id=component_id,
        page_id=page_id,
    )

    logger.info(f"Moved component '{component_id}' in page {page_id}")
    return service.to_response(component)
