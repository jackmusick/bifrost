"""
Integrations SDK for Bifrost.

Provides Python API for integration management and OAuth configuration.

Works in two modes:
1. Platform context (inside workflows): Direct database access via context
2. External context (via dev API key): API calls to SDK endpoints

All methods are async and must be awaited.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from src.models.contracts.sdk import IntegrationData, OAuthCredentials
from src.models.contracts.integrations import IntegrationMappingResponse

from ._context import _execution_context

logger = logging.getLogger(__name__)


def _is_platform_context() -> bool:
    """Check if running inside platform execution context."""
    return _execution_context.get() is not None


def _get_client():
    """Get the BifrostClient for API calls."""
    from .client import get_client
    return get_client()


class integrations:
    """
    Integration management operations.

    Allows workflows to retrieve integration configurations and mappings.

    In platform mode:
    - Reads from database via repositories
    - Resolves OAuth URLs with entity IDs

    In external mode:
    - Reads via SDK API endpoints

    All methods are async - await is required.
    """

    @staticmethod
    async def get(name: str, org_id: str | None = None) -> IntegrationData | None:
        """
        Get integration configuration for an organization.

        Returns the integration data including entity ID, configuration,
        and full OAuth details with decrypted credentials.

        When an org-specific mapping exists, returns that mapping's data.
        When no mapping exists, falls back to integration-level defaults.

        In platform mode: Reads from database via repositories.
        In external mode: Calls SDK API endpoint.

        Args:
            name: Integration name
            org_id: Organization ID (defaults to current org from context)

        Returns:
            IntegrationData | None: Integration data with attributes:
                - integration_id: str - UUID of the integration
                - entity_id: str | None - External entity ID (from mapping or default_entity_id)
                - entity_name: str | None - Display name for the mapped entity
                - config: dict[str, Any] - Configuration (org overrides + defaults)
                - oauth: OAuthCredentials | None - OAuth data with attributes:
                    - connection_name: str
                    - client_id: str
                    - client_secret: str | None (decrypted)
                    - authorization_url: str | None
                    - token_url: str | None (resolved with entity_id)
                    - scopes: list[str]
                    - access_token: str | None (decrypted)
                    - refresh_token: str | None (decrypted)
                    - expires_at: str | None (ISO format)
            Returns None if integration not found.

        Example:
            >>> from bifrost import integrations
            >>> integration = await integrations.get("HaloPSA")
            >>> if integration:
            ...     tenant_id = integration.entity_id
            ...     if integration.oauth:
            ...         client_id = integration.oauth.client_id
            ...         refresh_token = integration.oauth.refresh_token
        """
        if _is_platform_context():
            return await integrations._get_platform_mode(name, org_id)
        else:
            return await integrations._get_external_mode(name, org_id)

    @staticmethod
    async def _get_platform_mode(name: str, org_id: str | None = None) -> IntegrationData | None:
        """Platform mode implementation for integrations.get()."""
        from ._internal import get_context
        from src.repositories.integrations import IntegrationsRepository
        from src.services.oauth_provider import resolve_url_template
        from src.core.database import get_db_context
        from src.core.security import decrypt_secret

        context = get_context()
        target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

        async with get_db_context() as session:
            repo = IntegrationsRepository(session)

            # Try to get org-specific mapping first
            mapping = None
            org_uuid = None
            if target_org_id:
                try:
                    org_uuid = UUID(target_org_id) if isinstance(target_org_id, str) else target_org_id
                    mapping = await repo.get_integration_for_org(name, org_uuid)
                except (ValueError, TypeError):
                    logger.debug(f"integrations.get('{name}'): invalid org_id '{target_org_id}'")

            if mapping:
                # Org-specific mapping found - use mapping data
                logger.debug(
                    f"integrations.get('{name}'): found org mapping, "
                    f"entity_id={mapping.entity_id}"
                )
                return await integrations._build_response_from_mapping(
                    repo, mapping, org_uuid, resolve_url_template, decrypt_secret
                )

            # Fall back to integration defaults
            integration = await repo.get_integration_by_name(name)
            if not integration:
                logger.debug(f"integrations.get('{name}'): integration not found")
                return None

            logger.debug(
                f"integrations.get('{name}'): using integration defaults, "
                f"entity_id={integration.default_entity_id}"
            )
            return await integrations._build_response_from_integration(
                repo, integration, resolve_url_template, decrypt_secret
            )

    @staticmethod
    async def _build_response_from_mapping(
        repo: Any,
        mapping: Any,
        org_uuid: UUID | None,
        resolve_url_template: Any,
        decrypt_secret: Any,
    ) -> IntegrationData:
        """Build IntegrationData from an org-specific mapping."""
        integration = mapping.integration

        # Get merged configuration (defaults + org overrides)
        config = await repo.get_config_for_mapping(mapping.integration_id, org_uuid) if org_uuid else {}

        # Entity ID from mapping, fallback to integration default
        entity_id = mapping.entity_id or integration.default_entity_id or integration.entity_id

        # Build OAuth credentials if provider is configured
        oauth: OAuthCredentials | None = None
        if integration and integration.oauth_provider:
            provider = integration.oauth_provider

            # Get token - prefer mapping's oauth_token, fall back to provider's org-level token
            token = None
            if mapping.oauth_token:
                token = mapping.oauth_token
            else:
                token = await repo.get_provider_org_token(provider.id)

            oauth = integrations._build_oauth_data(
                provider, token, entity_id, resolve_url_template, decrypt_secret
            )

        return IntegrationData(
            integration_id=str(mapping.integration_id),
            entity_id=entity_id,
            entity_name=mapping.entity_name,
            config=config or {},
            oauth=oauth,
        )

    @staticmethod
    async def _build_response_from_integration(
        repo: Any,
        integration: Any,
        resolve_url_template: Any,
        decrypt_secret: Any,
    ) -> IntegrationData:
        """Build IntegrationData from integration defaults (no org mapping)."""
        # Entity ID from integration defaults
        entity_id = integration.default_entity_id or integration.entity_id

        # Get integration-level config defaults (org_id=NULL)
        config = await repo.get_integration_defaults(integration.id)

        # Build OAuth credentials if provider is configured
        oauth: OAuthCredentials | None = None
        if integration.oauth_provider:
            provider = integration.oauth_provider

            # Get org-level token from provider (user_id=NULL)
            token = await repo.get_provider_org_token(provider.id)

            oauth = integrations._build_oauth_data(
                provider, token, entity_id, resolve_url_template, decrypt_secret
            )

        return IntegrationData(
            integration_id=str(integration.id),
            entity_id=entity_id,
            entity_name=None,  # No org mapping = no entity name
            config=config or {},
            oauth=oauth,
        )

    @staticmethod
    def _build_oauth_data(
        provider: Any,
        token: Any,
        entity_id: str | None,
        resolve_url_template: Any,
        decrypt_secret: Any,
    ) -> OAuthCredentials:
        """Build OAuthCredentials from provider and token."""
        # Decrypt secrets
        client_secret = None
        if provider.encrypted_client_secret:
            try:
                raw = provider.encrypted_client_secret
                client_secret = decrypt_secret(raw.decode() if isinstance(raw, bytes) else raw)
            except Exception:
                logger.warning("Failed to decrypt client_secret")

        access_token = None
        refresh_token = None
        expires_at = None

        if token:
            if token.encrypted_access_token:
                try:
                    raw = token.encrypted_access_token
                    access_token = decrypt_secret(raw.decode() if isinstance(raw, bytes) else raw)
                except Exception:
                    logger.warning("Failed to decrypt access_token")

            if token.encrypted_refresh_token:
                try:
                    raw = token.encrypted_refresh_token
                    refresh_token = decrypt_secret(raw.decode() if isinstance(raw, bytes) else raw)
                except Exception:
                    logger.warning("Failed to decrypt refresh_token")

            if token.expires_at:
                expires_at = token.expires_at.isoformat()

        # Resolve token_url with entity_id
        resolved_token_url = None
        if provider.token_url and entity_id:
            resolved_token_url = resolve_url_template(
                url=provider.token_url,
                entity_id=entity_id,
                defaults=provider.token_url_defaults,
            )

        return OAuthCredentials(
            connection_name=provider.provider_name,
            client_id=provider.client_id,
            client_secret=client_secret,
            authorization_url=provider.authorization_url,
            token_url=resolved_token_url,
            scopes=provider.scopes or [],
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    @staticmethod
    async def _get_external_mode(name: str, org_id: str | None = None) -> IntegrationData | None:
        """External mode implementation for integrations.get()."""
        client = _get_client()
        response = await client.post(
            "/api/cli/integrations/get",
            json={"name": name, "org_id": org_id}
        )

        if response.status_code == 200:
            result = response.json()
            if result is None:
                return None
            # Convert UUID to string if needed for consistency
            if isinstance(result.get("integration_id"), dict):
                result["integration_id"] = str(result.get("integration_id"))
            # Convert oauth dict to OAuthCredentials if present
            if result.get("oauth"):
                result["oauth"] = OAuthCredentials(**result["oauth"])
            return IntegrationData(**result)
        else:
            logger.warning(f"Integrations API call failed: {response.status_code}")
            return None

    @staticmethod
    async def list_mappings(name: str) -> list[IntegrationMappingResponse] | None:
        """
        List all mappings for an integration.

        Returns metadata about all organizations mapped to this integration.

        In platform mode: Reads from database via repositories.
        In external mode: Calls SDK API endpoint.

        Args:
            name: Integration name

        Returns:
            list[IntegrationMappingResponse] | None: List of mappings, each with attributes:
                - id: UUID - Mapping ID
                - integration_id: UUID - Associated integration ID
                - organization_id: UUID - Organization ID
                - entity_id: str - External entity ID
                - entity_name: str | None - Display name
                - oauth_token_id: UUID | None - Per-org OAuth token override ID
                - config: dict[str, Any] | None - Organization-specific config
                - created_at: datetime - Creation timestamp
                - updated_at: datetime - Last update timestamp
            Returns None if integration not found.

        Raises:
            RuntimeError: If no execution context (in platform mode without API key)

        Example:
            >>> from bifrost import integrations
            >>> mappings = await integrations.list_mappings("Microsoft Partner")
            >>> if mappings:
            ...     for mapping in mappings:
            ...         org_id = mapping.organization_id
            ...         tenant_id = mapping.entity_id
        """
        if _is_platform_context():
            # Direct database access (platform mode)
            from ._internal import get_context
            from src.repositories.integrations import IntegrationsRepository
            from src.core.database import get_db_context

            _context = get_context()
            logger.debug("integrations.list_mappings(): platform mode")

            async with get_db_context() as session:
                repo = IntegrationsRepository(session)

                # Get the integration by name
                integration = await repo.get_integration_by_name(name)

                if not integration:
                    logger.warning(f"integrations.list_mappings(): integration '{name}' not found")
                    return None

                # Get all mappings for this integration
                orm_mappings = await repo.list_mappings(integration.id)

                logger.debug(
                    f"integrations.list_mappings('{name}'): found {len(orm_mappings)} mappings"
                )

                # Convert to IntegrationMappingResponse models
                result: list[IntegrationMappingResponse] = []
                for orm_mapping in orm_mappings:
                    # Get merged config for each mapping
                    mapping_config = await repo.get_config_for_mapping(integration.id, orm_mapping.organization_id)
                    result.append(IntegrationMappingResponse(
                        id=orm_mapping.id,
                        integration_id=orm_mapping.integration_id,
                        organization_id=orm_mapping.organization_id,
                        entity_id=orm_mapping.entity_id,
                        entity_name=orm_mapping.entity_name,
                        oauth_token_id=orm_mapping.oauth_token_id,
                        config=mapping_config,
                        created_at=orm_mapping.created_at,
                        updated_at=orm_mapping.updated_at,
                    ))
                return result
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/integrations/list_mappings",
                json={"name": name}
            )

            if response.status_code == 200:
                json_result = response.json()
                if json_result is None:
                    return None
                # API returns {"items": [...]} structure
                items = json_result.get("items", [])
                # Convert to IntegrationMappingResponse models
                sdk_mappings: list[IntegrationMappingResponse] = []
                for mapping_data in items:
                    sdk_mappings.append(IntegrationMappingResponse(**mapping_data))
                return sdk_mappings
            else:
                logger.warning(f"Integrations API call failed: {response.status_code}")
                return None
