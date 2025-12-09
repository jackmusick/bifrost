"""
SDK Router

Endpoints for the Bifrost SDK:
- Developer context (default organization, parameters)
- API key management
- SDK package download
- File operations (read, write, list, delete)
- Config operations (get, set, list, delete)
"""

import hashlib
import io
import json
import logging
import os
import secrets
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser
from src.core.database import get_db
from src.models.orm import DeveloperApiKey, DeveloperContext, Organization, User
from src.models.models import (
    SDKFileReadRequest,
    SDKFileWriteRequest,
    SDKFileListRequest,
    SDKFileDeleteRequest,
    SDKConfigGetRequest,
    SDKConfigSetRequest,
    SDKConfigListRequest,
    SDKConfigDeleteRequest,
    SDKConfigValue,
)
from src.core.cache import config_hash_key, get_redis

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
# SDK File Operations
# =============================================================================

# File storage paths (same as bifrost/files.py)
WORKSPACE_FILES_DIR = Path(os.getenv("BIFROST_WORKSPACE_LOCATION", "/mounts/workspace"))
TEMP_FILES_DIR = Path(os.getenv("BIFROST_TEMP_LOCATION", "/mounts/tmp"))


def _resolve_sdk_file_path(path: str, location: str) -> Path:
    """
    Resolve and validate a file path for SDK operations.

    Args:
        path: Relative path
        location: Storage location ("temp" or "workspace")

    Returns:
        Path: Resolved absolute path

    Raises:
        ValueError: If path is outside allowed directories
    """
    if location == "temp":
        base_dir = TEMP_FILES_DIR
    else:  # workspace
        base_dir = WORKSPACE_FILES_DIR

    p = Path(path)

    # If relative, resolve against base directory
    if not p.is_absolute():
        p = base_dir / p

    # Resolve to absolute path
    try:
        p = p.resolve()
    except Exception as e:
        raise ValueError(f"Invalid path: {path}") from e

    # Validate path is within allowed directory
    if not str(p).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path must be within {location} directory: {path}")

    return p


@router.post(
    "/files/read",
    summary="Read file content",
    description="Read a file from workspace or temp storage (requires API key)",
)
async def sdk_read_file(
    request: SDKFileReadRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> str:
    """Read a file via SDK API."""
    try:
        file_path = _resolve_sdk_file_path(request.path, request.location)

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {request.path}",
            )

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/files/write",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Write file content",
    description="Write content to a file in workspace or temp storage (requires API key)",
)
async def sdk_write_file(
    request: SDKFileWriteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> None:
    """Write a file via SDK API."""
    try:
        file_path = _resolve_sdk_file_path(request.path, request.location)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.content)

        logger.info(f"SDK wrote file {request.path} for user {current_user.email}")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/files/list",
    summary="List files in directory",
    description="List files in a directory (requires API key)",
)
async def sdk_list_files(
    request: SDKFileListRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> list[str]:
    """List files in a directory via SDK API."""
    try:
        dir_path = _resolve_sdk_file_path(request.directory or "", request.location)

        if not dir_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory not found: {request.directory}",
            )

        if not dir_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not a directory: {request.directory}",
            )

        return [item.name for item in dir_path.iterdir()]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/files/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete file or directory",
    description="Delete a file or directory (requires API key)",
)
async def sdk_delete_file(
    request: SDKFileDeleteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> None:
    """Delete a file or directory via SDK API."""
    try:
        file_path = _resolve_sdk_file_path(request.path, request.location)

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path not found: {request.path}",
            )

        if file_path.is_dir():
            shutil.rmtree(file_path)
        else:
            file_path.unlink()

        logger.info(f"SDK deleted {request.path} for user {current_user.email}")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# SDK Config Operations
# =============================================================================


