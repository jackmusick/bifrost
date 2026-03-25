"""
Datto RMM API helpers for Bifrost integrations.

Authentication:
  - POST /auth/oauth/token using the Datto RMM API key and secret
  - OAuth client credentials are the documented public Swagger values
    `public-client` / `public`

This client keeps the first pass deliberately narrow:
  - list_sites()
  - get_site()
  - list_site_devices()

The org-scoped integration mapping stores the Datto RMM site UID in
`integration.entity_id`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx


class DattoRMMClient:
    DEFAULT_OAUTH_CLIENT_ID = "public-client"
    DEFAULT_OAUTH_CLIENT_SECRET = "public"
    RETRYABLE_STATUS_CODES = {401, 429, 500, 502, 503, 504}

    def __init__(
        self,
        base_uri: str,
        api_key: str,
        api_secret: str,
        *,
        site_uid: str | None = None,
        oauth_client_id: str = DEFAULT_OAUTH_CLIENT_ID,
        oauth_client_secret: str = DEFAULT_OAUTH_CLIENT_SECRET,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_uri = base_uri.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._site_uid = str(site_uid or "").strip() or None
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None
        self._access_token: str | None = None

    @property
    def site_uid(self) -> str | None:
        return self._site_uid

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def _authenticate(self) -> str:
        http = await self._get_http()
        response = await http.post(
            f"{self._base_uri}/auth/oauth/token",
            data={
                "grant_type": "password",
                "username": self._api_key,
                "password": self._api_secret,
            },
            auth=(self._oauth_client_id, self._oauth_client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            body = response.text[:1000]
            raise RuntimeError(
                f"Datto RMM auth failed with HTTP {response.status_code}: {body}"
            )

        payload = response.json()
        access_token = str(payload.get("access_token") or payload.get("accessToken") or "")
        if not access_token:
            raise RuntimeError("Datto RMM auth response did not include access_token")
        self._access_token = access_token
        return access_token

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        return await self._authenticate()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            access_token = await self._get_access_token()
            response = await http.request(
                method,
                url,
                params=params or None,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 401 and attempt < self._max_retries:
                self._access_token = None
                continue

            if response.status_code not in self.RETRYABLE_STATUS_CODES or attempt >= self._max_retries:
                break

            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_seconds = float(retry_after)
                except ValueError:
                    wait_seconds = 2**attempt
            else:
                wait_seconds = 2**attempt
            await asyncio.sleep(min(wait_seconds, 30.0))

        assert response is not None
        if not response.is_success:
            body = response.text[:1000]
            raise RuntimeError(
                f"Datto RMM [{method.upper()} {url}] HTTP {response.status_code}: {body}"
            )
        return response

    @staticmethod
    def _extract_items(payload: dict[str, Any], key: str) -> list[dict]:
        items = payload.get(key, [])
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    async def _get_paginated(self, path: str, *, item_key: str) -> list[dict]:
        items: list[dict] = []
        next_url = f"{self._base_uri}{path}"

        while next_url:
            response = await self._request("GET", next_url)
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Datto RMM [{path}] returned unexpected payload type: {type(payload).__name__}"
                )

            items.extend(self._extract_items(payload, item_key))
            page_details = payload.get("pageDetails", {})
            raw_next_url = page_details.get("nextPageUrl") if isinstance(page_details, dict) else None
            next_url = urljoin(self._base_uri, raw_next_url) if raw_next_url else None

        return items

    @staticmethod
    def normalize_site(site: dict[str, Any]) -> dict[str, str]:
        site_uid = str(
            site.get("uid")
            or site.get("siteUid")
            or site.get("siteUID")
            or site.get("id")
            or ""
        )
        site_name = str(
            site.get("name")
            or site.get("siteName")
            or site.get("accountName")
            or site_uid
        )
        return {
            "id": site_uid,
            "name": site_name,
        }

    async def list_sites(self) -> list[dict]:
        return await self._get_paginated("/api/v2/account/sites", item_key="sites")

    async def get_site(self, site_uid: str | None = None) -> dict[str, Any]:
        resolved_site_uid = str(site_uid or self._site_uid or "").strip()
        if not resolved_site_uid:
            raise RuntimeError(
                "Datto RMM site UID is not available. Configure a site mapping first."
            )

        response = await self._request(
            "GET",
            f"{self._base_uri}/api/v2/site/{resolved_site_uid}",
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def list_site_devices(self, site_uid: str | None = None) -> list[dict]:
        resolved_site_uid = str(site_uid or self._site_uid or "").strip()
        if not resolved_site_uid:
            raise RuntimeError(
                "Datto RMM site UID is not available. Configure a site mapping first."
            )

        return await self._get_paginated(
            f"/api/v2/site/{resolved_site_uid}/devices",
            item_key="devices",
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> DattoRMMClient:
    """
    Build a Datto RMM client from the configured Bifrost integration.

    For org-scoped calls, the mapped Datto RMM site UID is exposed through
    `client.site_uid`.
    """
    from bifrost import integrations

    integration = await integrations.get("Datto RMM", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Datto RMM' not found in Bifrost")

    config = integration.config or {}
    required = ["base_uri", "api_key", "api_secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Datto RMM integration missing required config: {missing}"
        )

    return DattoRMMClient(
        base_uri=config["base_uri"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        site_uid=getattr(integration, "entity_id", None),
        oauth_client_id=config.get("oauth_client_id", DattoRMMClient.DEFAULT_OAUTH_CLIENT_ID),
        oauth_client_secret=config.get(
            "oauth_client_secret",
            DattoRMMClient.DEFAULT_OAUTH_CLIENT_SECRET,
        ),
    )
