"""
Shared HaloPSA Notes Tools

Reusable, LLM-friendly note/action operations for any Bifrost agent.
"""

import logging
import re
from typing import Optional

import markdown

from bifrost import tool, UserError
from modules import halopsa
from modules.extensions.halopsa import clean_html, get_enriched_ticket

from shared.halopsa.tools._auth import check_ticket_access, get_caller_scope
from shared.halopsa.tools.timeentry import _resolve_caller_agent

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<(?:p|br|div|ul|ol|li|h[1-6]|strong|em|a |table|tr|td|th)[\s>/]", re.IGNORECASE)


def _to_html(text: str) -> str:
    """Convert note text to HTML. Pass through if already HTML, otherwise treat as markdown."""
    if _HTML_TAG_RE.search(text):
        return text
    return markdown.markdown(text)


async def _try_resolve_agent() -> dict | None:
    """Try to resolve the caller to a HaloPSA agent. Returns None if it can't."""
    try:
        return await _resolve_caller_agent()
    except (UserError, Exception) as e:
        logger.info(f"Could not resolve caller agent, will default to API user: {e}")
        return None


@tool(
    description=(
        "Add a note to a HaloPSA ticket. Private by default (hidden from end user). "
        "Optionally include time entry fields to log time with the note. When time "
        "fields are provided, the calling agent is auto-resolved from your login "
        "when possible so the time entry appears on your timesheet. Falls back to "
        "the API user if the caller can't be resolved."
    ),
)
async def add_note(
    ticket_id: int,
    note: str,
    is_private: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timetaken: Optional[float] = None,
    is_billable: Optional[bool] = None,
) -> dict:
    """Add a note/action to a ticket, optionally with time entry.

    Args:
        ticket_id: The ticket to add the note to.
        note: The note text content (markdown or HTML).
        is_private: If True (default), note is hidden from the end user.
        start_date: Start time ISO string for time entry, e.g. "2026-03-19T09:00:00.000Z".
        end_date: End time ISO string for time entry, e.g. "2026-03-19T09:30:00.000Z".
        timetaken: Time taken in hours (e.g. 0.5 = 30 minutes).
        is_billable: If set, controls whether this time is billable.
    """
    if not note.strip():
        raise UserError("Note text is required.")

    # Verify access
    existing = await halopsa.get_tickets(str(ticket_id))
    existing_dict = existing if isinstance(existing, dict) else dict(existing)
    await check_ticket_access(existing_dict)

    # Try to resolve caller agent. If found, attribute the action to them.
    # If not, Halo defaults to the API user.
    agent = await _try_resolve_agent()

    action_data = {
        "ticket_id": ticket_id,
        "note_html": _to_html(note.strip()),
        "outcome": "Private Note" if is_private else "Public Note",
        "hiddenfromuser": is_private,
    }

    # Halo needs both "who" (display name) and "who_agentid" (numeric ID)
    # to properly attribute an action to an agent's timesheet.
    if agent:
        action_data["who"] = agent["name"]
        action_data["who_agentid"] = agent["id"]
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
        logger.error(f"Failed to add note to ticket {ticket_id}: {e}")
        raise UserError(f"Failed to add note: {e}")

    if isinstance(result, list):
        action = result[0] if result else {}
    elif isinstance(result, dict):
        action = result
    else:
        action = {}

    action = action if isinstance(action, dict) else dict(action)

    response = {
        "ticket_id": ticket_id,
        "note_id": action.get("id"),
        "is_private": is_private,
        "added": True,
    }

    if agent:
        response["agent_id"] = agent["id"]
        response["agent_name"] = agent["name"]

    has_time = timetaken is not None or start_date is not None
    if has_time:
        response["time_logged"] = True
        response["timetaken"] = timetaken
        response["start_date"] = start_date
        response["end_date"] = end_date

    return response


@tool(description="List notes/actions on a HaloPSA ticket, newest first. Org users only see public notes.")
async def list_notes(ticket_id: int, limit: int = 10) -> dict:
    """List notes/actions on a ticket.

    Args:
        ticket_id: The ticket to list notes for.
        limit: Max notes to return (capped at 25).
    """
    limit = min(limit, 25)

    enriched = await get_enriched_ticket(ticket_id)
    await check_ticket_access(enriched.ticket)

    scope = get_caller_scope()

    notes = []
    for a in enriched.actions:
        a = a if isinstance(a, dict) else dict(a)
        is_private = a.get("hiddenfromuser", False)

        # Org users only see public notes
        if not scope["is_provider"] and is_private:
            continue

        note_html = a.get("note") or a.get("note_html", "")
        cleaned = clean_html(note_html)
        if not cleaned:
            continue

        entry = {
            "who": a.get("who", ""),
            "note": cleaned,
            "datetime": a.get("actionarrivaldate") or a.get("actionsdate", ""),
            "is_private": is_private,
        }

        # Include time info if present
        tt = a.get("timetaken")
        if tt and tt > 0:
            entry["timetaken"] = tt
            entry["start_date"] = a.get("actionarrivaldate", "")
            entry["end_date"] = a.get("actioncompletiondate", "")

        notes.append(entry)

        if len(notes) >= limit:
            break

    return {
        "ticket_id": ticket_id,
        "notes": notes,
        "count": len(notes),
        "total_actions": len(enriched.actions),
    }
