"""
ConnectSecure public API helpers for Bifrost integrations.

Authentication:
  - POST /w/authorize with Client-Auth-Token: base64(tenant+client_id:client_secret)
  - Resource requests use:
      Authorization: JWT Bearer <access_token>
      X-USER-ID: <user_id>
      x-pod-id: <pod>

The company list under /r/company/companies is the primary org-mapping surface.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx


class ConnectSecureClient:
    """Focused async client for the ConnectSecure public API."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_uri: str,
        pod_id: str,
        tenant: str,
        api_key: str,
        api_secret: str,
        *,
        company_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_uri = base_uri.rstrip("/")
        self._pod_id = pod_id
        self._tenant = tenant
        self._api_key = api_key
        self._api_secret = api_secret
        self._company_id = str(company_id) if company_id is not None else None
        self._timeout = timeout
        self._max_retries = max_retries
        self._access_token: str | None = None
        self._user_id: str | None = None
        self._http: httpx.AsyncClient | None = None

    @property
    def company_id(self) -> str | None:
        return self._company_id

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_uri,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        return self._http

    def _client_auth_token(self) -> str:
        raw = f"{self._tenant}+{self._api_key}:{self._api_secret}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    async def _authorize(self) -> None:
        http = await self._get_http()
        response = await http.post(
            "/w/authorize",
            headers={
                "Client-Auth-Token": self._client_auth_token(),
                "x-pod-id": self._pod_id,
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
            },
            json={},
        )
        response.raise_for_status()
        payload = response.json()

        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            raise RuntimeError("ConnectSecure authorize returned unexpected payload")

        access_token = data.get("access_token")
        user_id = data.get("user_id")
        if not access_token or not user_id:
            raise RuntimeError(f"ConnectSecure authorize missing token data: {payload}")

        self._access_token = str(access_token)
        self._user_id = str(user_id)

    async def _ensure_auth(self) -> tuple[str, str]:
        if self._access_token and self._user_id:
            return self._access_token, self._user_id

        await self._authorize()
        assert self._access_token is not None
        assert self._user_id is not None
        return self._access_token, self._user_id

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token, user_id = await self._ensure_auth()
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=params or None,
                json=json_body,
                headers={
                    "Authorization": f"JWT Bearer {token}",
                    "X-USER-ID": user_id,
                    "x-pod-id": self._pod_id,
                },
            )

            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                self._user_id = None
                token, user_id = await self._ensure_auth()
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
                f"ConnectSecure [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _extract_data(payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        return payload.get("data", payload)

    async def list_companies(
        self,
        *,
        condition: str | None = None,
        limit: int = 100,
        order_by: str = "name asc",
    ) -> list[dict]:
        skip = 0
        results: list[dict] = []

        while True:
            payload = await self._request(
                "GET",
                "/r/company/companies",
                params={
                    "condition": condition,
                    "skip": skip,
                    "limit": limit,
                    "order_by": order_by,
                },
            )
            data = self._extract_data(payload)
            items = [item for item in (data or []) if isinstance(item, dict)]
            results.extend(items)

            if len(items) < limit:
                break
            skip += len(items)

        return results

    async def get_company(self, company_id: str | None = None) -> dict:
        resolved_company_id = company_id or self._company_id
        if not resolved_company_id:
            raise RuntimeError(
                "ConnectSecure company ID is not available. Configure an org mapping first."
            )

        payload = await self._request("GET", f"/r/company/companies/{resolved_company_id}")
        data = self._extract_data(payload)
        return data if isinstance(data, dict) else {}

    async def list_assets(
        self,
        *,
        company_id: str | None = None,
        limit: int = 100,
        order_by: str = "name asc",
    ) -> list[dict]:
        resolved_company_id = company_id or self._company_id
        if not resolved_company_id:
            raise RuntimeError(
                "ConnectSecure company ID is not available. Configure an org mapping first."
            )

        condition = f"company_id={resolved_company_id}"
        skip = 0
        results: list[dict] = []

        while True:
            payload = await self._request(
                "GET",
                "/r/asset/assets",
                params={
                    "condition": condition,
                    "skip": skip,
                    "limit": limit,
                    "order_by": order_by,
                },
            )
            data = self._extract_data(payload)
            items = [item for item in (data or []) if isinstance(item, dict)]
            results.extend(items)

            if len(items) < limit:
                break
            skip += len(items)

        return results

    @staticmethod
    def normalize_company(company: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(company.get("id") or ""),
            "name": str(company.get("name") or company.get("customer_name") or ""),
        }

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> ConnectSecureClient:
    """
    Build a ConnectSecure client from the configured Bifrost integration.

    For org-scoped calls, the mapped company ID is exposed through
    `client.company_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("ConnectSecure", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'ConnectSecure' not found in Bifrost")

    config = integration.config or {}
    required = ["base_uri", "pod_id", "tenant", "api_key", "api_secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"ConnectSecure integration missing required config: {missing}")

    return ConnectSecureClient(
        base_uri=config["base_uri"],
        pod_id=config["pod_id"],
        tenant=config["tenant"],
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        company_id=getattr(integration, "entity_id", None),
    )

