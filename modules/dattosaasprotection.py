"""
Datto SaaS Protection API client.

Auth: HTTP Basic using api_key:api_secret
Base URL: https://api.datto.com/v1

The currently validated read-only surface is limited to `/saas/domains`.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx


class DattoSaaSProtectionClient:
    """Focused async client for Datto SaaS Protection domain inventory."""

    BASE_URL = "https://api.datto.com/v1"

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str | None = None,
        saas_customer_id: str | None = None,
    ):
        token = base64.b64encode(f"{api_key}:{api_secret}".encode("utf-8")).decode("ascii")
        self._base_url = (base_url or self.BASE_URL).rstrip("/")
        self.saas_customer_id = (
            str(saas_customer_id) if saas_customer_id is not None else None
        )
        # Temporary alias so the just-added integration remains tolerant of
        # earlier naming while the entity model settles on saasCustomerId.
        self.domain_id = self.saas_customer_id
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=30.0,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {token}",
                # The local validation note showed curl succeeding where earlier
                # Python attempts were blocked upstream, so keep the request shape
                # conservative and explicit.
                "User-Agent": "curl/8.5.0",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = await self._client.request(method, path, params=params)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                if not response.content:
                    return {}
                return response.json()
            except httpx.HTTPStatusError as exc:
                body_text = exc.response.text[:1000] if exc.response.text else ""
                last_error = RuntimeError(
                    f"Datto SaaS Protection HTTP {exc.response.status_code} {method} {path}: {body_text}"
                )
                if exc.response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                break
            except httpx.HTTPError as exc:
                last_error = RuntimeError(
                    f"Datto SaaS Protection request failed for {method} {path}: {exc}"
                )
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                break

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Datto SaaS Protection request failed for {method} {path}")

    async def list_domains(self) -> list[dict]:
        """List SaaS domain records."""
        payload = await self._request("GET", "/saas/domains")
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("domains"), list):
                return payload["domains"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        return []

    async def get_domain(self, saas_customer_id: str | None = None) -> dict:
        """Resolve a domain record by explicit or mapped SaaS customer ID."""
        target_customer_id = saas_customer_id or self.saas_customer_id
        if not target_customer_id:
            raise RuntimeError(
                "Datto SaaS Protection client requires a mapped saas_customer_id for org-scoped access."
            )

        domains = await self.list_domains()
        for domain in domains:
            if str(domain.get("saasCustomerId") or domain.get("id")) == str(
                target_customer_id
            ):
                return domain

        raise RuntimeError(
            f"Datto SaaS Protection SaaS customer {target_customer_id} not found"
        )

    async def list_seats(
        self,
        saas_customer_id: str | None = None,
        *,
        seat_type: list[str] | None = None,
    ) -> list[dict]:
        """List SaaS Protection seats for a customer."""
        target_customer_id = saas_customer_id or self.saas_customer_id
        if not target_customer_id:
            raise RuntimeError(
                "Datto SaaS Protection client requires a mapped saas_customer_id for seat access."
            )

        params: dict[str, Any] | None = None
        if seat_type:
            params = {"seatType": ",".join(seat_type)}

        payload = await self._request(
            "GET",
            f"/saas/{target_customer_id}/seats",
            params=params,
        )
        return payload if isinstance(payload, list) else []

    async def list_applications(
        self,
        saas_customer_id: str | None = None,
        *,
        days_until: int | None = None,
    ) -> list[dict]:
        """List SaaS Protection application backup data for a customer."""
        target_customer_id = saas_customer_id or self.saas_customer_id
        if not target_customer_id:
            raise RuntimeError(
                "Datto SaaS Protection client requires a mapped saas_customer_id for application access."
            )

        params: dict[str, Any] | None = None
        if days_until is not None:
            params = {"daysUntil": days_until}

        payload = await self._request(
            "GET",
            f"/saas/{target_customer_id}/applications",
            params=params,
        )
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return items
        return payload if isinstance(payload, list) else []

    @staticmethod
    def normalize_domain(domain: dict) -> dict[str, str | None]:
        """Normalize a Datto SaaS Protection domain record for Bifrost mapping."""
        domain_id = domain.get("saasCustomerId") or domain.get("id")
        domain_name = domain.get("domain")
        organization_name = domain.get("organizationName") or domain.get("saasCustomerName")
        external_subscription_id = domain.get("externalSubscriptionId")

        if organization_name and domain_name and organization_name != domain_name:
            label = f"{organization_name} ({domain_name})"
        else:
            label = organization_name or domain_name

        return {
            "id": str(domain_id) if domain_id is not None else None,
            "name": organization_name or domain_name or None,
            "domain": domain_name or None,
            "label": label or None,
            "external_subscription_id": (
                str(external_subscription_id)
                if external_subscription_id is not None
                else None
            ),
        }


async def get_client(scope: str | None = None) -> DattoSaaSProtectionClient:
    """Get a Datto SaaS Protection client for the requested Bifrost scope."""
    from bifrost import integrations

    integration = await integrations.get("Datto SaaS Protection", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Datto SaaS Protection' not found in Bifrost")

    config = integration.config or {}
    api_key = config.get("api_key")
    api_secret = config.get("api_secret")
    if not api_key or not api_secret:
        raise RuntimeError(
            "Integration 'Datto SaaS Protection' is missing api_key or api_secret in config."
        )

    saas_customer_id = getattr(integration, "entity_id", None)
    return DattoSaaSProtectionClient(
        api_key=api_key,
        api_secret=api_secret,
        saas_customer_id=saas_customer_id,
    )
