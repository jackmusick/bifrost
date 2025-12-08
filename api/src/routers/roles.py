"""
Roles Router

Manage roles for organization users.
- Assign users to roles (UserRoles)
- Assign forms to roles (FormRoles)
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, delete

from src.core.auth import CurrentSuperuser
from src.core.database import DbSession
from src.models.orm import (
    Role as RoleORM,
    UserRole as UserRoleORM,
    FormRole as FormRoleORM,
    Form as FormORM,
    User as UserORM,
)
from src.models.models import (
    RoleCreate,
    RolePublic,
    RoleUpdate,
    RoleUsersResponse,
    RoleFormsResponse,
    AssignUsersToRoleRequest,
    AssignFormsToRoleRequest,
)

# Import cache invalidation
try:
    from shared.cache import (
        invalidate_role,
        invalidate_role_users,
        invalidate_role_forms,
    )

    CACHE_INVALIDATION_AVAILABLE = True
except ImportError:
    CACHE_INVALIDATION_AVAILABLE = False
    invalidate_role = None  # type: ignore
    invalidate_role_users = None  # type: ignore
    invalidate_role_forms = None  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roles", tags=["Roles"])


@router.get(
    "",
    response_model=list[RolePublic],
    summary="List all roles",
    description="Get all roles (Platform admin only)",
)
async def list_roles(
    user: CurrentSuperuser,
    db: DbSession,
) -> list[RolePublic]:
    """List all roles."""
    query = select(RoleORM).where(RoleORM.is_active).order_by(RoleORM.name)
    result = await db.execute(query)
    roles = result.scalars().all()
    return [RolePublic.model_validate(r) for r in roles]


@router.post(
    "",
    response_model=RolePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create a role",
    description="Create a new role (Platform admin only)",
)
async def create_role(
    request: RoleCreate,
    user: CurrentSuperuser,
    db: DbSession,
) -> RolePublic:
    """Create a new role."""
    now = datetime.utcnow()

    role = RoleORM(
        name=request.name,
        description=request.description,
        is_active=request.is_active,
        organization_id=request.organization_id,
        created_by=user.email,
        created_at=now,
        updated_at=now,
    )

    db.add(role)
    await db.flush()
    await db.refresh(role)

    logger.info(f"Created role {role.id}: {role.name}")

    # Invalidate cache
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role:
        org_id = str(role.organization_id) if role.organization_id else None
        await invalidate_role(org_id, str(role.id))

    return RolePublic.model_validate(role)


@router.get(
    "/{role_id}",
    response_model=RolePublic,
    summary="Get a role",
    description="Get a role by ID (Platform admin only)",
)
async def get_role(
    role_id: UUID,
    user: CurrentSuperuser,
    db: DbSession,
) -> RolePublic:
    """Get a role by ID."""
    result = await db.execute(select(RoleORM).where(RoleORM.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    return RolePublic.model_validate(role)


@router.patch(
    "/{role_id}",
    response_model=RolePublic,
    summary="Update a role",
    description="Update a role (Platform admin only)",
)
async def update_role(
    role_id: UUID,
    request: RoleUpdate,
    user: CurrentSuperuser,
    db: DbSession,
) -> RolePublic:
    """Update a role."""
    result = await db.execute(select(RoleORM).where(RoleORM.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    if request.name is not None:
        role.name = request.name
    if request.description is not None:
        role.description = request.description
    if request.is_active is not None:
        role.is_active = request.is_active

    role.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(role)

    logger.info(f"Updated role {role_id}")

    # Invalidate cache
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role:
        org_id = str(role.organization_id) if role.organization_id else None
        await invalidate_role(org_id, str(role_id))

    return RolePublic.model_validate(role)


# Keep PUT for backwards compatibility
@router.put(
    "/{role_id}",
    response_model=RolePublic,
    summary="Update a role",
    description="Update a role (Platform admin only)",
    include_in_schema=False,  # Hide from OpenAPI, use PATCH instead
)
async def update_role_put(
    role_id: UUID,
    request: RoleUpdate,
    user: CurrentSuperuser,
    db: DbSession,
) -> RolePublic:
    """Update a role (PUT - for backwards compatibility)."""
    return await update_role(role_id, request, user, db)


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a role",
    description="Soft delete a role (Platform admin only)",
)
async def delete_role(
    role_id: UUID,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Soft delete a role."""
    result = await db.execute(select(RoleORM).where(RoleORM.id == role_id))
    role = result.scalar_one_or_none()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        )

    role.is_active = False
    role.updated_at = datetime.utcnow()

    await db.flush()
    logger.info(f"Soft deleted role {role_id}")

    # Invalidate cache
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role:
        org_id = str(role.organization_id) if role.organization_id else None
        await invalidate_role(org_id, str(role_id))


# =============================================================================
# Role-User Assignments
# =============================================================================


@router.get(
    "/{role_id}/users",
    response_model=RoleUsersResponse,
    summary="Get role users",
    description="Get all users assigned to a role",
)
async def get_role_users(
    role_id: UUID,
    user: CurrentSuperuser,
    db: DbSession,
) -> RoleUsersResponse:
    """Get all users assigned to a role."""
    result = await db.execute(
        select(UserRoleORM.user_id).where(UserRoleORM.role_id == role_id)
    )
    user_ids = [str(uid) for uid in result.scalars().all()]
    return RoleUsersResponse(role_ids=user_ids)


