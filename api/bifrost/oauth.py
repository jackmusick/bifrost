"""
OAuth SDK for Bifrost.

Provides Python API for OAuth token retrieval.

Works in two modes:
1. Platform context (inside workflows): Direct Redis access (pre-warmed cache)
2. External context (via dev API key): API calls to SDK endpoints

All methods are async and must be awaited.
"""

from __future__ import annotations

import json as json_module
import logging
from typing import Any

from ._context import _execution_context

logger = logging.getLogger(__name__)


def _is_platform_context() -> bool:
    """Check if running inside platform execution context."""
    return _execution_context.get() is not None


def _get_client():
    """Get the BifrostClient for API calls."""
    from .client import get_client
    return get_client()


class oauth:
    """
    OAuth token management operations.

    Allows workflows to retrieve OAuth tokens for external integrations.

    In platform mode:
    - Reads from Redis cache (pre-warmed before execution with decrypted credentials)

    In external mode:
    - Reads via SDK API endpoint

    All methods are async - await is required.
    """

    @staticmethod
    async def get(provider: str, org_id: str | None = None) -> dict[str, Any] | None:
        """
        Get OAuth connection configuration and tokens for a provider.

        Returns the full OAuth configuration including decrypted credentials
        and tokens needed for API calls or custom token operations.

        In platform mode: Reads from Redis cache (pre-warmed with decrypted secrets).
        In external mode: Calls SDK API endpoint.

        Args:
            provider: OAuth provider/connection name (e.g., "microsoft", "partner_center")
            org_id: Organization ID (defaults to current org from context)

        Returns:
            dict | None: OAuth connection config with keys:
                - connection_name: str
                - client_id: str
                - client_secret: str (decrypted)
                - authorization_url: str | None
                - token_url: str | None
                - scopes: list[str]
                - access_token: str | None (decrypted, if available)
                - refresh_token: str | None (decrypted, if available)
                - expires_at: str | None (ISO format, if available)
            Returns None if connection not found.

        Raises:
            RuntimeError: If no execution context (in platform mode without API key)

        Example:
            >>> from bifrost import oauth
            >>> conn = await oauth.get("partner_center")
            >>> if conn:
            ...     client_id = conn["client_id"]
            ...     client_secret = conn["client_secret"]
            ...     refresh_token = conn["refresh_token"]
        """
        if _is_platform_context():
            # Direct Redis access (platform mode)
            from src.core.cache import get_redis, oauth_hash_key
            from ._internal import get_context

            context = get_context()
            target_org = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

            async with get_redis() as r:
                data = await r.hget(oauth_hash_key(target_org), provider)  # type: ignore[misc]

                if data is None:
                    logger.warning(f"OAuth connection '{provider}' not found in cache for org '{target_org}'")
                    return None

                try:
                    cache_entry = json_module.loads(data)
                except json_module.JSONDecodeError:
                    logger.warning(f"Invalid JSON for OAuth provider '{provider}'")
                    return None

                # Return the cached OAuth data (already decrypted at pre-warm time)
                return {
                    "connection_name": cache_entry.get("provider_name"),
                    "client_id": cache_entry.get("client_id"),
                    "client_secret": cache_entry.get("client_secret"),
                    "authorization_url": cache_entry.get("authorization_url"),
                    "token_url": cache_entry.get("token_url"),
                    "scopes": cache_entry.get("scopes", []),
                    "access_token": cache_entry.get("access_token"),
                    "refresh_token": cache_entry.get("refresh_token"),
                    "expires_at": cache_entry.get("expires_at"),
                }
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/oauth/get",
                json={"provider": provider, "org_id": org_id}
            )

            if response.status_code == 200:
                result = response.json()
                if result is None:
                    return None
                # Convert API response to standard format
                return {
                    "connection_name": result.get("connection_name"),
                    "client_id": result.get("client_id"),
                    "client_secret": result.get("client_secret"),
                    "authorization_url": result.get("authorization_url"),
                    "token_url": result.get("token_url"),
                    "scopes": result.get("scopes", []),
                    "access_token": result.get("access_token"),
                    "refresh_token": result.get("refresh_token"),
                    "expires_at": result.get("expires_at"),
                }
            else:
                logger.warning(f"OAuth API call failed: {response.status_code}")
                return None
