"""
Config Router

Manage global and organization-specific configuration key-value pairs.

Uses OrgScopedRepository for standardized org scoping.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

# Import existing Pydantic models for API compatibility
from shared.models import (
    Config as ConfigSchema,
    ConfigType,
    SetConfigRequest,
)

from src.core.auth import Context, CurrentSuperuser
from src.models import Config as ConfigModel
from src.models.enums import ConfigType as ConfigTypeEnum
from src.repositories.org_scoped import OrgScopedRepository

# Import cache invalidation
try:
    from shared.cache import invalidate_config
    CACHE_INVALIDATION_AVAILABLE = True
except ImportError:
    CACHE_INVALIDATION_AVAILABLE = False
    invalidate_config = None  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Configuration"])


# =============================================================================
# Repository (using OrgScopedRepository)
# =============================================================================


class ConfigRepository(OrgScopedRepository[ConfigModel]):
    """
    Config repository using OrgScopedRepository.

    Configs use the CASCADE scoping pattern:
    - Org-specific configs + global (NULL org_id) configs
    """

    model = ConfigModel

    async def list_configs(self) -> list[ConfigSchema]:
        """List all configs visible to current org scope."""
        query = select(self.model)
        query = self.filter_cascade(query)
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
                ConfigSchema(
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

    async def set_config(self, request: SetConfigRequest, updated_by: str) -> ConfigSchema:
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

        # Convert shared.models.ConfigType to src.models.enums.ConfigType
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
        return ConfigSchema(
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
    response_model=list[ConfigSchema],
    summary="Get configuration values",
    description="Get configuration values for current scope (includes global configs)",
)
async def get_config(
    ctx: Context,
    user: CurrentSuperuser,
) -> list[ConfigSchema]:
    """Get configuration for current scope."""
    repo = ConfigRepository(ctx.db, ctx.org_id)
    return await repo.list_configs()


@router.post(
    "/api/config",
    response_model=ConfigSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Set configuration value",
    description="Set a configuration value in the current scope",
)
async def set_config(
    request: SetConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> ConfigSchema:
    """Set a configuration key-value pair."""
    repo = ConfigRepository(ctx.db, ctx.org_id)

    try:
        result = await repo.set_config(request, updated_by=user.email)

        # Invalidate cache after successful write
        if CACHE_INVALIDATION_AVAILABLE and invalidate_config:
            org_id = str(ctx.org_id) if ctx.org_id else None
            await invalidate_config(org_id, request.key)

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
    if CACHE_INVALIDATION_AVAILABLE and invalidate_config:
        org_id = str(ctx.org_id) if ctx.org_id else None
        await invalidate_config(org_id, key)


# =============================================================================
# Integration Config Endpoints
# TODO: Migrate integrations to dedicated IntegrationConfiguration table with
#       PostgreSQL storage. The shared/handlers/org_config_handlers.py
#       integration handlers still use Azure Table Storage patterns.
# =============================================================================
