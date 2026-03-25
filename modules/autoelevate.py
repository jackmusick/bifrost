"""
AutoElevate API Client

Authentication: Username/Password + TOTP MFA (goofy multi-step flow)
Base URL: https://api-long.autoelevate.com/api/

Required Integration Config (global "AutoElevate" integration):
- username: Login email
- password: Login password
- totp_secret: Base32-encoded TOTP secret for MFA

Auth Flow:
1. POST /users/login with email/password -> returns mfaToken
2. Generate TOTP code from secret
3. POST /users/otpVerify with code + mfaToken -> returns Authorization header
4. Use Authorization header for subsequent requests

Token is cached in bifrost config (is_secret=True, scope="global") and reused
across executions until it expires (~23 hours) or gets a 401.

Note: Rate limited aggressively. Built-in retry logic with exponential backoff.
"""

from __future__ import annotations

import hmac
import struct
import time
import base64
import hashlib
import asyncio
import httpx
from typing import Any
from datetime import datetime, timedelta, timezone


def generate_totp(secret: str, interval: int = 30) -> str:
    """
    Generate a TOTP code from a base32-encoded secret.

    Args:
        secret: Base32-encoded secret (e.g., from authenticator app setup)
        interval: Time interval in seconds (default 30)

    Returns:
        6-digit TOTP code as string
    """
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time()) // interval
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    code = struct.unpack(">I", hmac_hash[offset:offset + 4])[0]
    code = (code & 0x7FFFFFFF) % 1000000
    return str(code).zfill(6)


