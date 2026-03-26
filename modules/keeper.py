"""
Keeper MSP client helpers for Bifrost integrations.

This integration is intentionally service-backed. Instead of embedding the
interactive Keeper CLI or the full `keepercommander` package into Bifrost,
it talks to Keeper Commander Service Mode over HTTP.

Design note:
  - docs/plans/2026-03-25-keeper-msp-integration-design-note.md

Expected service setup:
  - Keeper Commander Service Mode running separately, ideally in k3s
  - `msp-info` included in the service command allowlist
  - response encryption disabled so Bifrost receives JSON

The org-scoped integration mapping stores the Keeper managed company ID in
`integration.entity_id`.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import Any

import httpx


class KeeperMSPClient:
    """Async client for Keeper Commander Service Mode MSP company lookups."""

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_version: str = "v2",
        company_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        poll_interval: float = 1.0,
        command_timeout: float = 60.0,
    ) -> None:
        self._base_url = self._normalize_base_url(base_url)
        self._api_key = api_key
        self._api_version = self._normalize_api_version(api_version)
        self._company_id = str(company_id or "").strip() or None
        self._timeout = timeout
        self._max_retries = max_retries
        self._poll_interval = poll_interval
        self._command_timeout = command_timeout
        self._http: httpx.AsyncClient | None = None

    @property
    def company_id(self) -> str | None:
        return self._company_id

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        value = str(base_url or "").strip().rstrip("/")
        value = re.sub(r"/api/v[12]$", "", value)
        return value

    @staticmethod
    def _normalize_api_version(api_version: str) -> str:
        value = str(api_version or "v2").strip().lower()
        if value not in {"v1", "v2"}:
            raise RuntimeError("Keeper MSP api_version must be 'v1' or 'v2'")
        return value

    @property
    def _api_prefix(self) -> str:
        return f"/api/{self._api_version}"

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "api-key": self._api_key,
                },
            )
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        http = await self._get_http()
        last_error: RuntimeError | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await http.request(method, path, json=json_body)
            except httpx.HTTPError as exc:
                last_error = RuntimeError(
                    f"Keeper MSP request failed for {method} {path}: {exc}"
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2**attempt, 5.0))
                    continue
                break

            if response.status_code in self.RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                await asyncio.sleep(min(2**attempt, 5.0))
                continue

            if not response.is_success:
                body_text = response.text[:1000] if response.text else ""
                raise RuntimeError(
                    f"Keeper MSP [{method.upper()} {path}] HTTP {response.status_code}: {body_text}"
                )

            if not response.content:
                return {}

            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "Keeper MSP service returned non-JSON data. "
                    "Disable Commander Service Mode response encryption for Bifrost."
                ) from exc

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Keeper MSP request failed for {method} {path}")

    async def _execute_command(self, command: str) -> dict[str, Any]:
        if self._api_version == "v1":
            return await self._execute_command_v1(command)
        return await self._execute_command_v2(command)

    async def _execute_command_v1(self, command: str) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            f"{self._api_prefix}/executecommand",
            json_body={"command": command},
        )
        return self._validate_command_result(command, payload)

    async def _execute_command_v2(self, command: str) -> dict[str, Any]:
        submitted = await self._request(
            "POST",
            f"{self._api_prefix}/executecommand-async",
            json_body={"command": command},
        )
        request_id = (
            str(submitted.get("request_id") or "").strip()
            if isinstance(submitted, dict)
            else ""
        )
        if not request_id:
            raise RuntimeError(
                f"Keeper MSP service did not return a request_id for command: {command}"
            )

        deadline = asyncio.get_running_loop().time() + self._command_timeout
        last_status = "queued"

        while asyncio.get_running_loop().time() < deadline:
            status_payload = await self._request(
                "GET",
                f"{self._api_prefix}/status/{request_id}",
            )
            if isinstance(status_payload, dict):
                last_status = str(status_payload.get("status") or last_status).lower()

            if last_status == "completed":
                result = await self._request(
                    "GET",
                    f"{self._api_prefix}/result/{request_id}",
                )
                return self._validate_command_result(command, result)

            if last_status in {"failed", "expired"}:
                result = await self._request(
                    "GET",
                    f"{self._api_prefix}/result/{request_id}",
                )
                validated = self._validate_command_result(command, result, allow_error=True)
                error_message = validated.get("error") or f"request status={last_status}"
                raise RuntimeError(
                    f"Keeper MSP command failed for '{command}': {error_message}"
                )

            await asyncio.sleep(self._poll_interval)

        raise RuntimeError(
            f"Keeper MSP command timed out after {self._command_timeout}s: {command}"
        )

    @staticmethod
    def _validate_command_result(
        command: str,
        payload: Any,
        *,
        allow_error: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Keeper MSP command returned unexpected payload for '{command}': {payload!r}"
            )

        if payload.get("status") == "error":
            if allow_error:
                return payload
            raise RuntimeError(
                f"Keeper MSP command failed for '{command}': {payload.get('error') or payload}"
            )

        return payload

    @staticmethod
    def normalize_managed_company(company: dict[str, Any]) -> dict[str, str | None]:
        company_id = (
            company.get("company_id")
            or company.get("mc_enterprise_id")
            or company.get("id")
        )
        company_name = (
            company.get("company_name")
            or company.get("mc_enterprise_name")
            or company.get("name")
        )
        node = company.get("node") or company.get("node_name")
        plan = company.get("plan") or company.get("product_id")

        return {
            "id": str(company_id) if company_id is not None else None,
            "name": str(company_name) if company_name is not None else None,
            "node": str(node) if node is not None else None,
            "plan": str(plan) if plan is not None else None,
        }

    async def list_managed_companies(self, *, verbose: bool = False) -> list[dict[str, Any]]:
        command = "msp-info --format=json"
        if verbose:
            command += " --verbose"

        payload = await self._execute_command(command)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    async def get_managed_company(self, company_id: str | None = None) -> dict[str, Any]:
        resolved_company_id = str(company_id or self._company_id or "").strip()
        if not resolved_company_id:
            raise RuntimeError(
                "Keeper MSP company ID is not available. Configure an org mapping first."
            )

        command = (
            "msp-info --format=json --managed-company "
            f"{shlex.quote(resolved_company_id)}"
        )
        payload = await self._execute_command(command)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]

        raise RuntimeError(
            f"Keeper MSP managed company {resolved_company_id} was not found"
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


async def get_client(scope: str | None = None) -> KeeperMSPClient:
    """
    Build a Keeper MSP client from the configured Bifrost integration.

    For org-scoped calls, the mapped Keeper managed company ID is exposed
    through `client.company_id`.
    """
    from bifrost import integrations

    integration = await integrations.get("Keeper MSP", scope=scope)
    if not integration:
        raise RuntimeError("Integration 'Keeper MSP' not found in Bifrost")

    config = integration.config or {}
    required = ["base_url", "api_key"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Keeper MSP integration missing required config: {missing}")

    return KeeperMSPClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        api_version=config.get("api_version", "v2"),
        company_id=getattr(integration, "entity_id", None),
    )
