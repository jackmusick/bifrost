"""
TD SYNNEX Partner API helpers for Bifrost integrations.

This integration targets the reseller procurement API family exposed at:
  - https://api.us.tdsynnex.com
  - https://api.ca.tdsynnex.com

It is intentionally separate from TD SYNNEX StreamOne ION. The Partner API is
better suited to order, shipment, quote, and invoice lookups for known reseller
orders, while StreamOne ION is a different API family for cloud/customer/order
management.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx


class TDSynnexPartnerClient:
    """Focused async client for the TD SYNNEX Partner API."""

    BASE_URL = "https://api.us.tdsynnex.com"
    TOKEN_PATH = "/oauth2/v1/token"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._http

    async def _authorize(self) -> None:
        http = await self._get_http()
        response = await http.post(
            self.TOKEN_PATH,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 7200)
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
    ) -> Any:
        token = await self._ensure_token()
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=params or None,
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
                f"TD SYNNEX Partner API [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def extract_primary_record(payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            first = payload[0] if payload else {}
            return first if isinstance(first, dict) else {}
        return payload if isinstance(payload, dict) else {}

    async def get_quote_status(self, order_no: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/api/v1/webservice/ltd/partner/order/{order_no}/QUOTEID",
        )
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def get_order(self, order_no: str, *, order_type: str | None = None) -> list[dict[str, Any]]:
        path = f"/api/v1/orders/orderNo/{order_no}"
        if order_type:
            path = f"{path}/orderType/{order_type}"
        payload = await self._request("GET", path)
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def get_shipment_details(self, order_no: str) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            f"/api/v1/orders/shipment/details/orderNo/{order_no}",
        )
        return payload if isinstance(payload, dict) else {}

    async def get_invoice(self, invoice_no: str, *, invoice_type: str = "IV") -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/api/v1/invoices/invoiceNo/{invoice_no}/invoiceType/{invoice_type}",
        )
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> TDSynnexPartnerClient:
    """Build a TD SYNNEX Partner API client from the configured Bifrost integration."""
    from bifrost import integrations

    integration = await integrations.get("TD SYNNEX Partner API", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'TD SYNNEX Partner API' not found in Bifrost")

    config = integration.config or {}
    required = ["client_id", "client_secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"TD SYNNEX Partner API integration missing required config: {missing}"
        )

    return TDSynnexPartnerClient(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        base_url=config.get("base_url") or TDSynnexPartnerClient.BASE_URL,
    )
