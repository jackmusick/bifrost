"""
Cisco Meraki Dashboard API helpers for Bifrost integrations.

Authentication: API key in the X-Cisco-Meraki-API-Key header
Base URL: https://api.meraki.com/api/v1

The org-scoped integration mapping stores the Meraki organization ID in
`integration.entity_id`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx


class MerakiClient:
    """Focused async client for the Meraki organization and network endpoints."""

    BASE_URL = "https://api.meraki.com/api/v1"
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
                    "X-Cisco-Meraki-API-Key": self._api_key,
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
    ) -> httpx.Response:
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
                f"Meraki [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )
        return response

    @staticmethod
    def _next_starting_after(response: httpx.Response) -> str | None:
        next_link = response.links.get("next", {})
        next_url = next_link.get("url")
        if not next_url:
            return None
        return parse_qs(urlparse(next_url).query).get("startingAfter", [None])[0]

    async def _get_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        per_page: int = 1000,
    ) -> list[dict]:
        merged_params = dict(params or {})
        merged_params.setdefault("perPage", per_page)

        items: list[dict] = []
        starting_after: str | None = None

        while True:
            page_params = dict(merged_params)
            if starting_after:
                page_params["startingAfter"] = starting_after

            response = await self._request("GET", path, params=page_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError(
                    f"Meraki [{path}] returned unexpected payload type: {type(payload).__name__}"
                )

            items.extend(item for item in payload if isinstance(item, dict))
            starting_after = self._next_starting_after(response)
            if not starting_after:
                break

        return items

    @staticmethod
    def normalize_organization(organization: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(organization.get("id") or ""),
            "name": str(organization.get("name") or ""),
        }

    @staticmethod
    def normalize_admin(admin: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(admin.get("id") or ""),
            "name": str(admin.get("name") or ""),
            "email": str(admin.get("email") or "").strip().lower(),
            "orgAccess": str(admin.get("orgAccess") or ""),
            "tags": [
                str(tag)
                for tag in (admin.get("tags") or [])
                if isinstance(tag, str) and tag
            ],
            "networks": [
                str(network_id)
                for network_id in (admin.get("networks") or [])
                if network_id
            ],
            "accountStatus": str(admin.get("accountStatus") or ""),
            "twoFactorAuthEnabled": bool(admin.get("twoFactorAuthEnabled", False)),
            "hasApiKey": bool(admin.get("hasApiKey", False)),
            "authenticationMethod": str(admin.get("authenticationMethod") or ""),
        }

    @staticmethod
    def _build_admin_payload(
        *,
        name: str,
        org_access: str,
        email: str | None = None,
        tags: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "orgAccess": org_access,
        }
        if email:
            payload["email"] = email.strip().lower()
        if tags is not None:
            payload["tags"] = list(tags)
        if networks is not None:
            payload["networks"] = list(networks)
        return payload

    async def list_organizations(self, *, per_page: int = 1000) -> list[dict]:
        return await self._get_paginated("/organizations", per_page=per_page)

    async def get_organization(self, organization_id: str | None = None) -> dict:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        response = await self._request(
            "GET",
            f"/organizations/{resolved_organization_id}",
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def update_organization(
        self,
        organization_id: str | None = None,
        *,
        name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        payload: dict[str, Any] = {}
        if name not in (None, ""):
            payload["name"] = name
        if extra_fields:
            payload.update(extra_fields)
        if not payload:
            raise RuntimeError("Provide name or extra_fields to update the Meraki organization.")

        response = await self._request(
            "PUT",
            f"/organizations/{resolved_organization_id}",
            json_body=payload,
        )
        updated = response.json()
        return updated if isinstance(updated, dict) else {}

    async def list_organization_networks(
        self,
        organization_id: str | None = None,
        *,
        per_page: int = 1000,
    ) -> list[dict]:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        return await self._get_paginated(
            f"/organizations/{resolved_organization_id}/networks",
            per_page=per_page,
        )

    async def list_organization_admins(
        self,
        organization_id: str | None = None,
        *,
        network_ids: list[str] | None = None,
        per_page: int = 1000,
    ) -> list[dict]:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        params: dict[str, Any] = {}
        if network_ids:
            params["networkIds[]"] = network_ids

        return await self._get_paginated(
            f"/organizations/{resolved_organization_id}/admins",
            params=params,
            per_page=per_page,
        )

    async def create_organization_admin(
        self,
        organization_id: str | None = None,
        *,
        email: str,
        name: str,
        org_access: str = "full",
        tags: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        response = await self._request(
            "POST",
            f"/organizations/{resolved_organization_id}/admins",
            json_body=self._build_admin_payload(
                email=email,
                name=name,
                org_access=org_access,
                tags=tags,
                networks=networks,
            ),
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def update_organization_admin(
        self,
        organization_id: str | None = None,
        *,
        admin_id: str,
        name: str,
        org_access: str = "full",
        tags: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        response = await self._request(
            "PUT",
            f"/organizations/{resolved_organization_id}/admins/{admin_id}",
            json_body=self._build_admin_payload(
                name=name,
                org_access=org_access,
                tags=tags,
                networks=networks,
            ),
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def delete_organization_admin(
        self,
        organization_id: str | None = None,
        *,
        admin_id: str,
    ) -> None:
        resolved_organization_id = organization_id or self._organization_id
        if not resolved_organization_id:
            raise RuntimeError(
                "Meraki organization ID is not available. Configure an org mapping first."
            )

        await self._request(
            "DELETE",
            f"/organizations/{resolved_organization_id}/admins/{admin_id}",
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> MerakiClient:
    """
    Build a Meraki client from the configured Bifrost integration.

    For org-scoped calls, the mapped Meraki organization ID is exposed through
    `client.organization_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("Meraki", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Meraki' not found in Bifrost")

    config = integration.config or {}
    api_key = config.get("api_key")
    if not api_key:
        raise RuntimeError("Meraki integration missing required config: ['api_key']")

    return MerakiClient(
        api_key=api_key,
        organization_id=getattr(integration, "entity_id", None),
    )
