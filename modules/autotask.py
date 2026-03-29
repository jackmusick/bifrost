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
        return self._unwrap_item(response.json())

    async def update_company(
        self,
        *,
        company_id: str | None = None,
        company_name: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_company_id = company_id or self._company_id
        if not resolved_company_id:
            raise RuntimeError(
                "Autotask company ID is required to update a company. "
                "Pass company_id explicitly or configure an org mapping first."
            )

        payload: dict[str, Any] = {"id": self._coerce_int(resolved_company_id)}
        if company_name not in (None, ""):
            payload["companyName"] = company_name
        if extra_fields:
            payload.update(extra_fields)

        response = await self._request(
            "PATCH",
            f"{self._base_url}/V1.0/Companies",
            json_body=payload,
        )
        updated = response.json()
        if not isinstance(updated, dict):
            return {}

        item_id = updated.get("itemId") or resolved_company_id
        return await self.get_company(str(item_id))

    async def get_ticket(self, ticket_id: str | int) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"{self._base_url}/V1.0/Tickets/{ticket_id}",
        )
        return self._unwrap_item(response.json())

    async def update_ticket(
        self,
        ticket_id: str | int,
        *,
        status: str | None = None,
        resolution: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self._coerce_int(ticket_id)}
        if status not in (None, ""):
            payload["status"] = self._coerce_int(status)
        if resolution not in (None, ""):
            payload["resolution"] = resolution
        if extra_fields:
            payload.update(extra_fields)

        response = await self._request(
            "PATCH",
            f"{self._base_url}/V1.0/Tickets",
            json_body=payload,
        )
        updated = response.json()
        if not isinstance(updated, dict):
            return {}

        item_id = updated.get("itemId") or ticket_id
        return await self.get_ticket(item_id)

    async def create_ticket_note(
        self,
        *,
        ticket_id: str | int,
        description: str,
        note_type: str | None = None,
        publish: str | None = None,
        title: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"description": description}
        if note_type not in (None, ""):
            payload["noteType"] = self._coerce_int(note_type)
        if publish not in (None, ""):
            payload["publish"] = self._coerce_int(publish)
        if title not in (None, ""):
            payload["title"] = title
        if extra_fields:
            payload.update(extra_fields)

        response = await self._request(
            "POST",
            f"{self._base_url}/V1.0/Tickets/{self._coerce_int(ticket_id)}/notes",
            json_body=payload,
        )
        created = response.json()
        if not isinstance(created, dict):
            return {}
        return created

    @staticmethod
    def _unwrap_item(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            item = payload.get("item")
            if isinstance(item, dict):
                return item
            return payload
        return {}

    @staticmethod
    def normalize_company(company: dict[str, Any]) -> dict[str, str]:
        company = AutotaskClient._unwrap_item(company)
        return {
            "id": str(company.get("id") or ""),
            "name": str(company.get("companyName") or ""),
        }

    @staticmethod
    def _coerce_int(value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
            return stripped
        return value

    async def create_ticket(
        self,
        *,
        title: str,
        description: str = "",
        company_id: str | None = None,
        queue_id: str | None = None,
        issue_type: str | None = None,
        sub_issue_type: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        source: str | None = None,
        due_date: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_company_id = company_id or self._company_id
        if not resolved_company_id:
            raise RuntimeError(
                "Autotask company ID is required to create a ticket. "
                "Pass company_id explicitly or configure an org mapping first."
            )

        payload: dict[str, Any] = {
            "companyID": self._coerce_int(resolved_company_id),
            "title": title,
            "description": description,
        }

        optional_fields = {
            "queueID": queue_id,
            "issueType": issue_type,
            "subIssueType": sub_issue_type,
            "status": status,
            "priority": priority,
            "source": source,
            "dueDateTime": due_date,
        }
        for field_name, field_value in optional_fields.items():
            if field_value not in (None, ""):
                payload[field_name] = self._coerce_int(field_value)

        if extra_fields:
            payload.update(extra_fields)

        response = await self._request(
            "POST",
            f"{self._base_url}/V1.0/Tickets",
            json_body=payload,
        )
        created = response.json()
        if not isinstance(created, dict):
            return {}

        item_id = created.get("itemId")
        if item_id not in (None, ""):
            return await self.get_ticket(item_id)

        return created

    @staticmethod
    def normalize_ticket(ticket: dict[str, Any]) -> dict[str, str]:
        ticket = AutotaskClient._unwrap_item(ticket)
        return {
            "id": str(ticket.get("id") or ""),
            "ticket_number": str(ticket.get("ticketNumber") or ""),
            "company_id": str(ticket.get("companyID") or ""),
            "title": str(ticket.get("title") or ""),
            "status": str(ticket.get("status") or ""),
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
