"""
Integrations Repository

Database operations for integration management and mapping.
Handles CRUD operations for Integration and IntegrationMapping tables.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.models.orm.integrations import Integration, IntegrationMapping
from src.models.contracts.integrations import (
    IntegrationCreate,
    IntegrationUpdate,
    IntegrationMappingCreate,
    IntegrationMappingUpdate,
)
from src.repositories.base import BaseRepository


class IntegrationsRepository(BaseRepository[Integration]):
    """Repository for integration operations."""

    model = Integration

    def __init__(self, session: AsyncSession):
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session)

    # =========================================================================
    # Integration CRUD Operations
    # =========================================================================

    async def create_integration(
        self, data: IntegrationCreate
    ) -> Integration:
        """
        Create a new integration.

        Args:
            data: Integration creation data

        Returns:
            Created integration
        """
        integration = Integration(
            name=data.name,
            oauth_provider_id=data.oauth_provider_id,
            list_entities_data_provider_id=data.list_entities_data_provider_id,
            config_schema=[item.model_dump() for item in data.config_schema]
            if data.config_schema
            else None,
            entity_id=data.entity_id,
            entity_id_name=data.entity_id_name,
        )
        return await self.create(integration)

    async def get_integration(self, id: UUID) -> Integration | None:
        """
        Get integration by ID with relationships loaded.

        Args:
            id: Integration UUID

        Returns:
            Integration or None if not found
        """
        result = await self.session.execute(
            select(Integration)
            .where(Integration.id == id)
            .options(
                joinedload(Integration.oauth_provider),
                selectinload(Integration.mappings),
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_integration_by_name(self, name: str) -> Integration | None:
        """
        Get integration by name with relationships loaded.

        Args:
            name: Integration name

        Returns:
            Integration or None if not found
        """
        result = await self.session.execute(
            select(Integration)
            .where(Integration.name == name)
            .options(
                joinedload(Integration.oauth_provider),
                selectinload(Integration.mappings),
            )
        )
        return result.unique().scalar_one_or_none()

    async def list_integrations(
        self, include_deleted: bool = False
    ) -> list[Integration]:
        """
        List all integrations.

        Args:
            include_deleted: If True, include soft-deleted integrations

        Returns:
            List of integrations
        """
        query = select(Integration).options(
            joinedload(Integration.oauth_provider),
            selectinload(Integration.mappings),
        )

        if not include_deleted:
            query = query.where(Integration.is_deleted.is_(False))

        query = query.order_by(Integration.name)
        result = await self.session.execute(query)
        return list(result.unique().scalars().all())

    async def update_integration(
        self, id: UUID, data: IntegrationUpdate
    ) -> Integration | None:
        """
        Update an integration.

        Args:
            id: Integration UUID
            data: Update data (partial)

        Returns:
            Updated integration or None if not found
        """
        integration = await self.get_integration(id)
        if not integration:
            return None

        # Update only provided fields
        if data.name is not None:
            integration.name = data.name
        if data.oauth_provider_id is not None:
            integration.oauth_provider_id = data.oauth_provider_id
        if data.list_entities_data_provider_id is not None:
            integration.list_entities_data_provider_id = (
                data.list_entities_data_provider_id
            )
        if data.config_schema is not None:
            integration.config_schema = [
                item.model_dump() for item in data.config_schema
            ]
        if data.entity_id is not None:
            integration.entity_id = data.entity_id
        if data.entity_id_name is not None:
            integration.entity_id_name = data.entity_id_name

        await self.session.flush()
        await self.session.refresh(integration)
        return integration

    async def delete_integration(self, id: UUID) -> bool:
        """
        Soft delete an integration.

        Args:
            id: Integration UUID

        Returns:
            True if deleted, False if not found
        """
        integration = await self.get_integration(id)
        if not integration:
            return False

        integration.is_deleted = True
        await self.session.flush()
        return True

    # =========================================================================
    # Integration Mapping CRUD Operations
    # =========================================================================

    async def create_mapping(
        self, integration_id: UUID, data: IntegrationMappingCreate
    ) -> IntegrationMapping:
        """
        Create a new integration mapping.

        Args:
            integration_id: Integration UUID
            data: Mapping creation data

        Returns:
            Created mapping with relationships loaded
        """
        mapping = IntegrationMapping(
            integration_id=integration_id,
            organization_id=data.organization_id,
            entity_id=data.entity_id,
            entity_name=data.entity_name,
            oauth_token_id=data.oauth_token_id,
        )
        created = await self.create(mapping)
        # Reload with relationships
        result = await self.get_mapping(created.id)
        assert result is not None, "Created mapping should be retrievable"
        return result

    async def get_mapping(self, id: UUID) -> IntegrationMapping | None:
        """
        Get integration mapping by ID with relationships loaded.

        Args:
            id: Mapping UUID

        Returns:
            IntegrationMapping or None if not found
        """
        result = await self.session.execute(
            select(IntegrationMapping)
            .where(IntegrationMapping.id == id)
            .options(
                joinedload(IntegrationMapping.integration)
                .options(joinedload(Integration.oauth_provider)),
                joinedload(IntegrationMapping.organization),
                joinedload(IntegrationMapping.oauth_token),
            )
        )
        return result.unique().scalar_one_or_none()

    async def get_mapping_by_org(
        self, integration_id: UUID, organization_id: UUID
    ) -> IntegrationMapping | None:
        """
        Get integration mapping for a specific organization.

        Args:
            integration_id: Integration UUID
            organization_id: Organization UUID

        Returns:
            IntegrationMapping or None if not found
        """
        result = await self.session.execute(
            select(IntegrationMapping)
            .where(IntegrationMapping.integration_id == integration_id)
            .where(IntegrationMapping.organization_id == organization_id)
            .options(
                joinedload(IntegrationMapping.integration)
                .options(joinedload(Integration.oauth_provider)),
                joinedload(IntegrationMapping.organization),
                joinedload(IntegrationMapping.oauth_token),
            )
        )
        return result.unique().scalar_one_or_none()

    async def list_mappings(
        self, integration_id: UUID
    ) -> list[IntegrationMapping]:
        """
        List all mappings for an integration.

        Args:
            integration_id: Integration UUID

        Returns:
            List of mappings for the integration
        """
        result = await self.session.execute(
            select(IntegrationMapping)
            .where(IntegrationMapping.integration_id == integration_id)
            .options(
                joinedload(IntegrationMapping.integration)
                .options(joinedload(Integration.oauth_provider)),
                joinedload(IntegrationMapping.organization),
                joinedload(IntegrationMapping.oauth_token),
            )
            .order_by(IntegrationMapping.created_at)
        )
        return list(result.unique().scalars().all())

    async def update_mapping(
        self, id: UUID, data: IntegrationMappingUpdate
    ) -> IntegrationMapping | None:
        """
        Update an integration mapping.

        Args:
            id: Mapping UUID
            data: Update data (partial)

        Returns:
            Updated mapping or None if not found
        """
        mapping = await self.get_mapping(id)
        if not mapping:
            return None

        # Update only provided fields
        if data.entity_id is not None:
            mapping.entity_id = data.entity_id
        if data.entity_name is not None:
            mapping.entity_name = data.entity_name
        if data.oauth_token_id is not None:
            mapping.oauth_token_id = data.oauth_token_id

        await self.session.flush()
        await self.session.refresh(mapping)
        # Reload with relationships
        return await self.get_mapping(id)

    async def delete_mapping(self, id: UUID) -> bool:
        """
        Delete an integration mapping (hard delete).

        Args:
            id: Mapping UUID

        Returns:
            True if deleted, False if not found
        """
        mapping = await self.get_mapping(id)
        if not mapping:
            return False

        await self.delete(mapping)
        return True

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def get_integration_for_org(
        self, integration_name: str, org_id: UUID
    ) -> IntegrationMapping | None:
        """
        Get integration mapping for a specific organization.

        Convenience method that finds the integration by name and gets the
        mapping for the given organization. Returns None if either the
        integration or mapping doesn't exist.

        Used by SDK's `integrations.get()` method.

        Args:
            integration_name: Integration name to look up
            org_id: Organization UUID

        Returns:
            IntegrationMapping with integration and oauth data loaded,
            or None if integration or mapping not found
        """
        # First, find the integration by name
        integration = await self.get_integration_by_name(integration_name)
        if not integration:
            return None

        # Then get the mapping for this org
        return await self.get_mapping_by_org(integration.id, org_id)

    async def get_config_for_mapping(
        self, integration_id: UUID, org_id: UUID
    ) -> dict:
        """
        Get merged configuration for an integration mapping.

        Merges schema defaults from integration config_schema with
        organization-specific overrides from the Config table.

        Args:
            integration_id: Integration UUID
            org_id: Organization UUID

        Returns:
            dict: Merged configuration (schema defaults + org overrides)
        """
        from src.models.orm import Config as ConfigModel
        from sqlalchemy import and_

        # Get the integration to access config schema
        integration = await self.get_integration(integration_id)
        if not integration:
            return {}

        # Build config from schema defaults
        config = {}
        if integration.config_schema:
            for schema_item in integration.config_schema:
                if isinstance(schema_item, dict):
                    if "default" in schema_item:
                        config[schema_item["key"]] = schema_item["default"]
                else:
                    # Handle ConfigSchemaItem objects
                    if hasattr(schema_item, "default") and schema_item.default is not None:
                        config[schema_item.key] = schema_item.default

        # Query for org-specific config overrides
        # Config table entries with integration_id + org_id are per-org integration config
        config_query = select(ConfigModel).where(
            and_(
                ConfigModel.organization_id == org_id,
                ConfigModel.integration_id == integration_id,
            )
        )
        result = await self.session.execute(config_query)
        config_entries = result.scalars().all()

        # Merge org overrides into config
        for entry in config_entries:
            value = entry.value
            if isinstance(value, dict) and "value" in value:
                config[entry.key] = value["value"]
            else:
                config[entry.key] = value

        return config
