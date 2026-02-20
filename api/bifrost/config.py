"""
Configuration SDK for Bifrost - API-only implementation.

Provides Python API for configuration management (get, set, list, delete).
All operations go through HTTP API endpoints.
All methods are async and must be awaited.
"""

from __future__ import annotations

from typing import Any

from .client import get_client
from .models import ConfigData
from ._context import get_default_scope


def _resolve_scope(scope: str | None) -> str | None:
    """Resolve effective scope - explicit override or default from context."""
    if scope is not None:
        return scope
    return get_default_scope()


class config:
    """
    Configuration management operations.

    Allows workflows to read and write configuration values scoped to organizations.
    All operations are performed via HTTP API endpoints.

    All methods are async - await is required.
    """

    @staticmethod
    async def get(
        key: str,
        default: Any = None,
        scope: str | None = None,
    ) -> Any:
        """
        Get configuration value with automatic secret decryption.

        Calls SDK API endpoint to retrieve configuration.

        Args:
            key: Configuration key
            default: Default value if key not found (optional)
            scope: Organization scope - can be:
                - None: Use execution context default org
                - org UUID string: Target specific organization
                - "global": Bypass org resolution, use global config

        Returns:
            Any: Configuration value, or default if not found

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import config
            >>> api_key = await config.get("api_key")
            >>> timeout = await config.get("timeout", default=30)
            >>> global_setting = await config.get("global_key", scope="global")
            >>> org_setting = await config.get("key", scope="org-uuid-here")
        """
        client = get_client()
        effective_scope = _resolve_scope(scope)
        response = await client.post(
            "/api/cli/config/get",
            json={"key": key, "scope": effective_scope}
        )

        if response.status_code == 200:
            result = response.json()
            if result is None:
                return default
            value = result.get("value", default)
            if result.get("config_type") == "secret" and isinstance(value, str):
                from ._context import register_secret
                register_secret(value)
            return value
        else:
            return default

    @staticmethod
    async def set(
        key: str,
        value: Any,
        is_secret: bool = False,
        scope: str | None = None,
    ) -> None:
        """
        Set configuration value.

        Calls SDK API endpoint to store configuration (writes directly to database).

        Args:
            key: Configuration key
            value: Configuration value (must be JSON-serializable)
            is_secret: If True, encrypts the value before storage
            scope: Organization scope - can be:
                - None: Use execution context default org
                - org UUID string: Target specific organization
                - "global": Bypass org resolution, use global config

        Raises:
            RuntimeError: If not authenticated
            ValueError: If value is not JSON-serializable

        Example:
            >>> from bifrost import config
            >>> await config.set("api_url", "https://api.example.com")
            >>> await config.set("api_key", "secret123", is_secret=True)
            >>> await config.set("global_setting", "value", scope="global")
            >>> await config.set("org_setting", "value", scope="org-uuid-here")
        """
        client = get_client()
        effective_scope = _resolve_scope(scope)
        response = await client.post(
            "/api/cli/config/set",
            json={
                "key": key,
                "value": value,
                "is_secret": is_secret,
                "scope": effective_scope,
            }
        )
        response.raise_for_status()

    @staticmethod
    async def list(scope: str | None = None) -> ConfigData:
        """
        List configuration key-value pairs.

        Note: Secret values are shown as the decrypted value (or "[SECRET]" on error).

        Args:
            scope: Organization scope - can be:
                - None: Use execution context default org
                - org UUID string: Target specific organization
                - "global": Bypass org resolution, use global config

        Returns:
            ConfigData: Configuration data with dot-notation and dict-like access:
                >>> cfg = await config.list()
                >>> cfg.api_url        # Dot notation access
                >>> cfg["api_url"]     # Dict-like access
                >>> "api_url" in cfg   # Containment check
                >>> cfg.keys()         # Iterate keys

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import config
            >>> cfg = await config.list()
            >>> api_url = cfg.api_url
            >>> timeout = cfg.timeout or 30
            >>> global_cfg = await config.list(scope="global")
        """
        client = get_client()
        effective_scope = _resolve_scope(scope)
        response = await client.post(
            "/api/cli/config/list",
            json={"scope": effective_scope}
        )
        response.raise_for_status()
        return ConfigData.model_validate({"data": response.json()})

    @staticmethod
    async def delete(key: str, scope: str | None = None) -> bool:
        """
        Delete configuration value.

        Calls SDK API endpoint to delete configuration (deletes directly from database).

        Args:
            key: Configuration key
            scope: Organization scope - can be:
                - None: Use execution context default org
                - org UUID string: Target specific organization
                - "global": Bypass org resolution, use global config

        Returns:
            bool: True if deleted successfully

        Raises:
            RuntimeError: If not authenticated

        Example:
            >>> from bifrost import config
            >>> await config.delete("old_api_url")
            >>> await config.delete("global_key", scope="global")
        """
        client = get_client()
        effective_scope = _resolve_scope(scope)
        response = await client.post(
            "/api/cli/config/delete",
            json={"key": key, "scope": effective_scope}
        )
        response.raise_for_status()
        return response.json()
