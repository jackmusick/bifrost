"""
GoToConnect agent tools for MTG's own phone system.

These tools are designed for use by Bifrost agents to correlate phone
activity with service desk work — matching callers to HaloPSA clients,
pulling call history for ticket context, checking tech availability,
and sending SMS to customers.
"""

from bifrost import tool
from datetime import datetime, timedelta, timezone


@tool(
    name="GoToConnect: Call History for Number",
    description="Get recent call history for a specific phone number. Useful for identifying callers and correlating calls to HaloPSA clients.",
    category="GoToConnect",
    tags=["gotoconnect", "calls", "agent"],
)
async def get_call_history_for_number(
    phone_number: str,
    days: int = 30,
) -> dict:
    """
    Get recent call history for a specific phone number.

    Useful for identifying a caller, understanding call frequency from a
    customer, or correlating a phone number to a HaloPSA client contact.

    Args:
        phone_number: The external phone number to look up (e.g. "+13175551234").
        days: How many days back to search (default 30).

    Returns:
        Dict with call records and a summary (total calls, total duration).
    """
    from modules.gotoconnect import get_client

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = await get_client()
    try:
        calls = await client.get_call_history(
            count=200,
            start_time=since,
            phone_number=phone_number,
        )
    finally:
        await client.close()

    total_duration = sum(c.get("durationSeconds", 0) for c in calls)
    return {
        "phone_number": phone_number,
        "days_searched": days,
        "total_calls": len(calls),
        "total_duration_minutes": round(total_duration / 60, 1),
        "calls": calls,
    }


@tool(
    name="GoToConnect: Tech Availability",
    description="Get presence and availability for all MTG GoToConnect users.",
    category="GoToConnect",
    tags=["gotoconnect", "presence", "agent"],
)
async def get_tech_availability() -> list[dict]:
    """
    Get presence and call queue status for all MTG GoToConnect users.

    Returns each tech's name, extension, current presence status, and
    whether they're logged into any call queues. Use this to determine
    who is available to take a call or handle an escalation.
    """
    from modules.gotoconnect import get_client

    client = await get_client()
    try:
        users = await client.list_users()
        user_keys = [u["key"] for u in users if u.get("key")]
        presence = await client.get_presence(user_keys) if user_keys else []
    finally:
        await client.close()

    presence_by_key = {p.get("userKey"): p for p in presence}

    return [
        {
            "name": u.get("firstName", "") + " " + u.get("lastName", ""),
            "email": u.get("email"),
            "user_key": u.get("key"),
            "extension": u.get("extension"),
            "presence": presence_by_key.get(u.get("key"), {}).get("status", "unknown"),
        }
        for u in users
    ]


@tool(
    name="GoToConnect: Send SMS",
    description="Send an SMS to a customer from an MTG GoToConnect number.",
    category="GoToConnect",
    tags=["gotoconnect", "sms", "messaging", "agent"],
)
async def send_sms_to_customer(
    to_number: str,
    message: str,
    from_number: str | None = None,
) -> dict:
    """
    Send an SMS message from an MTG GoToConnect number to a customer.

    Args:
        to_number: Customer's phone number (E.164 format, e.g. "+13175551234").
        message: SMS body text.
        from_number: MTG GoToConnect number to send from. If not provided,
                     the first available line is used.

    Returns:
        The sent message record from GoToConnect.
    """
    from modules.gotoconnect import get_client

    client = await get_client()
    try:
        if not from_number:
            lines = await client.list_my_lines()
            if not lines:
                raise RuntimeError("No GoToConnect lines available for sending SMS.")
            from_number = lines[0].get("phoneNumber")
            if not from_number:
                raise RuntimeError("Could not determine a sending phone number from your lines.")

        result = await client.send_sms(
            from_number=from_number,
            to_number=to_number,
            body=message,
        )
    finally:
        await client.close()

    return result


@tool(
    name="GoToConnect: Recent Missed Calls",
    description="Get recent missed inbound calls for proactive customer follow-up.",
    category="GoToConnect",
    tags=["gotoconnect", "calls", "agent"],
)
async def get_recent_missed_calls(count: int = 20) -> list[dict]:
    """
    Get recent missed inbound calls across the MTG GoToConnect account.

    Useful for identifying customers who called but didn't reach anyone,
    so agents can proactively follow up.

    Args:
        count: Number of recent calls to check (default 20).

    Returns:
        List of missed call records with caller number, time, and duration.
    """
    from modules.gotoconnect import get_client

    client = await get_client()
    try:
        calls = await client.get_call_history(count=count * 3)  # over-fetch to filter
    finally:
        await client.close()

    missed = [
        c for c in calls
        if c.get("callDirection") == "inbound"
        and (c.get("callResult") in ("missed", "abandoned") or c.get("durationSeconds", 1) == 0)
    ]

    return missed[:count]


@tool(
    name="GoToConnect: Call Activity Report",
    description="Per-tech call summary for the past N days. Useful for timesheet verification and capacity planning.",
    category="GoToConnect",
    tags=["gotoconnect", "reporting", "agent"],
)
async def get_call_activity_report(days: int = 7) -> dict:
    """
    Get a summary of call activity for all MTG techs over the past N days.

    Returns per-tech call counts and total duration, useful for capacity
    planning and timesheet verification.

    Args:
        days: Number of days to report on (default 7).
    """
    from modules.gotoconnect import get_client

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = await get_client()
    try:
        activity = await client.get_user_activity(start_time=since, end_time=until)
    finally:
        await client.close()

    return {
        "period_days": days,
        "generated_at": until,
        "techs": activity,
    }
