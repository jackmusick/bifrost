"""
Users Router

List and manage users, view user roles and forms.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from src.core.auth import CurrentSuperuser
from src.core.database import DbSession
from src.core.org_filter import resolve_org_filter, OrgFilterType
from src.models import User as UserORM, UserRole as UserRoleORM, FormRole as FormRoleORM
from src.models import (
    UserCreate,
    UserPublic,
    UserUpdate,
    UserRolesResponse,
    UserFormsResponse,
)
from src.models.enums import UserType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get(
    "",
    response_model=list[UserPublic],
    summary="List users",
    description="List all users with optional filtering by type and organization",
)
async def list_users(
    user: CurrentSuperuser,
    db: DbSession,
    type: str | None = Query(None, description="Filter by user type: 'platform' or 'org'"),
    scope: str | None = Query(
        None,
        description="Filter scope: omit for all (superusers), 'global' for global only, "
        "or org UUID for specific org."
    ),
) -> list[UserPublic]:
    """List users with optional filtering.

    Superusers can filter by scope or see all users.
    Note: Users are not org-scoped resources - they belong to one org.
    """
    # Resolve organization filter based on user permissions
    try:
        filter_type, filter_org = resolve_org_filter(user, scope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Filter out system users (used for API key executions)
    query = select(UserORM).where(
        UserORM.is_active,
        UserORM.user_type != UserType.SYSTEM,
    )

    if type:
        if type.lower() == "platform":
            query = query.where(UserORM.is_superuser.is_(True))
        elif type.lower() == "org":
            query = query.where(UserORM.is_superuser.is_(False))

    # Apply org filter based on scope
    # For users, GLOBAL_ONLY means users without an org (platform admins)
    # ORG_ONLY and ORG_PLUS_GLOBAL filter to specific org
    if filter_type == OrgFilterType.GLOBAL_ONLY:
        query = query.where(UserORM.organization_id.is_(None))
    elif filter_type == OrgFilterType.ORG_ONLY and filter_org is not None:
        # Platform admin filtering to specific org - just that org's users
        query = query.where(UserORM.organization_id == filter_org)
    elif filter_type == OrgFilterType.ORG_PLUS_GLOBAL and filter_org is not None:
        # Org user - their org's users only (users don't cascade like configs)
        query = query.where(UserORM.organization_id == filter_org)
    # ALL: no filter applied

    query = query.order_by(UserORM.email)

    result = await db.execute(query)
    users = result.scalars().all()

    return [UserPublic.model_validate(u) for u in users]


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Create a new user proactively (Platform admin only)",
)
async def create_user(
    request: UserCreate,
    user: CurrentSuperuser,
    db: DbSession,
) -> UserPublic:
    """Create a new user."""
    now = datetime.utcnow()

    new_user = UserORM(
        email=request.email,
        name=request.name,
        hashed_password="",  # No password for admin-created users
        is_active=request.is_active,
        is_superuser=request.is_superuser,
        is_verified=True,  # Trusted since created by admin
        is_registered=False,  # User must complete registration to set password
        user_type=request.user_type,
        organization_id=request.organization_id,
        created_at=now,
        updated_at=now,
    )

    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    logger.info(f"Created user {new_user.email} (id: {new_user.id})")
    return UserPublic.model_validate(new_user)


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Get user details",
    description="Get a specific user's details (Platform admin only)",
)
async def get_user(
    user_id: str,
    user: CurrentSuperuser,
    db: DbSession,
) -> UserPublic:
    """Get a specific user's details."""
    # Try UUID first
    try:
        uuid_id = UUID(user_id)
        result = await db.execute(select(UserORM).where(UserORM.id == uuid_id))
    except ValueError:
        # Fall back to email lookup
        result = await db.execute(select(UserORM).where(UserORM.email == user_id))

    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserPublic.model_validate(db_user)


