"""
Quoter API helpers for Bifrost integrations.

Authentication: OAuth 2.0 client credentials
Base URL: https://api.quoter.com/v1

Quoter does not expose a first-class organization resource in the documented API.
For Bifrost org mapping, organizations are inferred from the `organization`
field on Quoter contacts.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


class QuoterClient:
    """Focused async client for the current Quoter API contract."""

    BASE_URL = "https://api.quoter.com/v1"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        organization: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._organization = organization
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None

    @property
    def organization(self) -> str | None:
        return self._organization

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        return self._http

    async def _authorize(self) -> None:
        http = await self._get_http()
        response = await http.post(
            "/auth/oauth/authorize",
            json={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

        self._access_token = payload["access_token"]
        self._refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = time.time() + float(expires_in)

    async def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        await self._authorize()
        assert self._access_token is not None
        return self._access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._ensure_token()
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=params or None,
                json=json_body,
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                token = await self._ensure_token()
                continue

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
                f"Quoter [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _extract_data(payload: Any) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data", [])
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _has_more(payload: Any) -> bool:
        return bool(payload.get("has_more")) if isinstance(payload, dict) else False

    async def _list_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        page = 1
        all_items: list[dict] = []

        while True:
            page_params = dict(params or {})
            page_params["page"] = page
            page_params["limit"] = limit

            payload = await self._request("GET", path, params=page_params)
            items = self._extract_data(payload)
            all_items.extend(items)

            if not self._has_more(payload) or not items:
                break
            page += 1

        return all_items

    async def list_contacts(
        self,
        *,
        organization: str | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        resolved_organization = organization or self._organization
        if resolved_organization:
            params["organization"] = resolved_organization
        if fields:
            params["fields"] = ",".join(fields)
        return await self._list_paginated("/contacts", params=params, limit=limit)

    async def list_quotes(
        self,
        *,
        limit: int = 100,
        fields: list[str] | None = None,
        filters: dict[str, str] | None = None,
    ) -> list[dict]:
        params = dict(filters or {})
        if fields:
            params["fields"] = ",".join(fields)
        return await self._list_paginated("/quotes", params=params, limit=limit)

    @staticmethod
    def infer_organization_from_contact(contact: dict[str, Any]) -> dict[str, str]:
        organization = str(contact.get("organization") or "").strip()
        return {
            "id": organization,
            "name": organization,
        }

    async def infer_organizations_from_contacts(self) -> list[dict]:
        contacts = await self.list_contacts(fields=["id", "organization"])
        organizations_by_name: dict[str, dict[str, str]] = {}

        for contact in contacts:
            organization = self.infer_organization_from_contact(contact)
            organization_id = organization["id"]
            if not organization_id:
                continue
            organizations_by_name.setdefault(organization_id, organization)

        return sorted(
            organizations_by_name.values(),
            key=lambda item: item["name"].lower(),
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> QuoterClient:
    """
    Build a Quoter client from the configured Bifrost integration.

    For org-scoped calls, the mapped Quoter organization name is exposed through
    `client.organization`.
    """
    from bifrost import integrations

    integration = await integrations.get("Quoter", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Quoter' not found in Bifrost")

    config = integration.config or {}
    required = ["client_id", "client_secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Quoter integration missing required config: {missing}")

    return QuoterClient(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        organization=getattr(integration, "entity_id", None),
    )

