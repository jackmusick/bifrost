"""CRUD endpoints for Custom Claims (org-scoped).

Custom Claims are query-resolved facts about the calling user (e.g.
``allowed_campus_ids``) that table policies in the same org can reference
as ``{claims: <name>}``. See
``docs/superpowers/specs/2026-05-21-table-policies-custom-claims.md``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.claims.registry import (
    claim_dependency_graph,
    find_cycle,
    referenced_claim_names,
)
from src.core.auth import Context, CurrentSuperuser
from src.models.contracts.claims import (
    ClaimsList,
    CustomClaim as ClaimDTO,
    CustomClaimCreate,
    CustomClaimUpdate,
)
from src.models.orm.custom_claims import CustomClaim as ClaimORM
from src.models.orm.tables import Table

router = APIRouter(prefix="/api/claims", tags=["Claims"])


def _require_org(ctx: Context) -> UUID:
    """Custom Claims are org-scoped — callers must have a home org."""
    if ctx.org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Custom Claims are org-scoped; caller has no organization",
        )
    return ctx.org_id


async def _check_source_table_exists(
    db: AsyncSession, org_id: UUID, table_name: str
) -> None:
    result = await db.execute(
        select(Table.id).where(
            Table.organization_id == org_id, Table.name == table_name
        )
    )
    if result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source table {table_name!r} not found in this org",
        )


async def _check_no_cycles(db: AsyncSession, org_id: UUID) -> None:
    """Run cycle detection over the full set of claims in the org."""
    # registry.load_org_claims is sync (uses db.execute().scalars()); inline
    # the async equivalent here to avoid a sync/async split in shared/.
    rows = (
        await db.execute(
            select(ClaimORM).where(ClaimORM.organization_id == org_id)
        )
    ).scalars().all()
    claims = {r.name: ClaimDTO.model_validate(r) for r in rows}
    cycle = find_cycle(claim_dependency_graph(claims.values()))
    if cycle is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "claim dependency cycle detected", "cycle": cycle},
        )


async def _tables_referencing_claim(
    db: AsyncSession, org_id: UUID, claim_name: str
) -> list[str]:
    """Return names of tables whose policies reference ``claim_name``."""
    rows = (
        await db.execute(
            select(Table).where(
                Table.organization_id == org_id, Table.access.is_not(None)
            )
        )
    ).scalars().all()
    out: list[str] = []
    for t in rows:
        access = t.access or {}
        for policy in access.get("policies", []):
            if claim_name in referenced_claim_names(policy.get("when")):
                out.append(t.name)
                break
    return out


@router.get("", response_model=ClaimsList, summary="List custom claims for caller's org")
async def list_claims(ctx: Context) -> ClaimsList:
    org_id = _require_org(ctx)
    rows = (
        await ctx.db.execute(
            select(ClaimORM).where(ClaimORM.organization_id == org_id)
        )
    ).scalars().all()
    return ClaimsList(claims=[ClaimDTO.model_validate(r) for r in rows])


@router.get("/{name}", response_model=ClaimDTO, summary="Get a custom claim by name")
async def get_claim(name: str, ctx: Context) -> ClaimDTO:
    org_id = _require_org(ctx)
    row = (
        await ctx.db.execute(
            select(ClaimORM).where(
                ClaimORM.organization_id == org_id, ClaimORM.name == name
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return ClaimDTO.model_validate(row)


@router.post(
    "",
    response_model=ClaimDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom claim (admin only)",
)
async def create_claim(
    body: CustomClaimCreate,
    ctx: Context,
    user: CurrentSuperuser,
) -> ClaimDTO:
    org_id = _require_org(ctx)
    await _check_source_table_exists(ctx.db, org_id, body.query.table)
    row = ClaimORM(
        organization_id=org_id,
        name=body.name,
        description=body.description,
        type=body.type,
        query=body.query.model_dump(mode="json"),
    )
    ctx.db.add(row)
    try:
        await ctx.db.flush()
    except IntegrityError as exc:
        await ctx.db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"claim {body.name!r} already exists in this org",
        ) from exc
    # Cycle check sees the new row via the same session (post-flush).
    try:
        await _check_no_cycles(ctx.db, org_id)
    except HTTPException:
        await ctx.db.rollback()
        raise
    await ctx.db.commit()
    await ctx.db.refresh(row)
    return ClaimDTO.model_validate(row)


@router.patch(
    "/{name}",
    response_model=ClaimDTO,
    summary="Update a custom claim (admin only)",
)
async def update_claim(
    name: str,
    body: CustomClaimUpdate,
    ctx: Context,
    user: CurrentSuperuser,
) -> ClaimDTO:
    org_id = _require_org(ctx)
    row = (
        await ctx.db.execute(
            select(ClaimORM).where(
                ClaimORM.organization_id == org_id, ClaimORM.name == name
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")

    fields = body.model_fields_set
    if "description" in fields:
        row.description = body.description
    if "type" in fields and body.type is not None:
        row.type = body.type
    if "query" in fields and body.query is not None:
        await _check_source_table_exists(ctx.db, org_id, body.query.table)
        row.query = body.query.model_dump(mode="json")

    await ctx.db.flush()
    try:
        await _check_no_cycles(ctx.db, org_id)
    except HTTPException:
        await ctx.db.rollback()
        raise
    await ctx.db.commit()
    await ctx.db.refresh(row)
    return ClaimDTO.model_validate(row)


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom claim (admin only)",
)
async def delete_claim(
    name: str,
    ctx: Context,
    user: CurrentSuperuser,
) -> None:
    org_id = _require_org(ctx)
    row = (
        await ctx.db.execute(
            select(ClaimORM).where(
                ClaimORM.organization_id == org_id, ClaimORM.name == name
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")

    refs = await _tables_referencing_claim(ctx.db, org_id, name)
    if refs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "claim is referenced by table policies; remove references first",
                "tables": refs,
            },
        )
    await ctx.db.delete(row)
    await ctx.db.commit()
