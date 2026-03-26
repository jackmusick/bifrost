"""
Shared HaloPSA Timesheet & Time Entry Tools

Tools for interacting with the HaloPSA timesheet and logging time.

Key concepts:
- Timesheet: The daily view of an agent's logged time (GET /Timesheet/0)
- QuickTime: A lightweight time entry that auto-creates and closes a ticket (POST /TimesheetEvent)
- Actions: The core primitive for notes, emails, and time entries on tickets (POST /Actions)
- Appointments: Calendar events synced from 365 into Halo (GET /Appointment)

Time in HaloPSA:
- timetaken is in HOURS (float), not minutes. e.g. 0.5 = 30 minutes
- Dates are ISO 8601 strings: "2026-03-19T15:10:00.000Z"
- The calling agent is resolved automatically from Bifrost execution context
- Halo actions need BOTH "who" (display name) and "who_agentid" (numeric ID)
  to properly attribute to an agent's timesheet
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from bifrost import tool, UserError
from modules import halopsa

from shared.halopsa.tools._auth import get_caller_scope

logger = logging.getLogger(__name__)


async def _resolve_caller_agent() -> dict:
    """Resolve the current caller to a HaloPSA agent.

    Uses the Bifrost execution context email to look up the agent.
    Fetches all agents and matches by email (client-side) because Halo's
    search param on the agents endpoint is unreliable for email lookups.

    Returns dict with 'id' and 'name'.
    Raises UserError if the caller can't be resolved.
    """
    scope = get_caller_scope()
    email = scope.get("email")
    if not email:
        raise UserError(
            "Could not determine your email from the execution context. "
            "Are you logged in?"
        )

    try:
        result = await halopsa.list_agents()
    except Exception as e:
        raise UserError(f"Failed to fetch HaloPSA agents: {e}")

    if hasattr(result, "agents"):
        agents = result.agents or []
    elif isinstance(result, dict):
        agents = result.get("agents", [])
    elif isinstance(result, list):
        agents = result
    else:
        agents = []

    email_lower = email.lower()
    for agent in agents:
        agent = agent if isinstance(agent, dict) else dict(agent)
        agent_email = (agent.get("email") or "").lower()
        if agent_email == email_lower:
            agent_id = agent.get("id")
            agent_name = agent.get("name", "")
            if not agent_id:
                raise UserError("Found a matching agent but it has no ID.")
            logger.info(f"Resolved caller {email} to agent {agent_id} ({agent_name})")
            return {"id": agent_id, "name": agent_name}

    raise UserError(
        f"Could not find a HaloPSA agent matching {email}. "
        "Make sure your Bifrost account email matches your HaloPSA agent email."
    )


def _agent_fields(agent: dict) -> dict:
    """Return the who + who_agentid fields Halo needs for proper agent attribution."""
    return {"who": agent["name"], "who_agentid": agent["id"]}


def _extract_result(result) -> dict:
    """Normalize API response to a single dict."""
    if isinstance(result, list):
        return dict(result[0]) if result else {}
    if isinstance(result, dict):
        return result
    return dict(result) if result else {}


def _format_event(event: dict) -> dict:
    """Extract compact timesheet event for display."""
    return {
        "id": event.get("id"),
        "ticket_id": event.get("ticket_id"),
        "action_number": event.get("action_number"),
        "subject": event.get("subject", ""),
        "start_date": event.get("start_date", ""),
        "end_date": event.get("end_date", ""),
        "timetaken": event.get("timetaken", 0),
        "customer": event.get("customer", ""),
        "charge_type": event.get("charge_type_name", ""),
        "note": event.get("note", ""),
        "event_type": event.get("event_type", 0),
        "break_type": event.get("break_type", 0),
    }


def _format_appointment(appt: dict) -> dict:
    """Extract compact appointment for display."""
    ticket_id = appt.get("ticket_id")
    # ticket_id of -1 means synced from 365 with no ticket linked
    if ticket_id == -1:
        ticket_id = None

    return {
        "id": appt.get("id"),
        "subject": appt.get("subject", ""),
        "start_date": appt.get("start_date", ""),
        "end_date": appt.get("end_date", ""),
        "allday": appt.get("allday", False),
        "ticket_id": ticket_id,
        "client_id": appt.get("client_id") or None,
        "client_name": appt.get("client_name", "") or None,
        "attendees": appt.get("attendees", ""),
        "appointment_type": appt.get("appointment_type_name", ""),
        "complete_status": appt.get("complete_status"),
    }


# ============================================================================
# Timesheet Tools
# ============================================================================


@tool(
    description=(
        "Get your timesheet for a specific day. Returns the full day state: "
        "logged events with ticket/customer context, target hours, actual hours, "
        "unlogged hours, and break allowance. The calling agent is resolved "
        "automatically from your login."
    ),
)
async def get_my_timesheet(
    date: str,
    utcoffset: int = 240,
) -> dict:
    """Fetch a single day's timesheet for the calling agent.

    Args:
        date: ISO date string for the day, e.g. "2026-03-19T00:00:00.000Z".
        utcoffset: UTC offset in minutes (240 = US Eastern, 300 = US Central). Defaults to 240.
    """
    agent = await _resolve_caller_agent()

    try:
        result = await halopsa.get_timesheet(
            "0",
            agent_id=agent["id"],
            date=date,
            utcoffset=utcoffset,
        )
    except Exception as e:
        logger.error(f"Failed to fetch timesheet for agent {agent['id']}: {e}")
        raise UserError(f"Failed to fetch timesheet: {e}")

    ts = result if isinstance(result, dict) else dict(result) if result else {}

    raw_events = ts.get("events", [])
    events = [_format_event(ev if isinstance(ev, dict) else dict(ev)) for ev in raw_events]

    return {
        "agent_id": ts.get("agent_id"),
        "agent_name": ts.get("agent_name", ""),
        "date": ts.get("date", ""),
        "target_hours": ts.get("target_hours", 0),
        "actual_hours": ts.get("actual_hours", 0),
        "unlogged_hours": ts.get("unlogged_hours", 0),
        "allowed_break_hours": ts.get("allowed_break_hours", 0),
        "chargeable_hours": ts.get("chargeable_hours", 0),
        "percentage": ts.get("percentage", 0),
        "events": events,
        "event_count": len(events),
    }


# ============================================================================
# Appointment / Signal Tools
# ============================================================================


@tool(
    description=(
        "Get your HaloPSA appointments for a date range. These are synced from "
        "Microsoft 365 and may already have client and ticket associations. "
        "Completed appointments (complete_status != -1) with ticket associations "
        "likely already have time logged via their outcome actions. Returns timed "
        "appointments only (not dateless tasks/reminders). The calling agent is "
        "resolved automatically."
    ),
)
async def get_appointments(
    start_date: str,
    end_date: str,
    include_allday: bool = False,
) -> dict:
    """Fetch appointments for the calling agent in a date range.

    Args:
        start_date: Range start ISO string, e.g. "2026-03-19T00:00:00.000Z".
        end_date: Range end ISO string, e.g. "2026-03-20T04:00:00.000Z".
        include_allday: If True, include all-day events (birthdays, holidays, etc.). Default False.
    """
    agent = await _resolve_caller_agent()

    try:
        result = await halopsa.list_appointments(
            agents=str(agent["id"]),
            start_date=start_date,
            end_date=end_date,
            excluderecurringmaster=True,
            excludenonticketapptodo=False,
            pageinate=True,
            page_size=100,
            page_no=1,
        )
    except Exception as e:
        logger.error(f"Failed to fetch appointments for agent {agent['id']}: {e}")
        raise UserError(f"Failed to fetch appointments: {e}")

    appts_raw = result.get("appointments", []) if isinstance(result, dict) else []
    all_appts = [a if isinstance(a, dict) else dict(a) for a in appts_raw]

    # Filter to timed events only (skip dateless tasks/reminders)
    events = []
    for a in all_appts:
        if not a.get("start_date"):
            continue
        if not include_allday and a.get("allday"):
            continue
        events.append(_format_appointment(a))

    # Sort by start_date
    events.sort(key=lambda e: e.get("start_date", ""))

    return {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "start_date": start_date,
        "end_date": end_date,
        "events": events,
        "event_count": len(events),
    }


# ============================================================================
# QuickTime
# ============================================================================


@tool(
    description=(
        "Log a QuickTime entry, break, or lunch on the timesheet. For work time, creates "
        "a lightweight time entry that auto-creates and closes a ticket behind the scenes. "
        "For breaks and lunch, logs the time as a break event (no ticket created). "
        "Use entry_type='work' (default) for quick calls, meetings, QBRs, internal work. "
        "Use entry_type='break' or entry_type='lunch' to record break time in gaps. "
        "The calling agent is resolved automatically from your login."
    ),
)
async def log_quicktime(
    start_date: str,
    end_date: str,
    note: str = "",
    entry_type: str = "work",
    subject: Optional[str] = None,
    client_id: Optional[int] = None,
    charge_rate: int = 0,
    lognewticket: bool = False,
) -> dict:
    """Create a QuickTime entry via POST /TimesheetEvent.

    Args:
        start_date: Start time ISO string, e.g. "2026-03-19T15:10:00.000Z".
        end_date: End time ISO string, e.g. "2026-03-19T15:20:00.000Z".
        note: Description of what the time was spent on (or break reason).
        entry_type: "work" (default), "break", or "lunch".
        subject: Ticket subject line. Auto-generated if not provided.
        client_id: HaloPSA client ID. Null (default) logs against the provider org.
        charge_rate: Charge rate ID. 0 = No Charge (default). Only applies to work entries.
        lognewticket: If True, creates a new visible ticket instead of a QuickTime ticket.
    """
    agent = await _resolve_caller_agent()
    agent_id_str = str(agent["id"])
    agent_name = agent["name"]

    now_str = datetime.now(timezone.utc).strftime("%-m/%-d/%Y %-I:%M %p")

    is_break = entry_type in ("break", "lunch")

    if is_break:
        break_type = "2" if entry_type == "lunch" else "1"
        default_subject = f"{'Lunch' if entry_type == 'lunch' else 'Break'} - {agent_name} - {now_str}"

        event_data = {
            "end_date": end_date,
            "start_date": start_date,
            "ticket_id": None,
            "tickettype_id": None,
            "lognewticket": False,
            "client_id": None,
            "agent_id": agent_id_str,
            "agents": [
                {
                    "id": agent_id_str,
                    "name": agent_name,
                }
            ],
            "event_type": 1,
            "break_type": break_type,
            "break_note": note,
            "subject": subject or default_subject,
        }
    else:
        default_subject = f"Quick Time - {agent_name} - {now_str}"

        event_data = {
            "end_date": end_date,
            "start_date": start_date,
            "ticket_id": None,
            "tickettype_id": None,
            "lognewticket": lognewticket,
            "client_id": client_id,
            "agent_id": agent_id_str,
            "agents": [
                {
                    "id": agent_id_str,
                    "name": agent_name,
                }
            ],
            "event_type": 0,
            "charge_rate": charge_rate,
            "note": note,
            "subject": subject or default_subject,
        }

    try:
        result = await halopsa.create_timesheet_event([event_data])
    except Exception as e:
        logger.error(f"Failed to create QuickTime entry: {e}")
        raise UserError(f"Failed to create QuickTime entry: {e}")

    entry = _extract_result(result)

    return {
        "created": True,
        "ticket_id": entry.get("ticket_id"),
        "start_date": start_date,
        "end_date": end_date,
        "note": note,
        "entry_type": entry_type,
        "subject": event_data["subject"],
        "client_id": client_id if not is_break else None,
        "agent_id": agent["id"],
        "agent_name": agent_name,
    }


# ============================================================================
# Appointment Completion
# ============================================================================


@tool(
    description=(
        "Complete a HaloPSA appointment with time taken and an optional note. "
        "This logs the time entry, marks the appointment as done (clearing it from "
        "dispatch), and creates the action on the linked ticket if one exists. "
        "Use this instead of creating separate time entries for scheduled meetings "
        "and appointments. The actual time taken can differ from the appointment "
        "duration (e.g. a 30-min meeting that ran 2 hours). "
        "The calling agent is resolved automatically."
    ),
)
async def complete_appointment(
    appointment_id: int,
    timetaken: float,
    note: str = "",
    complete_date: Optional[str] = None,
    charge_rate: int = 0,
) -> dict:
    """Complete a HaloPSA appointment and log time.

    Args:
        appointment_id: The appointment ID to complete.
        timetaken: Actual time spent in hours (e.g. 2.0 for a 2-hour meeting).
        note: Completion note (HTML supported).
        complete_date: When the work was completed (ISO string). Defaults to
            the appointment's end_date. Adjust when actual end differs from
            scheduled (e.g. meeting ran over).
        charge_rate: Charge rate ID. 0 = No Charge (default).
    """
    agent = await _resolve_caller_agent()

    # Fetch the existing appointment so we can echo back its fields
    try:
        appt = await halopsa.get_appointment(str(appointment_id))
    except Exception as e:
        raise UserError(f"Failed to fetch appointment {appointment_id}: {e}")

    appt = appt if isinstance(appt, dict) else dict(appt) if appt else {}

    if not complete_date:
        complete_date = appt.get("end_date") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000")

    note_html = f"<p>{note}</p>" if note and not note.strip().startswith("<") else (note or "")

    payload = {
        "id": appointment_id,
        "subject": appt.get("subject", ""),
        "start_date": appt.get("start_date"),
        "end_date": appt.get("end_date"),
        "allday": appt.get("allday", False),
        "is_private": appt.get("is_private", False),
        "agents": [{"id": agent["id"], "name": agent["name"], "use": "agent"}],
        "user_id": appt.get("user_id", -1),
        "ticket_id": appt.get("ticket_id", -1),
        "reminderminutes": 0,
        "agent_status": 1,
        "note_html": appt.get("note_html") or "",
        "is_task": appt.get("is_task", False),
        "appointment_type_id": appt.get("appointment_type_id", 0),
        "shift_type_id": appt.get("shift_type_id", 0),
        "followup_start_date": appt.get("start_date"),
        "followup_end_date": appt.get("end_date"),
        "followup_allday": appt.get("allday", False),
        "followup_is_private": appt.get("is_private", False),
        "followup_user_id": appt.get("user_id", -1),
        "followup_reminderminutes": 0,
        "followup_agent_status": 1,
        "followup_note_html": appt.get("note_html") or "",
        "followup_agent_id": agent["id"],
        "complete_status": "0",
        "chargerate": str(charge_rate),
        "complete_date": complete_date,
        "complete_timetaken": timetaken,
        "complete_notehtml": note_html,
        "complete_agent_id": agent["id"],
        "utcoffset": 240,
        "apfaultidremoved": appt.get("ticket_id") in (None, -1),
        "agent_id": agent["id"],
    }

    try:
        result = await halopsa.create_appointment([payload])
    except Exception as e:
        logger.error(f"Failed to complete appointment {appointment_id}: {e}")
        raise UserError(f"Failed to complete appointment: {e}")

    entry = _extract_result(result)

    return {
        "completed": True,
        "appointment_id": appointment_id,
        "timetaken": timetaken,
        "complete_date": complete_date,
        "agent_id": agent["id"],
        "agent_name": agent["name"],
    }


# ============================================================================
# Action Tools (move, email)
# ============================================================================


@tool(
    description=(
        "Delete a break or lunch entry from the timesheet. Only works on timesheet "
        "events (event_type=1), not on ticket actions. Use adjust_time_entry with "
        "timetaken=0 to remove work entries from the timesheet instead. "
        "The event ID comes from the timesheet events list."
    ),
)
async def delete_break_entry(
    event_id: int,
) -> dict:
    """Delete a break/lunch timesheet event.

    Args:
        event_id: The timesheet event ID (from get_my_timesheet results).
    """
    try:
        result = await halopsa.delete_timesheet_event(str(event_id))
    except Exception as e:
        logger.error(f"Failed to delete timesheet event {event_id}: {e}")
        raise UserError(f"Failed to delete timesheet event: {e}")

    entry = result if isinstance(result, dict) else dict(result) if result else {}

    return {
        "deleted": True,
        "event_id": event_id,
        "subject": entry.get("subject", ""),
    }


@tool(
    description=(
        "Adjust a time entry on the timesheet. Can update the duration, reposition "
        "the start/end time, or both. Set timetaken to 0 to effectively remove an "
        "entry from the timesheet without deleting the underlying action. Use this "
        "to fix overlapping entries, correct durations, round to 5-minute increments, "
        "or clean up duplicate/test entries. The calling agent is resolved automatically."
    ),
)
async def adjust_time_entry(
    action_id: int,
    ticket_id: int,
    timetaken: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Adjust a time entry's duration and/or position.

    Args:
        action_id: The action/note ID (action_number from timesheet events).
        ticket_id: The ticket the action belongs to.
        timetaken: New duration in hours (e.g. 0.5 = 30 min, 0 = remove from timesheet).
        start_date: Optional new start time ISO string. If provided, repositions the entry.
        end_date: Optional new end time ISO string.
    """
    agent = await _resolve_caller_agent()

    action_data = {
        "id": action_id,
        "ticket_id": ticket_id,
        **_agent_fields(agent),
        "timetaken": timetaken,
    }

    if start_date:
        action_data["actionarrivaldate"] = start_date
    if end_date:
        action_data["actioncompletiondate"] = end_date

    try:
        result = await halopsa.create_actions([action_data])
    except Exception as e:
        logger.error(f"Failed to adjust time entry {action_id}: {e}")
        raise UserError(f"Failed to adjust time entry: {e}")

    return {
        "adjusted": True,
        "action_id": action_id,
        "ticket_id": ticket_id,
        "timetaken": timetaken,
        "start_date": start_date,
        "end_date": end_date,
    }


