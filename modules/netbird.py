"""
NetBird Management API helpers for Bifrost integrations.

NetBird exposes a token-authenticated REST API for account-wide resources such
as peers, groups, users, setup keys, and audit events.

Docs:
- https://docs.netbird.io/api/resources/peers
- https://docs.netbird.io/api/resources/groups
- https://docs.netbird.io/api/resources/setup-keys
- https://docs.netbird.io/api/resources/users
- https://docs.netbird.io/api/resources/events
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class NetBirdClient:
    """Focused async client for the NetBird Management API."""

    BASE_URL = "https://api.netbird.io"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = (base_url or self.BASE_URL).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {api_token}",
            },
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            response = await self._http.request(
                method,
                path,
                params=params or None,
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
                f"NetBird [{method.upper()} {path}] HTTP {response.status_code}: {body}"
            )

        if not response.content:
            return {}
        return response.json()

    async def list_peers(
        self,
        *,
        name: str | None = None,
        ip: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if name:
            params["name"] = name
        if ip:
            params["ip"] = ip
        payload = await self._request("GET", "/api/peers", params=params or None)
        return payload if isinstance(payload, list) else []

    async def list_groups(self, *, name: str | None = None) -> list[dict[str, Any]]:
        params = {"name": name} if name else None
        payload = await self._request("GET", "/api/groups", params=params)
        return payload if isinstance(payload, list) else []

    async def list_setup_keys(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/setup-keys")
        return payload if isinstance(payload, list) else []

    async def list_users(
        self,
        *,
        service_user: bool | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] | None = None
        if service_user is not None:
            params = {"service_user": str(service_user).lower()}
        payload = await self._request("GET", "/api/users", params=params)
        return payload if isinstance(payload, list) else []

    async def list_audit_events(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/events/audit")
        return payload if isinstance(payload, list) else []

    @staticmethod
    def normalize_peer(peer: dict[str, Any]) -> dict[str, Any]:
        groups = peer.get("groups") if isinstance(peer.get("groups"), list) else []
        return {
            "id": str(peer.get("id") or ""),
            "name": str(peer.get("name") or peer.get("hostname") or ""),
            "ip": str(peer.get("ip") or ""),
            "dns_label": str(peer.get("dns_label") or ""),
            "connected": bool(peer.get("connected", False)),
            "os": str(peer.get("os") or ""),
            "version": str(peer.get("version") or ""),
            "last_seen": str(peer.get("last_seen") or ""),
            "group_ids": [
                str(group.get("id"))
                for group in groups
                if isinstance(group, dict) and group.get("id")
            ],
        }

    @staticmethod
    def normalize_group(group: dict[str, Any]) -> dict[str, Any]:
        peers = group.get("peers") if isinstance(group.get("peers"), list) else []
        resources = (
            group.get("resources") if isinstance(group.get("resources"), list) else []
        )
        return {
            "id": str(group.get("id") or ""),
            "name": str(group.get("name") or ""),
            "issued": str(group.get("issued") or ""),
            "peers_count": int(group.get("peers_count") or len(peers)),
            "resources_count": int(group.get("resources_count") or len(resources)),
            "peer_ids": [
                str(peer.get("id"))
                for peer in peers
                if isinstance(peer, dict) and peer.get("id")
            ],
        }

    @staticmethod
    def normalize_setup_key(setup_key: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(setup_key.get("id") or ""),
            "name": str(setup_key.get("name") or ""),
            "type": str(setup_key.get("type") or ""),
            "state": str(setup_key.get("state") or ""),
            "valid": bool(setup_key.get("valid", False)),
            "revoked": bool(setup_key.get("revoked", False)),
            "ephemeral": bool(setup_key.get("ephemeral", False)),
            "usage_limit": int(setup_key.get("usage_limit") or 0),
            "used_times": int(setup_key.get("used_times") or 0),
            "expires": str(setup_key.get("expires") or ""),
            "last_used": str(setup_key.get("last_used") or ""),
            "auto_groups": [
                str(group_id)
                for group_id in (setup_key.get("auto_groups") or [])
                if group_id
            ],
        }

    @staticmethod
    def normalize_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(user.get("id") or ""),
            "name": str(user.get("name") or ""),
            "email": str(user.get("email") or "").strip().lower(),
            "role": str(user.get("role") or ""),
            "status": str(user.get("status") or ""),
            "is_service_user": bool(user.get("is_service_user", False)),
            "is_blocked": bool(user.get("is_blocked", False)),
            "pending_approval": bool(user.get("pending_approval", False)),
            "last_login": str(user.get("last_login") or ""),
            "auto_groups": [
                str(group_id)
                for group_id in (user.get("auto_groups") or [])
                if group_id
            ],
        }

    @staticmethod
    def normalize_audit_event(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(event.get("id") or ""),
            "timestamp": str(event.get("timestamp") or ""),
            "activity": str(event.get("activity") or ""),
            "activity_code": str(event.get("activity_code") or ""),
            "initiator_email": str(event.get("initiator_email") or "").strip().lower(),
            "initiator_name": str(event.get("initiator_name") or ""),
            "target_id": str(event.get("target_id") or ""),
            "meta": event.get("meta") if isinstance(event.get("meta"), dict) else {},
        }


async def get_client(scope: str | None = "global") -> NetBirdClient:
    """Build a NetBird client from the configured Bifrost integration."""
    from bifrost import integrations

    integration = await integrations.get("NetBird", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'NetBird' not found in Bifrost")

    config = integration.config or {}
    required = ["api_token"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"NetBird integration missing required config: {missing}")

    return NetBirdClient(
        api_token=str(config["api_token"]),
        base_url=config.get("base_url") or NetBirdClient.BASE_URL,
    )
