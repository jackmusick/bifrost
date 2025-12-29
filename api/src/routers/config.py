"""
Config Router

Manage global and organization-specific configuration key-value pairs.

Uses OrgScopedRepository for standardized org scoping.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

# Import existing Pydantic models for API compatibility
from src.models import (
    ConfigResponse,
    ConfigType,
    SetConfigRequest,
)

from src.core.auth import Context, CurrentSuperuser
from src.core.org_filter import resolve_org_filter, OrgFilterType
from src.models import Config as ConfigModel
from src.models.enums import ConfigType as ConfigTypeEnum
from src.repositories.org_scoped import OrgScopedRepository

# Import cache functions
try:
    from src.core.cache import invalidate_config, upsert_config
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    invalidate_config = None  # type: ignore
    upsert_config = None  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Configuration"])


# =============================================================================
# Repository (using OrgScopedRepository)
# =============================================================================


class ConfigRepository(OrgScopedRepository[ConfigModel]):  # type: ignore[type-var]
    """
    Config repository using OrgScopedRepository.

    Configs use the CASCADE scoping pattern:
    - Org-specific configs + global (NULL org_id) configs
    """

    model = ConfigModel

    async def list_configs(
        self,
        filter_type: OrgFilterType = OrgFilterType.ORG_PLUS_GLOBAL,
    ) -> list[ConfigResponse]:
        """List configs with specified filter type.

        Args:
            filter_type: How to filter by organization scope
        """
        query = select(self.model)
        query = self.apply_filter(query, filter_type, self.org_id)
        query = query.order_by(self.model.key)

        result = await self.session.execute(query)
        configs = result.scalars().all()

        schemas = []
        for c in configs:
            raw_value = c.value.get("value") if isinstance(c.value, dict) else c.value
            # Mask secret values in list responses
            if c.config_type == ConfigTypeEnum.SECRET:
                display_value = "[SECRET]"
            else:
                display_value = raw_value

            schemas.append(
                ConfigResponse(
                    key=c.key,
                    value=display_value,
                    type=ConfigType(c.config_type.value) if c.config_type else ConfigType.STRING,
                    scope="org" if c.organization_id else "GLOBAL",
                    org_id=str(c.organization_id) if c.organization_id else None,
                    description=c.description,
                    updated_at=c.updated_at,
                    updated_by=c.updated_by,
                )
            )
        return schemas

    async def get_config(self, key: str) -> ConfigModel | None:
        """Get config by key with cascade scoping."""
        query = select(self.model).where(self.model.key == key)
        query = self.filter_cascade(query)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_config_strict(self, key: str) -> ConfigModel | None:
        """Get config strictly in current org scope (no fallback)."""
        query = select(self.model).where(
            self.model.key == key,
            self.model.organization_id == self.org_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def set_config(self, request: SetConfigRequest, updated_by: str) -> ConfigResponse:
        """Create or update a config in current org scope."""
        now = datetime.utcnow()

        # Handle secret encryption if this is a SECRET type
        stored_value = request.value
        if request.type == ConfigType.SECRET:
            from src.core.security import encrypt_secret
            stored_value = encrypt_secret(request.value)

        # Build value object for JSONB storage
        config_value = {
            "value": stored_value,
        }

        # Convert API ConfigType to DB ConfigTypeEnum
        # Both enums have same values, so we can use the value to lookup
        db_config_type = ConfigTypeEnum(request.type.value) if request.type else ConfigTypeEnum.STRING

        # Check if config exists in current org scope
        existing = await self.get_config_strict(request.key)

        if existing:
            # Update existing
            existing.value = config_value
            existing.config_type = db_config_type
            existing.description = request.description
            existing.updated_at = now
            existing.updated_by = updated_by
            await self.session.flush()
            await self.session.refresh(existing)
            config = existing
        else:
            # Create new
            config = ConfigModel(
                key=request.key,
                value=config_value,
                config_type=db_config_type,
                description=request.description,
                organization_id=self.org_id,
                created_at=now,
                updated_at=now,
                updated_by=updated_by,
            )
            self.session.add(config)
            await self.session.flush()
            await self.session.refresh(config)

        logger.info(f"Set config {request.key} in org {self.org_id}")

        # Extract value from JSONB for response
        stored_value = config.value.get("value") if isinstance(config.value, dict) else config.value
        return ConfigResponse(
            key=config.key,
            value=stored_value,
            type=request.type if request.type else ConfigType.STRING,
            scope="org" if config.organization_id else "GLOBAL",
            org_id=str(config.organization_id) if config.organization_id else None,
            description=config.description,
            updated_at=config.updated_at,
            updated_by=config.updated_by,
        )

    async def delete_config(self, key: str) -> bool:
        """Delete config from current org scope."""
        config = await self.get_config_strict(key)
        if not config:
            return False

        # In SQLAlchemy 2.0 async, delete() is async
        await self.session.delete(config)
        await self.session.flush()

        logger.info(f"Deleted config {key}")
        return True


# =============================================================================
# Config Endpoints
# =============================================================================


@router.get(
    "/api/config",
    response_model=list[ConfigResponse],
    summary="Get configuration values",
    description="Get configuration values for current scope (includes global configs)",
)
async def get_config(
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(
        None,
        description="Filter scope: omit for all (superusers), 'global' for global only, "
        "or org UUID for specific org."
    ),
) -> list[ConfigResponse]:
    """Get configuration for current scope.

    Superusers can filter by scope or see all configs.
    """
    # Resolve organization filter based on user permissions
    try:
        filter_type, filter_org = resolve_org_filter(ctx.user, scope)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    # Use repository for all filtering - centralized in apply_filter()
    repo = ConfigRepository(ctx.db, filter_org)
    return await repo.list_configs(filter_type)


@router.post(
    "/api/config",
    response_model=ConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set configuration value",
    description="Set a configuration value in the current scope",
)
async def set_config(
    request: SetConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
    scope: str | None = Query(
        default=None,
        description="Target scope: 'global' for global config, or org UUID for org-specific config. "
        "If omitted, uses the user's current organization context.",
    ),
) -> ConfigResponse:
    """Set a configuration key-value pair.

    Superusers can specify a scope to create configs in a specific organization
    or explicitly create global configs.
    """
    # Determine target organization for the config
    target_org_id = ctx.org_id
    if user.is_superuser and scope is not None:
        if scope == "global":
            target_org_id = None
        else:
            try:
                target_org_id = UUID(scope)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid scope value: {scope}",
                )

    repo = ConfigRepository(ctx.db, target_org_id)

    try:
        result = await repo.set_config(request, updated_by=user.email)

        # Upsert to cache after successful write (dual-write pattern)
        if CACHE_AVAILABLE and upsert_config:
            org_id_str = str(target_org_id) if target_org_id else None
            config_type_str = request.type.value if request.type else "string"
            # Note: For secrets, stored_value is already encrypted by the repository
            stored_value = result.value
            await upsert_config(org_id_str, request.key, stored_value, config_type_str)

        return result
    except Exception as e:
        logger.error(f"Error setting config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set configuration",
        )


@router.delete(
    "/api/config/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete configuration value",
    description="Delete a configuration value by key",
)
async def delete_config(
    key: str,
    ctx: Context,
    user: CurrentSuperuser,
) -> None:
    """Delete a configuration key."""
    repo = ConfigRepository(ctx.db, ctx.org_id)

    success = await repo.delete_config(key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found",
        )

    # Invalidate cache after successful delete
    if CACHE_AVAILABLE and invalidate_config:
        org_id_str = str(ctx.org_id) if ctx.org_id else None
        await invalidate_config(org_id_str, key)
