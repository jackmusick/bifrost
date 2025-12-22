"""
CLI Router

Endpoints for the Bifrost CLI:
- Developer context (default organization, parameters)
- API key management
- CLI package download
- File operations (read, write, list, delete)
- Config operations (get, set, list, delete)
- CLI Sessions (register, state, continue, pending, log, result)
"""

import hashlib
import io
import json
import logging
import secrets
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import CurrentUser, get_current_user_optional, UserPrincipal
from src.core.database import get_db
from src.models import DeveloperApiKey, DeveloperContext, Organization, User
from src.models.contracts.cli import (
    CLIConfigDeleteRequest,
    CLIConfigGetRequest,
    CLIConfigListRequest,
    CLIConfigSetRequest,
    CLIConfigValue,
    CLIFileDeleteRequest,
    CLIFileListRequest,
    CLIFileReadRequest,
    CLIFileWriteRequest,
    CLIOAuthGetRequest,
    CLIOAuthGetResponse,
    CLIRegisteredWorkflow,
    CLISessionContinueRequest,
    CLISessionContinueResponse,
    CLISessionExecutionSummary,
    CLISessionListResponse,
    CLISessionLogRequest,
    CLISessionPendingResponse,
    CLISessionRegisterRequest,
    CLISessionResponse,
    CLISessionResultRequest,
    SDKIntegrationsGetRequest,
    SDKIntegrationsGetResponse,
    SDKIntegrationsListMappingsRequest,
    SDKIntegrationsListMappingsResponse,
)
from src.core.cache import config_hash_key, get_redis
from src.core.pubsub import publish_cli_session_update, publish_execution_log, publish_execution_update
from src.repositories.cli_sessions import CLISessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cli", tags=["CLI"])


# =============================================================================
# Pydantic Models (Developer Context & API Keys)
# =============================================================================


class DeveloperContextResponse(BaseModel):
    """Developer context for CLI initialization."""

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
    key_suffix = secrets.token_urlsafe(32)
    full_key = f"bfsk_{key_suffix}"
    key_prefix = full_key[:12]
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_prefix, key_hash


async def _get_user_from_api_key(
    authorization: str | None,
    db: AsyncSession,
) -> User | None:
    """
    Authenticate user from API key in Authorization header.
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    if not token.startswith("bfsk_"):
        return None

    key_hash = hashlib.sha256(token.encode()).hexdigest()

    stmt = select(DeveloperApiKey).where(
        DeveloperApiKey.key_hash == key_hash,
        DeveloperApiKey.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None

    await db.execute(
        update(DeveloperApiKey)
        .where(DeveloperApiKey.id == api_key.id)
        .values(
            last_used_at=datetime.utcnow(),
            use_count=DeveloperApiKey.use_count + 1,
        )
    )
    await db.commit()

    stmt = select(User).where(User.id == api_key.user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _session_to_response(
    session,
    is_connected: bool,
) -> CLISessionResponse:
    """Convert CLISession ORM to response model."""
    from sqlalchemy import inspect as sa_inspect

    executions = []
    # Use SQLAlchemy inspect to check if executions were eagerly loaded
    # This avoids triggering a lazy load which would fail in async context
    state = sa_inspect(session)
    if 'executions' in state.dict and state.dict['executions']:
        for ex in sorted(state.dict['executions'], key=lambda e: e.created_at, reverse=True)[:10]:
            executions.append(CLISessionExecutionSummary(
                id=str(ex.id),
                workflow_name=ex.workflow_name,
                status=ex.status.value if hasattr(ex.status, 'value') else str(ex.status),
                created_at=ex.created_at,
                duration_ms=ex.duration_ms,
            ))

    workflows = []
    if session.workflows:
        for w in session.workflows:
            workflows.append(CLIRegisteredWorkflow(
                name=w.get("name", ""),
                description=w.get("description", ""),
                parameters=w.get("parameters", []),
            ))

    return CLISessionResponse(
        id=str(session.id),
        user_id=str(session.user_id),
        file_path=session.file_path,
        workflows=workflows,
        selected_workflow=session.selected_workflow,
        params=session.params,
        pending=session.pending,
        last_seen=session.last_seen,
        created_at=session.created_at,
        is_connected=is_connected,
        executions=executions,
    )


# =============================================================================
# Dependencies
# =============================================================================


async def get_current_user_from_api_key(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency to get current user from CLI API key."""
    user = await _get_user_from_api_key(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_dual_auth(
    authorization: Annotated[str | None, Header()] = None,
    current_user_session: UserPrincipal | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that accepts EITHER session auth OR API key."""
    if current_user_session:
        stmt = select(User).where(User.id == current_user_session.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

    user = await _get_user_from_api_key(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (session or API key)",
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
)
async def get_dev_context(
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> DeveloperContextResponse:
    """Get development context for CLI initialization."""
    stmt = select(DeveloperContext).where(DeveloperContext.user_id == current_user.id)
    result = await db.execute(stmt)
    dev_ctx = result.scalar_one_or_none()

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
)
async def update_dev_context(
    request: DeveloperContextUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> DeveloperContextResponse:
    """Update developer context settings."""
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
)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    """Create a new API key."""
    full_key, key_prefix, key_hash = _generate_api_key()

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

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
)
async def delete_api_key(
    key_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an API key."""
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
)
async def revoke_api_key(
    key_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    """Revoke an API key (set is_active to False)."""
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
# CLI File Operations
# =============================================================================

WORKSPACE_FILES_DIR = Path("/tmp/bifrost/workspace")
TEMP_FILES_DIR = Path("/tmp/bifrost/tmp")
WORKSPACE_FILES_DIR.mkdir(parents=True, exist_ok=True)
TEMP_FILES_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_cli_file_path(path: str, location: str) -> Path:
    """Resolve and validate a file path for CLI operations."""
    if location == "temp":
        base_dir = TEMP_FILES_DIR
    else:
        base_dir = WORKSPACE_FILES_DIR

    p = Path(path)
    if not p.is_absolute():
        p = base_dir / p

    try:
        p = p.resolve()
    except Exception as e:
        raise ValueError(f"Invalid path: {path}") from e

    if not str(p).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path must be within {location} directory: {path}")

    return p


@router.post(
    "/files/read",
    summary="Read file content",
)
async def cli_read_file(
    request: CLIFileReadRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> str:
    """Read a file via CLI API."""
    try:
        file_path = _resolve_cli_file_path(request.path, request.location)

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
)
async def cli_write_file(
    request: CLIFileWriteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> None:
    """Write a file via CLI API."""
    try:
        file_path = _resolve_cli_file_path(request.path, request.location)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.content)

        logger.info(f"CLI wrote file {request.path} for user {current_user.email}")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/files/list",
    summary="List files in directory",
)
async def cli_list_files(
    request: CLIFileListRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> list[str]:
    """List files in a directory via CLI API."""
    try:
        dir_path = _resolve_cli_file_path(request.directory or "", request.location)

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
)
async def cli_delete_file(
    request: CLIFileDeleteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
) -> None:
    """Delete a file or directory via CLI API."""
    try:
        file_path = _resolve_cli_file_path(request.path, request.location)

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path not found: {request.path}",
            )

        if file_path.is_dir():
            shutil.rmtree(file_path)
        else:
            file_path.unlink()

        logger.info(f"CLI deleted {request.path} for user {current_user.email}")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# =============================================================================