class AutoElevateClient:
    """
    AutoElevate API client with username/password + TOTP authentication.

    Token is cached persistently via bifrost.config between executions.
    On 401, clears cached token, re-authenticates, and retries once.
    """

    BASE_URL = "https://api-long.autoelevate.com/api"
    LOGIN_URL = "https://apollo.autoelevate.com/api"

    def __init__(
        self,
        username: str,
        password: str,
        totp_secret: str,
    ):
        self.username = username
        self.password = password
        self.totp_secret = totp_secret

        self._auth_token: str | None = None
        self._token_expires: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    def _get_headers(self, include_auth: bool = True) -> dict:
        """Get request headers."""
        headers = {
            "Accept": "application/vnd.autoelevate.v2+json",
            "Origin": "https://msp.autoelevate.com",
            "Content-Type": "application/json;charset=UTF-8",
        }
        if include_auth and self._auth_token:
            headers["Authorization"] = self._auth_token
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _load_cached_token(self) -> bool:
        """Try to load a cached token from bifrost config. Returns True if valid token loaded."""
        from bifrost import config

        token = await config.get("autoelevate_token", scope="global")
        expires = await config.get("autoelevate_token_expires", scope="global")

        if not token or not expires:
            return False

        try:
            expires_dt = datetime.fromisoformat(str(expires))
            if datetime.now(timezone.utc) >= expires_dt:
                return False
            self._auth_token = str(token)
            self._token_expires = expires_dt
            return True
        except (ValueError, TypeError):
            return False

    async def _cache_token(self) -> None:
        """Persist the current token to bifrost config."""
        from bifrost import config

        if self._auth_token and self._token_expires:
            await config.set("autoelevate_token", self._auth_token, is_secret=True, scope="global")
            await config.set("autoelevate_token_expires", self._token_expires.isoformat(), scope="global")

    async def _clear_cached_token(self) -> None:
        """Clear the cached token from both memory and config."""
        from bifrost import config

        self._auth_token = None
        self._token_expires = None
        await config.set("autoelevate_token", "", scope="global")
        await config.set("autoelevate_token_expires", "", scope="global")

    async def authenticate(self) -> None:
        """
        Perform the multi-step authentication flow.

        1. Login with email/password to get MFA token
        2. Generate TOTP code
        3. Verify OTP to get auth token
        4. Cache token in bifrost config for reuse across executions
        """
        client = await self._get_client()
        headers = self._get_headers(include_auth=False)

        # Step 1: Login
        login_response = await self._request_with_retry(
            client,
            "POST",
            f"{self.LOGIN_URL}/users/login",
            headers=headers,
            json={"email": self.username, "password": self.password},
        )
        mfa_token = login_response.get("token")

        if not mfa_token:
            raise ValueError("No MFA token received from login")

        # Step 2: Generate TOTP
        totp_code = generate_totp(self.totp_secret)

        # Step 3: Verify OTP
        otp_response = await client.post(
            f"{self.LOGIN_URL}/users/otpVerify",
            headers=headers,
            json={"code": totp_code, "mfaToken": mfa_token},
        )
        otp_response.raise_for_status()

        # Get auth token from response headers
        self._auth_token = otp_response.headers.get("Authorization")
        if not self._auth_token:
            raise ValueError("No Authorization header received from OTP verification")

        # Token typically lasts 24 hours, refresh after 23
        self._token_expires = datetime.now(timezone.utc) + timedelta(hours=23)

        # Persist for reuse across executions
        await self._cache_token()

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid auth token, loading from cache if available."""
        if self._auth_token and self._token_expires and datetime.now(timezone.utc) < self._token_expires:
            return

        # Try loading from persistent cache first
        if await self._load_cached_token():
            return

        # No cached token — do the full MFA dance
        await self.authenticate()

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        max_retries: int = 5,
        **kwargs,
    ) -> dict:
        """Make a request with retry logic for rate limiting."""
        delay = 5
        for attempt in range(max_retries):
            try:
                response = await client.request(method, url, **kwargs)

                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                    raise Exception("Rate limited after max retries")

                response.raise_for_status()
                return response.json() if response.content else {}

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise

        raise Exception("Max retries exceeded")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        """Make an authenticated request. Retries once on 401 with fresh token."""
        await self._ensure_authenticated()
        client = await self._get_client()
        url = f"{self.BASE_URL}/{path.lstrip('/')}"

        try:
            return await self._request_with_retry(
                client, method, url,
                params=params, json=json, headers=self._get_headers(),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await self._clear_cached_token()
                await self.authenticate()
                return await self._request_with_retry(
                    client, method, url,
                    params=params, json=json, headers=self._get_headers(),
                )
            raise

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------------------------
    # Requests (elevation requests)
    # -------------------------------------------------------------------------

    async def list_requests(self, *, take: int = 500, skip: int = 0, start: str | None = None, end: str | None = None) -> list[dict]:
        """List elevation requests. API returns {items: [...]}, we unwrap to just the list."""
        params = {"take": take, "skip": skip}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        result = await self._request("GET", "requests", params=params)
        if isinstance(result, dict) and "items" in result:
            return result["items"]
        return result

    async def get_request(self, request_id: str) -> dict:
        """Get a specific elevation request. API wraps in {request: {...}}, we unwrap."""
        result = await self._request("GET", f"requests/{request_id}")
        if isinstance(result, dict) and "request" in result:
            return result["request"]
        return result

    async def approve_request(self, request_id: str, *, json_body: dict | None = None) -> dict:
        """Approve an elevation request."""
        return await self._request("POST", f"requests/{request_id}/approve", json=json_body)

    async def deny_request(self, request_id: str, *, json_body: dict | None = None) -> dict:
        """Deny an elevation request."""
        return await self._request("POST", f"requests/{request_id}/deny", json=json_body)

    # -------------------------------------------------------------------------
    # Rules
    # -------------------------------------------------------------------------

    async def list_rules(self, *, take: int = 500) -> list[dict]:
        """List rules. API wraps each item in {rule: {...}}, we unwrap."""
        result = await self._request("GET", "rules", params={"take": take})
        if isinstance(result, list) and result and isinstance(result[0], dict) and "rule" in result[0]:
            return [item["rule"] for item in result]
        return result

    async def get_rule(self, rule_id: str) -> dict:
        """Get a specific rule. API may wrap in {rule: {...}}, we unwrap."""
        result = await self._request("GET", f"rules/{rule_id}")
        if isinstance(result, dict) and "rule" in result:
            return result["rule"]
        return result

    async def update_rule(self, rule_id: str, *, json_body: dict) -> dict:
        """Update a rule (PATCH)."""
        return await self._request("PATCH", f"rules/{rule_id}", json=json_body)


# ---------------------------------------------------------------------------
# Bifrost SDK integration
# ---------------------------------------------------------------------------

async def get_client() -> AutoElevateClient:
    """
    Get an AutoElevate client configured from Bifrost integration config.

    Note: AutoElevate credentials are global (MSP-level), not per-organization.
    Authentication happens lazily on first request — no need to call authenticate().
    """
    from bifrost import integrations

    integration = await integrations.get("AutoElevate", scope="global")
    if not integration:
        raise RuntimeError("Integration 'AutoElevate' not found in Bifrost")

    cfg = integration.config or {}
    username = cfg.get("username")
    password = cfg.get("password")
    totp_secret = cfg.get("totp_secret")

    if not username or not password or not totp_secret:
        raise RuntimeError(
            f"Integration 'AutoElevate' is missing required config keys. "
            f"Found keys: {list(cfg.keys())}"
        )

    return AutoElevateClient(
        username=username,
        password=password,
        totp_secret=totp_secret,
    )


class _LazyClient:
    """
    Module-level proxy that auto-initializes from Bifrost config.
    Caches a single AutoElevateClient instance (MSP-level, not per-org).
    On 401, clears and recreates the client.
    """

    def __init__(self):
        self._client: AutoElevateClient | None = None

    async def _get_or_create(self) -> AutoElevateClient:
        if self._client is None:
            self._client = await get_client()
        return self._client

    def __getattr__(self, name: str):
        """Proxy attribute access to a real AutoElevateClient instance."""
        async def _wrapper(*args, **kwargs):
            client = await self._get_or_create()
            try:
                return await getattr(client, name)(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    # Client-level 401 retry already ran — recreate client entirely
                    self._client = None
                    client = await self._get_or_create()
                    return await getattr(client, name)(*args, **kwargs)
                raise
        return _wrapper


# Module-level lazy client — use like: await autoelevate.list_organizations()
_lazy = _LazyClient()


def __getattr__(name: str):
    """Enable top-level module attribute access via the lazy client."""
    return getattr(_lazy, name)
