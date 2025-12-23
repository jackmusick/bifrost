"""
Integrations Router

Manages integrations and their mappings to organizations with external entities.
Integrations combine OAuth providers, data providers, and configuration schemas.
"""

import logging
import secrets
from datetime import datetime
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert

from src.core.auth import Context, CurrentSuperuser
from sqlalchemy.orm import joinedload, selectinload

from src.models import (
    ConfigSchemaItem,
    Integration,
    IntegrationCreate,
    IntegrationData,
    IntegrationDetailResponse,
    IntegrationListResponse,
    IntegrationMapping,
    IntegrationMappingCreate,
    IntegrationMappingListResponse,
    IntegrationMappingResponse,
    IntegrationMappingUpdate,
    IntegrationResponse,
    IntegrationUpdate,
    OAuthConfigSummary,
)
from src.models.orm import Config as ConfigModel
from src.models.orm import IntegrationConfigSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])


# =============================================================================
# Response Models
# =============================================================================


class OAuthConfigResponse(BaseModel):
    """Response model for OAuth provider configuration."""

    id: UUID = Field(..., description="OAuth provider ID")
    provider_name: str = Field(..., description="Provider name")
    display_name: str | None = Field(default=None, description="Display name")
    oauth_flow_type: str = Field(..., description="OAuth flow type (authorization_code or client_credentials)")
    client_id: str = Field(..., description="OAuth client ID")
    authorization_url: str | None = Field(
        default=None,
        description="OAuth authorization endpoint URL (only for authorization_code flow)"
    )
    token_url: str | None = Field(..., description="OAuth token endpoint URL")
    scopes: list[str] = Field(default_factory=list, description="OAuth scopes")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class OAuthAuthorizeResponse(BaseModel):
    """Response model for OAuth authorization URL."""

    authorization_url: str = Field(..., description="URL to redirect user for authorization")
    state: str = Field(..., description="State parameter for CSRF protection")
    message: str = Field(default="Redirect user to authorization_url to complete OAuth flow")


# =============================================================================
# Repository
# =============================================================================


