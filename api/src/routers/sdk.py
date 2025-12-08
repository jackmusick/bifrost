"""
SDK Router

Endpoints for the Bifrost SDK:
- Developer context (default organization, parameters)
- API key management
- SDK package download
"""

import hashlib
import io
import logging
import secrets
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser
from src.core.database import get_db
from src.models.orm import DeveloperApiKey, DeveloperContext, Organization, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sdk", tags=["SDK"])


# =============================================================================
# Pydantic Models
# =============================================================================


class DeveloperContextResponse(BaseModel):
    """Developer context for SDK initialization."""

    user: dict = Field(description="User information")
    organization: dict | None = Field(description="Default organization")
    default_parameters: dict = Field(default={}, description="Default workflow parameters")
    track_executions: bool = Field(default=True, description="Whether to track executions in history")


class DeveloperContextUpdate(BaseModel):
    """Update developer context settings."""

    default_org_id: UUID | None = Field(default=None, description="Default organization ID")
    default_parameters: dict | None = Field(default=None, description="Default workflow parameters")
    track_executions: bool | None = Field(default=None, description="Track executions in history")


class ApiKeyCreate(BaseModel):
    """Create a new API key."""

    name: str = Field(min_length=1, max_length=100, description="Key name/description")
    expires_in_days: int | None = Field(default=None, ge=1, le=365, description="Days until expiration")


class ApiKeyResponse(BaseModel):
    """API key response (without the actual key)."""

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    use_count: int
    created_at: datetime


class ApiKeyCreated(ApiKeyResponse):
    """Response when creating a new API key (includes the actual key)."""

    key: str = Field(description="The API key (only shown once)")


class ApiKeyList(BaseModel):
    """List of API keys."""

    keys: list[ApiKeyResponse]


# =============================================================================
# Helper Functions
# =============================================================================


