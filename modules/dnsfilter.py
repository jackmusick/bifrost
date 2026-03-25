"""
DNSFilter API client helpers for Bifrost integrations.

Authentication: API key in the Authorization header
Base URL: https://api.dnsfilter.com

The DNSFilter MSP API exposes networks as the customer-level entity that maps
cleanly to Bifrost organizations. The scoped integration mapping stores the
DNSFilter network ID in `integration.entity_id`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class DNSFilterClient:
    """Async client for a focused subset of the DNSFilter MSP API."""

    BASE_URL = "https://api.dnsfilter.com"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        *,
        network_id: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._network_id = str(network_id) if network_id is not None else None
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None

    @property
    def network_id(self) -> str | None:
        return self._network_id

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": self._api_key,
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
        return self._http

    @staticmethod
    def _flatten_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if not params:
            return {}

        flattened: dict[str, Any] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if nested_value is not None:
                        flattened[f"{key}[{nested_key}]"] = nested_value
                continue
            flattened[key] = value
        return flattened

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        http = await self._get_http()
        request_params = self._flatten_params(params)
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=request_params or None,
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
                f"DNSFilter [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _extract_list(payload: Any) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", [])
        return data if isinstance(data, list) else []

    @staticmethod
    def _extract_item(payload: Any) -> dict:
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data", {})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def normalize_network(network: dict[str, Any]) -> dict[str, str | None]:
        attributes = network.get("attributes", {}) if isinstance(network, dict) else {}
        relationships = (
            network.get("relationships", {}) if isinstance(network, dict) else {}
        )
        org_data = (
            relationships.get("organization", {}).get("data", {})
            if isinstance(relationships, dict)
            else {}
        )

        network_id = network.get("id")
        name = attributes.get("name") if isinstance(attributes, dict) else None
        organization_id = org_data.get("id") if isinstance(org_data, dict) else None

        return {
            "id": str(network_id) if network_id is not None else "",
            "name": name or "",
            "organization_id": (
                str(organization_id) if organization_id is not None else None
            ),
        }

    async def list_networks(
        self,
        *,
        search: str | None = None,
        basic_info: bool = True,
        force_truncate_ips: bool = True,
    ) -> list[dict]:
        payload = await self._request(
            "GET",
            "/v1/networks/all",
            params={
                "search": search,
                "basic_info": basic_info,
                "force_truncate_ips": force_truncate_ips,
            },
        )
        return self._extract_list(payload)

    async def get_network(
        self,
        network_id: str | None = None,
        *,
        count_network_ips: bool = False,
    ) -> dict:
        resolved_network_id = network_id or self._network_id
        if not resolved_network_id:
            raise RuntimeError(
                "DNSFilter network ID is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "GET",
            f"/v1/networks/{resolved_network_id}",
            params={"count_network_ips": count_network_ips},
        )
        return self._extract_item(payload)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> DNSFilterClient:
    """
    Build a DNSFilter client from the configured Bifrost integration.

    For org-scoped calls, the mapped DNSFilter network ID is exposed through
    `client.network_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("DNSFilter", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'DNSFilter' not found in Bifrost")

    config = integration.config or {}
    api_key = config.get("api_key")
    if not api_key:
        raise RuntimeError("DNSFilter integration missing required config: ['api_key']")

    return DNSFilterClient(
        api_key=api_key,
        network_id=getattr(integration, "entity_id", None),
    )

