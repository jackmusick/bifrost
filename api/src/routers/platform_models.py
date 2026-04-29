"""
Platform Models Router

Read-only catalog (`/api/platform-models`) and the admin model-migration flow
(`/api/admin/models/preview-migration`, `/api/admin/models/apply-migration`).

The migration flow is what the admin sees when an AI-settings change is about
to remove access to currently-referenced models — they pick a replacement for
each affected model before the change commits.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from shared.model_migration import (
    apply_model_migration,
    scan_model_references,
    suggest_replacements,
)
from src.core.auth import CurrentActiveUser, RequirePlatformAdmin
from src.core.database import DbSession
from src.models import (
    ModelMigrationApplyRequest,
    ModelMigrationApplyResponse,
    ModelMigrationImpactItem,
    ModelMigrationPreviewRequest,
    ModelMigrationPreviewResponse,
    PlatformModelListResponse,
    PlatformModelPublic,
)
from src.models.orm import PlatformModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Platform Models"])


@router.get(
    "/api/platform-models",
    response_model=PlatformModelListResponse,
    summary="List platform model catalog",
    description="Active models from the global registry (synced from models.json).",
)
async def list_platform_models(
    user: CurrentActiveUser,
    db: DbSession,
) -> PlatformModelListResponse:
    rows = (
        await db.scalars(
            select(PlatformModel)
            .where(PlatformModel.is_active.is_(True))
            .order_by(PlatformModel.cost_tier, PlatformModel.model_id)
        )
    ).all()
    return PlatformModelListResponse(
        models=[PlatformModelPublic.model_validate(r) for r in rows]
    )


@router.post(
    "/api/admin/models/preview-migration",
    response_model=ModelMigrationPreviewResponse,
    summary="Preview impact of removing model access",
    description=(
        "Given a list of model IDs the admin is about to lose access to, "
        "return how many references exist and a suggested replacement per model."
    ),
    dependencies=[RequirePlatformAdmin],
)
async def preview_migration(
    request: ModelMigrationPreviewRequest,
    user: CurrentActiveUser,
    db: DbSession,
) -> ModelMigrationPreviewResponse:
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no organization context.",
        )

    impact = await scan_model_references(db, request.old_model_ids)

    available = (
        await db.scalars(
            select(PlatformModel).where(PlatformModel.is_active.is_(True))
        )
    ).all()
    suggestions = suggest_replacements(impact, list(available))

    items = [
        ModelMigrationImpactItem(
            model_id=mid,
            total=ref.total,
            by_kind=ref.to_summary()["by_kind"],
            suggested_replacement=suggestions.get(mid),
        )
        for mid, ref in impact.items()
    ]
    total = sum(i.total for i in items)
    return ModelMigrationPreviewResponse(
        organization_id=user.organization_id,
        items=items,
        total_references=total,
    )


@router.post(
    "/api/admin/models/apply-migration",
    response_model=ModelMigrationApplyResponse,
    summary="Rewrite model references",
    description=(
        "Apply replacements: rewrite every reference of `old -> new` and add "
        "an org-level deprecation entry per pair so any leftover string "
        "references (workflow code, in-flight conversations) also remap."
    ),
    dependencies=[RequirePlatformAdmin],
)
async def apply_migration(
    request: ModelMigrationApplyRequest,
    user: CurrentActiveUser,
    db: DbSession,
) -> ModelMigrationApplyResponse:
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no organization context.",
        )

    result = await apply_model_migration(
        db,
        organization_id=user.organization_id,
        replacements=request.replacements,
    )
    return ModelMigrationApplyResponse(
        organization_id=user.organization_id,
        rewrites=result.rewrites,
        deprecations_added=result.deprecations_added,
    )