def _generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (full_key, key_prefix, key_hash)
    """
    # Generate random bytes for key
    key_suffix = secrets.token_urlsafe(32)

    # Full key format: bfsk_<random>
    full_key = f"bfsk_{key_suffix}"

    # Prefix for display (first 12 chars)
    key_prefix = full_key[:12]

    # SHA-256 hash for storage
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()

    return full_key, key_prefix, key_hash


async def _get_user_from_api_key(
    authorization: str | None,
    db: AsyncSession,
) -> User | None:
    """
    Authenticate user from API key in Authorization header.

    Args:
        authorization: Authorization header value
        db: Database session

    Returns:
        User if authenticated, None otherwise
    """
    if not authorization:
        return None

    # Parse bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]

    # Check if it's an SDK API key (starts with bfsk_)
    if not token.startswith("bfsk_"):
        return None

    # Hash the key and look it up
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    stmt = select(DeveloperApiKey).where(
        DeveloperApiKey.key_hash == key_hash,
        DeveloperApiKey.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None

    # Update usage stats
    await db.execute(
        update(DeveloperApiKey)
        .where(DeveloperApiKey.id == api_key.id)
        .values(
            last_used_at=datetime.utcnow(),
            use_count=DeveloperApiKey.use_count + 1,
        )
    )
    await db.commit()

    # Load user
    stmt = select(User).where(User.id == api_key.user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# =============================================================================
# Dependency
# =============================================================================


async def get_current_user_from_api_key(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency to get current user from SDK API key.

    Raises 401 if not authenticated.
    """
    user = await _get_user_from_api_key(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# =============================================================================
# Context Endpoints
# =============================================================================


@router.get(
    "/context",
    response_model=DeveloperContextResponse,
    summary="Get developer context",
    description="Get development context for SDK initialization (requires API key)",
)
async def get_dev_context(
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> DeveloperContextResponse:
    """
    Get development context for SDK initialization.

    Returns user info, default organization, and workflow parameters.
    """
    # Get developer context
    stmt = select(DeveloperContext).where(DeveloperContext.user_id == current_user.id)
    result = await db.execute(stmt)
    dev_ctx = result.scalar_one_or_none()

    # Get default organization if set
    org_data = None
    if dev_ctx and dev_ctx.default_org_id:
        stmt = select(Organization).where(Organization.id == dev_ctx.default_org_id)
        result = await db.execute(stmt)
        org = result.scalar_one_or_none()
        if org:
            org_data = {
                "id": str(org.id),
                "name": org.name,
                "is_active": org.is_active,
            }

    return DeveloperContextResponse(
        user={
            "id": str(current_user.id),
            "email": current_user.email,
            "name": current_user.name,
        },
        organization=org_data,
        default_parameters=dev_ctx.default_parameters if dev_ctx else {},
        track_executions=dev_ctx.track_executions if dev_ctx else True,
    )


@router.put(
    "/context",
    response_model=DeveloperContextResponse,
    summary="Update developer context",
    description="Update development context settings",
)
async def update_dev_context(
    request: DeveloperContextUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> DeveloperContextResponse:
    """
    Update developer context settings.

    Creates context if it doesn't exist.
    """
    # Get or create developer context
    stmt = select(DeveloperContext).where(DeveloperContext.user_id == current_user.user_id)
    result = await db.execute(stmt)
    dev_ctx = result.scalar_one_or_none()

    if not dev_ctx:
        dev_ctx = DeveloperContext(
            user_id=current_user.user_id,
            default_org_id=request.default_org_id,
            default_parameters=request.default_parameters or {},
            track_executions=request.track_executions if request.track_executions is not None else True,
        )
        db.add(dev_ctx)
    else:
        if request.default_org_id is not None:
            dev_ctx.default_org_id = request.default_org_id
        if request.default_parameters is not None:
            dev_ctx.default_parameters = request.default_parameters
        if request.track_executions is not None:
            dev_ctx.track_executions = request.track_executions

    await db.commit()
    await db.refresh(dev_ctx)

    # Get organization data
    org_data = None
    if dev_ctx.default_org_id:
        stmt = select(Organization).where(Organization.id == dev_ctx.default_org_id)
        result = await db.execute(stmt)
        org = result.scalar_one_or_none()
        if org:
            org_data = {
                "id": str(org.id),
                "name": org.name,
                "is_active": org.is_active,
            }

    return DeveloperContextResponse(
        user={
            "id": str(current_user.user_id),
            "email": current_user.email,
            "name": current_user.name,
        },
        organization=org_data,
        default_parameters=dev_ctx.default_parameters,
        track_executions=dev_ctx.track_executions,
    )


# =============================================================================
# API Key Management
# =============================================================================


@router.get(
    "/keys",
    response_model=ApiKeyList,
    summary="List API keys",
    description="List all API keys for the current user",
)
async def list_api_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyList:
    """List all API keys for the current user."""
    stmt = (
        select(DeveloperApiKey)
        .where(DeveloperApiKey.user_id == current_user.user_id)
        .order_by(DeveloperApiKey.created_at.desc())
    )
    result = await db.execute(stmt)
    keys = result.scalars().all()

    return ApiKeyList(
        keys=[
            ApiKeyResponse(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                is_active=k.is_active,
                expires_at=k.expires_at,
                last_used_at=k.last_used_at,
                use_count=k.use_count,
                created_at=k.created_at,
            )
            for k in keys
        ]
    )


@router.post(
    "/keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key",
    description="Create a new API key for SDK authentication",
)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    """
    Create a new API key.

    The actual key is only returned once - store it securely.
    """
    # Generate key
    full_key, key_prefix, key_hash = _generate_api_key()

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    # Create key record
    api_key = DeveloperApiKey(
        user_id=current_user.user_id,
        name=request.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    logger.info(f"Created API key {key_prefix}... for user {current_user.email}")

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        use_count=api_key.use_count,
        created_at=api_key.created_at,
        key=full_key,
    )


@router.delete(
    "/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete API key",
    description="Delete an API key",
)
async def delete_api_key(
    key_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an API key."""
    # Verify ownership
    stmt = select(DeveloperApiKey).where(
        DeveloperApiKey.id == key_id,
        DeveloperApiKey.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    await db.execute(delete(DeveloperApiKey).where(DeveloperApiKey.id == key_id))
    await db.commit()

    logger.info(f"Deleted API key {api_key.key_prefix}... for user {current_user.email}")


@router.patch(
    "/keys/{key_id}/revoke",
    response_model=ApiKeyResponse,
    summary="Revoke API key",
    description="Revoke (deactivate) an API key without deleting it",
)
async def revoke_api_key(
    key_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    """Revoke an API key (set is_active to False)."""
    # Verify ownership
    stmt = select(DeveloperApiKey).where(
        DeveloperApiKey.id == key_id,
        DeveloperApiKey.user_id == current_user.user_id,
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    await db.commit()
    await db.refresh(api_key)

    logger.info(f"Revoked API key {api_key.key_prefix}... for user {current_user.email}")

    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        is_active=api_key.is_active,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        use_count=api_key.use_count,
        created_at=api_key.created_at,
    )


# =============================================================================
# SDK Download
# =============================================================================


@router.get(
    "/download",
    summary="Download SDK package",
    description="Download the Bifrost SDK as a pip-installable tarball",
)
async def download_sdk() -> StreamingResponse:
    """
    Serve SDK as installable package.

    Returns a tarball that can be installed with:
    pip install https://your-bifrost-instance.com/api/sdk/download
    """
    # Find the bifrost_sdk package directory
    # It should be at api/bifrost_sdk relative to project root
    package_dir = Path(__file__).parent.parent.parent / "bifrost_sdk"

    if not package_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SDK package not found",
        )

    # Create tarball in memory
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        # Add package files
        for file_path in package_dir.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                arcname = f"bifrost_sdk/{file_path.relative_to(package_dir)}"
                tar.add(file_path, arcname=arcname)

        # Create setup.py in memory
        setup_py = """
from setuptools import setup, find_packages

setup(
    name="bifrost-sdk",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.26.0",
        "pydantic>=2.5.0",
    ],
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "bifrost=bifrost_sdk.cli:main",
        ],
    },
)
"""
        setup_info = tarfile.TarInfo(name="setup.py")
        setup_bytes = setup_py.encode("utf-8")
        setup_info.size = len(setup_bytes)
        tar.addfile(setup_info, io.BytesIO(setup_bytes))

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={
            "Content-Disposition": "attachment; filename=bifrost_sdk-1.0.0.tar.gz",
        },
    )