# CLI Config Operations
# =============================================================================


async def _get_cli_org_id(
    user: User,
    requested_org_id: str | None,
    db: AsyncSession,
) -> str | None:
    """Get the organization ID for CLI config operations."""
    if requested_org_id:
        return requested_org_id

    stmt = select(DeveloperContext).where(DeveloperContext.user_id == user.id)
    result = await db.execute(stmt)
    dev_ctx = result.scalar_one_or_none()

    if dev_ctx and dev_ctx.default_org_id:
        return str(dev_ctx.default_org_id)

    return None


@router.post(
    "/config/get",
    response_model=CLIConfigValue | None,
    summary="Get config value",
)
async def cli_get_config(
    request: CLIConfigGetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> CLIConfigValue | None:
    """Get a config value via CLI API."""
    org_id = await _get_cli_org_id(current_user, request.org_id, db)

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

        return CLIConfigValue(
            key=request.key,
            value=raw_value,
            config_type=config_type,
        )


@router.post(
    "/config/set",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set config value",
)
async def cli_set_config(
    request: CLIConfigSetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set a config value via CLI API."""
    from src.models import Config as ConfigModel
    from src.models.enums import ConfigType as ConfigTypeEnum

    org_id = await _get_cli_org_id(current_user, request.org_id, db)
    org_uuid = UUID(org_id) if org_id else None
    now = datetime.utcnow()

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

    try:
        from src.core.cache import invalidate_config
        await invalidate_config(org_id, request.key)
    except ImportError:
        pass

    logger.info(f"CLI set config {request.key} for user {current_user.email}")


@router.post(
    "/config/list",
    summary="List config values",
)
async def cli_list_config(
    request: CLIConfigListRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List all config values via CLI API."""
    org_id = await _get_cli_org_id(current_user, request.org_id, db)

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
)
async def cli_delete_config(
    request: CLIConfigDeleteRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """Delete a config value via CLI API."""
    from src.models import Config as ConfigModel

    org_id = await _get_cli_org_id(current_user, request.org_id, db)
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

    try:
        from src.core.cache import invalidate_config
        await invalidate_config(org_id, request.key)
    except ImportError:
        pass

    logger.info(f"CLI deleted config {request.key} for user {current_user.email}")
    return True


# =============================================================================
# CLI OAuth Operations
# =============================================================================


@router.post(
    "/oauth/get",
    response_model=CLIOAuthGetResponse | None,
    summary="Get OAuth connection data",
)
async def cli_get_oauth(
    request: CLIOAuthGetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> CLIOAuthGetResponse | None:
    """Get OAuth connection data via CLI API."""
    from sqlalchemy import or_
    from src.core.security import decrypt_secret
    from src.models.orm.oauth import OAuthProvider, OAuthToken

    org_id = await _get_cli_org_id(current_user, request.org_id, db)
    org_uuid = UUID(org_id) if org_id else None

    if org_uuid:
        query = select(OAuthProvider).where(
            OAuthProvider.provider_name == request.provider,
            or_(
                OAuthProvider.organization_id == org_uuid,
                OAuthProvider.organization_id.is_(None),
            )
        ).order_by(
            OAuthProvider.organization_id.desc().nulls_last()
        )
    else:
        query = select(OAuthProvider).where(
            OAuthProvider.provider_name == request.provider,
            OAuthProvider.organization_id.is_(None),
        )

    result = await db.execute(query)
    provider = result.scalars().first()

    if not provider:
        logger.warning(f"OAuth provider '{request.provider}' not found for org '{org_id}'")
        return None

    token_query = select(OAuthToken).where(
        OAuthToken.provider_id == provider.id,
        OAuthToken.user_id.is_(None),
    )
    token_result = await db.execute(token_query)
    token = token_result.scalars().first()

    try:
        client_secret_raw = provider.encrypted_client_secret
        client_secret = (
            decrypt_secret(
                client_secret_raw.decode() if isinstance(client_secret_raw, bytes) else client_secret_raw
            )
            if client_secret_raw
            else None
        )

        access_token = None
        refresh_token = None
        expires_at = None

        if token:
            access_token_raw = token.encrypted_access_token
            access_token = (
                decrypt_secret(
                    access_token_raw.decode() if isinstance(access_token_raw, bytes) else access_token_raw
                )
                if access_token_raw
                else None
            )

            refresh_token_raw = token.encrypted_refresh_token
            refresh_token = (
                decrypt_secret(
                    refresh_token_raw.decode() if isinstance(refresh_token_raw, bytes) else refresh_token_raw
                )
                if refresh_token_raw
                else None
            )

            expires_at = token.expires_at.isoformat() if token.expires_at else None

    except Exception as e:
        logger.error(f"Failed to decrypt OAuth credentials: {e}")
        return None

    logger.info(f"CLI retrieved OAuth '{request.provider}' for user {current_user.email}")

    return CLIOAuthGetResponse(
        connection_name=provider.provider_name,
        client_id=provider.client_id,
        client_secret=client_secret,
        authorization_url=provider.authorization_url,
        token_url=provider.token_url,
        scopes=provider.scopes or [],
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


# =============================================================================
# SDK Integrations Endpoints
# =============================================================================


@router.post(
    "/integrations/get",
    response_model=SDKIntegrationsGetResponse | None,
    summary="Get integration data for an organization",
)
async def sdk_integrations_get(
    request: SDKIntegrationsGetRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> SDKIntegrationsGetResponse | None:
    """Get integration mapping data for an organization via SDK."""
    from src.repositories.integrations import IntegrationsRepository
    from src.services.oauth_provider import resolve_url_template

    org_id = await _get_cli_org_id(current_user, request.org_id, db)
    org_uuid = UUID(org_id) if org_id else None

    if not org_uuid:
        logger.warning("SDK integrations.get: No organization ID provided or in context")
        return None

    try:
        repo = IntegrationsRepository(db)
        mapping = await repo.get_integration_for_org(request.name, org_uuid)

        if not mapping:
            logger.debug(f"SDK integrations.get('{request.name}'): mapping not found for org '{org_uuid}'")
            return None

        # Get merged configuration
        config = await repo.get_config_for_mapping(mapping.integration_id, org_uuid)

        # Build the response
        response_data = {
            "integration_id": str(mapping.integration_id),
            "entity_id": mapping.entity_id,
            "entity_name": mapping.entity_name,
            "config": config or {},
            "oauth_client_id": None,
            "oauth_token_url": None,
            "oauth_scopes": None,
        }

        # Add OAuth details if provider is configured
        if mapping.integration and mapping.integration.oauth_provider:
            provider = mapping.integration.oauth_provider
            response_data["oauth_client_id"] = provider.client_id

            # Format scopes as space-separated string
            if provider.scopes:
                response_data["oauth_scopes"] = " ".join(provider.scopes)

            # Resolve OAuth token URL with entity_id
            if provider.token_url:
                resolved_url = resolve_url_template(
                    url=provider.token_url,
                    entity_id=mapping.entity_id,
                    defaults=provider.token_url_defaults,
                )
                response_data["oauth_token_url"] = resolved_url

        logger.info(f"SDK retrieved integration '{request.name}' for user {current_user.email}")
        return SDKIntegrationsGetResponse(**response_data)

    except Exception as e:
        logger.error(f"SDK integrations.get failed: {e}")
        return None


@router.post(
    "/integrations/list_mappings",
    response_model=SDKIntegrationsListMappingsResponse | None,
    summary="List all mappings for an integration",
)
async def sdk_integrations_list_mappings(
    request: SDKIntegrationsListMappingsRequest,
    current_user: User = Depends(get_current_user_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> SDKIntegrationsListMappingsResponse | None:
    """List all mappings for an integration via SDK."""
    from src.repositories.integrations import IntegrationsRepository

    try:
        repo = IntegrationsRepository(db)
        integration = await repo.get_integration_by_name(request.name)

        if not integration:
            logger.warning(f"SDK integrations.list_mappings: integration '{request.name}' not found")
            return None

        mappings = await repo.list_mappings(integration.id)

        logger.info(f"SDK listed {len(mappings)} mappings for integration '{request.name}' for user {current_user.email}")

        items = [
            {
                "organization_id": str(mapping.organization_id),
                "entity_id": mapping.entity_id,
                "entity_name": mapping.entity_name,
                "config": mapping.config,
            }
            for mapping in mappings
        ]

        return SDKIntegrationsListMappingsResponse(items=items)

    except Exception as e:
        logger.error(f"SDK integrations.list_mappings failed: {e}")
        return None


# =============================================================================
# CLI Session Endpoints (Database-backed)
# =============================================================================


@router.post(
    "/sessions",
    summary="Register/create a CLI session",
    response_model=CLISessionResponse,
)
async def register_cli_session(
    request: CLISessionRegisterRequest,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> CLISessionResponse:
    """
    Register workflows discovered by CLI for web UI.

    Called by `bifrost run <file>` to register workflows before
    opening the browser to the CLI session page.
    """
    repo = CLISessionRepository(db)

    # Convert workflows to dict format for storage
    workflows_data = [
        {
            "name": w.name,
            "description": w.description,
            "parameters": [p.model_dump() if hasattr(p, 'model_dump') else p for p in w.parameters],
        }
        for w in request.workflows
    ]

    session = await repo.create_session(
        session_id=UUID(request.session_id),
        user_id=current_user.id,
        file_path=request.file_path,
        workflows=workflows_data,
        selected_workflow=request.selected_workflow,
    )
    await db.commit()

    logger.info(
        f"CLI session registered: {len(request.workflows)} workflows from {request.file_path} "
        f"for user {current_user.email}, session_id={request.session_id}"
    )

    response = _session_to_response(session, is_connected=True)

    # Broadcast state update via websocket
    await publish_cli_session_update(str(current_user.id), request.session_id, response.model_dump(mode="json"))

    return response


@router.get(
    "/sessions",
    summary="List user's CLI sessions",
    response_model=CLISessionListResponse,
)
async def list_cli_sessions(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CLISessionListResponse:
    """List all CLI sessions for the current user."""
    repo = CLISessionRepository(db)
    sessions = await repo.get_user_sessions(current_user.user_id)

    return CLISessionListResponse(
        sessions=[
            _session_to_response(s, is_connected=repo.is_connected(s))
            for s in sessions
        ]
    )


@router.get(
    "/sessions/{session_id}",
    summary="Get CLI session state",
    response_model=CLISessionResponse,
)
async def get_cli_session(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CLISessionResponse:
    """Get current CLI session state for web UI."""
    repo = CLISessionRepository(db)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await repo.get_session_for_user(session_uuid, current_user.user_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return _session_to_response(session, is_connected=repo.is_connected(session))


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete CLI session",
)
async def delete_cli_session(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a CLI session."""
    repo = CLISessionRepository(db)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await repo.get_session_for_user(session_uuid, current_user.user_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    await repo.delete(session)
    await db.commit()

    logger.info(f"CLI session deleted: {session_id} for user {current_user.email}")


@router.post(
    "/sessions/{session_id}/continue",
    summary="Continue workflow execution",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CLISessionContinueResponse,
)
async def continue_cli_session(
    session_id: str,
    request: CLISessionContinueRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CLISessionContinueResponse:
    """
    Submit parameters to continue workflow execution.

    Called by web UI when user clicks "Continue".
    Creates a real Execution record and sets pending=True so CLI can pick up.
    """
    from src.repositories.executions import ExecutionRepository
    from src.models.enums import ExecutionStatus

    repo = CLISessionRepository(db)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await repo.get_session_for_user(session_uuid, current_user.user_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active CLI session. Run `bifrost run <file>` first.",
        )

    # Validate workflow exists
    workflow_names = [w.get("name") for w in session.workflows]
    if request.workflow_name not in workflow_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow '{request.workflow_name}' not found. Available: {workflow_names}",
        )

    # Create a real Execution record
    execution_id = str(uuid4())
    exec_repo = ExecutionRepository(db)

    await exec_repo.create_execution(
        execution_id=execution_id,
        workflow_name=request.workflow_name,
        parameters=request.params,
        org_id=str(current_user.organization_id) if current_user.organization_id else None,
        user_id=str(current_user.user_id),
        user_name=current_user.name or current_user.email,
        status=ExecutionStatus.PENDING,
        is_local_execution=True,
    )

    # Link execution to session
    from src.models.orm import Execution
    stmt = select(Execution).where(Execution.id == UUID(execution_id))
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()
    if execution:
        execution.session_id = session_uuid

    # Update session state
    await repo.set_pending(
        session_uuid,
        request.workflow_name,
        request.params,
    )
    await db.commit()

    logger.info(
        f"CLI session continue: workflow={request.workflow_name}, "
        f"execution_id={execution_id}, session_id={session_id}, user={current_user.email}"
    )

    # Broadcast state update via websocket
    updated_session = await repo.get_session_with_executions(session_uuid)
    if updated_session:
        response_data = _session_to_response(updated_session, is_connected=repo.is_connected(updated_session))
        await publish_cli_session_update(str(current_user.user_id), session_id, response_data.model_dump(mode="json"))

    return CLISessionContinueResponse(
        status="pending",
        execution_id=execution_id,
        workflow=request.workflow_name,
    )


@router.get(
    "/sessions/{session_id}/pending",
    summary="Poll for pending execution",
    response_model=CLISessionPendingResponse,
)
async def get_pending_execution(
    session_id: str,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> CLISessionPendingResponse:
    """
    Poll for pending workflow execution.

    Returns 204 No Content if no execution pending.
    Returns execution_id, params and clears pending flag when execution is ready.
    """
    from src.repositories.executions import ExecutionRepository
    from src.models.enums import ExecutionStatus

    repo = CLISessionRepository(db)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await repo.get_session_for_user(session_uuid, current_user.id)

    if session is None or not session.pending:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No pending execution",
        )

    workflow_name = session.selected_workflow
    params = session.params

    if workflow_name is None or params is None:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No pending execution",
        )

    # Find the most recent pending execution for this session
    from src.models.orm import Execution
    stmt = select(Execution).where(
        Execution.session_id == session_uuid,
        Execution.status == ExecutionStatus.PENDING,
    ).order_by(Execution.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_204_NO_CONTENT,
            detail="No pending execution",
        )

    execution_id = str(execution.id)

    # Update execution status to RUNNING
    exec_repo = ExecutionRepository(db)
    await exec_repo.update_execution(
        execution_id=execution_id,
        status=ExecutionStatus.RUNNING,
    )

    # Clear pending and update last_seen
    await repo.clear_pending(session_uuid)
    await repo.update_last_seen(session_uuid)
    await db.commit()

    # Broadcast execution status update
    await publish_execution_update(execution_id, "Running")

    logger.info(f"CLI session pending picked up: workflow={workflow_name}, execution_id={execution_id}, session_id={session_id}")

    # Broadcast session state update
    updated_session = await repo.get_session_with_executions(session_uuid)
    if updated_session:
        response_data = _session_to_response(updated_session, is_connected=repo.is_connected(updated_session))
        await publish_cli_session_update(str(current_user.id), session_id, response_data.model_dump(mode="json"))

    return CLISessionPendingResponse(
        execution_id=execution_id,
        workflow_name=workflow_name,
        params=params,
    )


@router.post(
    "/sessions/{session_id}/heartbeat",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update session heartbeat",
)
async def session_heartbeat(
    session_id: str,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Update session's last_seen timestamp (CLI heartbeat)."""
    repo = CLISessionRepository(db)

    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format",
        )

    session = await repo.get_session_for_user(session_uuid, current_user.id)
    if session:
        await repo.update_last_seen(session_uuid)
        await db.commit()


@router.post(
    "/sessions/{session_id}/executions/{execution_id}/log",
    summary="Stream log entry from CLI",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_cli_log(
    session_id: str,
    execution_id: str,
    request: CLISessionLogRequest,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Stream a log entry from CLI to the execution."""
    from src.models.orm import Execution

    try:
        exec_uuid = UUID(execution_id)
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format",
        )

    stmt = select(Execution).where(
        Execution.id == exec_uuid,
        Execution.session_id == session_uuid,
        Execution.executed_by == current_user.id,
        Execution.is_local_execution == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found or not authorized",
        )

    timestamp = None
    if request.timestamp:
        try:
            # Parse timestamp and strip timezone to match engine behavior
            # (engine uses datetime.utcnow() which is timezone-naive)
            ts = datetime.fromisoformat(request.timestamp.replace("Z", "+00:00"))
            timestamp = ts.replace(tzinfo=None) if ts.tzinfo else ts
        except ValueError:
            timestamp = datetime.utcnow()

    try:
        # Use unified log function - same as workflow engine
        # Writes to Redis Stream (for persistence) AND publishes to PubSub (for WebSocket)
        from bifrost._logging import log_and_broadcast_async

        await log_and_broadcast_async(
            execution_id=execution_id,
            level=request.level,
            message=request.message,
            metadata=request.metadata,
            timestamp=timestamp,
        )
    except ImportError:
        logger.warning(f"Log streaming not available, log skipped: {request.message}")


@router.post(
    "/sessions/{session_id}/executions/{execution_id}/result",
    summary="Post execution result from CLI",
    status_code=status.HTTP_200_OK,
)
async def post_cli_result(
    session_id: str,
    execution_id: str,
    request: CLISessionResultRequest,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Post execution result from CLI."""
    from src.models.orm import Execution
    from src.models.enums import ExecutionStatus
    from src.repositories.executions import ExecutionRepository

    try:
        exec_uuid = UUID(execution_id)
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format",
        )

    stmt = select(Execution).where(
        Execution.id == exec_uuid,
        Execution.session_id == session_uuid,
        Execution.executed_by == current_user.id,
        Execution.is_local_execution == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found or not authorized",
        )

    if request.status.lower() in ("success", "completed"):
        status_enum = ExecutionStatus.SUCCESS
    else:
        status_enum = ExecutionStatus.FAILED

    repo = ExecutionRepository(db)
    await repo.update_execution(
        execution_id=execution_id,
        status=status_enum,
        result=request.result,
        error_message=request.error_message,
        duration_ms=request.duration_ms,  # completed_at is set automatically when duration_ms is provided
    )

    # Persist logs directly from request (avoids race conditions)
    logs_persisted = 0
    if request.logs:
        from src.models.orm import ExecutionLog
        from datetime import datetime as dt

        logs_to_insert = []
        for seq, log in enumerate(request.logs):
            try:
                # Parse timestamp, strip timezone for DB
                if log.timestamp:
                    ts = dt.fromisoformat(log.timestamp)
                    if ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)
                else:
                    ts = dt.utcnow()

                log_entry = ExecutionLog(
                    execution_id=exec_uuid,
                    level=log.level.upper(),
                    message=log.message,
                    log_metadata=log.metadata,
                    timestamp=ts,
                    sequence=seq,
                )
                logs_to_insert.append(log_entry)

                # Also broadcast to WebSocket for real-time UI update
                await publish_execution_log(
                    execution_id,
                    log.level,
                    log.message,
                    {"metadata": log.metadata, "timestamp": ts.isoformat()},
                )
            except Exception as e:
                logger.warning(f"Failed to process log entry: {e}")
                continue

        if logs_to_insert:
            db.add_all(logs_to_insert)
            logs_persisted = len(logs_to_insert)
            logger.debug(f"Persisted {logs_persisted} logs directly for CLI execution {execution_id}")

    await db.commit()

    # Fallback: flush any logs from Redis Stream (backwards compatibility)
    logs_flushed = 0
    if not request.logs:
        try:
            from bifrost._logging import flush_logs_to_postgres
            logs_flushed = await flush_logs_to_postgres(execution_id)
            if logs_flushed > 0:
                logger.debug(f"Flushed {logs_flushed} logs from stream for CLI execution {execution_id}")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to flush logs from stream: {e}")

    # Match workflow engine format exactly for unified UI handling
    update_data: dict[str, Any] = {
        "result": request.result,
        "durationMs": request.duration_ms if request.duration_ms else 0,
    }
    if request.error_message:
        update_data["error"] = request.error_message

    await publish_execution_update(
        execution_id,
        status_enum.value,
        update_data,
    )

    # Broadcast updated session state
    session_repo = CLISessionRepository(db)
    updated_session = await session_repo.get_session_with_executions(session_uuid)
    if updated_session:
        response_data = _session_to_response(updated_session, is_connected=session_repo.is_connected(updated_session))
        await publish_cli_session_update(str(current_user.id), session_id, response_data.model_dump(mode="json"))

    total_logs = logs_persisted + logs_flushed
    logger.info(
        f"CLI result: execution_id={execution_id}, session_id={session_id}, status={status_enum.value}, "
        f"logs_persisted={logs_persisted}, logs_flushed={logs_flushed}, user={current_user.email}"
    )

    return {
        "status": status_enum.value,
        "logs_persisted": logs_persisted,
        "logs_flushed": logs_flushed,
        "total_logs": total_logs,
    }


# =============================================================================
# CLI Download (generates installable package)
# =============================================================================


@router.get(
    "/download",
    summary="Download CLI package",
    description="Download the Bifrost CLI as a pip-installable tarball",
)
async def download_cli() -> StreamingResponse:
    """
    Serve CLI as installable package.

    Returns a tarball that can be installed with:
    pip install https://your-bifrost-instance.com/api/cli/download
    """
    package_dir = Path(__file__).parent.parent.parent / "bifrost"

    if not package_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CLI package not found",
        )

    buffer = io.BytesIO()
    include_files = {"client.py", "files.py", "config.py", "oauth.py"}

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for file_path in package_dir.rglob("*"):
            if file_path.is_file() and "__pycache__" not in str(file_path):
                if file_path.name in include_files:
                    arcname = f"bifrost/{file_path.relative_to(package_dir)}"
                    tar.add(file_path, arcname=arcname)

        # Create generated files inline (context, decorators, errors, cli, models, __init__, pyproject.toml)
        # These are generated with /api/cli/* paths instead of /api/sdk/*

        _add_generated_files_to_tarball(tar)

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={
            "Content-Disposition": "attachment; filename=bifrost-cli-2.0.0.tar.gz",
        },
    )


def _add_generated_files_to_tarball(tar: tarfile.TarFile) -> None:
    """Add generated Python files to the tarball."""

    # _context.py
    context_py = '''"""
Execution context for external Bifrost CLI.
"""
from contextvars import ContextVar
from typing import Any


class _ExternalContextProxy:
    """Context proxy that fetches developer context from API."""

    def __init__(self):
        self._cached: dict[str, Any] | None = None

    def _get_context(self) -> dict[str, Any]:
        if self._cached is None:
            from .client import get_client
            client = get_client()
            self._cached = client.context
        return self._cached

    def _clear_cache(self) -> None:
        self._cached = None

    @property
    def user_id(self) -> str:
        return self._get_context().get("user", {}).get("id", "")

    @property
    def email(self) -> str:
        return self._get_context().get("user", {}).get("email", "")

    @property
    def name(self) -> str:
        return self._get_context().get("user", {}).get("name", "")

    @property
    def org_id(self) -> str | None:
        org = self._get_context().get("organization")
        return org.get("id") if org else None

    @property
    def org_name(self) -> str | None:
        org = self._get_context().get("organization")
        return org.get("name") if org else None

    @property
    def organization(self) -> dict | None:
        return self._get_context().get("organization")

    @property
    def scope(self) -> str:
        return self.org_id or "GLOBAL"

    @property
    def default_parameters(self) -> dict[str, Any]:
        return self._get_context().get("default_parameters", {})

    @property
    def track_executions(self) -> bool:
        return self._get_context().get("track_executions", True)


context = _ExternalContextProxy()
_execution_context: ContextVar[None] = ContextVar("bifrost_execution_context", default=None)
'''
    _add_file_to_tar(tar, "bifrost/_context.py", context_py)

    # errors.py
    errors_py = '''"""Custom exception classes for Bifrost workflows."""


class UserError(Exception):
    """Exception that displays its message to end users."""
    pass


class WorkflowError(Exception):
    """Base class for workflow-related errors."""
    pass


class ValidationError(WorkflowError):
    """Raised when workflow input validation fails."""
    pass


class IntegrationError(WorkflowError):
    """Raised when integration with external service fails."""
    pass


class ConfigurationError(WorkflowError):
    """Raised when workflow configuration is invalid."""
    pass
'''
    _add_file_to_tar(tar, "bifrost/errors.py", errors_py)

    # decorators.py (abbreviated for space - full version in production)
    decorators_py = _get_decorators_py()
    _add_file_to_tar(tar, "bifrost/decorators.py", decorators_py)

    # cli.py - the main CLI entry point with /api/cli/* paths
    cli_py = _get_cli_runner_py()
    _add_file_to_tar(tar, "bifrost/cli.py", cli_py)

    # __main__.py
    main_py = '''"""Entry point for python -m bifrost."""
from .cli import main

if __name__ == "__main__":
    main()
'''
    _add_file_to_tar(tar, "bifrost/__main__.py", main_py)

    # models.py
    models_py = _get_models_py()
    _add_file_to_tar(tar, "bifrost/models.py", models_py)

    # __init__.py
    init_py = '''"""
Bifrost CLI - External client for Bifrost API.

Usage:
    export BIFROST_DEV_URL=https://your-bifrost-instance.com
    export BIFROST_DEV_KEY=bfsk_xxxxxxxxxxxx

    from bifrost import workflow, context, config

    @workflow(category="Admin")
    async def my_workflow(name: str) -> dict:
        return {"message": f"Hello {name}"}

    # bifrost run my_workflows.py
"""
from .client import BifrostClient, get_client
from .files import files
from .config import config
from .oauth import oauth
from ._context import context
from .decorators import workflow, data_provider, WorkflowMetadata, DataProviderMetadata, WorkflowParameter
from .errors import UserError, WorkflowError, ValidationError, IntegrationError, ConfigurationError

__all__ = [
    "BifrostClient", "get_client",
    "files", "config", "oauth", "context",
    "workflow", "data_provider", "WorkflowMetadata", "DataProviderMetadata", "WorkflowParameter",
    "UserError", "WorkflowError", "ValidationError", "IntegrationError", "ConfigurationError",
]
__version__ = "2.0.0"
'''
    _add_file_to_tar(tar, "bifrost/__init__.py", init_py)

    # pyproject.toml
    pyproject_toml = """
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bifrost-cli"
version = "2.0.0"
description = "Bifrost Platform CLI for workflow automation"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.26.0",
    "pydantic>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
bifrost = "bifrost.cli:main"

[tool.setuptools]
packages = ["bifrost"]
"""
    _add_file_to_tar(tar, "pyproject.toml", pyproject_toml)


def _add_file_to_tar(tar: tarfile.TarFile, name: str, content: str) -> None:
    """Add a file to the tarball."""
    info = tarfile.TarInfo(name=name)
    content_bytes = content.encode("utf-8")
    info.size = len(content_bytes)
    tar.addfile(info, io.BytesIO(content_bytes))


def _get_decorators_py() -> str:
    """Return the decorators.py content."""
    return '''"""Bifrost decorators for workflow development."""
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Union, get_args, get_origin

TYPE_MAPPING: dict[type, str] = {
    str: "string", int: "int", float: "float", bool: "bool", list: "list", dict: "json",
}


@dataclass
class WorkflowParameter:
    name: str
    type: str
    label: str | None = None
    required: bool = False
    default_value: Any | None = None
    options: list[dict[str, str]] | None = None  # For Literal types


@dataclass
class WorkflowMetadata:
    id: str | None = None
    name: str = ""
    description: str = ""
    category: str = "General"
    tags: list[str] = field(default_factory=list)
    execution_mode: Literal["sync", "async"] = "async"
    timeout_seconds: int = 1800
    retry_policy: dict[str, Any] | None = None
    schedule: str | None = None
    endpoint_enabled: bool = False
    allowed_methods: list[str] = field(default_factory=lambda: ["POST"])
    disable_global_key: bool = False
    public_endpoint: bool = False
    source_file_path: str | None = None
    parameters: list[WorkflowParameter] = field(default_factory=list)
    function: Any = None


@dataclass
class DataProviderMetadata:
    name: str = ""
    description: str = ""
    category: str = "General"
    cache_ttl_seconds: int = 300
    function: Any = None
    parameters: list[WorkflowParameter] = field(default_factory=list)
    source: str | None = None
    source_file_path: str | None = None


def _get_ui_type(python_type: Any) -> str:
    if python_type is type(None):
        return "string"
    if python_type in TYPE_MAPPING:
        return TYPE_MAPPING[python_type]
    origin = get_origin(python_type)
    # Handle Literal types - infer base type from values
    if origin is Literal:
        args = get_args(python_type)
        if args:
            first_val = args[0]
            if isinstance(first_val, str):
                return "string"
            elif isinstance(first_val, bool):
                return "bool"
            elif isinstance(first_val, int):
                return "int"
            elif isinstance(first_val, float):
                return "float"
        return "string"
    if origin is list:
        return "list"
    if origin is dict:
        return "json"
    if origin is Union:
        args = get_args(python_type)
        non_none = [t for t in args if t is not type(None)]
        if non_none:
            return _get_ui_type(non_none[0])
    return "json"


def _get_literal_options(python_type: Any) -> list[dict[str, str]] | None:
    """Extract options from Literal type."""
    origin = get_origin(python_type)
    if origin is Literal:
        args = get_args(python_type)
        return [{"label": str(v), "value": str(v)} for v in args]
    if origin is Union:
        args = get_args(python_type)
        for arg in args:
            if arg is not type(None):
                options = _get_literal_options(arg)
                if options:
                    return options
    return None


def _is_optional(python_type: Any) -> bool:
    origin = get_origin(python_type)
    if origin is Union:
        return type(None) in get_args(python_type)
    return False


def _extract_parameters(func: Callable) -> list[WorkflowParameter]:
    params = []
    try:
        sig = inspect.signature(func)
        hints = getattr(func, "__annotations__", {})
        for name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name == "context":
                continue
            param_type = hints.get(name, param.annotation)
            has_default = param.default is not inspect.Parameter.empty
            default_val = param.default if has_default else None
            if param_type is inspect.Parameter.empty:
                ui_type = "string"
                is_optional = has_default
                options = None
            else:
                ui_type = _get_ui_type(param_type)
                is_optional = _is_optional(param_type) or has_default
                options = _get_literal_options(param_type)
            label = name.replace("_", " ").title()
            wp = WorkflowParameter(name=name, type=ui_type, required=not is_optional, label=label, options=options)
            if has_default and default_val is not None:
                if isinstance(default_val, (str, int, float, bool, list, dict)):
                    wp.default_value = default_val
            params.append(wp)
    except Exception:
        pass
    return params


def workflow(
    _func: Callable | None = None,
    *,
    id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    category: str = "General",
    tags: list[str] | None = None,
    execution_mode: Literal["sync", "async"] | None = None,
    timeout_seconds: int = 1800,
    retry_policy: dict[str, Any] | None = None,
    schedule: str | None = None,
    endpoint_enabled: bool = False,
    allowed_methods: list[str] | None = None,
    disable_global_key: bool = False,
    public_endpoint: bool = False,
):
    def decorator(func: Callable) -> Callable:
        wf_name = name or func.__name__
        wf_desc = description
        if wf_desc is None and func.__doc__:
            wf_desc = func.__doc__.strip().split("\\n")[0].strip()
        wf_desc = wf_desc or ""
        source_path = func.__code__.co_filename if hasattr(func, "__code__") else None
        metadata = WorkflowMetadata(
            id=id, name=wf_name, description=wf_desc, category=category,
            tags=tags or [], execution_mode=execution_mode or ("sync" if endpoint_enabled else "async"),
            timeout_seconds=timeout_seconds, retry_policy=retry_policy, schedule=schedule,
            endpoint_enabled=endpoint_enabled, allowed_methods=allowed_methods or ["POST"],
            disable_global_key=disable_global_key, public_endpoint=public_endpoint,
            source_file_path=source_path, parameters=_extract_parameters(func), function=func,
        )
        func._workflow_metadata = metadata
        return func
    if _func is not None:
        return decorator(_func)
    return decorator


def data_provider(
    _func: Callable | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    category: str = "General",
    cache_ttl_seconds: int = 300,
):
    def decorator(func: Callable) -> Callable:
        dp_name = name or func.__name__
        dp_desc = description
        if dp_desc is None and func.__doc__:
            dp_desc = func.__doc__.strip().split("\\n")[0].strip()
        dp_desc = dp_desc or ""
        source_path = func.__code__.co_filename if hasattr(func, "__code__") else None
        metadata = DataProviderMetadata(
            name=dp_name, description=dp_desc, category=category,
            cache_ttl_seconds=cache_ttl_seconds, parameters=_extract_parameters(func),
            function=func, source_file_path=source_path,
        )
        func._data_provider_metadata = metadata
        return func
    if _func is not None:
        return decorator(_func)
    return decorator
'''


def _get_cli_runner_py() -> str:
    """Return the cli.py content with /api/cli/* paths."""
    return '''"""
Bifrost CLI for local workflow execution.

Usage:
    bifrost run my_workflows.py
    bifrost run my_workflows.py --workflow greet_user
"""
import argparse
import asyncio
import importlib.util
import json
import logging
import os
import sys
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any


def is_html_result(result: Any) -> bool:
    """Check if result looks like HTML content.

    Mirrors backend detection in executions.py:150:
    result.strip().startswith("<")
    """
    if not isinstance(result, str):
        return False
    return result.strip().startswith("<")


def format_result_for_terminal(result: Any, session_url: str | None = None) -> str:
    """Format result for terminal output, masking HTML like the web terminal does."""
    if is_html_result(result):
        # Mirror web terminal's "Click to view HTML result" messaging
        if session_url:
            return f"[HTML Result] Click to view in session: {session_url}"
        else:
            return "[HTML Result] Run with web UI to view HTML results"
    return json.dumps(result, indent=2, default=str)


class BifrostLoggingHandler(logging.Handler):
    """Captures Python logging and forwards to Bifrost API.

    Uses synchronous HTTP requests to ensure logs are sent in order and complete
    before continuing, matching the engine's behavior with synchronous Redis.
    """

    def __init__(self, runner_logger: "LocalRunnerLogger", workflow_file: str):
        super().__init__()
        self.runner_logger = runner_logger
        self.workflow_basename = os.path.basename(workflow_file)
        self.workflow_dir = os.path.dirname(os.path.abspath(workflow_file))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            is_root_log = record.name == "root"
            record_basename = os.path.basename(record.pathname) if record.pathname else ""
            is_workflow_file = record_basename == self.workflow_basename
            record_dir = os.path.dirname(os.path.abspath(record.pathname)) if record.pathname else ""
            is_same_dir = record_dir.startswith(self.workflow_dir)
            if not (is_root_log or is_workflow_file or is_same_dir):
                return
            msg = self.format(record)
            level = record.levelname.upper()
            # Use synchronous logging to ensure logs complete in order
            # This matches the engine's sync Redis approach
            self.runner_logger.log_sync(level, msg)
        except Exception:
            pass


class LocalRunnerLogger:
    def __init__(self, client, session_id: str, execution_id: str, workflow_file: str):
        self.client = client
        self.session_id = session_id
        self.execution_id = execution_id
        self.workflow_file = workflow_file
        self.start_time = time.time()
        self._handler = None
        # Collect logs in memory to send with result (avoids race conditions)
        self._logs: list[dict] = []

    def install_logging_handler(self) -> None:
        self._handler = BifrostLoggingHandler(self, self.workflow_file)
        self._handler.setLevel(logging.DEBUG)
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        # Set root logger level to capture DEBUG/INFO (matches engine behavior)
        # Without this, DEBUG/INFO logs are filtered at the logger level before
        # reaching the handler, even though handler.setLevel(DEBUG) is set
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger().addHandler(self._handler)

    def uninstall_logging_handler(self) -> None:
        if self._handler:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    def log_sync(self, level: str, message: str, metadata: dict | None = None) -> None:
        """Synchronous log method used by BifrostLoggingHandler.

        Collects logs in memory to be sent with the result.
        This avoids race conditions from multiple HTTP requests.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        colors = {"DEBUG": "\033[90m", "INFO": "\033[0m", "WARNING": "\033[93m", "ERROR": "\033[91m"}
        print(f"{colors.get(level.upper(), '')}[{level.upper()}] {message}\033[0m")
        # Collect log instead of POSTing immediately
        self._logs.append({
            "level": level.upper(),
            "message": message,
            "timestamp": timestamp,
            "metadata": metadata,
        })

    async def log(self, level: str, message: str, metadata: dict | None = None) -> None:
        """Async log method for direct calls from workflow code."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        colors = {"DEBUG": "\033[90m", "INFO": "\033[0m", "WARNING": "\033[93m", "ERROR": "\033[91m"}
        print(f"{colors.get(level.upper(), '')}[{level.upper()}] {message}\033[0m")
        # Collect log instead of POSTing immediately
        self._logs.append({
            "level": level.upper(),
            "message": message,
            "timestamp": timestamp,
            "metadata": metadata,
        })

    async def debug(self, message: str, metadata: dict | None = None) -> None:
        await self.log("DEBUG", message, metadata)

    async def info(self, message: str, metadata: dict | None = None) -> None:
        await self.log("INFO", message, metadata)

    async def warning(self, message: str, metadata: dict | None = None) -> None:
        await self.log("WARNING", message, metadata)

    async def error(self, message: str, metadata: dict | None = None) -> None:
        await self.log("ERROR", message, metadata)

    async def complete(self, status: str, result: Any = None, error: str | None = None) -> None:
        duration_ms = int((time.time() - self.start_time) * 1000)
        try:
            # Send all logs with the result in a single request
            # This eliminates race conditions from multiple HTTP requests
            await self.client.post(
                f"/api/cli/sessions/{self.session_id}/executions/{self.execution_id}/result",
                json={
                    "status": status,
                    "result": result,
                    "error_message": error,
                    "duration_ms": duration_ms,
                    "logs": self._logs,
                },
            )
        except Exception as e:
            print(f"\033[91m[ERROR] Failed to post result: {e}\033[0m")


def discover_workflows(module) -> list[dict]:
    workflows = []
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and hasattr(obj, "_workflow_metadata"):
            meta = obj._workflow_metadata
            workflows.append({
                "name": meta.name, "description": meta.description,
                "parameters": [{"name": p.name, "type": p.type, "label": p.label, "required": p.required, "default_value": p.default_value} for p in meta.parameters],
                "_func": obj,
            })
    return workflows


async def run_with_web_ui(file_path: str, workflow_name: str | None, inline_params: dict | None, open_browser: bool = False):
    from .client import get_client

    spec = importlib.util.spec_from_file_location("workflow_module", file_path)
    module = importlib.util.module_from_spec(spec)

    # Add CWD (workspace root) to sys.path for imports like "from modules.x import y"
    # This matches the platform behavior where /tmp/bifrost/workspace is in sys.path
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # Also add workflow file's parent directory for relative imports within that directory
    sys.path.insert(0, str(Path(file_path).parent))

    spec.loader.exec_module(module)

    workflows = discover_workflows(module)
    if not workflows:
        print("No @workflow decorated functions found")
        sys.exit(1)

    workflow_map = {w["name"]: w["_func"] for w in workflows}

    if inline_params and workflow_name:
        func = workflow_map.get(workflow_name)
        if not func:
            print(f"Workflow '{workflow_name}' not found. Available: {', '.join(workflow_map.keys())}")
            sys.exit(1)
        print(f"Running {workflow_name}...")
        try:
            result = await func(**inline_params) if asyncio.iscoroutinefunction(func) else func(**inline_params)
            print(f"Result: {format_result_for_terminal(result)}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    client = get_client()
    abs_path = str(Path(file_path).resolve())

    session_id = str(uuid.uuid4())

    workflows_for_api = [{k: v for k, v in w.items() if k != "_func"} for w in workflows]
    try:
        response = await client.post("/api/cli/sessions", json={
            "session_id": session_id,
            "file_path": abs_path,
            "workflows": workflows_for_api,
            "selected_workflow": workflow_name,
        })
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to register with API: {e}")
        await run_with_terminal_input(workflows, workflow_map, workflow_name)
        return

    base_url = client.api_url.rstrip("/")
    if base_url.endswith("/api"):
        base_url = base_url[:-4]
    url = f"{base_url}/cli/{session_id}"

    # Open browser or just print URL
    if open_browser:
        webbrowser.open(url)
        print(f"Opened browser (session: {session_id[:8]}...)")
    else:
        print(f"\\033[96m\\U0001F517 Web UI: {url}\\033[0m")

    print("\\nWaiting for 'Continue' in web UI (Ctrl+C to cancel)\\n")

    # Start heartbeat task
    async def heartbeat():
        while True:
            try:
                await client.post(f"/api/cli/sessions/{session_id}/heartbeat")
            except Exception:
                pass
            await asyncio.sleep(5)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            try:
                response = await client.get(f"/api/cli/sessions/{session_id}/pending")
                if response.status_code == 204:
                    await asyncio.sleep(1)
                    continue

                data = response.json()
                wf_name = data["workflow_name"]
                params = data["params"]
                execution_id = data["execution_id"]

                func = workflow_map.get(wf_name)
                if not func:
                    print(f"Workflow '{wf_name}' not found")
                    continue

                logger = LocalRunnerLogger(client, session_id, execution_id, file_path)
                print(f"\\n{'='*60}")
                print(f"Executing: {wf_name} (ID: {execution_id[:8]}...)")
                print(f"{'='*60}")

                logger.install_logging_handler()

                try:
                    result = await func(**params) if asyncio.iscoroutinefunction(func) else func(**params)
                    await logger.complete("Success", result=result)
                    session_url = f"{base_url}/cli/{session_id}"
                    print(f"\\n\\033[92mResult:\\033[0m {format_result_for_terminal(result, session_url)}\\n")
                except Exception as e:
                    error_msg = str(e)
                    await logger.error(f"Workflow failed: {error_msg}")
                    await logger.complete("Failed", error=error_msg)
                    print(f"\\n\\033[91mError:\\033[0m {error_msg}\\n")
                finally:
                    logger.uninstall_logging_handler()

                print("Waiting for next 'Continue'...")

            except KeyboardInterrupt:
                print("\\nStopped.")
                break
    except KeyboardInterrupt:
        print("\\nStopped.")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


async def run_with_terminal_input(workflows: list[dict], workflow_map: dict, workflow_name: str | None):
    if workflow_name:
        func = workflow_map.get(workflow_name)
        if not func:
            print(f"Workflow '{workflow_name}' not found. Available: {', '.join(workflow_map.keys())}")
            sys.exit(1)
        selected = next(w for w in workflows if w["name"] == workflow_name)
    elif len(workflows) == 1:
        selected = workflows[0]
        func = workflow_map[selected["name"]]
    else:
        print("Available workflows:")
        for i, w in enumerate(workflows, 1):
            print(f"  {i}. {w['name']} - {w['description']}")
        choice = input("Select workflow number: ")
        selected = workflows[int(choice) - 1]
        func = workflow_map[selected["name"]]

    params = {}
    for p in selected["parameters"]:
        label = p["label"] or p["name"]
        prompt = f"{label}"
        if not p["required"]:
            prompt += f" (default: {p['default_value']})"
        prompt += ": "
        value = input(prompt)
        if value:
            if p["type"] == "int":
                value = int(value)
            elif p["type"] == "bool":
                value = value.lower() in ("true", "1", "yes")
            elif p["type"] == "json":
                value = json.loads(value)
            params[p["name"]] = value
        elif p["default_value"] is not None:
            params[p["name"]] = p["default_value"]

    print(f"\\nRunning {selected['name']}...")
    try:
        result = await func(**params) if asyncio.iscoroutinefunction(func) else func(**params)
        print(f"Result: {format_result_for_terminal(result)}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def load_dotenv_from_file_path(file_path: str) -> None:
    from dotenv import load_dotenv
    current = Path(file_path).resolve().parent
    env_files = []
    while current != current.parent:
        env_file = current / ".env"
        if env_file.exists():
            env_files.append(env_file)
        current = current.parent
    for env_file in reversed(env_files):
        load_dotenv(env_file, override=True)


def main():
    parser = argparse.ArgumentParser(prog="bifrost", description="Bifrost CLI")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run a workflow locally")
    run_parser.add_argument("file", help="Python file containing workflows")
    run_parser.add_argument("--workflow", "-w", help="Workflow name to run")
    run_parser.add_argument("--params", "-p", help="JSON params (skips web UI)")
    run_parser.add_argument("--open", action="store_true", help="Open browser automatically")
    args = parser.parse_args()

    if args.command == "run":
        load_dotenv_from_file_path(args.file)
        inline_params = json.loads(args.params) if args.params else None
        try:
            asyncio.run(run_with_web_ui(args.file, args.workflow, inline_params, getattr(args, 'open', False)))
        except KeyboardInterrupt:
            pass  # Already handled gracefully in run_with_web_ui
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
'''


def _get_models_py() -> str:
    """Return the models.py content."""
    return '''"""Unified models for Bifrost CLI."""
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class CLIFileReadRequest(BaseModel):
    path: str = Field(..., description="Relative path to file")
    location: Literal["temp", "workspace"] = Field(default="workspace")
    model_config = ConfigDict(from_attributes=True)


class CLIFileWriteRequest(BaseModel):
    path: str = Field(..., description="Relative path to file")
    content: str = Field(..., description="File content")
    location: Literal["temp", "workspace"] = Field(default="workspace")
    model_config = ConfigDict(from_attributes=True)


class CLIFileListRequest(BaseModel):
    directory: str = Field(default="", description="Directory path")
    location: Literal["temp", "workspace"] = Field(default="workspace")
    model_config = ConfigDict(from_attributes=True)


class CLIFileDeleteRequest(BaseModel):
    path: str = Field(..., description="Path to file or directory")
    location: Literal["temp", "workspace"] = Field(default="workspace")
    model_config = ConfigDict(from_attributes=True)


class CLIConfigGetRequest(BaseModel):
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(default=None)
    model_config = ConfigDict(from_attributes=True)


class CLIConfigSetRequest(BaseModel):
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    org_id: str | None = Field(default=None)
    is_secret: bool = Field(default=False)
    model_config = ConfigDict(from_attributes=True)


class CLIConfigListRequest(BaseModel):
    org_id: str | None = Field(default=None)
    model_config = ConfigDict(from_attributes=True)


class CLIConfigDeleteRequest(BaseModel):
    key: str = Field(..., description="Configuration key")
    org_id: str | None = Field(default=None)
    model_config = ConfigDict(from_attributes=True)


class CLIConfigValue(BaseModel):
    key: str
    value: Any
    config_type: str
    model_config = ConfigDict(from_attributes=True)


class CLIOAuthGetRequest(BaseModel):
    provider: str = Field(..., description="OAuth provider name")
    org_id: str | None = Field(default=None)
    model_config = ConfigDict(from_attributes=True)


class CLIOAuthGetResponse(BaseModel):
    connection_name: str
    client_id: str
    client_secret: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: str | None = None
    model_config = ConfigDict(from_attributes=True)
'''
