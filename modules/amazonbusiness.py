"""
Amazon Business API helpers for Bifrost integrations.

This first-pass integration targets the transactional procurement APIs used for:
  - order detail lookup
  - package tracking lookup

It is intentionally modeled as a global, lookup-oriented integration. Amazon
Business onboarding, role assignment, and notification plumbing can be added
later without forcing those requirements into the initial scaffold.
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class AmazonBusinessClient:
    """Focused async client for Amazon Business procurement lookups."""

    DEFAULT_REGION = "NA"
    DEFAULT_MARKETPLACE = "US"
    REGION_BASE_URLS = {
        "NA": "https://na.business-api.amazon.com",
        "EU": "https://eu.business-api.amazon.com",
        "FE": "https://jp.business-api.amazon.com",
    }
    TOKEN_URL = "https://api.amazon.com/auth/O2/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        buyer_email: str,
        *,
        api_region: str = DEFAULT_REGION,
        marketplace_region: str = DEFAULT_MARKETPLACE,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        region = api_region.upper().strip()
        if region not in self.REGION_BASE_URLS:
            supported = ", ".join(sorted(self.REGION_BASE_URLS))
            raise ValueError(
                f"Unsupported Amazon Business api_region '{api_region}'. Expected one of: {supported}"
            )

        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._buyer_email = buyer_email
        self._api_region = region
        self._marketplace_region = marketplace_region.upper().strip()
        self._base_url = (base_url or self.REGION_BASE_URLS[region]).rstrip("/")
        self._timeout = timeout
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
        response = await httpx.AsyncClient(timeout=self._timeout).post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        self._token_expires_at = time.time() + float(expires_in)

    async def _ensure_access_token(self) -> str:
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
        buyer_email: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        token = await self._ensure_access_token()
        http = await self._get_http()
        headers = {
            "x-amz-access-token": token,
            "x-amz-user-email": buyer_email or self._buyer_email,
        }
        response = await http.request(
            method,
            path,
            params=params or None,
            headers=headers,
        )

        if response.status_code == 401:
            self._access_token = None
            token = await self._ensure_access_token()
            headers["x-amz-access-token"] = token
            response = await http.request(
                method,
                path,
                params=params or None,
                headers=headers,
            )

        if not response.is_success:
            body = response.text[:1000]
            raise RuntimeError(
                f"Amazon Business [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    async def get_order_details(
        self,
        external_id: str,
        *,
        buyer_email: str | None = None,
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            f"/ordering/2022-10-30/orders/{external_id}",
            buyer_email=buyer_email,
        )
        return payload if isinstance(payload, dict) else {}

    async def get_package_tracking_details(
        self,
        order_id: str,
        shipment_id: str,
        package_id: str,
        *,
        region: str | None = None,
        locale: str | None = None,
        buyer_email: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if region:
            params["region"] = region
        if locale:
            params["locale"] = locale

        payload = await self._request(
            "GET",
            f"/packageTracking/2022-10-30/orders/{order_id}/shipments/{shipment_id}/packages/{package_id}",
            buyer_email=buyer_email,
            params=params or None,
        )
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def summarize_order_details(payload: dict[str, Any]) -> dict[str, Any]:
        line_items = payload.get("lineItems", [])
        acceptance_artifacts = payload.get("acceptanceArtifacts", [])
        rejection_artifacts = payload.get("rejectionArtifacts", [])

        accepted_count = 0
        rejected_count = 0
        order_identifiers: list[str] = []
        tracking_numbers: list[str] = []

        for item in line_items if isinstance(line_items, list) else []:
            if not isinstance(item, dict):
                continue
            accepted_items = item.get("acceptedItems", [])
            rejected_items = item.get("rejectedItems", [])
            accepted_count += len(accepted_items) if isinstance(accepted_items, list) else 0
            rejected_count += len(rejected_items) if isinstance(rejected_items, list) else 0

            for accepted in accepted_items if isinstance(accepted_items, list) else []:
                if not isinstance(accepted, dict):
                    continue
                artifacts = accepted.get("artifacts", [])
                for artifact in artifacts if isinstance(artifacts, list) else []:
                    if not isinstance(artifact, dict):
                        continue
                    artifact_type = artifact.get("acceptanceArtifactType")
                    if artifact_type == "OrderIdentifier" and artifact.get("identifier"):
                        order_identifiers.append(str(artifact["identifier"]))
                    if artifact_type in {"ShipmentGroup", "Shipment"}:
                        for package_ref in artifact.get("packageReferences", []):
                            if (
                                isinstance(package_ref, dict)
                                and package_ref.get("packageReferenceType") == "CarrierTrackingNumber"
                                and package_ref.get("value")
                            ):
                                tracking_numbers.append(str(package_ref["value"]))
                        for package in artifact.get("packages", []):
                            if not isinstance(package, dict):
                                continue
                            package_ref = package.get("packageReference", {})
                            if (
                                isinstance(package_ref, dict)
                                and package_ref.get("packageReferenceType") == "CarrierTrackingNumber"
                                and package_ref.get("value")
                            ):
                                tracking_numbers.append(str(package_ref["value"]))

        return {
            "line_item_count": len(line_items) if isinstance(line_items, list) else 0,
            "accepted_item_count": accepted_count,
            "rejected_item_count": rejected_count,
            "acceptance_artifact_count": (
                len(acceptance_artifacts) if isinstance(acceptance_artifacts, list) else 0
            ),
            "rejection_artifact_count": (
                len(rejection_artifacts) if isinstance(rejection_artifacts, list) else 0
            ),
            "order_identifiers": sorted(set(order_identifiers)),
            "tracking_numbers": sorted(set(tracking_numbers)),
        }

    @staticmethod
    def summarize_package_tracking(payload: dict[str, Any]) -> dict[str, Any]:
        package_status = payload.get("packageStatus")
        tracking_number = payload.get("trackingNumber")
        carrier_name = payload.get("carrierName")
        delivery_date = payload.get("deliveryDate")
        tracking_events = payload.get("trackingEvents", [])

        latest_event = None
        if isinstance(tracking_events, list) and tracking_events:
            latest_event = tracking_events[0]
            if not isinstance(latest_event, dict):
                latest_event = None

        return {
            "package_status": package_status,
            "tracking_number": tracking_number,
            "carrier_name": carrier_name,
            "delivery_date": delivery_date,
            "tracking_event_count": len(tracking_events) if isinstance(tracking_events, list) else 0,
            "latest_event": latest_event,
        }

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = "global") -> AmazonBusinessClient:
    """Build an Amazon Business client from the configured Bifrost integration."""
    from bifrost import integrations

    integration = await integrations.get("Amazon Business", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Amazon Business' not found in Bifrost")

    config = integration.config or {}
    required = ["client_id", "client_secret", "refresh_token", "buyer_email"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Amazon Business integration missing required config: {missing}"
        )

    return AmazonBusinessClient(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        refresh_token=config["refresh_token"],
        buyer_email=config["buyer_email"],
        api_region=config.get("api_region") or AmazonBusinessClient.DEFAULT_REGION,
        marketplace_region=(
            config.get("marketplace_region") or AmazonBusinessClient.DEFAULT_MARKETPLACE
        ),
        base_url=config.get("base_url"),
    )
