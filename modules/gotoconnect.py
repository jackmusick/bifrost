"""
GoToConnect API Client

Authentication: OAuth 2.0 authorization_code (global, Bifrost-managed)
Protocol: REST
Base URL: https://api.goto.com
Token URL: https://authentication.logmeininc.com/oauth/token

MTG uses GoToConnect as its own phone system. This is a single global
integration — one OAuth connection covers the entire MTG account. There is
no per-customer org mapping.

Useful for agent tools:
  - Match inbound caller numbers to HaloPSA clients/contacts
  - Pull call history for ticket context
  - Check tech availability via presence
  - Send SMS to customers from MTG's lines
  - Generate call activity reports

Usage:
    from modules.gotoconnect import get_client

    async def my_tool():
        client = await get_client()
        me = await client.get_me()            # MTG's accountKey + setup
        users = await client.list_users()     # MTG's GoToConnect users (techs)
        history = await client.get_call_history(count=50)
        await client.close()

Docs: https://developer.goto.com/GoToConnect
Postman collection: agents/integrations/gotoconnect/GoToConnect.postman_collection.json
"""

from __future__ import annotations

from typing import Any

import httpx


class GoToConnectClient:
    """
    Async REST client for the GoToConnect API.

    The Bearer token is provided by Bifrost's OAuth integration and refreshed
    automatically by the platform. If a 401 is returned mid-workflow, the
    Bifrost platform handles re-authorization.
    """

    BASE_URL = "https://api.goto.com"

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._http

    async def _get(self, path: str, **params: Any) -> Any:
        http = await self._get_http()
        resp = await http.get(path, params={k: v for k, v in params.items() if v is not None})
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict | None = None) -> Any:
        http = await self._get_http()
        resp = await http.post(path, json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _patch(self, path: str, body: dict) -> Any:
        http = await self._get_http()
        resp = await http.patch(path, json=body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    async def _delete(self, path: str, **params: Any) -> None:
        http = await self._get_http()
        resp = await http.delete(path, params=params or None)
        resp.raise_for_status()

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # -------------------------------------------------------------------------
    # Account identity
    # -------------------------------------------------------------------------

    async def get_me(self) -> dict:
        """
        Get GoToConnect setup for the authenticated account.
        Returns accountKey plus line/extension assignments.
        """
        return await self._get("/users/v1/me")

    # -------------------------------------------------------------------------
    # Users (MTG techs)
    # -------------------------------------------------------------------------

    async def list_users(self) -> list[dict]:
        """List all GoToConnect users in the MTG account."""
        data = await self._get("/users/v1/users")
        return data if isinstance(data, list) else data.get("users", data.get("items", []))

    async def list_lines(self, user_key: str) -> list[dict]:
        """List phone lines assigned to a specific user."""
        data = await self._get(f"/users/v1/users/{user_key}/lines")
        return data if isinstance(data, list) else data.get("lines", data.get("items", []))

    async def list_my_lines(self) -> list[dict]:
        """List the lines of the authenticated user."""
        data = await self._get("/users/v1/lines")
        return data if isinstance(data, list) else data.get("lines", data.get("items", []))

    # -------------------------------------------------------------------------
    # Voice admin — extensions, numbers, devices, queues
    # -------------------------------------------------------------------------

    async def list_extensions(self) -> list[dict]:
        """List all extensions in the MTG GoToConnect account."""
        data = await self._get("/voice-admin/v1/extensions")
        return data if isinstance(data, list) else data.get("extensions", data.get("items", []))

    async def list_phone_numbers(self) -> list[dict]:
        """List all phone numbers provisioned on the account."""
        data = await self._get("/voice-admin/v1/phone-numbers")
        return data if isinstance(data, list) else data.get("phoneNumbers", data.get("items", []))

    async def list_devices(self) -> list[dict]:
        """List all provisioned desk phones and devices."""
        data = await self._get("/voice-admin/v1/devices")
        return data if isinstance(data, list) else data.get("devices", data.get("items", []))

    async def list_locations(self) -> list[dict]:
        """List office locations on the account."""
        data = await self._get("/voice-admin/v1/locations")
        return data if isinstance(data, list) else data.get("locations", data.get("items", []))

    async def list_call_queues(self) -> list[dict]:
        """List call queues (e.g. support queue, sales queue)."""
        data = await self._get("/voice-admin/v1/call-queues")
        return data if isinstance(data, list) else data.get("callQueues", data.get("items", []))

    async def get_call_queue_users(self, call_queue_id: str) -> list[dict]:
        """List users currently logged into a call queue."""
        data = await self._get(f"/voice-admin/v1/call-queues/{call_queue_id}/users")
        return data if isinstance(data, list) else data.get("users", data.get("items", []))

    # -------------------------------------------------------------------------
    # Call history — most useful for agent context
    # -------------------------------------------------------------------------

    async def get_call_history(
        self,
        count: int = 100,
        start_time: str | None = None,
        end_time: str | None = None,
        user_key: str | None = None,
        phone_number: str | None = None,
    ) -> list[dict]:
        """
        Get call history records.

        Args:
            count: Max records to return.
            start_time: ISO 8601 start (e.g. "2026-03-01T00:00:00Z").
            end_time: ISO 8601 end.
            user_key: Filter to a specific tech's calls.
            phone_number: Filter to calls involving a specific number.
                          Useful for looking up a customer's call history.
        """
        data = await self._get(
            "/call-history/v1/calls",
            count=count,
            startTime=start_time,
            endTime=end_time,
            userKey=user_key,
            phoneNumber=phone_number,
        )
        return data if isinstance(data, list) else data.get("calls", data.get("items", []))

    # -------------------------------------------------------------------------
    # Call reports
    # -------------------------------------------------------------------------

    async def get_user_activity(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """Get per-tech call activity summary (calls made, received, duration)."""
        data = await self._get(
            "/call-reports/v1/reports/user-activity",
            startTime=start_time,
            endTime=end_time,
        )
        return data if isinstance(data, list) else data.get("items", [])

    async def get_phone_number_activity(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """Get per-number call activity summary."""
        data = await self._get(
            "/call-reports/v1/reports/phone-number-activity",
            startTime=start_time,
            endTime=end_time,
        )
        return data if isinstance(data, list) else data.get("items", [])

    async def get_caller_activity(
        self,
        caller_number: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """
        Get activity for external callers.
        With caller_number, returns call history for a specific customer number.
        """
        path = "/call-reports/v1/reports/caller-activity"
        if caller_number:
            path += f"/{caller_number}"
        data = await self._get(path, startTime=start_time, endTime=end_time)
        return data if isinstance(data, list) else data.get("items", [])

    # -------------------------------------------------------------------------
    # Presence — is a tech available?
    # -------------------------------------------------------------------------

    async def get_presence(self, user_keys: list[str]) -> list[dict]:
        """
        Get presence status for a list of users.
        Useful for checking if a tech is on a call before routing.
        """
        data = await self._get("/presence/v1/presence", userKeys=",".join(user_keys))
        return data if isinstance(data, list) else data.get("presence", data.get("items", []))

    async def get_my_presence(self) -> dict:
        """Get presence fields for the authenticated user."""
        return await self._get("/presence/v1/user-presence")

    # -------------------------------------------------------------------------
    # Messaging (SMS)
    # -------------------------------------------------------------------------

    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        body: str,
    ) -> dict:
        """Send an SMS from an MTG GoToConnect number to a customer."""
        return await self._post("/messaging/v1/messages", {
            "fromPhoneNumber": from_number,
            "toPhoneNumber": to_number,
            "body": body,
        })

    async def list_messages(
        self,
        phone_number: str | None = None,
        count: int = 50,
    ) -> list[dict]:
        """List SMS messages, optionally filtered by phone number."""
        data = await self._get(
            "/messaging/v1/messages",
            phoneNumber=phone_number,
            count=count,
        )
        return data if isinstance(data, list) else data.get("messages", data.get("items", []))

    async def list_conversations(self) -> list[dict]:
        """List SMS conversation threads."""
        data = await self._get("/messaging/v1/conversations")
        return data if isinstance(data, list) else data.get("conversations", data.get("items", []))

    # -------------------------------------------------------------------------
    # Voicemail
    # -------------------------------------------------------------------------

    async def list_voicemail_boxes(self) -> list[dict]:
        """List voicemail boxes on the account."""
        data = await self._get("/voicemail/v1/voicemailboxes")
        return data if isinstance(data, list) else data.get("voicemailBoxes", data.get("items", []))

    async def list_voicemails(self, voicemailbox_id: str, count: int = 50) -> list[dict]:
        """List voicemails in a voicemailbox."""
        data = await self._get(
            f"/voicemail/v1/voicemailboxes/{voicemailbox_id}/voicemails",
            count=count,
        )
        return data if isinstance(data, list) else data.get("voicemails", data.get("items", []))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

async def get_client() -> GoToConnectClient:
    """
    Get a GoToConnectClient using the Bifrost-managed OAuth token.

    GoToConnect is a global (non-per-org) integration for MTG's own phone
    system. No org_id is needed.
    """
    from bifrost import integrations

    integration = await integrations.get("GoToConnect")
    if not integration:
        raise RuntimeError(
            "Integration 'GoToConnect' not found in Bifrost. "
            "Complete the OAuth flow in Bifrost settings first."
        )

    token = getattr(integration.oauth, "access_token", None)
    if not token:
        raise RuntimeError(
            "GoToConnect OAuth token is missing or expired. "
            "Re-authorize the GoToConnect integration in Bifrost."
        )

    return GoToConnectClient(access_token=token)
