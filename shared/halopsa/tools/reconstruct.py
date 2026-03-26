"""
TimeKeeper Day Reconstruction Tool

Pulls timesheet, appointments, and emails for a day, runs enrichment,
and returns a structured picture of the day for the agent to review.
"""

import logging
from typing import Optional

from bifrost import tool, UserError
from modules import halopsa

from shared.halopsa.tools.timeentry import _resolve_caller_agent
from shared.halopsa.services.signal_enrichment import (
    assess_timesheet,
    build_domain_client_map,
    classify_email,
    correlate_appointments_to_timesheet,
    group_email_threads,
    lookup_user_by_email,
    propose_day,
    INTERNAL_DOMAINS,
)

logger = logging.getLogger(__name__)

# Configure with your Bifrost platform/provider organization ID
PLATFORM_ORG_ID = ""  # e.g., "00000000-0000-0000-0000-000000000002"


@tool(
    description=(
        "Reconstruct your day by pulling timesheet, appointments, and email signals, "
        "then correlating everything to build a complete picture. Returns: timesheet "
        "assessment (coverage, anomalies), uncovered appointments that need time logged, "
        "email activity threads matched to clients, and identified gaps. "
        "Use this as the starting point for reviewing and filling in a timesheet. "
        "Only pulls email/appointment signals when the timesheet shows gaps."
    ),
)
async def reconstruct_day(
    date: str,
    end_date: Optional[str] = None,
    utcoffset: int = 240,
) -> dict:
    """Pull all signals for a day and correlate them.

    Args:
        date: The day to reconstruct, ISO string e.g. "2026-03-19T00:00:00.000Z".
        end_date: End of range. Defaults to date + 28 hours (covers late work).
        utcoffset: UTC offset in minutes. Default 240 (US Eastern).
    """
    agent = await _resolve_caller_agent()

    if not end_date:
        # Default: date + 28 hours to catch late evening work
        end_date = date.replace("T00:00:00", "T04:00:00").replace(
            date[:10], _next_day(date[:10])
        ) if "T00:00:00" in date else date

    # Step 1: Always pull the timesheet
    try:
        ts_result = await halopsa.get_timesheet(
            "0",
            agent_id=agent["id"],
            date=date,
            utcoffset=utcoffset,
        )
    except Exception as e:
        raise UserError(f"Failed to fetch timesheet: {e}")

    ts = ts_result if isinstance(ts_result, dict) else dict(ts_result) if ts_result else {}
    ts_events = [
        (ev if isinstance(ev, dict) else dict(ev))
        for ev in ts.get("events", [])
    ]

    # Assess timesheet completeness
    timesheet_data = {
        "target_hours": ts.get("target_hours", 8.0),
        "actual_hours": ts.get("actual_hours", 0),
        "unlogged_hours": ts.get("unlogged_hours", 0),
        "events": ts_events,
    }
    assessment = assess_timesheet(timesheet_data)

    result = {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "date": date,
        "assessment": assessment,
        "timesheet_events": _compact_events(ts_events),
    }

    # Step 2: If timesheet is already complete with no anomalies, skip signal pull
    if not assessment["needs_signal_investigation"] and not assessment["anomalies"]:
        result["appointments"] = None
        result["email_threads"] = None
        result["message"] = "Timesheet looks complete. No further investigation needed."

        # Still run proposal for normalization (rounding, gap detection)
        proposal = propose_day(result)
        result["proposal"] = proposal
        return result

    # Step 3: Pull appointments
    try:
        appt_result = await halopsa.list_appointments(
            agents=str(agent["id"]),
            start_date=date,
            end_date=end_date,
            excluderecurringmaster=True,
            excludenonticketapptodo=False,
            pageinate=True,
            page_size=100,
            page_no=1,
        )
    except Exception as e:
        logger.warning(f"Failed to fetch appointments: {e}")
        appt_result = {}

    appts_raw = appt_result.get("appointments", []) if isinstance(appt_result, dict) else []
    appointments = []
    for a in appts_raw:
        a = a if isinstance(a, dict) else dict(a)
        if not a.get("start_date"):
            continue
        if a.get("allday"):
            continue
        # Normalize ticket_id
        tid = a.get("ticket_id")
        if tid == -1:
            tid = None
        appointments.append({
            "id": a.get("id"),
            "subject": a.get("subject", ""),
            "start_date": a.get("start_date", ""),
            "end_date": a.get("end_date", ""),
            "ticket_id": tid,
            "client_id": a.get("client_id") or None,
            "client_name": a.get("client_name", "") or None,
            "attendees": a.get("attendees", ""),
            "appointment_type": a.get("appointment_type_name", ""),
            "complete_status": a.get("complete_status"),
        })

    # Correlate appointments against timesheet
    enriched_appts = correlate_appointments_to_timesheet(appointments, ts_events)
    uncovered = [a for a in enriched_appts if not a.get("time_covered")]
    covered = [a for a in enriched_appts if a.get("time_covered")]

    result["appointments"] = {
        "total": len(enriched_appts),
        "uncovered": _compact_appointments(uncovered),
        "covered": _compact_appointments(covered),
        "uncovered_count": len(uncovered),
    }

    # Step 4: Pull sent emails for additional signal
    email_threads = []
    try:
        from modules.microsoft import create_graph_client
        from bifrost import context as ctx

        email_addr = getattr(ctx, "email", None)
        org_id = getattr(ctx, "org_id", None) or PLATFORM_ORG_ID

        if email_addr:
            graph = await create_graph_client(org_id=org_id)
            sent_result = graph.get(
                f"/users/{email_addr}/mailFolders/sentitems/messages",
                params={
                    "$select": "id,subject,from,toRecipients,ccRecipients,sentDateTime,receivedDateTime,conversationId,hasAttachments,importance",
                    "$top": 25,
                    "$orderby": "sentDateTime desc",
                    "$filter": f"sentDateTime ge {date[:10]}T00:00:00Z and sentDateTime le {end_date[:10]}T23:59:59Z" if end_date else None,
                },
            )
            sent_emails = sent_result.get("value", [])

            # Build domain map for client matching
            domain_map = await build_domain_client_map()

            # Collect external email addresses not in the domain map for targeted lookup
            unmatched_emails = set()
            for m in sent_emails:
                for r in m.get("toRecipients", []):
                    addr = (r.get("emailAddress", {}).get("address") or "").lower()
                    if addr and "@" in addr:
                        domain = addr.split("@")[1]
                        if domain not in INTERNAL_DOMAINS and domain not in domain_map:
                            unmatched_emails.add(addr)

            # Do targeted lookups for unmatched addresses
            user_lookups = {}
            for addr in unmatched_emails:
                user = await lookup_user_by_email(addr)
                if user:
                    user_lookups[addr] = user

            # Classify and format each email
            classified = []
            for m in sent_emails:
                from_addr = m.get("from", {}).get("emailAddress", {})
                formatted = {
                    "id": m.get("id"),
                    "subject": m.get("subject", ""),
                    "from_email": from_addr.get("address", ""),
                    "to": [r.get("emailAddress", {}).get("address", "") for r in m.get("toRecipients", [])],
                    "sent": m.get("sentDateTime", ""),
                    "received": m.get("receivedDateTime", ""),
                    "conversation_id": m.get("conversationId"),
                    "has_attachments": m.get("hasAttachments", False),
                }
                classified.append(classify_email(formatted, domain_map, user_lookups))

            # Group into threads, filter noise
            email_threads = group_email_threads(classified)
    except Exception as e:
        logger.warning(f"Failed to fetch/enrich emails: {e}")

    result["email_threads"] = email_threads if email_threads else None

    # Step 5: Build the proposed plan (normalization, gap detection, actions)
    proposal = propose_day(result)
    result["proposal"] = proposal

    return result


