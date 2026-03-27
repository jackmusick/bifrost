"""
Idemeum public API helpers for Bifrost integrations.

The public docs are published as a Postman collection at https://api.idemeum.com/.
This client stays focused on the MSP/customer-management surface that is most
relevant for Bifrost:

- customers
- groups
- customer devices
- tenant rules
- elevation approvals
- audit events

Authentication uses the X-Idemeum-Api-Key header against the parent tenant URL.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class IdemeumClient:
    """Focused async client for the Idemeum public API."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    ACCEPT_CUSTOMER_LIST = "application/vnd.dvmi.sdk.customer.basic.info.list+json"
    ACCEPT_CUSTOMER = "application/vnd.dvmi.sdk.customer.info+json"
    ACCEPT_GROUP_LIST = "application/vnd.dvmi.sdk.group.info.list+json"
    ACCEPT_CUSTOMER_DEVICES = "application/vnd.dvmi.sdk.customer.devices+json"
    CONTENT_TYPE_CUSTOMER_CREATE = "application/vnd.dvmi.sdk.customer.request+json"
    CONTENT_TYPE_CUSTOMER_UPDATE = "application/vnd.dvmi.sdk.customer.info+json"
    CONTENT_TYPE_DELEGATE = "application/vnd.dvmi.sdk.delegate.to.customer+json"
    CONTENT_TYPE_UNDELEGATE = "application/vnd.dvmi.sdk.undelegate.from.customer+json"
    CONTENT_TYPE_RULES = "application/vnd.dvmi.sdk.rule.definition+json"
    CONTENT_TYPE_ELEVATION = "application/vnd.dvmi.sdk.elevation.request.approval+json"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        customer_id: str | None = None,
        customer_name: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._customer_id = str(customer_id) if customer_id is not None else None
        self._customer_name = str(customer_name) if customer_name is not None else None
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None

    @property
    def customer_id(self) -> str | None:
        return self._customer_id

    @property
    def customer_name(self) -> str | None:
        return self._customer_name

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "X-Idemeum-Api-Key": self._api_key,
                },
            )
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        accept: str | None = None,
        content_type: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        http = await self._get_http()
        headers: dict[str, str] = {}
        if accept:
            headers["Accept"] = accept
        if content_type:
            headers["Content-Type"] = content_type

        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            response = await http.request(
                method,
                path,
                params=params or None,
                json=json_body,
                headers=headers,
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
                f"Idemeum [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    async def list_customers(self) -> list[dict]:
        payload = await self._request(
            "GET",
            "/api/integrations/customers",
            accept=self.ACCEPT_CUSTOMER_LIST,
        )
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [item for item in (items or []) if isinstance(item, dict)]

    async def get_customer(
        self,
        *,
        customer_id: str | None = None,
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_id = customer_id or self._customer_id
        resolved_customer_name = customer_name or self._customer_name

        if resolved_customer_id:
            payload = await self._request(
                "GET",
                f"/api/integrations/customers/id/{resolved_customer_id}",
                accept=self.ACCEPT_CUSTOMER,
            )
        elif resolved_customer_name:
            payload = await self._request(
                "GET",
                f"/api/integrations/customers/{resolved_customer_name}",
                accept=self.ACCEPT_CUSTOMER,
            )
        else:
            raise RuntimeError(
                "Idemeum customer identity is not available. Configure an org mapping first."
            )

        return payload if isinstance(payload, dict) else {}

    async def create_customer(self, payload: dict[str, Any]) -> dict:
        result = await self._request(
            "POST",
            "/api/integrations/customers",
            accept="application/vnd.dvmi.customer+json",
            content_type=self.CONTENT_TYPE_CUSTOMER_CREATE,
            json_body=payload,
        )
        return result if isinstance(result, dict) else {}

    async def update_customer_settings(
        self,
        payload: dict[str, Any],
        *,
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        result = await self._request(
            "PATCH",
            f"/api/integrations/customers/{resolved_customer_name}/settings",
            content_type=self.CONTENT_TYPE_CUSTOMER_UPDATE,
            json_body=payload,
        )
        return result if isinstance(result, dict) else {}

    async def delete_customer(self, *, customer_name: str | None = None) -> None:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )
        await self._request("DELETE", f"/api/integrations/customers/{resolved_customer_name}")

    async def list_groups(self) -> list[dict]:
        payload = await self._request(
            "GET",
            "/api/integrations/groups",
            accept=self.ACCEPT_GROUP_LIST,
        )
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        return [item for item in (items or []) if isinstance(item, dict)]

    async def list_devices(self, *, customer_id: str | None = None) -> dict:
        resolved_customer_id = customer_id or self._customer_id
        if not resolved_customer_id:
            raise RuntimeError(
                "Idemeum customer ID is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "GET",
            f"/api/integrations/customers/{resolved_customer_id}/devices",
            accept=self.ACCEPT_CUSTOMER_DEVICES,
        )
        return payload if isinstance(payload, dict) else {}

    async def delegate_user(
        self,
        user_email: str,
        *,
        role: str = "ADMIN",
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "POST",
            f"/api/integrations/customers/{resolved_customer_name}/delegation",
            content_type=self.CONTENT_TYPE_DELEGATE,
            json_body={"userEmail": user_email, "role": role},
        )
        return payload if isinstance(payload, dict) else {}

    async def undelegate_user(
        self,
        user_email: str,
        *,
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "POST",
            f"/api/integrations/customers/{resolved_customer_name}/undelegation",
            content_type=self.CONTENT_TYPE_UNDELEGATE,
            json_body={"userEmail": user_email},
        )
        return payload if isinstance(payload, dict) else {}

    async def get_parent_rules(self) -> dict:
        payload = await self._request("GET", "/api/integrations/msp/rules")
        return payload if isinstance(payload, dict) else {}

    async def save_parent_rules(self, rules: list[dict[str, Any]]) -> dict:
        payload = await self._request(
            "POST",
            "/api/integrations/msp/rules",
            content_type=self.CONTENT_TYPE_RULES,
            json_body={"rules": rules},
        )
        return payload if isinstance(payload, dict) else {}

    async def get_customer_rules(self, *, customer_name: str | None = None) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "GET",
            f"/api/integrations/customers/{resolved_customer_name}/rules",
        )
        return payload if isinstance(payload, dict) else {}

    async def save_customer_rules(
        self,
        rules: list[dict[str, Any]],
        *,
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "POST",
            f"/api/integrations/customers/{resolved_customer_name}/rules",
            content_type=self.CONTENT_TYPE_RULES,
            json_body={"rules": rules},
        )
        return payload if isinstance(payload, dict) else {}

    async def approve_elevation_request(
        self,
        request_id: str,
        *,
        customer_name: str | None = None,
        user_elevation_mode: str = "ADMIN",
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "POST",
            "/api/integrations/elevation/request/approve",
            content_type=self.CONTENT_TYPE_ELEVATION,
            json_body={
                "idemeumElevationRequestId": request_id,
                "idemeumCustomerName": resolved_customer_name,
                "userElevationMode": user_elevation_mode,
            },
        )
        return payload if isinstance(payload, dict) else {}

    async def deny_elevation_request(
        self,
        request_id: str,
        *,
        customer_name: str | None = None,
    ) -> dict:
        resolved_customer_name = customer_name or self._customer_name
        if not resolved_customer_name:
            raise RuntimeError(
                "Idemeum customer name is not available. Configure an org mapping first."
            )

        payload = await self._request(
            "POST",
            "/api/integrations/elevation/request/deny",
            content_type=self.CONTENT_TYPE_ELEVATION,
            json_body={
                "idemeumElevationRequestId": request_id,
                "idemeumCustomerName": resolved_customer_name,
            },
        )
        return payload if isinstance(payload, dict) else {}

    async def list_audit_events(
        self,
        *,
        range_name: str = "last_90d",
        page: int = 1,
        size: int = 100,
        customer_name: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {
            "page": page,
            "size": size,
            "range": range_name,
        }
        resolved_customer_name = customer_name or self._customer_name
        if resolved_customer_name:
            params["name"] = resolved_customer_name

        payload = await self._request("GET", "/api/integrations/audit/events", params=params)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def normalize_customer(customer: dict[str, Any]) -> dict[str, str]:
        customer_id = str(
            customer.get("id")
            or customer.get("customerId")
            or ""
        )
        customer_name = str(
            customer.get("displayName")
            or customer.get("customerDisplayName")
            or customer.get("name")
            or customer.get("customerName")
            or customer_id
        )
        customer_slug = str(customer.get("name") or customer.get("customerName") or "")
        customer_url = str(customer.get("url") or customer.get("customerUrl") or "")
        return {
            "id": customer_id,
            "name": customer_name,
            "slug": customer_slug,
            "url": customer_url,
        }

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> IdemeumClient:
    """
    Build an Idemeum client from the configured Bifrost integration.

    For org-scoped calls, the mapped customer ID and customer name are exposed
    through `client.customer_id` and `client.customer_name`.
    """
    from bifrost import integrations

    integration = await integrations.get("Idemeum", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Idemeum' not found in Bifrost")

    config = integration.config or {}
    required = ["base_url", "api_key"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Idemeum integration missing required config: {missing}")

    return IdemeumClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        customer_id=getattr(integration, "entity_id", None),
        customer_name=getattr(integration, "entity_name", None),
    )
