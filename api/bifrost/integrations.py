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
    async def get(name: str, org_id: str | None = None) -> dict[str, Any] | None:
        """
        Get integration configuration for an organization.

        Returns the integration mapping including entity ID, configuration,
        and OAuth details with resolved URLs.

        In platform mode: Reads from database via repositories.
        In external mode: Calls SDK API endpoint.

        Args:
            name: Integration name
            org_id: Organization ID (defaults to current org from context)

        Returns:
            dict | None: Integration data with keys:
                - integration_id: UUID of the integration
                - entity_id: str - Mapped external entity ID (e.g., tenant ID)
                - entity_name: str | None - Display name for the mapped entity
                - config: dict[str, Any] - Merged configuration (schema defaults + org overrides)
                - oauth_client_id: str | None - OAuth client ID from provider or override
                - oauth_token_url: str | None - Token URL with {entity_id} resolved
                - oauth_scopes: str | None - OAuth scopes for this integration
            Returns None if integration or mapping not found.

        Raises:
            RuntimeError: If no execution context (in platform mode without API key)

        Example:
            >>> from bifrost import integrations
            >>> integration = await integrations.get("Microsoft Partner", org_id=context.org_id)
            >>> if integration:
            ...     tenant_id = integration["entity_id"]
            ...     token_url = integration["oauth_token_url"]  # Already resolved
            ...     client_id = integration["oauth_client_id"]
        """
        if _is_platform_context():
            # Direct database access (platform mode)
            from ._internal import get_context
            from src.repositories.integrations import IntegrationsRepository
            from src.services.oauth_provider import resolve_url_template
            from src.core.database import get_db_context

            context = get_context()
            target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

            if not target_org_id:
                logger.warning("integrations.get(): No organization ID provided or in context")
                return None

            # Convert to UUID if needed
            try:
                org_uuid = UUID(target_org_id) if isinstance(target_org_id, str) else target_org_id
            except (ValueError, TypeError):
                logger.warning(f"integrations.get(): Invalid organization ID: {target_org_id}")
                return None

            logger.debug(
                f"integrations.get('{name}'): platform mode, org_id={org_uuid}"
            )

            # Get database session from async context
            async with get_db_context() as session:
                repo = IntegrationsRepository(session)

                # Get the integration mapping for this org
                mapping = await repo.get_integration_for_org(name, org_uuid)

                if not mapping:
                    logger.debug(f"integrations.get('{name}'): mapping not found for org '{org_uuid}'")
                    return None

                # Get merged configuration
                config = await repo.get_config_for_mapping(mapping.integration_id, org_uuid)

                # Build the integration data response
                integration_data = {
                    "integration_id": str(mapping.integration_id),
                    "entity_id": mapping.entity_id,
                    "entity_name": mapping.entity_name,
                    "config": config or {},
                    "oauth_client_id": None,
                    "oauth_token_url": None,
                    "oauth_scopes": None,
                }

                # Add OAuth details if provider is configured
                provider = None
                if mapping.integration and mapping.integration.oauth_provider:
                    provider = mapping.integration.oauth_provider
                    integration_data["oauth_client_id"] = provider.client_id

                    # Format scopes as space-separated string
                    if provider.scopes:
                        integration_data["oauth_scopes"] = " ".join(provider.scopes)

                    # Resolve OAuth token URL with entity_id
                    # Use mapping's entity_id first, fall back to integration's global entity_id
                    entity_id_for_url = mapping.entity_id or mapping.integration.entity_id
                    if provider.token_url and entity_id_for_url:
                        resolved_url = resolve_url_template(
                            url=provider.token_url,
                            entity_id=entity_id_for_url,
                            defaults=provider.token_url_defaults,
                        )
                        integration_data["oauth_token_url"] = resolved_url

                logger.debug(
                    f"integrations.get('{name}'): found integration "
                    f"entity_id={mapping.entity_id}, oauth={bool(provider)}"
                )

                return integration_data
        else:
            # API call (external mode)
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
                    # Handle case where UUID comes back as dict
                    result["integration_id"] = str(result.get("integration_id"))
                return result
            else:
                logger.warning(f"Integrations API call failed: {response.status_code}")
                return None

    @staticmethod
    async def list_mappings(name: str) -> list[dict[str, Any]] | None:
        """
        List all mappings for an integration.

        Returns metadata about all organizations mapped to this integration.

        In platform mode: Reads from database via repositories.
        In external mode: Calls SDK API endpoint.

        Args:
            name: Integration name

        Returns:
            list | None: List of mapping dicts, each containing:
                - organization_id: UUID of the organization
                - entity_id: str - External entity ID
                - entity_name: str | None - Display name
                - config: dict[str, Any] | None - Organization-specific config
            Returns None if integration not found.

        Raises:
            RuntimeError: If no execution context (in platform mode without API key)

        Example:
            >>> from bifrost import integrations
            >>> mappings = await integrations.list_mappings("Microsoft Partner")
            >>> if mappings:
            ...     for mapping in mappings:
            ...         org_id = mapping["organization_id"]
            ...         tenant_id = mapping["entity_id"]
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
                mappings = await repo.list_mappings(integration.id)

                logger.debug(
                    f"integrations.list_mappings('{name}'): found {len(mappings)} mappings"
                )

                # Convert to response format
                result = []
                for mapping in mappings:
                    # Get merged config for each mapping
                    config = await repo.get_config_for_mapping(integration.id, mapping.organization_id)
                    result.append({
                        "organization_id": str(mapping.organization_id),
                        "entity_id": mapping.entity_id,
                        "entity_name": mapping.entity_name,
                        "config": config,
                    })
                return result
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/integrations/list_mappings",
                json={"name": name}
            )

            if response.status_code == 200:
                result = response.json()
                if result is None:
                    return None
                # Convert UUIDs to strings for consistency
                for mapping in result:
                    if isinstance(mapping.get("organization_id"), dict):
                        mapping["organization_id"] = str(mapping.get("organization_id"))
                return result
            else:
                logger.warning(f"Integrations API call failed: {response.status_code}")
                return None
