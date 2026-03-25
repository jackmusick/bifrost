"""
Datto Networking / CloudTrax API helpers for Bifrost integrations.

Authentication:
  - Header-based HMAC authentication
  - OpenMesh-API-Version: 1
  - Authorization: key=<api-key>,timestamp=<unix-seconds>,nonce=<random>
  - Signature: sha256_hmac_hex(secret, authorization + path [+ raw_json_body])

The org-scoped integration mapping stores the Datto Networking network ID in
`integration.entity_id`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import httpx


class DattoNetworkingClient:
    BASE_URL = "https://api.cloudtrax.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        network_id: str | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._network_id = str(network_id or "").strip() or None
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    @property
    def network_id(self) -> str | None:
        return self._network_id

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    @staticmethod
    def _serialize_body(body: dict[str, Any] | None = None) -> str:
        if body is None:
            return ""
        return json.dumps(body, separators=(",", ":"), sort_keys=False)

    def _build_headers(
        self,
        path: str,
        *,
        body: str = "",
        timestamp: int | None = None,
        nonce: str | None = None,
    ) -> dict[str, str]:
        resolved_timestamp = int(timestamp if timestamp is not None else time.time())
        resolved_nonce = nonce or uuid.uuid4().hex
        authorization = (
            f"key={self._api_key},timestamp={resolved_timestamp},nonce={resolved_nonce}"
        )
        message = authorization + path + body
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "OpenMesh-API-Version": "1",
            "Authorization": authorization,
            "Signature": signature,
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        http = await self._get_http()
        raw_body = self._serialize_body(json_body if method.upper() in {"POST", "PUT"} else None)
        headers = self._build_headers(path, body=raw_body)
        if raw_body:
            headers["Content-Type"] = "application/json"

        response = await http.request(
            method,
            f"{self._base_url}{path}",
            content=raw_body if raw_body else None,
            headers=headers,
        )
        if not response.is_success:
            body = response.text[:1000]
            raise RuntimeError(
                f"Datto Networking [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def normalize_network(network: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(network.get("id") or network.get("network_id") or ""),
            "name": str(network.get("name") or ""),
        }

    async def get_time(self) -> str:
        payload = await self._request("GET", "/time")
        return str(payload.get("time") or "")

    async def list_networks(self) -> list[dict]:
        payload = await self._request("GET", "/network/list")
        networks = payload.get("networks", [])
        return [network for network in networks if isinstance(network, dict)] if isinstance(networks, list) else []

    async def get_network_settings(self, network_id: str | None = None) -> dict[str, Any]:
        resolved_network_id = str(network_id or self._network_id or "").strip()
        if not resolved_network_id:
            raise RuntimeError(
                "Datto Networking network ID is not available. Configure a network mapping first."
            )
        return await self._request("GET", f"/network/{resolved_network_id}/settings")

    async def list_network_nodes(self, network_id: str | None = None) -> list[dict]:
        resolved_network_id = str(network_id or self._network_id or "").strip()
        if not resolved_network_id:
            raise RuntimeError(
                "Datto Networking network ID is not available. Configure a network mapping first."
            )
        payload = await self._request("GET", f"/node/network/{resolved_network_id}/list")
        nodes = payload.get("nodes", [])
        return [node for node in nodes if isinstance(node, dict)] if isinstance(nodes, list) else []

    async def list_network_switches(self, network_id: str | None = None) -> list[dict]:
        resolved_network_id = str(network_id or self._network_id or "").strip()
        if not resolved_network_id:
            raise RuntimeError(
                "Datto Networking network ID is not available. Configure a network mapping first."
            )
        payload = await self._request("GET", f"/switch/network/{resolved_network_id}/list")
        switches = payload.get("switches", [])
        return (
            [switch for switch in switches if isinstance(switch, dict)]
            if isinstance(switches, list)
            else []
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> DattoNetworkingClient:
    """
    Build a Datto Networking client from the configured Bifrost integration.

    For org-scoped calls, the mapped network ID is exposed through
    `client.network_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("Datto Networking", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Datto Networking' not found in Bifrost")

    config = integration.config or {}
    required = ["api_key", "api_secret"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            f"Datto Networking integration missing required config: {missing}"
        )

    return DattoNetworkingClient(
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        network_id=getattr(integration, "entity_id", None),
        base_url=config.get("base_url", DattoNetworkingClient.BASE_URL),
    )