async def _get_sdk_org_id(
    user: User,
    requested_org_id: str | None,
    db: AsyncSession,
) -> str | None:
    """
    Get the organization ID for SDK config operations.

    Priority:
    1. Explicit org_id in request
    2. Default org from developer context
    3. None (global scope)
    """
    if requested_org_id:
        return requested_org_id

    # Try to get default org from developer context
    stmt = select(DeveloperContext).where(DeveloperContext.user_id == user.id)
    result = await db.execute(stmt)
    dev_ctx = result.scalar_one_or_none()

    if dev_ctx and dev_ctx.default_org_id:
        return str(dev_ctx.default_org_id)

    return None


@router.post(
    "/config/get",
    response_model=SDKConfigValue | None,
    summary="Get config value",
    description="Get a configuration value from Redis cache (requires API key)",
)
async def sdk_get_config(
    request: SDKConfigGetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> SDKConfigValue | None:
    """Get a config value via SDK API."""
    org_id = await _get_sdk_org_id(current_user, request.org_id, db)

    async with get_redis() as r:
        data = await r.hget(config_hash_key(org_id), request.key)  # type: ignore[misc]

        if data is None:
            return None

        try:
            cache_entry = json.loads(data)
        except json.JSONDecodeError:
            return None

        raw_value = cache_entry.get("value")
        config_type = cache_entry.get("type", "string")

        # Parse value based on type
        if config_type == "json" and isinstance(raw_value, str):
            try:
                raw_value = json.loads(raw_value)
            except json.JSONDecodeError:
                pass
        elif config_type == "bool":
            raw_value = str(raw_value).lower() == "true" if isinstance(raw_value, str) else bool(raw_value)
        elif config_type == "int":
            try:
                raw_value = int(raw_value)
            except (ValueError, TypeError):
                pass

        return SDKConfigValue(
            key=request.key,
            value=raw_value,
            config_type=config_type,
        )


@router.post(
    "/config/set",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set config value",
    description="Set a configuration value (requires API key). Note: For security, this writes directly to the database and invalidates cache.",
)
async def sdk_set_config(
    request: SDKConfigSetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Set a config value via SDK API.

    This endpoint writes directly to the database (not the buffer like internal SDK)
    because there's no execution context to flush.
    """
    from src.models import Config as ConfigModel
    from src.models.enums import ConfigType as ConfigTypeEnum

    org_id = await _get_sdk_org_id(current_user, request.org_id, db)
    org_uuid = UUID(org_id) if org_id else None
    now = datetime.utcnow()

    # Determine config type
    if request.is_secret:
        from src.core.security import encrypt_secret
        config_type = ConfigTypeEnum.SECRET
        stored_value = encrypt_secret(str(request.value))
    elif isinstance(request.value, dict) or isinstance(request.value, list):
        config_type = ConfigTypeEnum.JSON
        stored_value = request.value
    elif isinstance(request.value, bool):
        config_type = ConfigTypeEnum.BOOL
        stored_value = request.value
    elif isinstance(request.value, int):
        config_type = ConfigTypeEnum.INT
        stored_value = request.value
    else:
        config_type = ConfigTypeEnum.STRING
        stored_value = request.value

    config_value = {"value": stored_value}

    # Check if config exists
    stmt = select(ConfigModel).where(
        ConfigModel.key == request.key,
        ConfigModel.organization_id == org_uuid,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = config_value
        existing.config_type = config_type
        existing.updated_at = now
        existing.updated_by = current_user.email
    else:
        config = ConfigModel(
            key=request.key,
            value=config_value,
            config_type=config_type,
            organization_id=org_uuid,
            created_at=now,
            updated_at=now,
            updated_by=current_user.email,
        )
        db.add(config)

    await db.commit()

    # Invalidate cache
    try:
        from src.core.cache import invalidate_config
        await invalidate_config(org_id, request.key)
    except ImportError:
        pass

    logger.info(f"SDK set config {request.key} for user {current_user.email}")


@router.post(
    "/config/list",
    summary="List config values",
    description="List all configuration values for an organization (requires API key)",
)
async def sdk_list_config(
    request: SDKConfigListRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all config values via SDK API."""
    org_id = await _get_sdk_org_id(current_user, request.org_id, db)

    async with get_redis() as r:
        all_data = await r.hgetall(config_hash_key(org_id))  # type: ignore[misc]

        if not all_data:
            return {}

        config_dict: dict[str, Any] = {}
        for config_key, data in all_data.items():
            try:
                cache_entry = json.loads(data)
            except json.JSONDecodeError:
                continue

            raw_value = cache_entry.get("value")
            config_type = cache_entry.get("type", "string")

            # Parse value based on type
            if config_type == "secret":
                config_dict[config_key] = raw_value if raw_value else "[SECRET]"
            elif config_type == "json" and isinstance(raw_value, str):
                try:
                    config_dict[config_key] = json.loads(raw_value)
                except json.JSONDecodeError:
                    config_dict[config_key] = raw_value
            elif config_type == "bool":
                config_dict[config_key] = str(raw_value).lower() == "true" if isinstance(raw_value, str) else bool(raw_value)
            elif config_type == "int":
                try:
                    config_dict[config_key] = int(raw_value)
                except (ValueError, TypeError):
                    config_dict[config_key] = raw_value
            else:
                config_dict[config_key] = raw_value

        return config_dict


@router.post(
    "/config/delete",
    summary="Delete config value",
    description="Delete a configuration value (requires API key)",
)
async def sdk_delete_config(
    request: SDKConfigDeleteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """Delete a config value via SDK API."""
    from src.models import Config as ConfigModel

    org_id = await _get_sdk_org_id(current_user, request.org_id, db)
    org_uuid = UUID(org_id) if org_id else None

    stmt = select(ConfigModel).where(
        ConfigModel.key == request.key,
        ConfigModel.organization_id == org_uuid,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        return False

    await db.delete(config)
    await db.commit()

    # Invalidate cache
    try:
        from src.core.cache import invalidate_config
        await invalidate_config(org_id, request.key)
    except ImportError:
        pass

    logger.info(f"SDK deleted config {request.key} for user {current_user.email}")
    return True


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

    The package includes:
    - client.py: HTTP client for API communication
    - files.py: File operations (uses API in external mode)
    - config.py: Config operations (uses API in external mode)
    - models.py: Unified SDK models for type safety
    """
    # Find the bifrost package directory
    # It should be at api/bifrost relative to project root
    package_dir = Path(__file__).parent.parent.parent / "bifrost"

    if not package_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SDK package not found",
        )

    # Create tarball in memory
    buffer = io.BytesIO()

    # Files to include from bifrost/ directory
    include_files = {"client.py", "files.py", "config.py"}

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        # Add package files
        for file_path in package_dir.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                if file_path.name in include_files:
                    arcname = f"bifrost/{file_path.relative_to(package_dir)}"
                    tar.add(file_path, arcname=arcname)

        # Create _context.py stub for external SDK
        # This allows the context detection to work (always returns None in external mode)
        context_stub = '''"""
Context stub for external SDK.

In external mode, there's no execution context - all operations use API calls.
"""
from contextvars import ContextVar

# Always None in external SDK - forces API mode
_execution_context: ContextVar[None] = ContextVar("bifrost_execution_context", default=None)
'''
        context_info = tarfile.TarInfo(name="bifrost/_context.py")
        context_bytes = context_stub.encode("utf-8")
        context_info.size = len(context_bytes)
        tar.addfile(context_info, io.BytesIO(context_bytes))

        # Create models.py with unified SDK models for type safety
        models_py = '''"""
Unified SDK Models for Bifrost.

These models are used by both internal (workflow) and external (API) SDK modes.
"""
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class SDKFileReadRequest(BaseModel):
    """Request to read a file via SDK."""
    path: str = Field(..., description="Relative path to file")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")
    model_config = ConfigDict(from_attributes=True)


class SDKFileWriteRequest(BaseModel):
    """Request to write a file via SDK."""
    path: str = Field(..., description="Relative path to file")
    content: str = Field(..., description="File content (text)")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")
    model_config = ConfigDict(from_attributes=True)


class SDKFileListRequest(BaseModel):
    """Request to list files in a directory via SDK."""
    directory: str = Field(default="", description="Directory path (relative)")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")
    model_config = ConfigDict(from_attributes=True)


class SDKFileDeleteRequest(BaseModel):
    """Request to delete a file or directory via SDK."""
    path: str = Field(..., description="Path to file or directory")
    location: Literal["temp", "workspace"] = Field(
        default="workspace", description="Storage location")
    model_config = ConfigDict(from_attributes=True)


class SDKConfigGetRequest(BaseModel):
    """Request to get a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")
    model_config = ConfigDict(from_attributes=True)


class SDKConfigSetRequest(BaseModel):
    """Request to set a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")
    is_secret: bool = Field(
        default=False, description="Whether to encrypt the value")
    model_config = ConfigDict(from_attributes=True)


class SDKConfigListRequest(BaseModel):
    """Request to list config values via SDK."""
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")
    model_config = ConfigDict(from_attributes=True)


class SDKConfigDeleteRequest(BaseModel):
    """Request to delete a config value via SDK."""
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(
        default=None, description="Organization ID (optional, uses context default)")
    model_config = ConfigDict(from_attributes=True)


class SDKConfigValue(BaseModel):
    """Config value response from SDK."""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    config_type: str = Field(..., description="Type of the config")
    model_config = ConfigDict(from_attributes=True)
'''
        models_info = tarfile.TarInfo(name="bifrost/models.py")
        models_bytes = models_py.encode("utf-8")
        models_info.size = len(models_bytes)
        tar.addfile(models_info, io.BytesIO(models_bytes))

        # Create __init__.py for the package
        init_py = '''"""
Bifrost SDK - External client for Bifrost API.

Works with dev API keys for external development and testing.

Usage:
    # Set environment variables
    export BIFROST_DEV_URL=https://your-bifrost-instance.com
    export BIFROST_DEV_KEY=bfsk_xxxxxxxxxxxx

    # Use the SDK
    from bifrost import files, config, get_client

    # File operations
    files.write("data.txt", "Hello, Bifrost!")
    content = files.read("data.txt")

    # Config operations (async)
    import asyncio
    value = asyncio.run(config.get("my_key"))
"""
from .client import BifrostClient, get_client
from .files import files
from .config import config
from .models import (
    SDKFileReadRequest,
    SDKFileWriteRequest,
    SDKFileListRequest,
    SDKFileDeleteRequest,
    SDKConfigGetRequest,
    SDKConfigSetRequest,
    SDKConfigListRequest,
    SDKConfigDeleteRequest,
    SDKConfigValue,
)

__all__ = [
    "BifrostClient",
    "get_client",
    "files",
    "config",
    "SDKFileReadRequest",
    "SDKFileWriteRequest",
    "SDKFileListRequest",
    "SDKFileDeleteRequest",
    "SDKConfigGetRequest",
    "SDKConfigSetRequest",
    "SDKConfigListRequest",
    "SDKConfigDeleteRequest",
    "SDKConfigValue",
]
__version__ = "2.0.0"
'''
        init_info = tarfile.TarInfo(name="bifrost/__init__.py")
        init_bytes = init_py.encode("utf-8")
        init_info.size = len(init_bytes)
        tar.addfile(init_info, io.BytesIO(init_bytes))

        # Create setup.py in memory
        setup_py = """
from setuptools import setup, find_packages

setup(
    name="bifrost-sdk",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.26.0",
        "pydantic>=2.0.0",
    ],
    python_requires=">=3.11",
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
            "Content-Disposition": "attachment; filename=bifrost-sdk-2.0.0.tar.gz",
        },
    )