@router.post(
    "/{role_id}/users",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Assign users to role",
    description="Assign users to a role (batch operation)",
)
async def assign_users_to_role(
    role_id: UUID,
    request: AssignUsersToRoleRequest,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Assign users to a role."""
    now = datetime.utcnow()

    for user_id_str in request.user_ids:
        # Try to parse as UUID, otherwise lookup by email
        try:
            user_uuid = UUID(user_id_str)
        except ValueError:
            result = await db.execute(
                select(UserORM.id).where(UserORM.email == user_id_str)
            )
            user_uuid = result.scalar_one_or_none()
            if not user_uuid:
                logger.warning(f"User {user_id_str} not found, skipping")
                continue

        # Check if already assigned
        existing = await db.execute(
            select(UserRoleORM).where(
                UserRoleORM.user_id == user_uuid,
                UserRoleORM.role_id == role_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        user_role = UserRoleORM(
            user_id=user_uuid,
            role_id=role_id,
            assigned_by=user.email,
            assigned_at=now,
        )
        db.add(user_role)

    await db.flush()
    logger.info(f"Assigned users to role {role_id}")

    # Invalidate cache - need to get role's org_id
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role_users:
        role_result = await db.execute(
            select(RoleORM.organization_id).where(RoleORM.id == role_id)
        )
        role_org_id = role_result.scalar_one_or_none()
        org_id_str = str(role_org_id) if role_org_id else None
        await invalidate_role_users(org_id_str, str(role_id))


@router.delete(
    "/{role_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove user from role",
    description="Remove a user from a role",
)
async def remove_user_from_role(
    role_id: UUID,
    user_id: str,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Remove a user from a role."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        result = await db.execute(select(UserORM.id).where(UserORM.email == user_id))
        user_uuid = result.scalar_one_or_none()
        if not user_uuid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    result = await db.execute(
        delete(UserRoleORM).where(
            UserRoleORM.user_id == user_uuid,
            UserRoleORM.role_id == role_id,
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User-role assignment not found",
        )

    logger.info(f"Removed user {user_id} from role {role_id}")

    # Invalidate cache - need to get role's org_id
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role_users:
        role_result = await db.execute(
            select(RoleORM.organization_id).where(RoleORM.id == role_id)
        )
        role_org_id = role_result.scalar_one_or_none()
        org_id_str = str(role_org_id) if role_org_id else None
        await invalidate_role_users(org_id_str, str(role_id))


# =============================================================================
# Role-Form Assignments
# =============================================================================


@router.get(
    "/{role_id}/forms",
    response_model=RoleFormsResponse,
    summary="Get role forms",
    description="Get all forms assigned to a role",
)
async def get_role_forms(
    role_id: UUID,
    user: CurrentSuperuser,
    db: DbSession,
) -> RoleFormsResponse:
    """Get all forms assigned to a role."""
    result = await db.execute(
        select(FormRoleORM.form_id).where(FormRoleORM.role_id == role_id)
    )
    form_ids = [str(fid) for fid in result.scalars().all()]
    return RoleFormsResponse(form_ids=form_ids)


@router.post(
    "/{role_id}/forms",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Assign forms to role",
    description="Assign forms to a role (batch operation)",
)
async def assign_forms_to_role(
    role_id: UUID,
    request: AssignFormsToRoleRequest,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Assign forms to a role."""
    now = datetime.utcnow()

    for form_id_str in request.form_ids:
        form_uuid = UUID(form_id_str)

        # Verify form exists before creating assignment
        form_result = await db.execute(
            select(FormORM.id).where(FormORM.id == form_uuid)
        )
        if not form_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Form with ID '{form_id_str}' not found",
            )

        # Check if already assigned
        existing = await db.execute(
            select(FormRoleORM).where(
                FormRoleORM.form_id == form_uuid,
                FormRoleORM.role_id == role_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        form_role = FormRoleORM(
            form_id=form_uuid,
            role_id=role_id,
            assigned_by=user.email,
            assigned_at=now,
        )
        db.add(form_role)

    await db.flush()
    logger.info(f"Assigned forms to role {role_id}")

    # Invalidate cache - need to get role's org_id
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role_forms:
        role_result = await db.execute(
            select(RoleORM.organization_id).where(RoleORM.id == role_id)
        )
        role_org_id = role_result.scalar_one_or_none()
        org_id_str = str(role_org_id) if role_org_id else None
        await invalidate_role_forms(org_id_str, str(role_id))


@router.delete(
    "/{role_id}/forms/{form_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove form from role",
    description="Remove a form from a role",
)
async def remove_form_from_role(
    role_id: UUID,
    form_id: UUID,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Remove a form from a role."""
    result = await db.execute(
        delete(FormRoleORM).where(
            FormRoleORM.form_id == form_id,
            FormRoleORM.role_id == role_id,
        )
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Form-role assignment not found",
        )

    logger.info(f"Removed form {form_id} from role {role_id}")

    # Invalidate cache - need to get role's org_id
    if CACHE_INVALIDATION_AVAILABLE and invalidate_role_forms:
        role_result = await db.execute(
            select(RoleORM.organization_id).where(RoleORM.id == role_id)
        )
        role_org_id = role_result.scalar_one_or_none()
        org_id_str = str(role_org_id) if role_org_id else None
        await invalidate_role_forms(org_id_str, str(role_id))