class IntegrationsRepository:
    """Repository for integration CRUD operations."""

    def __init__(self, db_session):
        self.db = db_session

    async def list_integrations(self) -> list[Integration]:
        """List all integrations (excluding deleted)."""
        query = (
            select(Integration)
            .where(Integration.is_deleted.is_(False))
            .options(selectinload(Integration.config_schema))
            .order_by(Integration.name)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_integration_by_id(self, integration_id: UUID) -> Integration | None:
        """Get integration by ID."""
        result = await self.db.execute(
            select(Integration)
            .where(
                and_(
                    Integration.id == integration_id,
                    Integration.is_deleted.is_(False),
                )
            )
            .options(selectinload(Integration.config_schema))
        )
        return result.scalar_one_or_none()

    async def get_integration_detail_by_id(self, integration_id: UUID) -> Integration | None:
        """Get integration by ID with relationships loaded (oauth_provider, mappings, config_schema)."""
        result = await self.db.execute(
            select(Integration)
            .where(
                and_(
                    Integration.id == integration_id,
                    Integration.is_deleted.is_(False),
                )
            )
            .options(
                joinedload(Integration.oauth_provider),
                selectinload(Integration.mappings),
                selectinload(Integration.config_schema),
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_integration_by_name(self, name: str) -> Integration | None:
        """Get integration by name."""
        result = await self.db.execute(
            select(Integration)
            .where(
                and_(
                    Integration.name == name,
                    Integration.is_deleted.is_(False),
                )
            )
            .options(selectinload(Integration.config_schema))
        )
        return result.scalar_one_or_none()

    async def create_integration(self, request: IntegrationCreate) -> Integration:
        """Create a new integration with normalized config schema."""
        integration = Integration(
            name=request.name,
            entity_id=request.entity_id,
            entity_id_name=request.entity_id_name,
            is_deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Add config schema items to the normalized table
        if request.config_schema:
            for idx, item in enumerate(request.config_schema):
                schema_item = IntegrationConfigSchema(
                    key=item.key,
                    type=item.type,
                    required=item.required,
                    description=item.description,
                    options=item.options,
                    position=idx,
                )
                integration.config_schema.append(schema_item)

        self.db.add(integration)
        await self.db.flush()
        await self.db.refresh(integration)
        return integration

    async def update_integration(
        self, integration_id: UUID, request: IntegrationUpdate
    ) -> Integration | None:
        """Update an integration with normalized config schema handling."""
        integration = await self.get_integration_by_id(integration_id)
        if not integration:
            return None

        if request.name is not None:
            integration.name = request.name
        if request.list_entities_data_provider_id is not None:
            integration.list_entities_data_provider_id = (
                request.list_entities_data_provider_id
            )
        if request.entity_id is not None:
            integration.entity_id = request.entity_id
        if request.entity_id_name is not None:
            integration.entity_id_name = request.entity_id_name

        # Handle config_schema updates (normalized table)
        if request.config_schema is not None:
            # Build lookup of existing schema items by key
            existing_by_key = {item.key: item for item in integration.config_schema}
            new_keys = {item.key for item in request.config_schema}

            # Remove schema items that are not in the new list
            # (cascade delete will remove related configs)
            for key in list(existing_by_key.keys()):
                if key not in new_keys:
                    item = existing_by_key[key]
                    integration.config_schema.remove(item)
                    await self.db.delete(item)

            # Update existing or add new schema items
            for idx, item_data in enumerate(request.config_schema):
                if item_data.key in existing_by_key:
                    # Update existing
                    existing = existing_by_key[item_data.key]
                    existing.type = item_data.type
                    existing.required = item_data.required
                    existing.description = item_data.description
                    existing.options = item_data.options
                    existing.position = idx
                else:
                    # Add new
                    new_item = IntegrationConfigSchema(
                        integration_id=integration.id,
                        key=item_data.key,
                        type=item_data.type,
                        required=item_data.required,
                        description=item_data.description,
                        options=item_data.options,
                        position=idx,
                    )
                    integration.config_schema.append(new_item)

        integration.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(integration)
        # Reload with relationships
        return await self.get_integration_by_id(integration_id)

    async def delete_integration(self, integration_id: UUID) -> bool:
        """Soft delete an integration."""
        integration = await self.get_integration_by_id(integration_id)
        if not integration:
            return False

        integration.is_deleted = True
        integration.updated_at = datetime.utcnow()
        await self.db.flush()
        return True

    async def list_mappings_for_integration(
        self, integration_id: UUID
    ) -> list[IntegrationMapping]:
        """List all mappings for a specific integration."""
        result = await self.db.execute(
            select(IntegrationMapping)
            .where(IntegrationMapping.integration_id == integration_id)
            .order_by(IntegrationMapping.organization_id)
        )
        return list(result.scalars().all())

    async def get_mapping_by_id(
        self, integration_id: UUID, mapping_id: UUID
    ) -> IntegrationMapping | None:
        """Get a specific mapping by ID and integration ID."""
        result = await self.db.execute(
            select(IntegrationMapping).where(
                and_(
                    IntegrationMapping.id == mapping_id,
                    IntegrationMapping.integration_id == integration_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_mapping_by_org(
        self, integration_id: UUID, org_id: UUID
    ) -> IntegrationMapping | None:
        """Get the mapping for an integration in a specific organization."""
        result = await self.db.execute(
            select(IntegrationMapping).where(
                and_(
                    IntegrationMapping.integration_id == integration_id,
                    IntegrationMapping.organization_id == org_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_mapping(
        self, request: IntegrationMappingCreate, integration_id: UUID
    ) -> IntegrationMapping:
        """Create a new integration mapping."""
        mapping = IntegrationMapping(
            integration_id=integration_id,
            organization_id=request.organization_id,
            entity_id=request.entity_id,
            entity_name=request.entity_name,
            oauth_token_id=request.oauth_token_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(mapping)
        await self.db.flush()
        await self.db.refresh(mapping)
        return mapping

    async def _save_config(
        self,
        integration_id: UUID,
        organization_id: UUID | None,
        config: dict[str, Any],
        updated_by: str = "system",
    ) -> None:
        """
        Persist config values to the configs table.

        For each key-value pair:
        - If value is None or empty string, delete the entry (fall back to default)
        - Otherwise, upsert the entry

        Uses explicit SELECT + INSERT/UPDATE pattern because PostgreSQL's
        ON CONFLICT doesn't work with functional indexes (COALESCE for NULL handling).
        """
        # Look up schema items for this integration to get config_schema_id
        schema_result = await self.db.execute(
            select(IntegrationConfigSchema)
            .where(IntegrationConfigSchema.integration_id == integration_id)
        )
        schema_items = {item.key: item for item in schema_result.scalars().all()}

        for key, value in config.items():
            # Get the schema item for this key (for FK reference)
            schema_item = schema_items.get(key)

            # Build the WHERE clause for matching existing config
            # Handle NULL comparison properly with IS NULL
            if organization_id is None:
                where_clause = and_(
                    ConfigModel.integration_id == integration_id,
                    ConfigModel.organization_id.is_(None),
                    ConfigModel.key == key,
                )
            else:
                where_clause = and_(
                    ConfigModel.integration_id == integration_id,
                    ConfigModel.organization_id == organization_id,
                    ConfigModel.key == key,
                )

            if value is None or value == "":
                # Delete override (fall back to default)
                await self.db.execute(delete(ConfigModel).where(where_clause))
            else:
                # Check if record exists
                result = await self.db.execute(
                    select(ConfigModel.id).where(where_clause)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing record
                    from sqlalchemy import update
                    await self.db.execute(
                        update(ConfigModel)
                        .where(ConfigModel.id == existing)
                        .values(
                            value={"value": value},
                            updated_by=updated_by,
                            config_schema_id=schema_item.id if schema_item else None,
                        )
                    )
                else:
                    # Insert new record
                    new_config = ConfigModel(
                        integration_id=integration_id,
                        organization_id=organization_id,
                        key=key,
                        value={"value": value},
                        updated_by=updated_by,
                        config_schema_id=schema_item.id if schema_item else None,
                    )
                    self.db.add(new_config)

    async def update_mapping(
        self,
        integration_id: UUID,
        mapping_id: UUID,
        request: IntegrationMappingUpdate,
        updated_by: str = "system",
    ) -> IntegrationMapping | None:
        """Update an integration mapping."""
        mapping = await self.get_mapping_by_id(integration_id, mapping_id)
        if not mapping:
            return None

        if request.entity_id is not None:
            mapping.entity_id = request.entity_id
        if request.entity_name is not None:
            mapping.entity_name = request.entity_name
        if request.oauth_token_id is not None:
            mapping.oauth_token_id = request.oauth_token_id

        # Persist config to configs table
        if request.config is not None:
            await self._save_config(
                integration_id=integration_id,
                organization_id=mapping.organization_id,
                config=request.config,
                updated_by=updated_by,
            )

        mapping.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(mapping)
        return mapping

    async def delete_mapping(
        self, integration_id: UUID, mapping_id: UUID
    ) -> bool:
        """Delete an integration mapping."""
        mapping = await self.get_mapping_by_id(integration_id, mapping_id)
        if not mapping:
            return False

        await self.db.delete(mapping)
        await self.db.flush()
        return True

    async def get_integration_defaults(self, integration_id: UUID) -> dict[str, Any]:
        """
        Get integration-level default config values.

        These are stored in the configs table with integration_id set
        but organization_id is NULL.
        """
        config_query = select(ConfigModel).where(
            and_(
                ConfigModel.integration_id == integration_id,
                ConfigModel.organization_id.is_(None),
            )
        )
        result = await self.db.execute(config_query)
        config_entries = result.scalars().all()

        config: dict[str, Any] = {}
        for entry in config_entries:
            value = entry.value
            if isinstance(value, dict) and "value" in value:
                config[entry.key] = value["value"]
            else:
                config[entry.key] = value

        return config

    async def get_org_config_overrides(
        self, integration_id: UUID, org_id: UUID
    ) -> dict[str, Any]:
        """
        Get ONLY org-specific config overrides (not merged with defaults).

        Used for admin UI where we only want to show what the org has explicitly set,
        not the default values. This prevents users from accidentally saving defaults
        back to the org config.
        """
        config_query = select(ConfigModel).where(
            and_(
                ConfigModel.organization_id == org_id,
                ConfigModel.integration_id == integration_id,
            )
        )
        result = await self.db.execute(config_query)
        config_entries = result.scalars().all()

        config: dict[str, Any] = {}
        for entry in config_entries:
            value = entry.value
            if isinstance(value, dict) and "value" in value:
                config[entry.key] = value["value"]
            else:
                config[entry.key] = value

        return config

    async def get_config_for_mapping(
        self, integration_id: UUID, org_id: UUID
    ) -> dict[str, Any]:
        """
        Get merged configuration for an integration mapping.

        Config resolution order:
        1. Integration-level defaults (integration_id set, org_id is NULL)
        2. Per-org overrides (both integration_id and org_id set)

        Per-org values override integration defaults.

        Used by SDK endpoint where we need the fully resolved config.
        """
        # Start with integration-level defaults
        config = await self.get_integration_defaults(integration_id)

        # Merge org overrides
        org_overrides = await self.get_org_config_overrides(integration_id, org_id)
        config.update(org_overrides)

        return config

    async def get_oauth_provider(self, integration_id: UUID):
        """Get the OAuth provider associated with an integration."""
        integration = await self.get_integration_by_id(integration_id)
        if not integration:
            return None
        return integration.oauth_provider


# =============================================================================
# HTTP Endpoints - Integration CRUD
# =============================================================================


@router.post(
    "",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create integration",
    description="Create a new integration (Platform admin only)",
)
async def create_integration(
    request: IntegrationCreate,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationResponse:
    """Create a new integration."""
    repo = IntegrationsRepository(ctx.db)

    # Check for duplicate name
    existing = await repo.get_integration_by_name(request.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Integration '{request.name}' already exists",
        )

    integration = await repo.create_integration(request)
    logger.info(f"Created integration: {integration.name}")

    return IntegrationResponse.model_validate(integration)


@router.get(
    "",
    response_model=IntegrationListResponse,
    summary="List integrations",
    description="List all integrations (Platform admin only)",
)
async def list_integrations(
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationListResponse:
    """List all integrations."""
    repo = IntegrationsRepository(ctx.db)
    integrations = await repo.list_integrations()

    items = [IntegrationResponse.model_validate(i) for i in integrations]
    return IntegrationListResponse(items=items, total=len(items))


@router.get(
    "/{integration_id}",
    response_model=IntegrationDetailResponse,
    summary="Get integration by ID",
    description="Get a specific integration by ID with mappings and OAuth config (Platform admin only)",
)
async def get_integration(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationDetailResponse:
    """Get a specific integration by ID with nested mappings and OAuth config."""
    repo = IntegrationsRepository(ctx.db)
    integration = await repo.get_integration_detail_by_id(integration_id)

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Build OAuth config summary if OAuth provider exists
    oauth_config = None
    if integration.oauth_provider:
        provider = integration.oauth_provider
        # Get connection status from provider
        oauth_config = OAuthConfigSummary(
            provider_name=provider.provider_name,
            oauth_flow_type=provider.oauth_flow_type,
            client_id=provider.client_id,
            authorization_url=provider.authorization_url,
            token_url=provider.token_url or "",
            scopes=provider.scopes or [],
            status=provider.status or "not_connected",
            status_message=provider.status_message,
            expires_at=None,  # Token-level data, not provider-level
            last_refresh_at=provider.last_token_refresh,
        )

    # Build mapping responses with org-specific overrides only (not merged with defaults)
    # This prevents users from accidentally saving defaults back to org config
    mapping_responses = []
    for m in integration.mappings:
        org_config = await repo.get_org_config_overrides(integration.id, m.organization_id)
        mapping_responses.append(
            IntegrationMappingResponse(
                id=m.id,
                integration_id=m.integration_id,
                organization_id=m.organization_id,
                entity_id=m.entity_id,
                entity_name=m.entity_name,
                oauth_token_id=m.oauth_token_id,
                config=org_config if org_config else None,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
        )

    # Convert ORM config_schema items to Pydantic models
    config_schema_items = None
    if integration.config_schema:
        config_schema_items = [
            ConfigSchemaItem.model_validate(item)
            for item in integration.config_schema
        ]

    # Get integration-level default config values
    config_defaults = await repo.get_integration_defaults(integration.id)

    return IntegrationDetailResponse(
        id=integration.id,
        name=integration.name,
        list_entities_data_provider_id=integration.list_entities_data_provider_id,
        config_schema=config_schema_items,
        config_defaults=config_defaults if config_defaults else None,
        entity_id=integration.entity_id,
        entity_id_name=integration.entity_id_name,
        has_oauth_config=integration.has_oauth_config,
        is_deleted=integration.is_deleted,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        mappings=mapping_responses,
        oauth_config=oauth_config,
    )


@router.get(
    "/by-name/{name}",
    response_model=IntegrationResponse,
    summary="Get integration by name",
    description="Get a specific integration by name (Platform admin only)",
)
async def get_integration_by_name(
    name: str,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationResponse:
    """Get a specific integration by name."""
    repo = IntegrationsRepository(ctx.db)
    integration = await repo.get_integration_by_name(name)

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    return IntegrationResponse.model_validate(integration)


@router.put(
    "/{integration_id}",
    response_model=IntegrationResponse,
    summary="Update integration",
    description="Update an existing integration (Platform admin only)",
)
async def update_integration(
    integration_id: UUID,
    request: IntegrationUpdate,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationResponse:
    """Update an integration."""
    repo = IntegrationsRepository(ctx.db)
    integration = await repo.update_integration(integration_id, request)

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    logger.info(f"Updated integration: {integration.name}")
    return IntegrationResponse.model_validate(integration)


@router.delete(
    "/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete integration",
    description="Soft delete an integration (Platform admin only)",
)
async def delete_integration(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> None:
    """Soft delete an integration."""
    repo = IntegrationsRepository(ctx.db)
    deleted = await repo.delete_integration(integration_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    logger.info(f"Deleted integration: {integration_id}")


# =============================================================================
# HTTP Endpoints - Integration Config Defaults
# =============================================================================


class IntegrationConfigUpdate(BaseModel):
    """Request model for updating integration default config values."""

    config: dict[str, Any] = Field(
        ..., description="Default config values for this integration"
    )


class IntegrationConfigResponse(BaseModel):
    """Response model for integration config."""

    integration_id: UUID
    config: dict[str, Any]


@router.put(
    "/{integration_id}/config",
    response_model=IntegrationConfigResponse,
    summary="Update integration default config",
    description="Set default config values for an integration (Platform admin only)",
)
async def update_integration_config(
    integration_id: UUID,
    request: IntegrationConfigUpdate,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationConfigResponse:
    """Update integration-level default config values.

    These defaults are stored in the configs table with integration_id set
    but no organization_id. Per-org configs override these values.
    """
    repo = IntegrationsRepository(ctx.db)

    # Verify integration exists
    integration = await repo.get_integration_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Save config with integration_id only (no org_id = defaults)
    await repo._save_config(
        integration_id=integration_id,
        organization_id=None,
        config=request.config,
        updated_by=user.email,
    )

    logger.info(f"Updated default config for integration {integration_id}")

    # Return the saved config
    saved_config = await repo.get_integration_defaults(integration_id)
    return IntegrationConfigResponse(
        integration_id=integration_id,
        config=saved_config,
    )


@router.get(
    "/{integration_id}/config",
    response_model=IntegrationConfigResponse,
    summary="Get integration default config",
    description="Get default config values for an integration (Platform admin only)",
)
async def get_integration_config(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationConfigResponse:
    """Get integration-level default config values."""
    repo = IntegrationsRepository(ctx.db)

    # Verify integration exists
    integration = await repo.get_integration_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    config = await repo.get_integration_defaults(integration_id)
    return IntegrationConfigResponse(
        integration_id=integration_id,
        config=config,
    )


# =============================================================================
# HTTP Endpoints - Integration Mappings
# =============================================================================


@router.post(
    "/{integration_id}/mappings",
    response_model=IntegrationMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create integration mapping",
    description="Create a new mapping between an integration and organization (Platform admin only)",
)
async def create_mapping(
    integration_id: UUID,
    request: IntegrationMappingCreate,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingResponse:
    """Create a new integration mapping."""
    repo = IntegrationsRepository(ctx.db)

    # Verify integration exists
    integration = await repo.get_integration_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    # Check for duplicate mapping (one per org per integration)
    existing = await repo.get_mapping_by_org(integration_id, request.organization_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mapping already exists for this organization and integration",
        )

    mapping = await repo.create_mapping(request, integration_id)
    logger.info(
        f"Created mapping for integration {integration_id} in org {request.organization_id}"
    )

    # Get org-specific overrides only (not merged with defaults)
    org_config = await repo.get_org_config_overrides(integration_id, request.organization_id)

    return IntegrationMappingResponse(
        id=mapping.id,
        integration_id=mapping.integration_id,
        organization_id=mapping.organization_id,
        entity_id=mapping.entity_id,
        entity_name=mapping.entity_name,
        oauth_token_id=mapping.oauth_token_id,
        config=org_config if org_config else None,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.get(
    "/{integration_id}/mappings",
    response_model=IntegrationMappingListResponse,
    summary="List mappings for integration",
    description="List all mappings for a specific integration (Platform admin only)",
)
async def list_mappings(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingListResponse:
    """List all mappings for an integration."""
    repo = IntegrationsRepository(ctx.db)

    # Verify integration exists
    integration = await repo.get_integration_by_id(integration_id)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    mappings = await repo.list_mappings_for_integration(integration_id)

    items = [
        IntegrationMappingResponse(
            id=m.id,
            integration_id=m.integration_id,
            organization_id=m.organization_id,
            entity_id=m.entity_id,
            entity_name=m.entity_name,
            oauth_token_id=m.oauth_token_id,
            config=None,  # Not included in list response
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in mappings
    ]
    return IntegrationMappingListResponse(items=items, total=len(items))


@router.get(
    "/{integration_id}/mappings/{mapping_id}",
    response_model=IntegrationMappingResponse,
    summary="Get integration mapping",
    description="Get a specific mapping by ID (Platform admin only)",
)
async def get_mapping(
    integration_id: UUID,
    mapping_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingResponse:
    """Get a specific mapping."""
    repo = IntegrationsRepository(ctx.db)

    mapping = await repo.get_mapping_by_id(integration_id, mapping_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapping not found",
        )

    # Get org-specific overrides only (not merged with defaults)
    org_config = await repo.get_org_config_overrides(integration_id, mapping.organization_id)

    return IntegrationMappingResponse(
        id=mapping.id,
        integration_id=mapping.integration_id,
        organization_id=mapping.organization_id,
        entity_id=mapping.entity_id,
        entity_name=mapping.entity_name,
        oauth_token_id=mapping.oauth_token_id,
        config=org_config if org_config else None,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.get(
    "/{integration_id}/mappings/by-org/{org_id}",
    response_model=IntegrationMappingResponse,
    summary="Get mapping by organization",
    description="Get the mapping for an integration in a specific organization (Platform admin only)",
)
async def get_mapping_by_org(
    integration_id: UUID,
    org_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingResponse:
    """Get the mapping for an integration in a specific organization."""
    repo = IntegrationsRepository(ctx.db)

    mapping = await repo.get_mapping_by_org(integration_id, org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapping not found for this organization",
        )

    # Get org-specific overrides only (not merged with defaults)
    org_config = await repo.get_org_config_overrides(integration_id, org_id)

    return IntegrationMappingResponse(
        id=mapping.id,
        integration_id=mapping.integration_id,
        organization_id=mapping.organization_id,
        entity_id=mapping.entity_id,
        entity_name=mapping.entity_name,
        oauth_token_id=mapping.oauth_token_id,
        config=org_config if org_config else None,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.put(
    "/{integration_id}/mappings/{mapping_id}",
    response_model=IntegrationMappingResponse,
    summary="Update integration mapping",
    description="Update an existing mapping (Platform admin only)",
)
async def update_mapping(
    integration_id: UUID,
    mapping_id: UUID,
    request: IntegrationMappingUpdate,
    ctx: Context,
    user: CurrentSuperuser,
) -> IntegrationMappingResponse:
    """Update an integration mapping."""
    repo = IntegrationsRepository(ctx.db)

    mapping = await repo.update_mapping(
        integration_id, mapping_id, request, updated_by=user.email
    )
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapping not found",
        )

    logger.info(f"Updated mapping {mapping_id} for integration {integration_id}")

    # Get org-specific overrides only (not merged with defaults)
    org_config = await repo.get_org_config_overrides(integration_id, mapping.organization_id)

    return IntegrationMappingResponse(
        id=mapping.id,
        integration_id=mapping.integration_id,
        organization_id=mapping.organization_id,
        entity_id=mapping.entity_id,
        entity_name=mapping.entity_name,
        oauth_token_id=mapping.oauth_token_id,
        config=org_config if org_config else None,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.delete(
    "/{integration_id}/mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete integration mapping",
    description="Delete an integration mapping (Platform admin only)",
)
async def delete_mapping(
    integration_id: UUID,
    mapping_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> None:
    """Delete an integration mapping."""
    repo = IntegrationsRepository(ctx.db)

    deleted = await repo.delete_mapping(integration_id, mapping_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mapping not found",
        )

    logger.info(f"Deleted mapping {mapping_id} for integration {integration_id}")


# =============================================================================
# HTTP Endpoints - OAuth Configuration
# =============================================================================


@router.get(
    "/{integration_id}/oauth",
    response_model=OAuthConfigResponse,
    summary="Get OAuth provider config",
    description="Get the OAuth provider configuration for this integration (Platform admin only)",
)
async def get_oauth_config(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
) -> OAuthConfigResponse:
    """Get the OAuth provider configuration associated with an integration."""
    repo = IntegrationsRepository(ctx.db)

    oauth_provider = await repo.get_oauth_provider(integration_id)
    if not oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth configuration found for this integration",
        )

    return OAuthConfigResponse(
        id=oauth_provider.id,
        provider_name=oauth_provider.provider_name,
        display_name=oauth_provider.display_name,
        oauth_flow_type=oauth_provider.oauth_flow_type,
        client_id=oauth_provider.client_id,
        authorization_url=oauth_provider.authorization_url,
        token_url=oauth_provider.token_url,
        scopes=oauth_provider.scopes or [],
        created_at=oauth_provider.created_at,
        updated_at=oauth_provider.updated_at,
    )


@router.get(
    "/{integration_id}/oauth/authorize",
    response_model=OAuthAuthorizeResponse,
    summary="Get OAuth authorization URL",
    description="Get the authorization URL for this integration's OAuth flow (Platform admin only)",
)
async def get_oauth_authorization_url(
    integration_id: UUID,
    ctx: Context,
    user: CurrentSuperuser,
    redirect_uri: str = Query(..., description="Frontend callback URL for OAuth redirect"),
) -> OAuthAuthorizeResponse:
    """
    Get the authorization URL for this integration's OAuth flow.

    This initiates the OAuth authorization flow and returns the URL
    where the user should be redirected for authorization.
    """
    repo = IntegrationsRepository(ctx.db)

    oauth_provider = await repo.get_oauth_provider(integration_id)
    if not oauth_provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No OAuth configuration found for this integration",
        )

    # Check if authorization_url is available (not all flows require it)
    if not oauth_provider.authorization_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This integration uses client_credentials flow and does not require user authorization",
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Build authorization URL
    # Convert scopes list to space-separated string (OAuth 2.0 standard format)
    scopes_str = " ".join(oauth_provider.scopes) if oauth_provider.scopes else ""
    params = {
        "client_id": oauth_provider.client_id,
        "response_type": "code",
        "state": state,
        "scope": scopes_str,
        "redirect_uri": redirect_uri,
    }

    authorization_url = f"{oauth_provider.authorization_url}?{urlencode(params)}"

    logger.info(
        f"Generated OAuth authorization URL for integration {integration_id}, "
        f"provider {oauth_provider.provider_name}"
    )

    return OAuthAuthorizeResponse(
        authorization_url=authorization_url,
        state=state,
        message="Redirect user to authorization_url to complete OAuth flow",
    )


# =============================================================================
# HTTP Endpoints - SDK Data
# =============================================================================


@router.get(
    "/sdk/{name}",
    response_model=IntegrationData,
    summary="Get integration data for SDK",
    description="Get integration data with resolved OAuth and merged config for SDK consumption",
)
async def get_integration_sdk_data(
    name: str,
    ctx: Context,
    org_id: UUID = Query(..., description="Organization ID for resolving mapping"),
) -> IntegrationData:
    """
    Get integration data for SDK consumption.
    Returns resolved OAuth provider and merged configuration.
    Called from workflow execution contexts with organization scope.
    """
    repo = IntegrationsRepository(ctx.db)

    # Get integration by name
    integration = await repo.get_integration_by_name(name)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration '{name}' not found",
        )

    # Get mapping for this org
    mapping = await repo.get_mapping_by_org(integration.id, org_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mapping not found for integration '{name}' in organization",
        )

    # Get merged configuration
    config = await repo.get_config_for_mapping(integration.id, org_id)

    # Get OAuth provider info if present
    oauth_client_id = None
    oauth_token_url = None
    oauth_scopes = None

    if integration.oauth_provider:
        oauth_client_id = integration.oauth_provider.client_id
        oauth_token_url = integration.oauth_provider.token_url
        oauth_scopes = (
            " ".join(integration.oauth_provider.scopes)
            if integration.oauth_provider.scopes
            else None
        )

    return IntegrationData(
        integration_id=integration.id,
        entity_id=mapping.entity_id,
        entity_name=mapping.entity_name,
        config=config if config else {},
        oauth_client_id=oauth_client_id,
        oauth_token_url=oauth_token_url,
        oauth_scopes=oauth_scopes,
    )
