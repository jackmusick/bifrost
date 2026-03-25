"""
Shared HaloPSA Ticket Tools

Reusable, LLM-friendly ticket operations for any Bifrost agent.
All tools enforce authorization — org users can only access their own tickets.
"""

import logging
from typing import Optional

from bifrost import tool, UserError
from modules import halopsa
from modules.extensions.halopsa import (
    clean_html,
    close_ticket_impl,
    create_ticket as ext_create_ticket,
    get_enriched_ticket,
    resolve_client_id,
)

from shared.halopsa.tools._auth import check_ticket_access, get_caller_scope

logger = logging.getLogger(__name__)


def _summarize_ticket(t: dict) -> dict:
    """Extract compact ticket summary for list responses."""
    t = t if isinstance(t, dict) else dict(t)
    return {
        "id": t.get("id"),
        "summary": t.get("summary", ""),
        "status": t.get("status_name", ""),
        "priority": t.get("priority_name", ""),
        "requester": t.get("user_name", ""),
        "agent": t.get("agent_name", ""),
        "team": t.get("team", ""),
        "client": t.get("client_name", ""),
        "date": t.get("dateoccurred", ""),
    }


def _format_action(a: dict) -> dict:
    """Extract compact action/note summary."""
    a = a if isinstance(a, dict) else dict(a)
    note_html = a.get("note") or a.get("note_html", "")
    return {
        "who": a.get("who", ""),
        "note": clean_html(note_html),
        "datetime": a.get("actionarrivaldate") or a.get("actionsdate", ""),
        "outcome": a.get("outcome", ""),
        "is_private": a.get("hiddenfromuser", False),
    }


@tool(description="Get a HaloPSA ticket by ID with full details, recent notes, and metadata.")
async def get_ticket(ticket_id: int) -> dict:
    """Fetch a single ticket with enriched details and recent actions.

    Returns curated fields: id, summary, details, status, priority, requester,
    agent, team, type, dates, and the most recent actions/notes.
    """
    enriched = await get_enriched_ticket(ticket_id)
    ticket = enriched.ticket

    await check_ticket_access(ticket)

    # Build recent actions (last 10, newest first)
    scope = get_caller_scope()
    actions = []
    for a in enriched.actions[:10]:
        formatted = _format_action(a)
        # Org users only see public notes
        if not scope["is_provider"] and formatted["is_private"]:
            continue
        actions.append(formatted)

    return {
        "id": ticket.get("id"),
        "summary": ticket.get("summary", ""),
        "details": clean_html(ticket.get("details", "") or ticket.get("details_html", "") or ""),
        "status": ticket.get("status_name", ""),
        "status_id": ticket.get("status_id"),
        "priority": ticket.get("priority_name", ""),
        "priority_id": ticket.get("priority_id"),
        "requester": ticket.get("user_name", ""),
        "requester_email": ticket.get("user_emailaddress", ""),
        "agent": ticket.get("agent_name", ""),
        "team": ticket.get("team", ""),
        "client": ticket.get("client_name", ""),
        "type": ticket.get("tickettype_name", ""),
        "date_opened": ticket.get("dateoccurred", ""),
        "date_closed": ticket.get("dateclosed", ""),
        "actions": actions,
    }


@tool(description="List HaloPSA tickets with filtering, search, and pagination. Org users only see their own tickets.")
async def list_tickets(
    search: str = "",
    status: str = "open",
    page: int = 1,
    page_size: int = 10,
    client_name: Optional[str] = None,
) -> dict:
    """List tickets sorted by most recent first.

    Args:
        search: Free-text search across ticket fields.
        status: "open" (default), "closed", or "all".
        page: Page number (1-based).
        page_size: Results per page (max 25).
        client_name: Filter by client name (provider users only).
    """
    page_size = min(page_size, 25)
    scope = get_caller_scope()

    params: dict = {
        "pageinate": True,
        "page_size": page_size,
        "page_no": page,
        "order": "dateoccurred",
        "orderdesc": True,
    }

    if search:
        params["search"] = search

    if status == "open":
        params["open_only"] = True
    elif status == "closed":
        params["open_only"] = False

    # Org user: scope to their client
    if not scope["is_provider"]:
        client_id = await resolve_client_id(scope["org_id"])
        params["client_id"] = client_id
    elif client_name:
        # Provider filtering by client name — search for the client first
        params["search"] = f"{client_name} {search}".strip() if search else client_name

    result = await halopsa.list_tickets(**params)

    tickets_raw = (
        result.get("tickets", []) if isinstance(result, dict)
        else getattr(result, "tickets", []) or []
    )
    record_count = (
        result.get("record_count", 0) if isinstance(result, dict)
        else getattr(result, "record_count", 0)
    )

    # Org user: filter to only their tickets by email
    if not scope["is_provider"] and scope["email"]:
        caller_email = scope["email"].lower()
        filtered = []
        for t in tickets_raw:
            t_dict = t if isinstance(t, dict) else dict(t)
            ticket_email = (t_dict.get("user_emailaddress") or t_dict.get("useremail") or "").lower()
            if ticket_email == caller_email:
                filtered.append(t_dict)
        tickets_raw = filtered
        record_count = len(filtered)

    tickets = [_summarize_ticket(t) for t in tickets_raw]

    return {
        "tickets": tickets,
        "total": record_count,
        "page": page,
        "page_size": page_size,
    }