@tool(
    description=(
        "Send an email from a HaloPSA ticket. Creates an action with email delivery. "
        "Optionally include time entry fields if the email represents billable work. "
        "Uses email template 11 (Ticket Update with signature) by default. "
        "The sending agent is resolved automatically from your login."
    ),
)
async def send_ticket_email(
    ticket_id: int,
    email_to: str,
    note_html: str,
    outcome: str = "Email Sent",
    email_template_id: int = 11,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timetaken: Optional[float] = None,
    is_billable: Optional[bool] = None,
) -> dict:
    """Send an email from a Halo ticket and optionally log time.

    Args:
        ticket_id: The ticket to send from.
        email_to: Recipient email address.
        note_html: Email body as HTML.
        outcome: Action outcome label. Defaults to "Email Sent".
        email_template_id: Halo email template ID. Default 11 (Ticket Update w/ signature).
        start_date: Optional start time for time entry (ISO string).
        end_date: Optional end time for time entry (ISO string).
        timetaken: Optional time taken in hours (e.g. 0.25 = 15 min).
        is_billable: If set, controls whether this time is billable.
    """
    if not note_html.strip():
        raise UserError("Email body (note_html) is required.")

    agent = await _resolve_caller_agent()

    action_data = {
        "ticket_id": ticket_id,
        "note_html": note_html,
        "outcome": outcome,
        "hiddenfromuser": False,
        "sendemail": True,
        "emailto": email_to,
        "emailtemplate_id": email_template_id,
        **_agent_fields(agent),
    }

    if start_date:
        action_data["actionarrivaldate"] = start_date
    if end_date:
        action_data["actioncompletiondate"] = end_date
    if timetaken is not None:
        action_data["timetaken"] = timetaken
    if is_billable is not None:
        action_data["actisbillable"] = is_billable

    try:
        result = await halopsa.create_actions([action_data])
    except Exception as e:
        logger.error(f"Failed to send email from ticket {ticket_id}: {e}")
        raise UserError(f"Failed to send email: {e}")

    entry = _extract_result(result)

    return {
        "sent": True,
        "ticket_id": ticket_id,
        "action_id": entry.get("id"),
        "email_to": email_to,
        "timetaken": timetaken,
    }
