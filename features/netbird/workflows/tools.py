"""
NetBird inventory tools.

This integration is modeled as a global, account-level connection. The first
pass focuses on visibility into peers, groups, setup keys, users, and audit
events.
"""

from __future__ import annotations

from bifrost import tool


@tool(
    name="NetBird: Get Account Inventory",
    description="Summarize NetBird account inventory across peers, groups, setup keys, users, and audit events.",
    category="NetBird",
    tags=["netbird", "inventory", "vpn", "network"],
)
async def get_netbird_account_inventory() -> dict:
    """Return a high-level NetBird account inventory summary."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        peers = await client.list_peers()
        groups = await client.list_groups()
        setup_keys = await client.list_setup_keys()
        users = await client.list_users()
        audit_events = await client.list_audit_events()
    finally:
        await client.close()

    normalized_peers = [NetBirdClient.normalize_peer(peer) for peer in peers]
    normalized_groups = [NetBirdClient.normalize_group(group) for group in groups]
    normalized_setup_keys = [
        NetBirdClient.normalize_setup_key(setup_key) for setup_key in setup_keys
    ]
    normalized_users = [NetBirdClient.normalize_user(user) for user in users]
    normalized_events = [
        NetBirdClient.normalize_audit_event(event) for event in audit_events
    ]

    connected_peers = [peer for peer in normalized_peers if peer["connected"]]
    service_users = [user for user in normalized_users if user["is_service_user"]]
    blocked_users = [user for user in normalized_users if user["is_blocked"]]
    valid_setup_keys = [key for key in normalized_setup_keys if key["valid"]]

    return {
        "summary": {
            "peer_count": len(normalized_peers),
            "connected_peer_count": len(connected_peers),
            "group_count": len(normalized_groups),
            "setup_key_count": len(normalized_setup_keys),
            "valid_setup_key_count": len(valid_setup_keys),
            "user_count": len(normalized_users),
            "service_user_count": len(service_users),
            "blocked_user_count": len(blocked_users),
            "audit_event_count": len(normalized_events),
        },
        "peers": normalized_peers,
        "groups": normalized_groups,
        "setup_keys": normalized_setup_keys,
        "users": normalized_users,
        "audit_events": normalized_events,
    }


@tool(
    name="NetBird: List Peers",
    description="List NetBird peers for the connected account, optionally filtered by name or IP.",
    category="NetBird",
    tags=["netbird", "peers", "network"],
)
async def list_netbird_peers(
    name: str | None = None,
    ip: str | None = None,
) -> dict:
    """Return NetBird peers in a normalized shape."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        peers = await client.list_peers(name=name, ip=ip)
    finally:
        await client.close()

    normalized = [NetBirdClient.normalize_peer(peer) for peer in peers]
    return {
        "count": len(normalized),
        "filters": {"name": name, "ip": ip},
        "peers": normalized,
    }


@tool(
    name="NetBird: List Groups",
    description="List NetBird groups for the connected account, optionally filtered by exact group name.",
    category="NetBird",
    tags=["netbird", "groups", "network"],
)
async def list_netbird_groups(name: str | None = None) -> dict:
    """Return NetBird groups in a normalized shape."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        groups = await client.list_groups(name=name)
    finally:
        await client.close()

    normalized = [NetBirdClient.normalize_group(group) for group in groups]
    return {"count": len(normalized), "filters": {"name": name}, "groups": normalized}


@tool(
    name="NetBird: List Setup Keys",
    description="List NetBird setup keys for the connected account.",
    category="NetBird",
    tags=["netbird", "setup-keys", "network"],
)
async def list_netbird_setup_keys() -> dict:
    """Return NetBird setup keys in a normalized shape."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        setup_keys = await client.list_setup_keys()
    finally:
        await client.close()

    normalized = [
        NetBirdClient.normalize_setup_key(setup_key) for setup_key in setup_keys
    ]
    return {"count": len(normalized), "setup_keys": normalized}


@tool(
    name="NetBird: List Users",
    description="List NetBird users for the connected account, optionally filtering for service users.",
    category="NetBird",
    tags=["netbird", "users", "network"],
)
async def list_netbird_users(service_user: bool | None = None) -> dict:
    """Return NetBird users in a normalized shape."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        users = await client.list_users(service_user=service_user)
    finally:
        await client.close()

    normalized = [NetBirdClient.normalize_user(user) for user in users]
    return {
        "count": len(normalized),
        "filters": {"service_user": service_user},
        "users": normalized,
    }


@tool(
    name="NetBird: List Audit Events",
    description="List NetBird audit events for the connected account.",
    category="NetBird",
    tags=["netbird", "audit", "events", "network"],
)
async def list_netbird_audit_events() -> dict:
    """Return NetBird audit events in a normalized shape."""
    from modules.netbird import NetBirdClient, get_client

    client = await get_client()
    try:
        audit_events = await client.list_audit_events()
    finally:
        await client.close()

    normalized = [
        NetBirdClient.normalize_audit_event(event) for event in audit_events
    ]
    return {"count": len(normalized), "events": normalized}
