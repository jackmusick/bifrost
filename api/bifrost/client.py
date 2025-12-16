"""
Bifrost SDK Client

HTTP client for Bifrost API communication.
Auto-initializes from environment variables or .env file.
"""

import os
from typing import Any

import httpx

# Auto-load .env file if present (for local development)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on environment variables


class BifrostClient:
    """
    HTTP client for Bifrost API.

    Singleton pattern - use get_client() to get the instance.
    """

    _instance: "BifrostClient | None" = None

    def __init__(self, api_url: str, api_key: str):
        """
        Initialize client.

        Args:
            api_url: Bifrost API URL
            api_key: Developer API key (bfsk_...)
        """
        self.api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._sync_http = httpx.Client(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._context: dict[str, Any] | None = None

    @classmethod
    def get_instance(cls) -> "BifrostClient":
        """
        Get singleton client instance.

        Auto-initializes from environment variables:
        - BIFROST_DEV_URL: API URL
        - BIFROST_DEV_KEY: Developer API key

        Returns:
            BifrostClient instance

        Raises:
            RuntimeError: If environment variables not set
        """
        if cls._instance is None:
            api_url = os.getenv("BIFROST_DEV_URL")
            api_key = os.getenv("BIFROST_DEV_KEY")

            if not api_url or not api_key:
                raise RuntimeError(
                    "BIFROST_DEV_URL and BIFROST_DEV_KEY environment variables required.\n"
                    "Set them in your .env file or export them:\n"
                    "  export BIFROST_DEV_URL=https://your-bifrost-instance.com\n"
                    "  export BIFROST_DEV_KEY=bfsk_xxxxxxxxxxxx"
                )

            cls._instance = cls(api_url, api_key)

        return cls._instance

    def _fetch_context_sync(self) -> dict[str, Any]:
        """Fetch development context synchronously."""
        if self._context is None:
            response = self._sync_http.get("/api/cli/context")
            response.raise_for_status()
            self._context = response.json()
        return self._context or {}

    async def _fetch_context(self) -> dict[str, Any]:
        """Fetch development context."""
        if self._context is None:
            response = await self._http.get("/api/cli/context")
            response.raise_for_status()
            self._context = response.json()
        return self._context or {}

    @property
    def context(self) -> dict[str, Any]:
        """Get cached development context (fetches synchronously if needed)."""
        return self._fetch_context_sync()

    @property
    def user(self) -> dict[str, Any]:
        """Get current user info."""
        return self.context.get("user", {})

    @property
    def organization(self) -> dict[str, Any] | None:
        """Get default organization."""
        return self.context.get("organization")

    @property
    def default_parameters(self) -> dict[str, Any]:
        """Get default workflow parameters."""
        return self.context.get("default_parameters", {})

    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make GET request."""
        return await self._http.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make POST request."""
        return await self._http.post(path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        """Make PUT request."""
        return await self._http.put(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """Make DELETE request."""
        return await self._http.delete(path, **kwargs)

    def get_sync(self, path: str, **kwargs) -> httpx.Response:
        """Make synchronous GET request."""
        return self._sync_http.get(path, **kwargs)

    def post_sync(self, path: str, **kwargs) -> httpx.Response:
        """Make synchronous POST request."""
        return self._sync_http.post(path, **kwargs)

    async def close(self):
        """Close HTTP clients."""
        await self._http.aclose()
        self._sync_http.close()


def get_client() -> BifrostClient:
    """Get the singleton Bifrost client."""
    return BifrostClient.get_instance()
