"""
Bifrost SDK Generic API Client

Thin wrapper exposing authenticated HTTP methods for arbitrary API calls.
Returns httpx.Response objects for full control over status codes, headers, etc.

Usage:
    from bifrost import api

    response = await api.get("/api/workflows")
    data = response.json()

    response = await api.post("/api/some-endpoint", json={"key": "value"})
"""

import httpx

from .client import get_client


class api:
    """Generic authenticated HTTP client for Bifrost API.

    Returns httpx.Response objects for full control over status codes, headers, etc.

    Example:
        response = await api.get("/api/workflows")
        data = response.json()
    """

    @staticmethod
    async def get(path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make an authenticated GET request."""
        return await get_client().get(path, **kwargs)

    @staticmethod
    async def post(path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make an authenticated POST request."""
        return await get_client().post(path, **kwargs)

    @staticmethod
    async def put(path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make an authenticated PUT request."""
        return await get_client().put(path, **kwargs)

    @staticmethod
    async def patch(path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make an authenticated PATCH request."""
        return await get_client().patch(path, **kwargs)

    @staticmethod
    async def delete(path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        """Make an authenticated DELETE request."""
        return await get_client().delete(path, **kwargs)
