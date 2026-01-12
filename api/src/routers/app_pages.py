"""
App Pages Router

CRUD operations for application pages.
Pages are children of applications and contain components.

Endpoints use UUID for internal APIs (not slug).
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status
from sqlalchemy import select

from src.core.auth import Context, CurrentUser
from src.models.contracts.applications import (
    AppPageCreate,
    AppPageListResponse,
    AppPageResponse,
    AppPageSummary,
    AppPageUpdate,
)
from src.models.contracts.app_components import PageDefinition
from src.core.pubsub import publish_app_draft_update
from src.models.orm.applications import AppPage, Application
from src.services.app_builder_service import AppBuilderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/applications/{app_id}/pages", tags=["App Pages"])


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

    # Check org access (org_id matches user org or app is global)
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


def page_to_summary(page: AppPage) -> AppPageSummary:
    """Convert ORM model to summary response."""
    return AppPageSummary(
        id=page.id,
        page_id=page.page_id,
        title=page.title,
        path=page.path,
        version_id=page.version_id,
        page_order=page.page_order,
        permission=page.permission,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def page_to_response(page: AppPage) -> AppPageResponse:
    """Convert ORM model to full response."""
    return AppPageResponse(
        id=page.id,
        page_id=page.page_id,
        title=page.title,
        path=page.path,
        version_id=page.version_id,
        page_order=page.page_order,
        permission=page.permission,
        created_at=page.created_at,
        updated_at=page.updated_at,
        application_id=page.application_id,
        data_sources=page.data_sources,
        variables=page.variables,
        launch_workflow_id=page.launch_workflow_id,
        launch_workflow_params=page.launch_workflow_params,
        launch_workflow_data_source_id=page.launch_workflow_data_source_id,
        root_layout_type=page.root_layout_type,
        root_layout_config=page.root_layout_config,
    )


# =============================================================================
# Page CRUD Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AppPageListResponse,
    summary="List pages",
)
async def list_pages(
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
    version_id: UUID | None = Query(default=None, description="Version UUID (defaults to draft)"),
) -> AppPageListResponse:
    """List all pages for an application (summaries only).

    Requires version_id to specify which version of pages to list.
    Defaults to app's draft_version_id if not provided.
    """
    # Verify app access
    app = await get_application_or_404(ctx, app_id)

    # Use draft_version_id if version_id not specified
    effective_version_id = version_id or app.draft_version_id

    query = (
        select(AppPage)
        .where(
            AppPage.application_id == app_id,
            AppPage.version_id == effective_version_id,
        )
        .order_by(AppPage.page_order)
    )
    result = await ctx.db.execute(query)
    pages = list(result.scalars().all())

    return AppPageListResponse(
        pages=[page_to_summary(p) for p in pages],
        total=len(pages),
    )


@router.get(
    "/{page_id}",
    response_model=PageDefinition,
    summary="Get page definition",
)
async def get_page(
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
    version_id: UUID | None = Query(default=None, description="Version UUID (defaults to draft)"),
) -> PageDefinition:
    """
    Get a page with its full layout tree.

    Requires version_id to specify which version of the page to get.
    Defaults to app's draft_version_id if not provided.

    Returns a PageDefinition with nested layout structure that matches
    the frontend TypeScript PageDefinition interface exactly.
    The response is serialized to camelCase JSON.
    """
    # Verify app access
    app = await get_application_or_404(ctx, app_id)

    # Use draft_version_id if version_id not specified
    effective_version_id = version_id or app.draft_version_id

    service = AppBuilderService(ctx.db)
    page_def = await service.get_page_definition(app_id, page_id, version_id=effective_version_id)

    if not page_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page '{page_id}' not found",
        )

    return page_def


@router.post(
    "",
    response_model=AppPageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create page",
)
async def create_page(
    data: AppPageCreate,
    app_id: UUID = Path(..., description="Application UUID"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppPageResponse:
    """Create a new page with optional layout."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)

    if not app.draft_version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application has no draft version",
        )

    # Check for duplicate page_id in draft version
    existing_query = select(AppPage).where(
        AppPage.application_id == app_id,
        AppPage.page_id == data.page_id,
        AppPage.version_id == app.draft_version_id,
    )
    existing = await ctx.db.execute(existing_query)
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Page with ID '{data.page_id}' already exists",
        )

    # Build initial layout from root_layout_type if no explicit layout provided
    layout = {
        "type": data.root_layout_type,
        **data.root_layout_config,
        "children": [],
    }

    service = AppBuilderService(ctx.db)
    page = await service.create_page_with_layout(
        application_id=app_id,
        page_id=data.page_id,
        title=data.title,
        path=data.path,
        layout=layout,
        version_id=app.draft_version_id,
        data_sources=data.data_sources,
        variables=data.variables,
        launch_workflow_id=data.launch_workflow_id,
        launch_workflow_params=data.launch_workflow_params,
        permission=data.permission,
        page_order=data.page_order,
    )

    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="page",
        entity_id=data.page_id,
    )

    logger.info(f"Created page '{data.page_id}' in app {app_id}")
    return page_to_response(page)


