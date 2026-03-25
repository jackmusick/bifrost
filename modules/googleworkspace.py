"""
Google Workspace and Reseller API helpers for Bifrost integrations.

This module intentionally stays API-native for the first pass. GAM7 remains a
useful operational reference and a possible future execution backend, but the
core Bifrost integration path here uses service-account JWT bearer auth so it
fits org-scoped config, mapping, and test patterns cleanly.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

DIRECTORY_READONLY_SCOPES = (
    "https://www.googleapis.com/auth/admin.directory.customer.readonly",
    "https://www.googleapis.com/auth/admin.directory.domain.readonly",
    "https://www.googleapis.com/auth/admin.directory.group.readonly",
    "https://www.googleapis.com/auth/admin.directory.orgunit.readonly",
    "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
)

RESELLER_READONLY_SCOPES = (
    "https://www.googleapis.com/auth/apps.order.readonly",
)


@dataclass(slots=True)
class ServiceAccountInfo:
    client_email: str
    private_key: str
    private_key_id: str | None
    token_uri: str


def _parse_service_account_json(raw_value: str) -> ServiceAccountInfo:
    if not raw_value:
        raise RuntimeError("Google Workspace integration missing service_account_json")

    text = raw_value.strip()
    payload: dict[str, Any] | None = None

    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            payload = loaded
    except json.JSONDecodeError:
        payload = None

    if payload is None:
        try:
            decoded = base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8")
            loaded = json.loads(decoded)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception as exc:  # pragma: no cover - defensive parse fallback
            raise RuntimeError(
                "service_account_json must be raw JSON or base64-encoded JSON"
            ) from exc

    assert payload is not None
    client_email = str(payload.get("client_email") or "")
    private_key = str(payload.get("private_key") or "")
    token_uri = str(payload.get("token_uri") or GOOGLE_TOKEN_URL)

    if not client_email or not private_key:
        raise RuntimeError(
            "service_account_json must include client_email and private_key"
        )

    return ServiceAccountInfo(
        client_email=client_email,
        private_key=private_key,
        private_key_id=str(payload.get("private_key_id") or "") or None,
        token_uri=token_uri,
    )


class GoogleAPIClient:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        service_account_json: str,
        delegated_admin_email: str,
        scopes: tuple[str, ...],
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._service_account = _parse_service_account_json(service_account_json)
        self._delegated_admin_email = delegated_admin_email.strip()
        self._scopes = scopes
        self._timeout = timeout
        self._max_retries = max_retries
        self._http: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    def _build_assertion(self) -> str:
        now = int(time.time())
        claims = {
            "iss": self._service_account.client_email,
            "scope": " ".join(self._scopes),
            "aud": self._service_account.token_uri,
            "iat": now,
            "exp": now + 3600,
            "sub": self._delegated_admin_email,
        }
        headers = {}
        if self._service_account.private_key_id:
            headers["kid"] = self._service_account.private_key_id

        assertion = jwt.encode(
            claims,
            self._service_account.private_key,
            algorithm="RS256",
            headers=headers or None,
        )
        return assertion if isinstance(assertion, str) else assertion.decode("utf-8")

    async def _refresh_access_token(self) -> str:
        http = await self._get_http()
        response = await http.post(
            self._service_account.token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": self._build_assertion(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            body = response.text[:1000]
            raise RuntimeError(
                f"Google token request failed with HTTP {response.status_code}: {body}"
            )

        payload = response.json()
        access_token = str(payload.get("access_token") or "")
        expires_in = int(payload.get("expires_in") or 3600)
        if not access_token:
            raise RuntimeError("Google token response did not include access_token")

        self._access_token = access_token
        self._token_expires_at = time.time() + max(expires_in - 60, 60)
        return access_token

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        return await self._refresh_access_token()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        http = await self._get_http()
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            access_token = await self._get_access_token()
            response = await http.request(
                method,
                url,
                params=params or None,
                json=json_body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                self._token_expires_at = 0.0
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
                f"Google API [{method.upper()} {url}] HTTP {response.status_code}: {body}"
            )
        return response

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


class GoogleWorkspaceClient(GoogleAPIClient):
    DIRECTORY_BASE_URL = "https://admin.googleapis.com/admin/directory/v1"

    def __init__(
        self,
        *,
        service_account_json: str,
        delegated_admin_email: str,
        customer_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            service_account_json=service_account_json,
            delegated_admin_email=delegated_admin_email,
            scopes=DIRECTORY_READONLY_SCOPES,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._customer_id = str(customer_id or "").strip() or None

    @property
    def customer_id(self) -> str | None:
        return self._customer_id

    def _resolve_customer(self, customer_id: str | None = None) -> str:
        return str(customer_id or self._customer_id or "my_customer")

    async def _get_paginated(
        self,
        url: str,
        *,
        item_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        items: list[dict] = []
        next_page_token: str | None = None
        merged_params = dict(params or {})

        while True:
            page_params = dict(merged_params)
            if next_page_token:
                page_params["pageToken"] = next_page_token

            response = await self._request("GET", url, params=page_params)
            payload = response.json()
            page_items = payload.get(item_key, []) if isinstance(payload, dict) else []
            if isinstance(page_items, list):
                items.extend(item for item in page_items if isinstance(item, dict))

            next_page_token = (
                str(payload.get("nextPageToken") or "") if isinstance(payload, dict) else ""
            ) or None
            if not next_page_token:
                break

        return items

    @staticmethod
    def normalize_customer(
        customer: dict[str, Any],
        domains: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_domains = [domain for domain in (domains or []) if isinstance(domain, dict)]
        primary_domain = str(customer.get("customerDomain") or "")
        if not primary_domain:
            for domain in normalized_domains:
                if domain.get("isPrimary"):
                    primary_domain = str(domain.get("domainName") or "")
                    break
        if not primary_domain and normalized_domains:
            primary_domain = str(normalized_domains[0].get("domainName") or "")

        customer_id = str(customer.get("id") or customer.get("customerId") or primary_domain)
        return {
            "id": customer_id,
            "name": primary_domain or customer_id,
            "primary_domain": primary_domain,
            "customer": customer,
            "domains": normalized_domains,
        }

    async def get_customer(self, customer_id: str | None = None) -> dict[str, Any]:
        resolved_customer = self._resolve_customer(customer_id)
        response = await self._request(
            "GET",
            f"{self.DIRECTORY_BASE_URL}/customers/{resolved_customer}",
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def list_domains(self, customer_id: str | None = None) -> list[dict]:
        resolved_customer = self._resolve_customer(customer_id)
        response = await self._request(
            "GET",
            f"{self.DIRECTORY_BASE_URL}/customer/{resolved_customer}/domains",
        )
        payload = response.json()
        domains = payload.get("domains", []) if isinstance(payload, dict) else []
        return [domain for domain in domains if isinstance(domain, dict)]

    async def list_users(
        self,
        customer_id: str | None = None,
        *,
        max_results: int = 200,
    ) -> list[dict]:
        return await self._get_paginated(
            f"{self.DIRECTORY_BASE_URL}/users",
            item_key="users",
            params={
                "customer": self._resolve_customer(customer_id),
                "maxResults": max_results,
                "orderBy": "email",
            },
        )

    async def list_groups(
        self,
        customer_id: str | None = None,
        *,
        max_results: int = 200,
    ) -> list[dict]:
        return await self._get_paginated(
            f"{self.DIRECTORY_BASE_URL}/groups",
            item_key="groups",
            params={
                "customer": self._resolve_customer(customer_id),
                "maxResults": max_results,
            },
        )

    async def list_org_units(self, customer_id: str | None = None) -> list[dict]:
        resolved_customer = self._resolve_customer(customer_id)
        response = await self._request(
            "GET",
            f"{self.DIRECTORY_BASE_URL}/customer/{resolved_customer}/orgunits",
            params={"orgUnitPath": "/", "type": "all"},
        )
        payload = response.json()
        org_units = payload.get("organizationUnits", []) if isinstance(payload, dict) else []
        return [org_unit for org_unit in org_units if isinstance(org_unit, dict)]

    async def list_roles(
        self,
        customer_id: str | None = None,
        *,
        max_results: int = 200,
    ) -> list[dict]:
        resolved_customer = self._resolve_customer(customer_id)
        return await self._get_paginated(
            f"{self.DIRECTORY_BASE_URL}/customer/{resolved_customer}/roles",
            item_key="items",
            params={"maxResults": max_results},
        )

    async def list_role_assignments(
        self,
        customer_id: str | None = None,
        *,
        max_results: int = 200,
    ) -> list[dict]:
        resolved_customer = self._resolve_customer(customer_id)
        return await self._get_paginated(
            f"{self.DIRECTORY_BASE_URL}/customer/{resolved_customer}/roleassignments",
            item_key="items",
            params={"maxResults": max_results},
        )

    async def get_tenant_summary(self, customer_id: str | None = None) -> dict[str, Any]:
        customer, domains = await asyncio.gather(
            self.get_customer(customer_id),
            self.list_domains(customer_id),
        )
        normalized = self.normalize_customer(customer, domains)
        return {
            "id": normalized["id"],
            "name": normalized["name"],
            "primary_domain": normalized["primary_domain"],
            "customer": customer,
            "domains": domains,
        }


class GoogleWorkspaceResellerClient(GoogleAPIClient):
    RESELLER_BASE_URL = "https://reseller.googleapis.com/apps/reseller/v1"

    def __init__(
        self,
        *,
        service_account_json: str,
        delegated_admin_email: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            service_account_json=service_account_json,
            delegated_admin_email=delegated_admin_email,
            scopes=RESELLER_READONLY_SCOPES,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def _get_paginated(
        self,
        url: str,
        *,
        item_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        items: list[dict] = []
        next_page_token: str | None = None
        merged_params = dict(params or {})

        while True:
            page_params = dict(merged_params)
            if next_page_token:
                page_params["pageToken"] = next_page_token

            response = await self._request("GET", url, params=page_params)
            payload = response.json()
            page_items = payload.get(item_key, []) if isinstance(payload, dict) else []
            if isinstance(page_items, list):
                items.extend(item for item in page_items if isinstance(item, dict))

            next_page_token = (
                str(payload.get("nextPageToken") or "") if isinstance(payload, dict) else ""
            ) or None
            if not next_page_token:
                break

        return items

    @staticmethod
    def normalize_customer(customer: dict[str, Any]) -> dict[str, str]:
        customer_id = str(customer.get("customerId") or customer.get("id") or "")
        customer_domain = str(customer.get("customerDomain") or customer.get("primaryDomain") or "")
        return {
            "id": customer_id or customer_domain,
            "name": customer_domain or customer_id,
        }

    async def list_subscriptions(
        self,
        *,
        customer_id: str | None = None,
        customer_name_prefix: str | None = None,
        max_results: int = 200,
    ) -> list[dict]:
        params: dict[str, Any] = {"maxResults": max_results}
        if customer_id:
            params["customerId"] = customer_id
        if customer_name_prefix:
            params["customerNamePrefix"] = customer_name_prefix

        return await self._get_paginated(
            f"{self.RESELLER_BASE_URL}/subscriptions",
            item_key="subscriptions",
            params=params,
        )

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"{self.RESELLER_BASE_URL}/customers/{customer_id}",
        )
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def list_customers(
        self,
        *,
        customer_name_prefix: str | None = None,
    ) -> list[dict]:
        # The Reseller API does not expose a customers.list endpoint.
        # We derive the customer set from subscriptions.list and then enrich
        # each unique customer with customers.get where possible.
        subscriptions = await self.list_subscriptions(
            customer_name_prefix=customer_name_prefix,
        )

        customers_by_id: dict[str, dict[str, Any]] = {}
        for subscription in subscriptions:
            customer_id = str(subscription.get("customerId") or "")
            if not customer_id:
                continue
            customers_by_id.setdefault(
                customer_id,
                {
                    "customerId": customer_id,
                    "customerDomain": str(subscription.get("customerDomain") or ""),
                },
            )

        customers: list[dict] = []
        for customer_id, preview in customers_by_id.items():
            try:
                customer = await self.get_customer(customer_id)
                customers.append(customer if customer else preview)
            except Exception:
                customers.append(preview)

        return customers


async def get_workspace_client(scope: str | None = None) -> GoogleWorkspaceClient:
    from bifrost import integrations

    integration = await integrations.get("Google Workspace", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Google Workspace' not found in Bifrost")

    config = integration.config or {}
    required = ["service_account_json", "delegated_admin_email"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Google Workspace integration missing required config: {missing}"
        )

    customer_id = (
        getattr(integration, "entity_id", None)
        or config.get("customer_id")
        or None
    )
    return GoogleWorkspaceClient(
        service_account_json=config["service_account_json"],
        delegated_admin_email=config["delegated_admin_email"],
        customer_id=customer_id,
    )


async def get_reseller_client(scope: str | None = "global") -> GoogleWorkspaceResellerClient:
    from bifrost import integrations

    integration = await integrations.get("Google Workspace Reseller", scope=scope)
    if not integration:
        raise RuntimeError(
            "Integration 'Google Workspace Reseller' not found in Bifrost"
        )

    config = integration.config or {}
    required = ["service_account_json", "delegated_admin_email"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Google Workspace Reseller integration missing required config: {missing}"
        )

    return GoogleWorkspaceResellerClient(
        service_account_json=config["service_account_json"],
        delegated_admin_email=config["delegated_admin_email"],
    )
