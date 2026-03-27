"""
Autotask PSA REST API helpers for Bifrost integrations.

Authentication uses these headers on each request:
  - ApiIntegrationCode
  - UserName
  - Secret

The org-scoped integration mapping stores the Autotask company ID in
`integration.entity_id`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


CUSTOMER_COMPANY_TYPE = 1


class AutotaskClient:
    """Focused async client for the Autotask company endpoints used by Bifrost."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        api_integration_code: str,
        username: str,
        secret: str,
        *,
        company_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_integration_code = api_integration_code
        self._username = username
        self._secret = secret
        self._company_id = str(company_id) if company_id is not None else None
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None

    @property
    def company_id(self) -> str | None:
        return self._company_id

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self._timeout,
                headers={
                    "ApiIntegrationCode": self._api_integration_code,
                    "UserName": self._username,
                    "Secret": self._secret,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._http

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await http.request(method, url, json=json_body)

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
                f"Autotask [{method.upper()} {url}] HTTP {response.status_code}: {body}"
            )
        return response

    @staticmethod
    def _active_customer_filter() -> list[dict[str, Any]]:
        return [
            {
                "op": "and",
                "field": "",
                "value": None,
                "udf": False,
                "items": [
                    {
                        "op": "eq",
                        "field": "companyType",
                        "value": CUSTOMER_COMPANY_TYPE,
                        "udf": False,
                        "items": [],
                    },
                    {
                        "op": "eq",
                        "field": "isActive",
                        "value": True,
                        "udf": False,
                        "items": [],
                    },
                ],
            }
        ]

    async def query_companies(
        self,
        *,
        include_fields: list[str] | None = None,
        filter_items: list[dict[str, Any]] | None = None,
        max_records: int = 500,
    ) -> list[dict[str, Any]]:
        next_url: str | None = f"{self._base_url}/V1.0/Companies/query"
        query = {
            "maxRecords": max_records,
            "includeFields": include_fields
            or ["id", "companyName", "companyType", "isActive"],
            "filter": filter_items or self._active_customer_filter(),
        }

        companies: list[dict[str, Any]] = []
        while next_url:
            response = await self._request("POST", next_url, json_body=query)
            payload = response.json()
            items = payload.get("items", []) if isinstance(payload, dict) else []
            companies.extend(item for item in items if isinstance(item, dict))
            page_details = payload.get("pageDetails", {}) if isinstance(payload, dict) else {}
            next_url = page_details.get("nextPageUrl") if isinstance(page_details, dict) else None

        return companies

    async def list_active_companies(self) -> list[dict[str, Any]]:
        return await self.query_companies()

    async def get_company(self, company_id: str | None = None) -> dict[str, Any]:
        resolved_company_id = company_id or self._company_id
        if not resolved_company_id:
            raise RuntimeError(
                "Autotask company ID is not available. Configure an org mapping first."
            )

        response = await self._request(
            "GET",
            f"{self._base_url}/V1.0/Companies/{resolved_company_id}",
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def normalize_company(company: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(company.get("id") or ""),
            "name": str(company.get("companyName") or ""),
        }

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> AutotaskClient:
    """
    Build an Autotask client from the configured Bifrost integration.

    For org-scoped calls, the mapped Autotask company ID is exposed through
    `client.company_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("Autotask", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Autotask' not found in Bifrost")

    config = integration.config or {}
    required = ["base_url", "api_integration_code", "username", "secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Autotask integration missing required config: {missing}")

    return AutotaskClient(
        base_url=config["base_url"],
        api_integration_code=config["api_integration_code"],
        username=config["username"],
        secret=config["secret"],
        company_id=getattr(integration, "entity_id", None),
    )
