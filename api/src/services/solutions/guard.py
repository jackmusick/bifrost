"""Read-only enforcement for solution-managed entities.

A solution-managed entity (``solution_id IS NOT NULL``) has exactly one writer:
the deploy path (or git auto-pull). Every other mutation surface — REST routers,
MCP tools, CLI mutation commands — must refuse to change it (success-criteria
§3.2, criterion 6). Routers call :func:`assert_not_solution_managed` right after
loading the target row, before applying any change.

The instance still owns the few things that cannot be portable — OAuth token
mappings and secret config *values* (criterion 7). Those live on their own
records (OAuthToken / Config), not on the managed entity, so they simply never
call this guard; the guard is about the portable entity itself.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SOLUTION_MANAGED_MESSAGE = (
    "Solution-managed entities can only be managed by deployment methods."
)


def is_solution_managed(entity: Any) -> bool:
    """True if ``entity`` carries a non-null ``solution_id``."""
    return getattr(entity, "solution_id", None) is not None


def assert_not_solution_managed(entity: Any) -> None:
    """Raise HTTP 409 with the locked message if ``entity`` is solution-managed.

    No-op for ad-hoc ``_repo/`` entities (``solution_id`` None or absent), so
    existing mutation paths are unchanged for non-solution entities.
    """
    if is_solution_managed(entity):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=SOLUTION_MANAGED_MESSAGE,
        )


async def assert_entity_id_not_solution_managed(
    db: AsyncSession, model: type, entity_id: UUID
) -> None:
    """Guard by id with a RAW lookup (no cascade scope).

    Repository ``get()`` now filters out solution-managed rows (cascade is
    _repo/-only), so a router that wants to return the specific read-only error
    — rather than a misleading 404 — must look the row up directly. A missing
    row is left alone (the caller's own not-found handling applies).
    """
    solution_id = (
        await db.execute(select(model.solution_id).where(model.id == entity_id))  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if solution_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=SOLUTION_MANAGED_MESSAGE,
        )
