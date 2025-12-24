"""
Configuration SDK for Bifrost.

Provides Python API for configuration management (get, set, list, delete).

Works in two modes:
1. Platform context (inside workflows): Direct Redis access (pre-warmed cache)
2. External context (via dev API key): API calls to SDK endpoints

All methods are async and must be awaited.
"""

from __future__ import annotations

import json as json_module
import logging
from typing import Any

from src.models.contracts.sdk import ConfigData

from ._context import _execution_context

logger = logging.getLogger(__name__)


def _is_platform_context() -> bool:
    """Check if running inside platform execution context."""
    return _execution_context.get() is not None


def _get_client():
    """Get the BifrostClient for API calls."""
    from .client import get_client
    return get_client()


class config:
    """
    Configuration management operations.

    Allows workflows to read and write configuration values scoped to organizations.

    In platform mode:
    - Reads from Redis cache (populated by pre-warming)
    - Writes to buffer (flushed post-execution)

    In external mode:
    - Reads/writes via SDK API endpoints

    All methods are async - await is required.
    """

    @staticmethod
    async def get(key: str, org_id: str | None = None, default: Any = None) -> Any:
        """
        Get configuration value with automatic secret decryption.

        In platform mode: Reads from Redis cache (pre-warmed before execution).
        In external mode: Calls SDK API endpoint.

        Args:
            key: Configuration key
            org_id: Organization ID (defaults to current org from context)
            default: Default value if key not found (optional)

        Returns:
            Any: Configuration value, or default if not found

        Raises:
            RuntimeError: If no execution context (in platform mode without API key)

        Example:
            >>> from bifrost import config
            >>> api_key = await config.get("api_key")
            >>> timeout = await config.get("timeout", default=30)
        """
        if _is_platform_context():
            # Direct Redis access (platform mode)
            from src.core.cache import config_hash_key, get_redis
            from ._internal import get_context

            context = get_context()
            target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)
            logger.debug(
                f"config.get('{key}'): context.scope={getattr(context, 'scope', None)}, "
                f"context.org_id={getattr(context, 'org_id', None)}, target_org_id={target_org_id}"
            )

            async with get_redis() as r:
                data = await r.hget(config_hash_key(target_org_id), key)  # type: ignore[misc]

                if data is None:
                    logger.debug(f"config.get('{key}'): not found in cache, returning default={default}")
                    return default

                try:
                    cache_entry = json_module.loads(data)
                except json_module.JSONDecodeError:
                    return default

                raw_value = cache_entry.get("value")
                config_type = cache_entry.get("type", "string")

                logger.debug(
                    f"config.get('{key}'): found in cache with "
                    f"type={config_type}, value={raw_value if config_type != 'secret' else '[SECRET]'}"
                )

                # Parse value based on type
                if config_type == "secret":
                    return raw_value
                elif config_type == "json":
                    if isinstance(raw_value, str):
                        try:
                            return json_module.loads(raw_value)
                        except json_module.JSONDecodeError:
                            return raw_value
                    return raw_value
                elif config_type == "bool":
                    if isinstance(raw_value, bool):
                        return raw_value
                    return str(raw_value).lower() == "true"
                elif config_type == "int":
                    try:
                        return int(raw_value)
                    except (ValueError, TypeError):
                        return raw_value
                else:
                    return raw_value
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/config/get",
                json={"key": key, "org_id": org_id}
            )

            if response.status_code == 200:
                result = response.json()
                if result is None:
                    return default
                return result.get("value", default)
            else:
                return default

    @staticmethod
    async def set(key: str, value: Any, org_id: str | None = None, is_secret: bool = False) -> None:
        """
        Set configuration value.

        In platform mode: Writes to Redis buffer (flushed to Postgres after execution).
        In external mode: Calls SDK API endpoint (writes directly to database).

        Args:
            key: Configuration key
            value: Configuration value (must be JSON-serializable)
            org_id: Organization ID (defaults to current org from context)
            is_secret: If True, encrypts the value before storage

        Raises:
            RuntimeError: If no execution context (in platform mode)
            ValueError: If value is not JSON-serializable

        Example:
            >>> from bifrost import config
            >>> await config.set("api_url", "https://api.example.com")
            >>> await config.set("api_key", "secret123", is_secret=True)
        """
        if _is_platform_context():
            # Write to buffer (platform mode)
            from ._internal import get_context
            from ._write_buffer import get_write_buffer

            context = get_context()
            target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

            # Determine config type
            if is_secret:
                from src.core.security import encrypt_secret
                config_type = "secret"
                stored_value = encrypt_secret(str(value))
            elif isinstance(value, (dict, list)):
                config_type = "json"
                stored_value = value
            elif isinstance(value, bool):
                config_type = "bool"
                stored_value = value
            elif isinstance(value, int):
                config_type = "int"
                stored_value = value
            else:
                config_type = "string"
                stored_value = value

            buffer = get_write_buffer()
            await buffer.add_config_change(
                operation="set",
                key=key,
                value=stored_value,
                org_id=target_org_id,
                config_type=config_type,
            )
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/config/set",
                json={"key": key, "value": value, "org_id": org_id, "is_secret": is_secret}
            )
            response.raise_for_status()

    @staticmethod
    async def list(org_id: str | None = None) -> ConfigData:
        """
        List configuration key-value pairs.

        Note: Secret values are shown as the decrypted value (or "[SECRET]" on error).

        Args:
            org_id: Organization ID (optional, defaults to current org)

        Returns:
            ConfigData: Configuration data with dot-notation and dict-like access:
                >>> cfg = await config.list()
                >>> cfg.api_url        # Dot notation access
                >>> cfg["api_url"]     # Dict-like access
                >>> "api_url" in cfg   # Containment check
                >>> cfg.keys()         # Iterate keys

        Raises:
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import config
            >>> cfg = await config.list()
            >>> api_url = cfg.api_url
            >>> timeout = cfg.timeout or 30
        """
        if _is_platform_context():
            # Direct Redis access (platform mode)
            from src.core.cache import config_hash_key, get_redis
            from ._internal import get_context

            context = get_context()
            target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

            async with get_redis() as r:
                all_data = await r.hgetall(config_hash_key(target_org_id))  # type: ignore[misc]

                if not all_data:
                    return ConfigData({})

                config_dict: dict[str, Any] = {}
                for config_key, data in all_data.items():
                    try:
                        cache_entry = json_module.loads(data)
                    except json_module.JSONDecodeError:
                        continue

                    raw_value = cache_entry.get("value")
                    config_type = cache_entry.get("type", "string")

                    # Parse value based on type
                    if config_type == "secret":
                        config_dict[config_key] = raw_value if raw_value else "[SECRET]"
                    elif config_type == "json" and isinstance(raw_value, str):
                        try:
                            config_dict[config_key] = json_module.loads(raw_value)
                        except json_module.JSONDecodeError:
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

                return ConfigData(config_dict)
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/config/list",
                json={"org_id": org_id}
            )
            response.raise_for_status()
            return ConfigData(response.json())

    @staticmethod
    async def delete(key: str, org_id: str | None = None) -> bool:
        """
        Delete configuration value.

        In platform mode: Writes to buffer (deletion applied to Postgres after execution).
        In external mode: Calls SDK API endpoint (deletes directly from database).

        Args:
            key: Configuration key
            org_id: Organization ID (defaults to current org from context)

        Returns:
            bool: True (deletion queued or completed)

        Raises:
            RuntimeError: If no execution context (in platform mode)

        Example:
            >>> from bifrost import config
            >>> await config.delete("old_api_url")
        """
        if _is_platform_context():
            # Write delete to buffer (platform mode)
            from ._internal import get_context
            from ._write_buffer import get_write_buffer

            context = get_context()
            target_org_id = org_id or getattr(context, 'org_id', None) or getattr(context, 'scope', None)

            buffer = get_write_buffer()
            await buffer.add_config_change(
                operation="delete",
                key=key,
                org_id=target_org_id,
            )
            return True
        else:
            # API call (external mode)
            client = _get_client()
            response = await client.post(
                "/api/cli/config/delete",
                json={"key": key, "org_id": org_id}
            )
            response.raise_for_status()
            return response.json()
