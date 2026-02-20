"""
Config Router

Manage global and organization-specific configuration key-value pairs.

Uses OrgScopedRepository for standardized org scoping.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

# Import existing Pydantic models for API compatibility
from src.models import (
    ConfigResponse,
    ConfigType,
    SetConfigRequest,
    UpdateConfigRequest,
)

from src.core.auth import Context, CurrentSuperuser
from src.core.org_filter import resolve_org_filter, resolve_target_org, OrgFilterType
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

    Config is SDK-only (no RBAC), so role_table is not set.
    """

    model = ConfigModel
    role_table = None  # No RBAC for configs

    async def list_configs(
        self,
        filter_type: OrgFilterType = OrgFilterType.ORG_PLUS_GLOBAL,
    ) -> list[ConfigResponse]:
        """List configs with specified filter type."""
        from src.models.orm.integrations import Integration
        from sqlalchemy import and_

        query = select(self.model, Integration.name.label("integration_name")).outerjoin(
            Integration,
            and_(
                self.model.integration_id == Integration.id,
                Integration.is_deleted.is_(False),
            )
        )

        # Apply filter based on filter_type
        if filter_type == OrgFilterType.ALL:
            pass
        elif filter_type == OrgFilterType.GLOBAL_ONLY:
            query = query.where(self.model.organization_id.is_(None))
        elif filter_type == OrgFilterType.ORG_ONLY:
            query = query.where(self.model.organization_id == self.org_id)
        else:
            # Inline cascade scope to avoid type mismatch with joined query
            from sqlalchemy import or_
            if self.org_id is not None:
                query = query.where(
                    or_(
                        self.model.organization_id == self.org_id,
                        self.model.organization_id.is_(None),
                    )
                )
            else:
                query = query.where(self.model.organization_id.is_(None))

        query = query.order_by(self.model.key)

        result = await self.session.execute(query)
        rows = result.all()

        schemas = []
        for row in rows:
            c = row[0]  # ConfigModel
            integration_name = row[1]  # Integration.name or None

            raw_value = c.value.get("value") if isinstance(c.value, dict) else c.value
            # Mask secret values in list responses
            if c.config_type == ConfigTypeEnum.SECRET:
                display_value = "[SECRET]"
            else:
                display_value = raw_value

            schemas.append(
                ConfigResponse(
                    id=c.id,
                    key=c.key,
                    value=display_value,
                    type=ConfigType(c.config_type.value) if c.config_type else ConfigType.STRING,
                    scope="org" if c.organization_id else "GLOBAL",
                    org_id=str(c.organization_id) if c.organization_id else None,
                    integration_id=str(c.integration_id) if c.integration_id else None,
                    integration_name=integration_name,
                    description=c.description,
                    updated_at=c.updated_at,
                    updated_by=c.updated_by,
                )
            )
        return schemas

    async def get_config(self, key: str) -> ConfigModel | None:
        """Get config by key with cascade scoping: org-specific > global.

        Uses base class get() which prioritizes org-specific over global
        to avoid MultipleResultsFound when the same key exists in both scopes.
        """
        return await self.get(key=key)

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
        now = datetime.now(timezone.utc)

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
            id=config.id,
            key=config.key,
            value=stored_value,
            type=request.type if request.type else ConfigType.STRING,
            scope="org" if config.organization_id else "GLOBAL",
            org_id=str(config.organization_id) if config.organization_id else None,
            description=config.description,
            updated_at=config.updated_at,
            updated_by=config.updated_by,
        )

    async def update_config_by_id(
        self,
        config_id: UUID,
        request: UpdateConfigRequest,
        updated_by: str,
    ) -> ConfigResponse | None:
        """Update a config by ID. Allows changing organization scope.

        For SECRET type configs, if value is None or empty string, the existing
        encrypted value is preserved.
        """
        query = select(self.model).where(self.model.id == config_id)
        result = await self.session.execute(query)
        config = result.scalar_one_or_none()
        if not config:
            return None

        now = datetime.now(timezone.utc)

        # Determine the effective type (use request type if provided, else keep existing)
        effective_type = request.type if request.type is not None else (
            ConfigType(config.config_type.value) if config.config_type else ConfigType.STRING
        )

        # Handle value update — for secrets, empty/None means keep existing
        if request.value is not None and request.value != "":
            stored_value = request.value
            if effective_type == ConfigType.SECRET:
                from src.core.security import encrypt_secret
                stored_value = encrypt_secret(request.value)
            config.value = {"value": stored_value}
        elif effective_type != ConfigType.SECRET:
            # Non-secret types: empty string is a valid value, None means no change
            if request.value is not None:
                config.value = {"value": request.value}

        if request.key is not None:
            config.key = request.key
        if request.type is not None:
            config.config_type = ConfigTypeEnum(request.type.value)
        if "description" in (request.model_fields_set or set()):
            config.description = request.description
        if "organization_id" in (request.model_fields_set or set()):
            config.organization_id = request.organization_id
        config.updated_at = now
        config.updated_by = updated_by
        await self.session.flush()
        await self.session.refresh(config)

        logger.info(f"Updated config {config.key} (id={config_id}) org={config.organization_id}")

        response_type = ConfigType(config.config_type.value) if config.config_type else ConfigType.STRING
        stored_value = config.value.get("value") if isinstance(config.value, dict) else config.value
        return ConfigResponse(
            id=config.id,
            key=config.key,
            value=stored_value,
            type=response_type,
            scope="org" if config.organization_id else "GLOBAL",
            org_id=str(config.organization_id) if config.organization_id else None,
            description=config.description,
            updated_at=config.updated_at,
            updated_by=config.updated_by,
        )

    async def delete_config(self, config_id: UUID) -> ConfigModel | None:
        """Delete config by ID. Returns the deleted config or None if not found."""
        query = select(self.model).where(self.model.id == config_id)
        result = await self.session.execute(query)
        config = result.scalar_one_or_none()
        if not config:
            return None

        key = config.key
        await self.session.delete(config)
        await self.session.flush()

        logger.info(f"Deleted config {key} (id={config_id})")
        return config


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

    # Use repository for all filtering
    # Config endpoints are superuser-only, so is_superuser=True (no role checks)
    repo = ConfigRepository(ctx.db, org_id=filter_org, is_superuser=True)
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
        description="Deprecated: use organization_id in the request body instead. "
        "Target scope: 'global' for global config, or org UUID for org-specific config. "
        "If omitted, uses the user's current organization context.",
    ),
) -> ConfigResponse:
    """Set a configuration key-value pair.

    Superusers can specify organization_id in the request body to target a
    specific organization, or set it to null for global configs.
    The scope query param is supported for backward compatibility.
    """
    # Prefer organization_id from request body; fall back to scope query param
    if scope is not None:
        # Legacy: scope query param takes precedence if explicitly provided
        try:
            target_org_id = resolve_target_org(ctx.user, scope, ctx.org_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )
    elif "organization_id" in (request.model_fields_set or set()):
        # Body explicitly included organization_id (even if null → global)
        target_org_id = request.organization_id
    else:
        # Neither provided — default to user's current org
        target_org_id = ctx.org_id

    # Config endpoints are superuser-only, so is_superuser=True (no role checks)
    repo = ConfigRepository(ctx.db, org_id=target_org_id, is_superuser=True)

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


