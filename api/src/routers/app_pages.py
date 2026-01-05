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
    PageDefinition,
)
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


async def get_page_or_404(
    ctx: Context,
    app_id: UUID,
    page_id: str,
    is_draft: bool = True,
) -> AppPage:
    """Get page by app_id and page_id or raise 404."""
    query = select(AppPage).where(
        AppPage.application_id == app_id,
        AppPage.page_id == page_id,
        AppPage.is_draft == is_draft,
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
        is_draft=page.is_draft,
        version=page.version,
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
        is_draft=page.is_draft,
        version=page.version,
        page_order=page.page_order,
        permission=page.permission,
        created_at=page.created_at,
        updated_at=page.updated_at,
        application_id=page.application_id,
        data_sources=page.data_sources,
        variables=page.variables,
        launch_workflow_id=page.launch_workflow_id,
        launch_workflow_params=page.launch_workflow_params,
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
    is_draft: bool = Query(default=True, description="Get draft or live pages"),
) -> AppPageListResponse:
    """List all pages for an application (summaries only)."""
    # Verify app access
    await get_application_or_404(ctx, app_id)

    query = (
        select(AppPage)
        .where(
            AppPage.application_id == app_id,
            AppPage.is_draft == is_draft,
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
    is_draft: bool = Query(default=True, description="Get draft or live version"),
) -> PageDefinition:
    """
    Get a page with its full layout tree.

    Returns a PageDefinition with nested layout structure that matches
    the frontend TypeScript PageDefinition interface exactly.
    The response is serialized to camelCase JSON.
    """
    # Verify app access
    await get_application_or_404(ctx, app_id)

    service = AppBuilderService(ctx.db)
    page_def = await service.get_page_definition(app_id, page_id, is_draft)

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

    # Check for duplicate page_id
    existing_query = select(AppPage).where(
        AppPage.application_id == app_id,
        AppPage.page_id == data.page_id,
        AppPage.is_draft == True,  # noqa: E712
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
        is_draft=True,
        data_sources=data.data_sources,
        variables=data.variables,
        launch_workflow_id=data.launch_workflow_id,
        launch_workflow_params=data.launch_workflow_params,
        permission=data.permission,
        page_order=data.page_order,
    )

    # Increment app draft version
    app.draft_version += 1
    await ctx.db.flush()

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
    page = await get_page_or_404(ctx, app_id, page_id, is_draft=True)

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
    if data.permission is not None:
        page.permission = data.permission
    if data.page_order is not None:
        page.page_order = data.page_order
    if data.root_layout_type is not None:
        page.root_layout_type = data.root_layout_type
    if data.root_layout_config is not None:
        page.root_layout_config = data.root_layout_config

    page.version += 1
    app.draft_version += 1

    await ctx.db.flush()
    await ctx.db.refresh(page)

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
    page = await get_page_or_404(ctx, app_id, page_id, is_draft=True)

    # Delete page (cascade deletes components)
    await ctx.db.delete(page)
    app.draft_version += 1

    await ctx.db.flush()

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
    page = await get_page_or_404(ctx, app_id, page_id, is_draft=True)

    service = AppBuilderService(ctx.db)
    await service.update_page_layout(page, layout)

    app.draft_version += 1
    await ctx.db.flush()
    await ctx.db.refresh(page)

    logger.info(f"Replaced layout for page '{page_id}' in app {app_id}")
    return page_to_response(page)