def _next_day(date_str: str) -> str:
    """Get next day's date string from YYYY-MM-DD."""
    from datetime import datetime, timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d")


def _compact_events(events: list[dict]) -> list[dict]:
    """Slim down timesheet events for the response."""
    return [
        {
            "id": e.get("id"),
            "ticket_id": e.get("ticket_id"),
            "action_number": e.get("action_number"),
            "subject": e.get("subject", ""),
            "start_date": e.get("start_date", ""),
            "end_date": e.get("end_date", ""),
            "timetaken": e.get("timetaken", 0),
            "customer": e.get("customer", ""),
            "charge_type": e.get("charge_type_name", e.get("charge_type", "")),
            "event_type": e.get("event_type", 0),
            "break_type": e.get("break_type", 0),
        }
        for e in events
    ]


def _compact_appointments(appts: list[dict]) -> list[dict]:
    """Slim down appointments for the response."""
    return [
        {
            "id": a.get("id"),
            "subject": a.get("subject", ""),
            "start_date": a.get("start_date", ""),
            "end_date": a.get("end_date", ""),
            "ticket_id": a.get("ticket_id"),
            "client_name": a.get("client_name"),
            "attendees": a.get("attendees", ""),
            "complete_status": a.get("complete_status"),
        }
        for a in appts
    ]
