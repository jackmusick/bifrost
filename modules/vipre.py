"""
VIPRE External API helpers for Bifrost integrations.

Authentication:
  - X-Vipre-Endpoint-Key-Id
  - X-Vipre-Endpoint-Api-Key

The documented API does not expose a direct site-list endpoint for child MSP
sites, so site mappings are inferred from device inventory records that carry
`siteUuid` and `siteName`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx


class VipreClient:
    """Focused async client for the VIPRE External API."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_uri: str,
        key_id: str,
        api_key: str,
        *,
        site_uuid: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_uri = base_uri.rstrip("/")
        self._key_id = key_id
        self._api_key = api_key
        self._site_uuid = str(site_uuid) if site_uuid is not None else None
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None

    @property
    def site_uuid(self) -> str | None:
        return self._site_uuid

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_uri,
                headers={
                    "X-Vipre-Endpoint-Key-Id": self._key_id,
                    "X-Vipre-Endpoint-Api-Key": self._api_key,
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=params or None,
                json=json_body,
            )

            if response.status_code not in self.RETRYABLE_STATUS_CODES:
                break

            if attempt >= self._max_retries:
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
                f"VIPRE [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _build_filters(filters: list[str] | None = None) -> list[str] | None:
        values = [value for value in (filters or []) if value]
        return values or None

    @staticmethod
    def _extract_items(payload: Any) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        # The documented payload shape uses "devices", but tolerate "items"
        # so the client also works with generic paginated wrappers.
        items = payload.get("devices")
        if items is None:
            items = payload.get("items", [])
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _extract_total(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            return None
        total = metadata.get("total")
        return total if isinstance(total, int) else None

    async def get_site(self) -> dict:
        payload = await self._request("GET", "/ext/site")
        return payload if isinstance(payload, dict) else {}

    async def list_devices_page(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        filters: list[str] | None = None,
        sort: list[str] | None = None,
    ) -> dict:
        params: dict[str, Any] = {
            "offset": offset,
            "limit": limit,
        }
        built_filters = self._build_filters(filters)
        if built_filters:
            params["filter"] = built_filters
        if sort:
            params["sort"] = sort
        payload = await self._request("GET", "/ext/devices", params=params)
        return payload if isinstance(payload, dict) else {}

    async def list_all_devices(
        self,
        *,
        site_uuid: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        resolved_site_uuid = site_uuid or self._site_uuid
        filters = [f"siteUuid,{resolved_site_uuid}"] if resolved_site_uuid else None

        offset = 0
        items: list[dict] = []

        while True:
            payload = await self.list_devices_page(
                offset=offset,
                limit=limit,
                filters=filters,
            )
            page_items = self._extract_items(payload)
            items.extend(page_items)

            total = self._extract_total(payload)
            if not page_items:
                break
            offset += len(page_items)
            if total is not None and offset >= total:
                break
            if len(page_items) < limit:
                break

        return items

    async def get_device(self, agent_uuid: str) -> dict:
        payload = await self._request("GET", f"/ext/devices/{agent_uuid}")
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def infer_site_from_device(device: dict[str, Any]) -> dict[str, str]:
        identity = device.get("identity", {}) if isinstance(device, dict) else {}
        if not isinstance(identity, dict):
            identity = {}

        site_uuid = (
            device.get("siteUuid")
            or identity.get("siteUuid")
            or ""
        )
        site_name = (
            device.get("siteName")
            or identity.get("siteName")
            or ""
        )
        if not site_name:
            links = device.get("links", []) if isinstance(device, dict) else []
            if isinstance(links, list):
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    if link.get("rel") != "backtrack-details":
                        continue
                    raw_url = str(link.get("url") or "").strip()
                    if not raw_url:
                        continue
                    hostname = (urlparse(raw_url).hostname or "").strip()
                    if hostname:
                        site_name = hostname
                        break

        return {
            "id": str(site_uuid or ""),
            "name": str(site_name or ""),
        }

    async def infer_sites_from_devices(self) -> list[dict]:
        sites_by_id: dict[str, dict[str, str]] = {}
        for device in await self.list_all_devices():
            site = self.infer_site_from_device(device)
            site_id = site["id"]
            if not site_id:
                continue
            existing = sites_by_id.get(site_id)
            if existing is None or (not existing["name"] and site["name"]):
                sites_by_id[site_id] = site

        return sorted(
            sites_by_id.values(),
            key=lambda item: (item["name"] or item["id"]).lower(),
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> VipreClient:
    """
    Build a VIPRE client from the configured Bifrost integration.

    For org-scoped calls, the mapped VIPRE site UUID is exposed through
    `client.site_uuid`.
    """
    from bifrost import integrations

    integration = await integrations.get("VIPRE", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'VIPRE' not found in Bifrost")

    config = integration.config or {}
    required = ["base_uri", "key_id", "api_key"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"VIPRE integration missing required config: {missing}")

    return VipreClient(
        base_uri=config["base_uri"],
        key_id=config["key_id"],
        api_key=config["api_key"],
        site_uuid=getattr(integration, "entity_id", None),
    )
