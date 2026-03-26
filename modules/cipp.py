"""
CIPP (CyberDrain Improved Partner Portal) API Client

Authentication: OAuth 2.0 client credentials via Azure AD
Protocol: REST (Azure Functions HTTP triggers)
Base URL: https://{your-cipp-instance}.azurewebsites.net

Required integration config keys:
  base_url      — CIPP API base URL (e.g. https://cippidlq5.azurewebsites.net)
  tenant_id     — Azure AD tenant ID where CIPP is deployed
  client_id     — API client application ID
  client_secret — API client secret
  api_scope     — CIPP API scope (e.g. api://{function-app-id}/.default)

Azure AD prerequisite:
  The CIPP Function App's service principal must be admin-consented in your
  Azure AD tenant before OAuth tokens can be issued. In Azure Portal go to:
  Azure AD → Enterprise Applications → New application → find by client_id
  → Grant admin consent.
  See: https://docs.cipp.app/api-documentation/setup-and-authentication

Usage:
    from modules.cipp import get_client

    client = await get_client()
    tenants = await client.list_tenants()
    users = await client.list_users("contoso.onmicrosoft.com")
    await client.close()
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class CIPPClient:
    """
    Async REST client for the CIPP API.

    All API calls route through the generic `call()` method, which handles
    OAuth token acquisition/refresh automatically. Higher-level methods
    wrap the most common MSP operations.
    """

    def __init__(
        self,
        base_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        api_scope: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        )
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_scope = api_scope
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=60.0)
        return self._http

    async def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if within 60s of expiry."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        http = await self._get_http()
        resp = await http.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._api_scope,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        if "error" in body:
            raise RuntimeError(
                f"CIPP OAuth error: {body.get('error_description', body['error'])}"
            )

        self._access_token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 3600)
        return self._access_token

    async def call(
        self,
        function: str,
        *,
        method: str = "GET",
        **params: Any,
    ) -> Any:
        """
        Make a CIPP API call.

        Args:
            function: The CIPP function name (e.g. "ListTenants", "ListUsers").
            method:   HTTP method — "GET" (default) or "POST".
            **params: Query parameters (GET) or JSON body fields (POST).

        Returns:
            Parsed JSON response. CIPP returns either a list or
            {"Results": [...]} depending on the endpoint.
        """
        token = await self._ensure_token()
        http = await self._get_http()
        url = f"{self._base_url}/api/{function}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        if method.upper() == "GET":
            resp = await http.get(url, params=params or None, headers=headers)
        else:
            resp = await http.post(url, json=params or None, headers=headers)

        if not resp.is_success:
            raise RuntimeError(
                f"CIPP [{function}] HTTP {resp.status_code}: {resp.text[:500]}"
            )

        return resp.json()

    def _unwrap(self, raw: Any) -> list[dict]:
        """Normalise CIPP's two response shapes to a plain list."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("Results", raw.get("results", []))
        return []

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # -------------------------------------------------------------------------
    # Tenants
    # -------------------------------------------------------------------------

    async def list_tenants(self, *, include_excluded: bool = False) -> list[dict]:
        """
        List all CIPP-managed customer tenants.

        Each tenant dict contains at minimum:
          defaultDomainName, displayName, customerId, Excluded
        """
        raw = await self.call("ListTenants")
        tenants = self._unwrap(raw)
        if not include_excluded:
            tenants = [t for t in tenants if not t.get("Excluded", False)]
        return tenants

    async def get_tenant(self, tenant_filter: str) -> dict:
        """Get a single tenant by domain name or tenant ID."""
        raw = await self.call("ListTenants", tenantFilter=tenant_filter)
        results = self._unwrap(raw)
        return results[0] if results else {}

    # -------------------------------------------------------------------------
    # Users & Identity
    # -------------------------------------------------------------------------

    async def list_users(self, tenant: str) -> list[dict]:
        """List all users for a tenant (by defaultDomainName)."""
        raw = await self.call("ListUsers", tenantFilter=tenant)
        return self._unwrap(raw)

    async def list_groups(self, tenant: str) -> list[dict]:
        """List all groups for a tenant."""
        raw = await self.call("ListGroups", tenantFilter=tenant)
        return self._unwrap(raw)

    async def list_guest_users(self, tenant: str) -> list[dict]:
        """List guest/external users for a tenant."""
        raw = await self.call("ListGuestUsers", tenantFilter=tenant)
        return self._unwrap(raw)

    # -------------------------------------------------------------------------
    # Licenses
    # -------------------------------------------------------------------------

    async def list_licenses(self, tenant: str) -> list[dict]:
        """List license SKUs and usage counts for a tenant."""
        raw = await self.call("ListLicenses", tenantFilter=tenant)
        return self._unwrap(raw)

    # -------------------------------------------------------------------------
    # Security & Alerts
    # -------------------------------------------------------------------------

    async def list_alerts(self, tenant: str | None = None) -> list[dict]:
        """List active alerts, optionally scoped to a single tenant."""
        kwargs: dict[str, Any] = {}
        if tenant:
            kwargs["tenantFilter"] = tenant
        raw = await self.call("ListAlertsQueue", **kwargs)
        return self._unwrap(raw)

    async def list_incidents(self, tenant: str) -> list[dict]:
        """List Defender security incidents for a tenant."""
        raw = await self.call("ListIncidents", tenantFilter=tenant)
        return self._unwrap(raw)

    async def list_defender_status(self, tenant: str) -> list[dict]:
        """List Defender for Endpoint device status for a tenant."""
        raw = await self.call("ListDefenderState", tenantFilter=tenant)
        return self._unwrap(raw)

    # -------------------------------------------------------------------------
    # Domain health
    # -------------------------------------------------------------------------

    async def list_domain_health(self, tenant: str) -> list[dict]:
        """Get domain analyser results for all domains in a tenant."""
        raw = await self.call("DomainAnalyser_List", tenantFilter=tenant)
        return self._unwrap(raw)

    # -------------------------------------------------------------------------
    # Standards & Compliance
    # -------------------------------------------------------------------------

    async def list_standards(self, tenant: str) -> list[dict]:
        """List applied standards/best-practice policies for a tenant."""
        raw = await self.call("ListStandards", tenantFilter=tenant)
        return self._unwrap(raw)

    async def list_conditional_access(self, tenant: str) -> list[dict]:
        """List Conditional Access policies for a tenant."""
        raw = await self.call("ListConditionalAccessPolicies", tenantFilter=tenant)
        return self._unwrap(raw)

    # -------------------------------------------------------------------------
    # Devices (Intune / Autopilot)
    # -------------------------------------------------------------------------

    async def list_devices(self, tenant: str) -> list[dict]:
        """List Intune-managed devices for a tenant."""
        raw = await self.call("ListDevices", tenantFilter=tenant)
        return self._unwrap(raw)

    async def list_autopilot_devices(self, tenant: str) -> list[dict]:
        """List Autopilot-registered devices for a tenant."""
        raw = await self.call("ListAutopilotDevices", tenantFilter=tenant)
        return self._unwrap(raw)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

async def get_client() -> CIPPClient:
    """
    Get a CIPPClient configured from the 'CIPP' Bifrost integration.

    Integration must have config keys:
      base_url, tenant_id, client_id, client_secret, api_scope
    """
    from bifrost import integrations

    integration = await integrations.get("CIPP")
    if not integration:
        raise RuntimeError("Integration 'CIPP' not found in Bifrost")

    cfg = integration.config or {}
    required = ["base_url", "tenant_id", "client_id", "client_secret", "api_scope"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise RuntimeError(
            f"CIPP integration missing config: {missing}. "
            f"Found keys: {list(cfg.keys())}"
        )

    return CIPPClient(
        base_url=cfg["base_url"],
        tenant_id=cfg["tenant_id"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        api_scope=cfg["api_scope"],
    )
