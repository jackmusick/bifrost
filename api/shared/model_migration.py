"""
Platform-wide model migration — when models become unreachable at the install
level (provider switch, model removed from platform_models), find every org
whose `allowed_chat_models` references those models and let the platform
admin remap or drop the entries.

Why this is *only* org allowlists and not other tables:
  - Allowlists are the only place where a stored model_id *constrains* what
    can run. If the chat picker can't satisfy `Sonnet ∈ allowlist` because
    Sonnet is no longer reachable, the chat is broken until the allowlist
    is updated.
  - Defaults (org/role/workspace/user/conversation `default_*`) are picks,
    not constraints. The resolver walks defaults bottom-up at lookup time
    and falls through any that are now unreachable. They self-heal.
  - Aliases + deprecation remap (spec §5.8) handle in-flight string
    references (workflow code, conversations created mid-flight).

So this scan is intentionally narrow: scan `organizations`, rewrite
`organizations`. Nothing else.
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

from src.models.orm import Organization
from src.models.orm.platform_models import ModelDeprecation

logger = logging.getLogger(__name__)


@dataclass
class OrgAllowlistImpact:
    """Per-org list of orphaned model_ids in that org's allowlist."""

    organization_id: UUID
    organization_name: str
    orphaned_model_ids: list[str] = field(default_factory=list)


async def scan_orphaned_allowlists(
    db: AsyncSession,
    *,
    unreachable_model_ids: list[str],
) -> list[OrgAllowlistImpact]:
    """Return orgs whose `allowed_chat_models` contains any unreachable id.

    Platform-wide. The result is keyed by org so the admin sees per-org rows
    in the migration modal.
    """
    if not unreachable_model_ids:
        return []

    rows = (
        await db.execute(
            sa.select(
                Organization.id,
                Organization.name,
                Organization.allowed_chat_models,
            ).where(
                sa.cast(Organization.allowed_chat_models, JSONB).op("?|")(
                    sa.cast(unreachable_model_ids, sa.ARRAY(sa.Text))
                )
            )
        )
    ).all()

    bad = set(unreachable_model_ids)
    out: list[OrgAllowlistImpact] = []
    for org_id, name, allowlist in rows:
        orphans = [m for m in (allowlist or []) if m in bad]
        if orphans:
            out.append(
                OrgAllowlistImpact(
                    organization_id=org_id,
                    organization_name=name,
                    orphaned_model_ids=orphans,
                )
            )
    return out


@dataclass
class MigrationResult:
    orgs_rewritten: int = 0
    deprecations_added: int = 0


async def apply_allowlist_migration(
    db: AsyncSession,
    *,
    replacements: dict[str, str | None],
) -> MigrationResult:
    """Rewrite every org's `allowed_chat_models` according to `replacements`.

    `replacements[old_id] = new_id_or_None`:
      - new_id set → swap the entry to the new model_id (one platform-wide
        ModelDeprecation row added per pair so any stray strings remap too).
      - None → drop the entry from the allowlist.

    Idempotent: re-running with already-applied replacements is a no-op.
    """
    result = MigrationResult()
    if not replacements:
        return result

    unreachable = list(replacements.keys())
    rows = (
        await db.execute(
            sa.select(Organization).where(
                sa.cast(Organization.allowed_chat_models, JSONB).op("?|")(
                    sa.cast(unreachable, sa.ARRAY(sa.Text))
                )
            )
        )
    ).scalars().all()

    for org in rows:
        original = list(org.allowed_chat_models or [])
        next_list: list[str] = []
        changed = False
        for entry in original:
            if entry in replacements:
                replacement = replacements[entry]
                changed = True
                if replacement:
                    # Avoid duplicates if the replacement is already there.
                    if replacement not in next_list and replacement not in original:
                        next_list.append(replacement)
                # else: drop
            else:
                next_list.append(entry)
        if changed:
            org.allowed_chat_models = next_list
            result.orgs_rewritten += 1

    # Platform-wide deprecation rows for the (old → new) pairs.
    for old_id, new_id in replacements.items():
        if not new_id:
            continue
        existing = await db.scalar(
            sa.select(ModelDeprecation).where(
                ModelDeprecation.organization_id.is_(None),
                ModelDeprecation.old_model_id == old_id,
            )
        )
        if existing is None:
            db.add(
                ModelDeprecation(
                    old_model_id=old_id,
                    new_model_id=new_id,
                    deprecated_at=datetime.now(timezone.utc),
                    organization_id=None,
                    notes="Created by platform model migration",
                )
            )
            result.deprecations_added += 1
        else:
            existing.new_model_id = new_id
            existing.deprecated_at = datetime.now(timezone.utc)

    await db.commit()
    return result


# Legacy stubs kept for backward-compatibility while the router catches up.
# Remove once the new endpoints are wired.

async def scan_model_references(
    db: AsyncSession, old_model_ids: list[str]
) -> dict[str, Any]:
    """DEPRECATED: kept to avoid breaking the existing router import path."""
    impacts = await scan_orphaned_allowlists(
        db, unreachable_model_ids=old_model_ids
    )
    out: dict[str, Any] = {m: {"model_id": m, "total": 0} for m in old_model_ids}
    for impact in impacts:
        for mid in impact.orphaned_model_ids:
            if mid in out:
                out[mid]["total"] += 1
    return out


def suggest_replacements(*_args, **_kwargs):  # pragma: no cover
    return {}


async def apply_model_migration(*_args, **_kwargs):  # pragma: no cover
    raise NotImplementedError("Use apply_allowlist_migration instead.")


__all__ = [
    "OrgAllowlistImpact",
    "scan_orphaned_allowlists",
    "apply_allowlist_migration",
    "MigrationResult",
]
