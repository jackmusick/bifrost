"""
Model migration — find every reference to a model_id and rewrite them.

Two phases:
1. `scan_model_references(old_model_ids)` walks every place a model_id can be
   stored and returns an impact map per old model. Used by the preview endpoint
   so the admin can see what they're about to break.
2. `apply_model_migration({old: new})` rewrites those references in one
   transaction and adds an org-level deprecation entry per pair (so any
   leftover string references — workflow code, in-flight conversations —
   continue to resolve through the resolver's deprecation lookup).

Triggered when the admin is about to change AI settings in a way that removes
access to currently-referenced models (most commonly: switching the LLM
provider integration). The endpoint surface is in
`api/src/routers/admin_models.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orm import (
    Agent,
    Conversation,
    Organization,
    PlatformModel,
    Role,
    User,
    Workspace,
)
from src.models.orm.platform_models import ModelDeprecation

logger = logging.getLogger(__name__)


@dataclass
class ReferenceCount:
    """How many references exist of each kind for a single old model_id."""

    model_id: str
    organizations_default: list[UUID] = field(default_factory=list)
    organizations_allowlist: list[UUID] = field(default_factory=list)
    roles: list[UUID] = field(default_factory=list)
    users: list[UUID] = field(default_factory=list)
    workspaces: list[UUID] = field(default_factory=list)
    conversations: list[UUID] = field(default_factory=list)
    agents: list[UUID] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.organizations_default)
            + len(self.organizations_allowlist)
            + len(self.roles)
            + len(self.users)
            + len(self.workspaces)
            + len(self.conversations)
            + len(self.agents)
        )

    def to_summary(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "total": self.total,
            "by_kind": {
                "organizations_default": len(self.organizations_default),
                "organizations_allowlist": len(self.organizations_allowlist),
                "roles": len(self.roles),
                "users": len(self.users),
                "workspaces": len(self.workspaces),
                "conversations": len(self.conversations),
                "agents": len(self.agents),
            },
        }


async def scan_model_references(
    db: AsyncSession,
    old_model_ids: list[str],
) -> dict[str, ReferenceCount]:
    """For each `old_model_id`, find every place it's stored.

    Note: `Message.model` is intentionally excluded — it's immutable history
    (spec §5.8.4). Workflow code is excluded too (lives in S3 / Redis, no
    structured grep here; admins handle workflow code manually).
    """
    out: dict[str, ReferenceCount] = {m: ReferenceCount(model_id=m) for m in old_model_ids}
    if not old_model_ids:
        return out

    # Org default
    rows = (
        await db.execute(
            sa.select(Organization.id, Organization.default_chat_model).where(
                Organization.default_chat_model.in_(old_model_ids)
            )
        )
    ).all()
    for org_id, model_id in rows:
        if model_id in out:
            out[model_id].organizations_default.append(org_id)

    # Org allowlist (JSONB ?| operator: array overlap)
    org_allowlist_rows = (
        await db.execute(
            sa.select(Organization.id, Organization.allowed_chat_models).where(
                sa.cast(Organization.allowed_chat_models, JSONB).op("?|")(
                    sa.cast(old_model_ids, sa.ARRAY(sa.Text))
                )
            )
        )
    ).all()
    for org_id, allowlist in org_allowlist_rows:
        for m in allowlist or []:
            if m in out:
                out[m].organizations_allowlist.append(org_id)

    # Roles
    rows = (
        await db.execute(
            sa.select(Role.id, Role.default_chat_model).where(
                Role.default_chat_model.in_(old_model_ids)
            )
        )
    ).all()
    for role_id, model_id in rows:
        if model_id in out:
            out[model_id].roles.append(role_id)

    # Users
    rows = (
        await db.execute(
            sa.select(User.id, User.default_chat_model).where(
                User.default_chat_model.in_(old_model_ids)
            )
        )
    ).all()
    for user_id, model_id in rows:
        if model_id in out:
            out[model_id].users.append(user_id)

    # Workspaces
    rows = (
        await db.execute(
            sa.select(Workspace.id, Workspace.default_model).where(
                Workspace.default_model.in_(old_model_ids)
            )
        )
    ).all()
    for ws_id, model_id in rows:
        if model_id in out:
            out[model_id].workspaces.append(ws_id)

    # Conversations
    rows = (
        await db.execute(
            sa.select(Conversation.id, Conversation.current_model).where(
                Conversation.current_model.in_(old_model_ids)
            )
        )
    ).all()
    for conv_id, model_id in rows:
        if model_id in out:
            out[model_id].conversations.append(conv_id)

    # Agents — only if Agent has a default-model column. Agents currently
    # don't carry one in this milestone; included as a placeholder so future
    # additions don't get missed. Returning empty list for now.
    _ = Agent  # keeps the import meaningful

    return out


def suggest_replacements(
    impact: dict[str, ReferenceCount],
    available: list[PlatformModel],
) -> dict[str, str | None]:
    """For each old model in `impact`, suggest a replacement from `available`.

    Heuristic: prefer same cost_tier; if none, return None (admin will type a
    custom model_id into the free-text box).
    """
    by_tier: dict[str, list[PlatformModel]] = {}
    for pm in available:
        by_tier.setdefault(pm.cost_tier, []).append(pm)
    for pms in by_tier.values():
        pms.sort(key=lambda p: p.model_id)

    out: dict[str, str | None] = {}
    for old_id in impact.keys():
        # Try to learn the old tier from platform_models too — it might be
        # an inactive row (the kind we're trying to migrate away from).
        # If we don't know, default to balanced.
        existing_tier: str | None = None
        for pm in available:
            if pm.model_id == old_id:
                existing_tier = pm.cost_tier
                break
        tier = existing_tier or "balanced"
        peers = by_tier.get(tier) or by_tier.get("balanced") or []
        out[old_id] = peers[0].model_id if peers else None
    return out


@dataclass
class MigrationResult:
    rewrites: dict[str, int] = field(default_factory=dict)
    deprecations_added: int = 0


async def apply_model_migration(
    db: AsyncSession,
    *,
    organization_id: UUID,
    replacements: dict[str, str],
) -> MigrationResult:
    """Rewrite every reference of `old → new` and add deprecation entries.

    `organization_id` scopes the rewrite — only references belonging to that
    org (or its users / its conversations / its workspaces / its roles' usage)
    are rewritten. Deprecation rows are written at the org level so leftover
    string references (e.g., workflow code) also remap going forward.
    """
    result = MigrationResult()
    if not replacements:
        return result

    for old_id, new_id in replacements.items():
        if not new_id or old_id == new_id:
            continue

        # Org defaults (only the affected org)
        n = await db.execute(
            sa.update(Organization)
            .where(
                Organization.id == organization_id,
                Organization.default_chat_model == old_id,
            )
            .values(default_chat_model=new_id)
        )
        result.rewrites[f"{old_id}->org_default"] = n.rowcount or 0

        # Org allowlist — fetch + rewrite + persist (JSONB element replace)
        org = await db.get(Organization, organization_id)
        if org and old_id in (org.allowed_chat_models or []):
            org.allowed_chat_models = [
                new_id if m == old_id else m for m in org.allowed_chat_models
            ]
            result.rewrites.setdefault(f"{old_id}->org_allowlist", 0)
            result.rewrites[f"{old_id}->org_allowlist"] += 1

        # Workspaces in this org
        n = await db.execute(
            sa.update(Workspace)
            .where(
                Workspace.organization_id == organization_id,
                Workspace.default_model == old_id,
            )
            .values(default_model=new_id)
        )
        result.rewrites[f"{old_id}->workspaces"] = n.rowcount or 0

        # Users in this org
        n = await db.execute(
            sa.update(User)
            .where(
                User.organization_id == organization_id,
                User.default_chat_model == old_id,
            )
            .values(default_chat_model=new_id)
        )
        result.rewrites[f"{old_id}->users"] = n.rowcount or 0

        # Conversations whose user belongs to this org
        n = await db.execute(
            sa.update(Conversation)
            .where(
                Conversation.current_model == old_id,
                Conversation.user_id.in_(
                    sa.select(User.id).where(User.organization_id == organization_id)
                ),
            )
            .values(current_model=new_id)
        )
        result.rewrites[f"{old_id}->conversations"] = n.rowcount or 0

        # Roles are platform-wide (no org_id), so we don't rewrite them here —
        # an org admin can't reach across into another org's role config. If
        # this needs to change, the role migration becomes a platform-admin
        # action separate from this flow.

        # Org-level deprecation entry so any leftover string reference also
        # resolves to the new model going forward.
        existing = await db.scalar(
            sa.select(ModelDeprecation).where(
                ModelDeprecation.organization_id == organization_id,
                ModelDeprecation.old_model_id == old_id,
            )
        )
        if existing is None:
            db.add(
                ModelDeprecation(
                    old_model_id=old_id,
                    new_model_id=new_id,
                    deprecated_at=datetime.now(timezone.utc),
                    organization_id=organization_id,
                    notes="Created by admin model migration",
                )
            )
            result.deprecations_added += 1
        else:
            existing.new_model_id = new_id
            existing.deprecated_at = datetime.now(timezone.utc)

    await db.commit()
    return result


__all__ = [
    "ReferenceCount",
    "scan_model_references",
    "suggest_replacements",
    "apply_model_migration",
    "MigrationResult",
]