@router.put(
    "/api/config/{config_id}",
    response_model=ConfigResponse,
    summary="Update configuration value by ID",
    description="Update an existing configuration value, including its organization scope",
)
async def update_config(
    config_id: UUID,
    request: UpdateConfigRequest,
    ctx: Context,
    user: CurrentSuperuser,
) -> ConfigResponse:
    """Update a configuration by ID.

    Unlike POST (which upserts by key within an org scope), this updates the
    specific config row by ID — allowing changes to organization_id (scope).

    For SECRET type configs, omit value or send empty string to keep the
    existing encrypted value.
    """
    # Use is_superuser=True; org scoping not needed since we look up by ID
    repo = ConfigRepository(ctx.db, org_id=ctx.org_id, is_superuser=True)

    result = await repo.update_config_by_id(config_id, request, updated_by=user.email)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found",
        )

    # Upsert to cache after successful write
    if CACHE_AVAILABLE and upsert_config:
        org_id_str = str(result.org_id) if result.org_id else None
        config_type_str = result.type.value if result.type else "string"
        stored_value = result.value
        await upsert_config(org_id_str, result.key, stored_value, config_type_str)

    return result


@router.delete(
    "/api/config/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete configuration value",
    description="Delete a configuration value by ID",
)
async def delete_config(
    config_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> None:
    """Delete a configuration by ID."""
    # Config endpoints are superuser-only, so is_superuser=True (no role checks)
    repo = ConfigRepository(ctx.db, org_id=ctx.org_id, is_superuser=True)

    deleted = await repo.delete_config(config_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found",
        )

    # Invalidate cache after successful delete
    if CACHE_AVAILABLE and invalidate_config:
        org_id_str = str(deleted.organization_id) if deleted.organization_id else None
        await invalidate_config(org_id_str, deleted.key)
