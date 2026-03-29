"""
DNSFilter API client helpers for Bifrost integrations.

Authentication: API key in the Authorization header
Base URL: https://api.dnsfilter.com

The DNSFilter MSP API exposes first-class organizations. Bifrost org mappings
should use the DNSFilter organization ID in `integration.entity_id`.
Networks remain useful secondary context under an organization, but they are
too granular to act as the primary org-mapping surface.
"""

from __future__ import annotations

import asyncio
import re
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
        organization_id: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._organization_id = (
            str(organization_id) if organization_id is not None else None
        )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None

    @property
    def organization_id(self) -> str | None:
        return self._organization_id

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

    @staticmethod
    def normalize_organization(organization: dict[str, Any]) -> dict[str, Any]:
        attributes = (
            organization.get("attributes", {}) if isinstance(organization, dict) else {}
        )
        relationships = (
            organization.get("relationships", {}) if isinstance(organization, dict) else {}
        )
        networks = (
            relationships.get("networks", {}).get("data", [])
            if isinstance(relationships, dict)
            else []
        )
        organization_id = organization.get("id")
        name = attributes.get("name") if isinstance(attributes, dict) else None

        return {
            "id": str(organization_id) if organization_id is not None else "",
            "name": name or "",
            "network_ids": [
                str(item.get("id"))
                for item in networks
                if isinstance(item, dict) and item.get("id") is not None
            ],
        }

    @staticmethod
    def derive_network_target_name(
        *,
        current_network_name: str,
        current_organization_name: str,
        target_organization_name: str,
    ) -> str:
        current_network_name = (current_network_name or "").strip()
        current_organization_name = (current_organization_name or "").strip()
        target_organization_name = (target_organization_name or "").strip()
        if not current_network_name or not current_organization_name or not target_organization_name:
            return current_network_name

        def simplify(value: str) -> str:
            return re.sub(r"[^a-z0-9& ]+", "", value.lower()).strip()

        def trim_legal_suffix(value: str) -> str:
            trimmed = re.sub(
                r"(?i)(?:,\s*)?(p\.?\s*c\.?|llc|inc\.?|corp\.?|co\.?|company|ltd\.?|llp|pllc)\s*$",
                "",
                value,
            )
            return trimmed.strip(" ,")

        candidates: list[tuple[str, str]] = []
        for source, replacement in [
            (current_organization_name, target_organization_name),
            (trim_legal_suffix(current_organization_name), trim_legal_suffix(target_organization_name)),
        ]:
            source = source.strip()
            replacement = replacement.strip()
            if source and replacement:
                candidates.append((source, replacement))

        best: tuple[str, str] | None = None
        for source, replacement in candidates:
            if current_network_name == source or current_network_name.startswith(f"{source} "):
                if best is None or len(source) > len(best[0]):
                    best = (source, replacement)
                    continue
            simplified_network = simplify(current_network_name)
            simplified_source = simplify(source)
            if simplified_network == simplified_source or simplified_network.startswith(f"{simplified_source} "):
                if best is None or len(simplified_source) > len(simplify(best[0])):
                    best = (source, replacement)

        if best is None:
            return current_network_name

        source, replacement = best
        if current_network_name == source:
            return replacement
        if current_network_name.startswith(f"{source} "):
            return f"{replacement}{current_network_name[len(source):]}"

        simplified_network = simplify(current_network_name)
        simplified_source = simplify(source)
        if simplified_network == simplified_source:
            return replacement
        if simplified_network.startswith(f"{simplified_source} "):
            remainder = current_network_name.split(" ", maxsplit=len(source.split(" ")))
            if len(remainder) > 1:
                return f"{replacement} {remainder[-1]}".strip()

        return current_network_name

    async def list_organizations(self, *, search: str | None = None) -> list[dict]:
        payload = await self._request(
            "GET",
            "/v1/organizations",
            params={"search": search} if search else None,
        )
        return self._extract_list(payload)

    async def get_organization(self, organization_id: str | None = None) -> dict:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "DNSFilter organization ID is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "GET",
            f"/v1/organizations/{resolved_organization_id}",
        )
        return self._extract_item(payload)

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
        resolved_network_id = network_id
        if not resolved_network_id:
            raise RuntimeError(
                "DNSFilter network ID is required for direct network lookups."
            )

        payload = await self._request(
            "GET",
            f"/v1/networks/{resolved_network_id}",
            params={"count_network_ips": count_network_ips},
        )
        return self._extract_item(payload)

    async def update_organization(
        self,
        *,
        organization_id: str | None = None,
        name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "DNSFilter organization ID is not available. Configure an org mapping first."
            )
        attributes = dict(extra_fields or {})
        if name not in (None, ""):
            attributes["name"] = name
        if not attributes:
            raise RuntimeError("Provide name or extra_fields to update the DNSFilter organization.")
        payload = await self._request(
            "PATCH",
            f"/v1/organizations/{resolved_organization_id}",
            json_body={"organization": attributes},
        )
        return self._extract_item(payload)

    async def update_network(
        self,
        *,
        network_id: str,
        name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict:
        if not network_id:
            raise RuntimeError("DNSFilter network ID is required to update a network.")
        attributes = dict(extra_fields or {})
        if name not in (None, ""):
            attributes["name"] = name
        if not attributes:
            raise RuntimeError("Provide name or extra_fields to update the DNSFilter network.")
        payload = await self._request(
            "PATCH",
            f"/v1/networks/{network_id}",
            json_body={"network": attributes},
        )
        return self._extract_item(payload)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> DNSFilterClient:
    """
    Build a DNSFilter client from the configured Bifrost integration.

    For org-scoped calls, the mapped DNSFilter organization ID is exposed
    through `client.organization_id`.
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
        organization_id=getattr(integration, "entity_id", None),
    )