@router.patch(
    "/{page_id}",
    response_model=AppPageResponse,
    summary="Update page metadata",
)
async def update_page(
    data: AppPageUpdate,
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppPageResponse:
    """Update page metadata (not components)."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    # Apply updates
    if data.title is not None:
        page.title = data.title
    if data.path is not None:
        page.path = data.path
    if data.data_sources is not None:
        page.data_sources = data.data_sources
    if data.variables is not None:
        page.variables = data.variables
    if data.launch_workflow_id is not None:
        page.launch_workflow_id = data.launch_workflow_id
    if data.launch_workflow_params is not None:
        page.launch_workflow_params = data.launch_workflow_params
    if data.launch_workflow_data_source_id is not None:
        page.launch_workflow_data_source_id = data.launch_workflow_data_source_id
    if data.permission is not None:
        page.permission = data.permission
    if data.page_order is not None:
        page.page_order = data.page_order
    if data.root_layout_type is not None:
        page.root_layout_type = data.root_layout_type
    if data.root_layout_config is not None:
        page.root_layout_config = data.root_layout_config

    await ctx.db.flush()
    await ctx.db.refresh(page)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="page",
        entity_id=page_id,
    )

    logger.info(f"Updated page '{page_id}' in app {app_id}")
    return page_to_response(page)


@router.delete(
    "/{page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete page",
)
async def delete_page(
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> None:
    """Delete a page and all its components."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    # Delete page (cascade deletes components)
    await ctx.db.delete(page)

    await ctx.db.flush()

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="page",
        entity_id=page_id,
    )

    logger.info(f"Deleted page '{page_id}' from app {app_id}")


# =============================================================================
# Layout Endpoints
# =============================================================================


@router.put(
    "/{page_id}/layout",
    response_model=AppPageResponse,
    summary="Replace page layout",
)
async def replace_page_layout(
    layout: dict[str, Any],
    app_id: UUID = Path(..., description="Application UUID"),
    page_id: str = Path(..., description="Page ID (string identifier)"),
    ctx: Context = None,
    user: CurrentUser = None,
) -> AppPageResponse:
    """Replace the entire layout of a page (all components)."""
    # Verify app access
    app = await get_application_or_404(ctx, app_id)
    page = await get_draft_page_or_404(ctx, app, page_id)

    service = AppBuilderService(ctx.db)
    await service.update_page_layout(page, layout)

    await ctx.db.flush()
    await ctx.db.refresh(page)

    # Emit event for real-time updates
    await publish_app_draft_update(
        app_id=str(app_id),
        user_id=str(user.user_id),
        user_name=user.name or user.email or "Unknown",
        entity_type="page",
        entity_id=page_id,
    )

    logger.info(f"Replaced layout for page '{page_id}' in app {app_id}")
    return page_to_response(page)
