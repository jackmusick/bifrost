"""
Bifrost SDK Config Module

Configuration value access via the Bifrost API.
"""

from typing import Any

from bifrost_sdk.client import get_client


async def get(key: str, default: Any = None) -> Any:
    """
    Get configuration value.

    Args:
        key: Configuration key
        default: Default value if not found

    Returns:
        Configuration value or default

    Raises:
        httpx.HTTPStatusError: If request fails (except 404)
    """
    client = get_client()

    try:
        response = await client.get(f"/api/config/{key}")
        if response.status_code == 404:
            return default
        response.raise_for_status()

        data = response.json()
        return data.get("value", default)
    except Exception:
        return default


def get_sync(key: str, default: Any = None) -> Any:
    """
    Get configuration value synchronously.

    Args:
        key: Configuration key
        default: Default value if not found

    Returns:
        Configuration value or default
    """
    client = get_client()

    try:
        response = client.get_sync(f"/api/config/{key}")
        if response.status_code == 404:
            return default
        response.raise_for_status()

        data = response.json()
        return data.get("value", default)
    except Exception:
        return default


async def get_all() -> dict[str, Any]:
    """
    Get all configuration values.

    Returns:
        Dict of all config key-value pairs

    Raises:
        httpx.HTTPStatusError: If request fails
    """
    client = get_client()
    response = await client.get("/api/config")
    response.raise_for_status()

    data = response.json()
    return {item["key"]: item["value"] for item in data.get("configs", [])}


def get_all_sync() -> dict[str, Any]:
    """
    Get all configuration values synchronously.

    Returns:
        Dict of all config key-value pairs
    """
    client = get_client()
    response = client.get_sync("/api/config")
    response.raise_for_status()

    data = response.json()
    return {item["key"]: item["value"] for item in data.get("configs", [])}