@tool(description="Create a new HaloPSA ticket. Org users' client and requester are set automatically.")
async def create_ticket(
    summary: str,
    details: str = "",
    priority: str = "normal",
    client_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> dict:
    """Create a ticket in HaloPSA.

    Args:
        summary: Ticket subject/title (required).
        details: Ticket body/description.
        priority: Not currently mapped to priority_id — included for future use.
        client_id: HaloPSA client ID (required for provider users, auto-set for org users).
        user_email: Requester email (auto-set for org users).
    """
    if not summary.strip():
        raise UserError("Ticket summary is required.")

    scope = get_caller_scope()

    if not scope["is_provider"]:
        # Org user: auto-set client and requester
        resolved_client_id = await resolve_client_id(scope["org_id"])
        resolved_email = scope["email"]
    else:
        # Provider user: must supply client_id
        if not client_id:
            raise UserError("client_id is required for provider users.")
        resolved_client_id = client_id
        resolved_email = user_email

    ticket = await ext_create_ticket(
        summary=summary.strip(),
        client_id=resolved_client_id,
        user_email=resolved_email or None,
        initial_note=details.strip() if details.strip() else None,
    )

    return {
        "id": ticket.get("id"),
        "summary": ticket.get("summary", summary),
        "status": ticket.get("status_name", "New"),
        "is_new": ticket.get("is_new", True),
    }


@tool(description=(
    "Update fields on an existing HaloPSA ticket. Pass fields as a dict "
    "where keys match the api_field values from get_ticket_type_fields "
    "(e.g. summary, impact, urgency, category_2, category_4, team_id, "
    "agent_id, tickettype_id). Only provided fields are changed."
))
async def update_ticket(
    ticket_id: int,
    fields: dict,
) -> dict:
    """Update one or more fields on a ticket.

    Args:
        ticket_id: HaloPSA ticket ID to update.
        fields: Dict of api_field names to values. Keys should match the
            api_field values from get_ticket_type_fields. Examples:
            - {"summary": "New summary", "impact": 3, "urgency": 2}
            - {"tickettype_id": 1, "category_2": 18}
            - {"team_id": 5, "agent_id": 12}

    Checks access before updating. Only provided fields are changed.
    Do NOT set priority_id — HaloPSA calculates priority from impact
    and urgency automatically.
    """
    if not fields:
        raise UserError("No fields to update. Provide at least one field to change.")

    # Fetch ticket to verify access
    existing = await halopsa.get_tickets(str(ticket_id))
    existing_dict = existing if isinstance(existing, dict) else dict(existing)
    await check_ticket_access(existing_dict)

    # Build update payload from fields dict
    # Category fields need special handling: when passing a numeric ID,
    # HaloPSA expects categoryid_X instead of category_X
    payload: dict = {"id": ticket_id}
    for key, value in fields.items():
        if key.startswith("category_") and isinstance(value, (int, float)):
            # category_1 with int → categoryid_1
            payload[key.replace("category_", "categoryid_")] = int(value)
        else:
            payload[key] = value

    result = await halopsa.create_tickets([payload])

    if isinstance(result, list):
        updated = result[0] if result else {}
    elif isinstance(result, dict):
        updated = result
    else:
        updated = {}

    updated = updated if isinstance(updated, dict) else dict(updated)

    return {
        "id": updated.get("id", ticket_id),
        "summary": updated.get("summary", ""),
        "status": updated.get("status_name", ""),
        "priority": updated.get("priority_name", ""),
        "agent": updated.get("agent_name", ""),
        "team": updated.get("team", ""),
        "updated": True,
    }


@tool(description="Close a HaloPSA ticket with an optional resolution note.")
async def close_ticket(ticket_id: int, resolution_note: str = "") -> dict:
    """Close a ticket. Checks access first.

    Args:
        ticket_id: The ticket to close.
        resolution_note: Optional text explaining the resolution.
    """
    # Verify access
    existing = await halopsa.get_tickets(str(ticket_id))
    existing_dict = existing if isinstance(existing, dict) else dict(existing)
    await check_ticket_access(existing_dict)

    await close_ticket_impl(ticket_id, resolution_note=resolution_note or None)

    return {
        "id": ticket_id,
        "closed": True,
        "resolution_note": resolution_note or None,
    }
