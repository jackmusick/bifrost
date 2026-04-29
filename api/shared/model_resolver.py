"""
Model resolver — shared infrastructure for picking the right model at chat time.

The resolver walks the cascade:

    platform_models (is_active=true)
            ↓ intersect (optional)
    Org.allowed_chat_models
            ↓ then defaults cascade
    Org → Role → Workspace → User → Conversation → Message

Most-specific *default* wins, but every choice must still be in the
intersection of platform_models and the org allowlist.

It also resolves logical aliases (`bifrost-fast`, `bifrost-balanced`,
`bifrost-premium`, plus org-defined ones) and applies deprecation remaps at
*lookup time* — `Message.model` is never remapped (immutable history).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm.organizations import Organization
from src.models.orm.platform_models import (
    ModelDeprecation,
    OrgModelAlias,
    PlatformModel,
)
from src.models.orm.users import Role, User
from src.models.orm.workspaces import Workspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelResolutionContext:
    """All inputs the resolver needs in one place.

    Pass IDs, not ORM objects, so callers don't need to pre-load relations.
    The resolver fetches what it needs via the provided session.
    """

    organization_id: UUID
    user_id: UUID | None = None
    role_ids: tuple[UUID, ...] = ()
    workspace_id: UUID | None = None
    conversation_current_model: str | None = None
    message_override: str | None = None
    required_capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ModelChoice:
    """The resolver's verdict.

    `model_id` is the concrete provider model ID to call. `cost_tier`,
    `display_name`, and `capabilities` come from `platform_models` and are
    convenient for the caller (no second lookup needed).

    `provenance` names the level that decided the choice — used by the UI
    to render "restricted by ..." tooltips and the picker's source badges.
    """

    model_id: str
    cost_tier: str
    display_name: str
    capabilities: dict[str, Any]
    provenance: str  # one of: message, conversation, user, workspace, role, org, platform


class ModelResolutionError(RuntimeError):
    """Raised when no model in the chain is reachable for this context."""


_PROVENANCE_ORDER = (
    "message",
    "conversation",
    "user",
    "workspace",
    "role",
    "org",
    "platform",
)


async def resolve_model(
    db: AsyncSession,
    ctx: ModelResolutionContext,
) -> ModelChoice:
    """Resolve a `ModelResolutionContext` into a concrete `ModelChoice`.

    Steps:
    1. Load platform_models (active, deduped).
    2. Intersect with org allowlist (if non-empty).
    3. Walk the cascade of defaults bottom-up; first one that's in the
       intersection wins. The platform's first active model is the floor.
    4. Apply alias resolution and deprecation remap.
    5. Return the resolved row.
    """
    # 1. Active platform catalog
    platform_rows = (
        await db.scalars(
            select(PlatformModel).where(PlatformModel.is_active.is_(True))
        )
    ).all()
    by_id = {pm.model_id: pm for pm in platform_rows}
    if not by_id:
        raise ModelResolutionError(
            "platform_models is empty; sync job has not run yet."
        )

    # 2. Org allowlist (if non-empty)
    org = await db.get(Organization, ctx.organization_id)
    if org is None:
        raise ModelResolutionError(
            f"organization {ctx.organization_id} not found"
        )
    org_allowlist: set[str] = set(org.allowed_chat_models or [])
    allowed_ids = (
        set(by_id.keys()) & org_allowlist if org_allowlist else set(by_id.keys())
    )

    # 3. Cascade — most-specific wins. (model_id, provenance) tuples.
    candidates: list[tuple[str | None, str]] = []
    candidates.append((ctx.message_override, "message"))
    candidates.append((ctx.conversation_current_model, "conversation"))

    user = await db.get(User, ctx.user_id) if ctx.user_id else None
    candidates.append((user.default_chat_model if user else None, "user"))

    workspace = (
        await db.get(Workspace, ctx.workspace_id) if ctx.workspace_id else None
    )
    candidates.append(
        (workspace.default_model if workspace else None, "workspace")
    )

    # Roles: take the first role that has a default. Order is the order given.
    role_default: str | None = None
    if ctx.role_ids:
        roles = (
            await db.scalars(select(Role).where(Role.id.in_(ctx.role_ids)))
        ).all()
        roles_by_id = {r.id: r for r in roles}
        for rid in ctx.role_ids:
            r = roles_by_id.get(rid)
            if r and r.default_chat_model:
                role_default = r.default_chat_model
                break
    candidates.append((role_default, "role"))

    candidates.append((org.default_chat_model, "org"))

    chosen_id: str | None = None
    chosen_provenance: str = "platform"
    for raw, prov in candidates:
        if not raw:
            continue
        resolved = await _resolve_alias_and_deprecation(
            db, raw, ctx.organization_id
        )
        if resolved in allowed_ids:
            chosen_id = resolved
            chosen_provenance = prov
            break

    if chosen_id is None:
        # Floor: the first active model on the allowlist (deterministic by model_id).
        if not allowed_ids:
            raise ModelResolutionError(
                f"no models available for org {ctx.organization_id} "
                f"(org allowlist {sorted(org_allowlist)!r} excludes everything)"
            )
        chosen_id = sorted(allowed_ids)[0]
        chosen_provenance = "platform"

    pm = by_id[chosen_id]

    # 5. Capability pre-check (if caller asked for any)
    if ctx.required_capabilities:
        if not has_capabilities(pm, ctx.required_capabilities):
            # Try to find a peer in the allowed set that has them.
            peer = pick_compatible_from_set(
                allowed_ids, by_id, ctx.required_capabilities
            )
            if peer is None:
                raise ModelResolutionError(
                    f"no model in allowed set supports {sorted(ctx.required_capabilities)!r}"
                )
            chosen_id = peer
            chosen_provenance = "capability-fallback"
            pm = by_id[chosen_id]

    return ModelChoice(
        model_id=pm.model_id,
        cost_tier=pm.cost_tier,
        display_name=pm.display_name,
        capabilities=dict(pm.capabilities or {}),
        provenance=chosen_provenance,
    )


async def _resolve_alias_and_deprecation(
    db: AsyncSession,
    raw_model_id: str,
    organization_id: UUID,
) -> str:
    """Resolve org-level aliases first, then platform deprecations.

    Returns the canonical concrete model_id.
    """
    # Org alias?
    alias_row = await db.scalar(
        select(OrgModelAlias).where(
            OrgModelAlias.organization_id == organization_id,
            OrgModelAlias.alias == raw_model_id,
        )
    )
    if alias_row is not None:
        raw_model_id = alias_row.target_model_id

    # Org-level deprecation wins over platform-wide.
    org_deprecation = await db.scalar(
        select(ModelDeprecation).where(
            ModelDeprecation.organization_id == organization_id,
            ModelDeprecation.old_model_id == raw_model_id,
        )
    )
    if org_deprecation is not None:
        return org_deprecation.new_model_id

    platform_deprecation = await db.scalar(
        select(ModelDeprecation).where(
            ModelDeprecation.organization_id.is_(None),
            ModelDeprecation.old_model_id == raw_model_id,
        )
    )
    if platform_deprecation is not None:
        return platform_deprecation.new_model_id

    return raw_model_id


def has_capabilities(pm: PlatformModel, required: frozenset[str]) -> bool:
    caps = pm.capabilities or {}
    return all(bool(caps.get(c)) for c in required)


def pick_compatible_from_set(
    allowed_ids: set[str],
    by_id: dict[str, PlatformModel],
    required: frozenset[str],
) -> str | None:
    """Return the cheapest-tier compatible model from allowed_ids, or None.

    Tier preference: balanced > fast > premium (i.e., prefer balanced when
    capability compatibility forces a switch — fast may not have the capability,
    premium is expensive).
    """
    tier_order = {"balanced": 0, "fast": 1, "premium": 2}
    candidates = [
        by_id[mid]
        for mid in allowed_ids
        if mid in by_id and has_capabilities(by_id[mid], required)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda pm: (tier_order.get(pm.cost_tier, 99), pm.model_id))
    return candidates[0].model_id


def check_message_compat(
    pm: PlatformModel,
    *,
    has_image: bool = False,
    has_pdf: bool = False,
    needs_tool_use: bool = False,
    has_audio: bool = False,
) -> list[str]:
    """Return human-readable incompatibility reasons; empty list = compatible.

    Used by the composer pre-flight check. Composer wiring lives in M4
    (attachments); this is the underlying utility.
    """
    reasons: list[str] = []
    caps = pm.capabilities or {}
    if has_image and not caps.get("supports_images_in"):
        reasons.append(f"{pm.display_name} can't read images")
    if has_pdf and not caps.get("supports_pdf_in"):
        reasons.append(f"{pm.display_name} can't read PDFs")
    if needs_tool_use and not caps.get("supports_tool_use"):
        reasons.append(f"{pm.display_name} doesn't support tools")
    if has_audio and not caps.get("supports_audio_in"):
        reasons.append(f"{pm.display_name} doesn't support audio input")
    return reasons


__all__ = [
    "ModelResolutionContext",
    "ModelResolutionError",
    "ModelChoice",
    "resolve_model",
    "has_capabilities",
    "pick_compatible_from_set",
    "check_message_compat",
    "_PROVENANCE_ORDER",
]
