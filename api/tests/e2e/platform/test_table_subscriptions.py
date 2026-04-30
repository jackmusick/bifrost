"""Websocket subscription E2E for tables.

Tests the real-time push behaviour added in Tasks 7-8:
- Access-denied subscribe attempt → error ack (no subscription)
- Successful insert → document_change push
- Creator-only filter — only rows owned by the subscriber are forwarded
- Access revocation → subscription_revoked message
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

from tests.e2e.fixtures.setup import API_BASE_URL
from tests.e2e.fixtures.users import E2EUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ws_headers(user: E2EUser) -> dict:
    return {"Authorization": f"Bearer {user.access_token}"}


async def _ws_connect(ws_url: str, user: E2EUser):
    """Open a websocket connection and consume the initial 'connected' ack."""
    ws = await connect(ws_url, additional_headers=_ws_headers(user))
    # Always a 'connected' message first
    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
    connected = json.loads(raw)
    assert connected["type"] == "connected", f"Unexpected first message: {connected}"
    return ws


async def _subscribe(ws, channel: str) -> dict:
    """Send a subscribe message and return the ack."""
    await ws.send(json.dumps({"type": "subscribe", "channels": [channel]}))
    raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
    return json.loads(raw)


def _http(user: E2EUser) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_BASE_URL, headers=user.headers, timeout=30.0)


_DENY_ACCESS = {
    "everyone": {"read": False, "create": False, "update": False, "delete": False},
    "roles": [],
    "creator": {"read": False, "create": False, "update": False, "delete": False},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestTableWebsocketSubscriptions:
    """Websocket real-time subscription tests for tables."""

    async def test_subscribe_requires_read(
        self,
        e2e_ws_url: str,
        platform_admin: E2EUser,
        non_admin_user: E2EUser,
    ):
        """Subscribing to a table without read access → error ack."""
        # Create a table with no access grants (default deny)
        async with _http(platform_admin) as client:
            resp = await client.post("/api/tables", json={"name": "t_ws_deny"})
            assert resp.status_code == 201, resp.text
            table_id = resp.json()["id"]

        ws_url = f"{e2e_ws_url}/ws/connect"
        ws = await _ws_connect(ws_url, non_admin_user)
        try:
            ack = await _subscribe(ws, f"table:{table_id}")
            assert ack.get("type") == "error", (
                f"Expected error ack for denied table subscription, got: {ack}"
            )
        except ConnectionClosedError:
            # Also acceptable: server closed the connection on deny
            pass
        finally:
            await ws.close()

    async def test_receive_insert_event(
        self,
        e2e_ws_url: str,
        platform_admin: E2EUser,
        alice_user: E2EUser,
    ):
        """Subscribing then inserting a row → document_change push."""
        async with _http(platform_admin) as admin:
            resp = await admin.post("/api/tables", json={"name": "t_ws_insert"})
            assert resp.status_code == 201, resp.text
            table_id = resp.json()["id"]

            patch = await admin.patch(
                f"/api/tables/{table_id}",
                json={
                    "access": {
                        "everyone": {"read": True, "create": True, "update": False, "delete": False},
                        "roles": [],
                        "creator": {"read": False, "create": False, "update": False, "delete": False},
                    }
                },
            )
            assert patch.status_code == 200, patch.text

        ws_url = f"{e2e_ws_url}/ws/connect"
        ws = await _ws_connect(ws_url, alice_user)
        try:
            ack = await _subscribe(ws, f"table:{table_id}")
            assert ack.get("type") == "subscribed", f"Subscribe failed: {ack}"

            # Insert a row — this should trigger a push
            async with _http(alice_user) as alice:
                ins = await alice.post(
                    f"/api/tables/{table_id}/documents",
                    json={"data": {"x": 1}},
                )
                assert ins.status_code == 201, ins.text

            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["type"] == "document_change", f"Unexpected message: {data}"
            assert data["action"] == "insert", f"Unexpected action: {data}"
        finally:
            await ws.close()

    async def test_creator_filter_drops_other_users_rows(
        self,
        e2e_ws_url: str,
        platform_admin: E2EUser,
        alice_user: E2EUser,
        bob_user: E2EUser,
    ):
        """Creator-only read: bob's insert not visible to alice's ws; alice's own insert is."""
        async with _http(platform_admin) as admin:
            resp = await admin.post("/api/tables", json={"name": "t_ws_creator"})
            assert resp.status_code == 201, resp.text
            table_id = resp.json()["id"]

            patch = await admin.patch(
                f"/api/tables/{table_id}",
                json={
                    "access": {
                        "everyone": {"read": False, "create": True, "update": False, "delete": False},
                        "roles": [],
                        "creator": {"read": True, "create": True, "update": True, "delete": True},
                    }
                },
            )
            assert patch.status_code == 200, patch.text

        ws_url = f"{e2e_ws_url}/ws/connect"
        ws = await _ws_connect(ws_url, alice_user)
        try:
            ack = await _subscribe(ws, f"table:{table_id}")
            assert ack.get("type") == "subscribed", f"Subscribe failed: {ack}"

            # Bob inserts — Alice's ws should NOT see this
            async with _http(bob_user) as bob:
                ins = await bob.post(
                    f"/api/tables/{table_id}/documents",
                    json={"data": {"who": "bob"}},
                )
                assert ins.status_code == 201, ins.text

            # Alice inserts — Alice's ws SHOULD see this
            async with _http(alice_user) as alice:
                ins = await alice.post(
                    f"/api/tables/{table_id}/documents",
                    json={"data": {"who": "alice"}},
                )
                assert ins.status_code == 201, ins.text

            # The first message we receive must be alice's row
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data.get("data", {}).get("who") == "alice", (
                f"Expected alice's row, got: {data}"
            )

            # No further message should arrive (bob's row was filtered out)
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.recv(), timeout=0.5)
        finally:
            await ws.close()

    async def test_revocation_emits_subscription_revoked(
        self,
        e2e_ws_url: str,
        platform_admin: E2EUser,
        alice_user: E2EUser,
    ):
        """When admin revokes read access, alice's ws gets subscription_revoked."""
        async with _http(platform_admin) as admin:
            resp = await admin.post("/api/tables", json={"name": "t_ws_revoke"})
            assert resp.status_code == 201, resp.text
            table_id = resp.json()["id"]

            patch = await admin.patch(
                f"/api/tables/{table_id}",
                json={
                    "access": {
                        "everyone": {"read": True, "create": False, "update": False, "delete": False},
                        "roles": [],
                        "creator": {"read": False, "create": False, "update": False, "delete": False},
                    }
                },
            )
            assert patch.status_code == 200, patch.text

        ws_url = f"{e2e_ws_url}/ws/connect"
        ws = await _ws_connect(ws_url, alice_user)
        try:
            ack = await _subscribe(ws, f"table:{table_id}")
            assert ack.get("type") == "subscribed", f"Subscribe failed: {ack}"

            # Admin removes the everyone.read grant
            async with _http(platform_admin) as admin:
                patch = await admin.patch(
                    f"/api/tables/{table_id}",
                    json={
                        "access": {
                            "everyone": {"read": False, "create": False, "update": False, "delete": False},
                            "roles": [],
                            "creator": {"read": False, "create": False, "update": False, "delete": False},
                        }
                    },
                )
                assert patch.status_code == 200, patch.text

            # Alice's ws should receive subscription_revoked
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["type"] == "subscription_revoked", (
                f"Expected subscription_revoked, got: {data}"
            )
        finally:
            await ws.close()
