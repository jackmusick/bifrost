"""
Platform Models Router

Read-only catalog (`/api/platform-models`) and the platform-wide allowlist
migration flow:
- `/api/admin/models/preview-allowlist-migration`
- `/api/admin/models/apply-allowlist-migration`

The migration flow runs at the *platform* level: when a configuration change
makes some set of model_ids unreachable for the whole installation (provider
switch, model deactivation), it shows the platform admin which orgs have those
ids in their `allowed_chat_models` and lets them pick a replacement (or drop)
per id, before the saving change commits.

We do NOT scan defaults (org/role/workspace/user/conversation/agent
default_model fields), summarization model, tuning model, etc. Those are
picks, not constraints — the resolver walks them at lookup time and falls
through any that are unreachable. Only allowlists *constrain* what users can
pick in chat, so they're the only fields that need active migration.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import select

from shared.model_migration import (
    apply_allowlist_migration,
    scan_orphaned_allowlists,
)
from src.core.auth import CurrentActiveUser, RequirePlatformAdmin
from src.core.database import DbSession
from src.models import (
    OrgAllowlistImpactRow,
    PlatformAllowlistApplyRequest,
    PlatformAllowlistApplyResponse,
    PlatformAllowlistPreviewRequest,
    PlatformAllowlistPreviewResponse,
    PlatformModelListResponse,
    PlatformModelPublic,
)
from src.models.orm import PlatformModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Platform Models"])


@router.get(
    "/api/admin/models/referenced-allowlist-ids",
    response_model=list[str],
    summary="All model_ids currently in any org's allowlist",
    description=(
        "Used by the LLMConfig save flow to know which models are at risk "
        "of becoming unreachable when the provider changes. The frontend "
        "diffs this against the new provider's /v1/models response and "
        "passes the difference to /preview-allowlist-migration."
    ),
    dependencies=[RequirePlatformAdmin],
)
async def list_referenced_allowlist_ids(
    user: CurrentActiveUser,
    db: DbSession,
) -> list[str]:
    from src.models.orm import Organization

    rows = (
        await db.execute(
            select(Organization.allowed_chat_models).where(
                Organization.allowed_chat_models.isnot(None)
            )
        )
    ).all()
    out: set[str] = set()
    for (allowlist,) in rows:
        for m in allowlist or []:
            out.add(m)
    return sorted(out)


@router.get(
    "/api/platform-models",
    response_model=PlatformModelListResponse,
    summary="List platform model catalog",
    description="Active models from the global registry (synced from LiteLLM).",
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
    "/api/admin/models/preview-allowlist-migration",
    response_model=PlatformAllowlistPreviewResponse,
    summary="Preview which orgs reference soon-to-be-unreachable models",
    dependencies=[RequirePlatformAdmin],
)
async def preview_allowlist_migration(
    request: PlatformAllowlistPreviewRequest,
    user: CurrentActiveUser,
    db: DbSession,
) -> PlatformAllowlistPreviewResponse:
    impacts = await scan_orphaned_allowlists(
        db, unreachable_model_ids=request.unreachable_model_ids
    )
    rows = [
        OrgAllowlistImpactRow(
            organization_id=i.organization_id,
            organization_name=i.organization_name,
            orphaned_model_ids=i.orphaned_model_ids,
        )
        for i in impacts
    ]
    return PlatformAllowlistPreviewResponse(
        affected_orgs=rows,
        total_orgs=len(rows),
    )


@router.post(
    "/api/admin/models/apply-allowlist-migration",
    response_model=PlatformAllowlistApplyResponse,
    summary="Apply allowlist replacements platform-wide",
    description=(
        "For each unreachable model_id, swap it to the new model_id in every "
        "org's allowed_chat_models, or drop it (replacement = null). One "
        "platform-wide ModelDeprecation row is added per (old → new) pair "
        "so any in-flight string references also remap."
    ),
    dependencies=[RequirePlatformAdmin],
)
async def apply_allowlist_migration_endpoint(
    request: PlatformAllowlistApplyRequest,
    user: CurrentActiveUser,
    db: DbSession,
) -> PlatformAllowlistApplyResponse:
    result = await apply_allowlist_migration(db, replacements=request.replacements)
    return PlatformAllowlistApplyResponse(
        orgs_rewritten=result.orgs_rewritten,
        deprecations_added=result.deprecations_added,
    )