@router.patch(
    "/{user_id}",
    response_model=UserPublic,
    summary="Update user",
    description="Update user properties including role transitions",
)
async def update_user(
    user_id: str,
    request: UserUpdate,
    user: CurrentSuperuser,
    db: DbSession,
) -> UserPublic:
    """Update a user."""
    # Try UUID first
    try:
        uuid_id = UUID(user_id)
        result = await db.execute(select(UserORM).where(UserORM.id == uuid_id))
    except ValueError:
        result = await db.execute(select(UserORM).where(UserORM.email == user_id))

    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if request.email is not None:
        db_user.email = request.email
    if request.name is not None:
        db_user.name = request.name
    if request.is_active is not None:
        db_user.is_active = request.is_active
    if request.is_superuser is not None:
        db_user.is_superuser = request.is_superuser
        if request.is_superuser:
            # Promoting to platform admin - remove org
            db_user.organization_id = None
    if request.is_verified is not None:
        db_user.is_verified = request.is_verified
    if request.mfa_enabled is not None:
        db_user.mfa_enabled = request.mfa_enabled
    if request.organization_id is not None:
        db_user.organization_id = request.organization_id

    db_user.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(db_user)

    logger.info(f"Updated user {user_id}")
    return UserPublic.model_validate(db_user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user from the system",
)
async def delete_user(
    user_id: str,
    user: CurrentSuperuser,
    db: DbSession,
) -> None:
    """Delete a user (soft delete via is_active)."""
    # Users cannot delete themselves
    if user_id == str(user.user_id) or user_id == user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    # Try UUID first
    try:
        uuid_id = UUID(user_id)
        result = await db.execute(select(UserORM).where(UserORM.id == uuid_id))
    except ValueError:
        result = await db.execute(select(UserORM).where(UserORM.email == user_id))

    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db_user.is_active = False
    db_user.updated_at = datetime.utcnow()

    await db.flush()
    logger.info(f"Deleted user {user_id}")


@router.get(
    "/{user_id}/roles",
    response_model=UserRolesResponse,
    summary="Get user roles",
    description="Get all roles assigned to a user",
)
async def get_user_roles(
    user_id: str,
    user: CurrentSuperuser,
    db: DbSession,
) -> UserRolesResponse:
    """Get all roles assigned to a user."""
    # Get user UUID
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
        select(UserRoleORM.role_id).where(UserRoleORM.user_id == user_uuid)
    )
    role_ids = [str(rid) for rid in result.scalars().all()]

    return UserRolesResponse(role_ids=role_ids)


@router.get(
    "/{user_id}/forms",
    response_model=UserFormsResponse,
    summary="Get user forms",
    description="Get all forms a user can access based on their roles",
)
async def get_user_forms(
    user_id: str,
    user: CurrentSuperuser,
    db: DbSession,
) -> UserFormsResponse:
    """Get all forms a user can access."""
    # Get user
    try:
        uuid_id = UUID(user_id)
        result = await db.execute(select(UserORM).where(UserORM.id == uuid_id))
    except ValueError:
        result = await db.execute(select(UserORM).where(UserORM.email == user_id))

    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user_type = UserType.PLATFORM if db_user.is_superuser else UserType.ORG

    # Platform admins have access to all forms
    if db_user.is_superuser:
        return UserFormsResponse(
            user_type=user_type,
            has_access_to_all_forms=True,
            form_ids=[],
        )

    # Get user's roles
    role_result = await db.execute(
        select(UserRoleORM.role_id).where(UserRoleORM.user_id == db_user.id)
    )
    role_ids = list(role_result.scalars().all())

    if not role_ids:
        return UserFormsResponse(
            user_type=user_type,
            has_access_to_all_forms=False,
            form_ids=[],
        )

    # Get forms for those roles
    form_result = await db.execute(
        select(FormRoleORM.form_id).where(FormRoleORM.role_id.in_(role_ids))
    )
    form_ids = list(set(str(fid) for fid in form_result.scalars().all()))

    return UserFormsResponse(
        user_type=user_type,
        has_access_to_all_forms=False,
        form_ids=form_ids,
    )
