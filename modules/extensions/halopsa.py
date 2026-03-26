"""
HaloPSA Extension Helpers

Extension functions for the auto-generated HaloPSA SDK module.
Provides pagination, enriched ticket fetching, batch operations,
and standard automation patterns (ticket creation with idempotency, notes, etc.).
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, AsyncIterator, Literal, Any

import asyncio
from collections.abc import Awaitable, Callable

from bifrost import tables, executions, config, context, integrations, UserError
from modules import halopsa

if TYPE_CHECKING:
    from features.ai_ticketing.models import EnrichedTicket, TicketMetadata

logger = logging.getLogger(__name__)

# Table for storing match_id -> ticket_id mappings (idempotency)
MATCH_TABLE = "automation_ticket_matches"

# =============================================================================
# Reference Data Cache (module-level TTL cache)
# =============================================================================

_REF_CACHE_TTL = 600  # 10 minutes
_ref_cache: dict[str, tuple[float, Any]] = {}


def _get_ai_ticket_models() -> tuple[type["EnrichedTicket"], type["TicketMetadata"]]:
    """Import AI ticketing models lazily for workflows that actually need them."""
    from features.ai_ticketing.models import EnrichedTicket, TicketMetadata

    return EnrichedTicket, TicketMetadata


def _get_cached(key: str) -> Any | None:
    """Return cached value if present and not expired, else None."""
    entry = _ref_cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _REF_CACHE_TTL:
        del _ref_cache[key]
        return None
    return value


def _set_cached(key: str, value: Any) -> None:
    """Store a value in the cache with the current timestamp."""
    _ref_cache[key] = (time.monotonic(), value)


async def resolve_client_id(org_id: str) -> int:
    """Resolve a Bifrost org_id to a HaloPSA client_id via integration mapping.

    Raises UserError if no HaloPSA integration mapping is configured for the org.
    Result is cached for _REF_CACHE_TTL seconds since mappings change rarely.
    """
    cache_key = f"client_id:{org_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    integration = await integrations.get("HaloPSA", scope=org_id)
    if not integration or not integration.entity_id:
        raise UserError(
            "No HaloPSA client linked to this organization. "
            "Please configure the HaloPSA integration mapping first."
        )

    client_id = int(integration.entity_id)
    _set_cached(cache_key, client_id)
    return client_id


# =============================================================================
# Automation Helpers (Ticket Creation, Notes, etc.)
# =============================================================================


def normalize_halo_result(obj: Any) -> dict:
    """Normalize a HaloPSA DotDict result to a plain dict.

    The HaloPSA API returns DotDict objects which don't support .get().
    Use this instead of the repeated `x if isinstance(x, dict) else dict(x)` pattern.
    """
    return obj if isinstance(obj, dict) else dict(obj)


def normalize_halo_list(items: list | None) -> list[dict]:
    """Normalize a list of HaloPSA DotDict results to plain dicts."""
    return [i if isinstance(i, dict) else dict(i) for i in (items or [])]


def _build_execution_link() -> str:
    """Build the execution link URL for notes."""
    public_url = getattr(context, "public_url", None) or ""
    return f"{public_url}/history/{context.execution_id}"


def _build_note_html(
    note: str | None = None,
    automation_log: list[str] | None = None,
    error_log: list[str] | None = None,
    is_complete: bool = False,
) -> str:
    """
    Build HTML for a ticket note with standard formatting.

    Includes:
    - Note text (if provided)
    - Automation log (if provided)
    - Error log (if provided)
    - Execution link footer
    """
    parts = []

    if note:
        parts.append(f"<p>{note}</p>")

    if automation_log:
        items = "".join(f"<li>{item}</li>" for item in automation_log)
        parts.append(f"<br><h3>Automation Log</h3><ul>{items}</ul>")

    if error_log:
        items = "".join(f"<li>{item}</li>" for item in error_log)
        parts.append(f"<br><h3>Error Log</h3><ul>{items}</ul>")

    # Always add execution link footer
    execution_link = _build_execution_link()
    parts.append(f'<br><a href="{execution_link}">Workflow Status</a>')

    return "".join(parts)


def _build_initial_note_html(
    workflow_name: str,
    executed_by: str,
    context_details: dict[str, Any] | None = None,
) -> str:
    """
    Build HTML for the initial ticket note.

    Includes:
    - Who started the workflow
    - Workflow name
    - Context details (key/value pairs)
    - Execution link footer
    """
    parts = []

    parts.append(f"<p>This workflow was started by {executed_by}.<br>")
    parts.append(f"The <b>{workflow_name}</b> workflow has started.</p>")

    if context_details:
        parts.append("<br><p><u>Context Details</u></p><br>")
        details_lines = []
        for key, value in context_details.items():
            if value is not None and not isinstance(value, (dict, list)):
                details_lines.append(f"<b>{key}</b>: {value}")
        if details_lines:
            parts.append("<p>" + "<br>".join(details_lines) + "</p>")

    # Always add execution link footer
    execution_link = _build_execution_link()
    parts.append(f'<br><a href="{execution_link}">Workflow Status</a>')

    return "".join(parts)


async def _find_agent_by_email(email: str) -> dict | None:
    """Find a HaloPSA agent by email address.

    Fetches all agents and matches client-side because Halo's search
    param on the agents endpoint is unreliable for email lookups.
    """
    try:
        result = await halopsa.list_agents()
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
            agent = normalize_halo_result(agent)
            agent_email = (agent.get("email") or "").lower()
            if agent_email == email_lower:
                logger.info(f"Matched agent by email: {agent.get('id')} - {agent.get('name')}")
                return agent
    except Exception as e:
        logger.warning(f"Failed to find agent by email: {e}")
    return None


async def find_user_by_email(
    email: str,
    client_id: int | None = None,
    includeinactive: bool = False,
) -> dict | None:
    """Find a HaloPSA user by email address, optionally scoped to a client.

    Args:
        email: Email address to search for.
        client_id: Optional HaloPSA client ID to narrow the search.
        includeinactive: If True, also search inactive users.
    """
    try:
        params: dict = {"search": email}
        if client_id is not None:
            params["client_id"] = client_id
        if includeinactive:
            params["includeinactive"] = True
        result = await halopsa.list_users(**params)
        logger.info(f"list_users({params}) returned type={type(result)}")
        users = result.get("users", []) if isinstance(result, dict) else []
        logger.info(f"Found {len(users)} users matching '{email}' (client_id={client_id})")
        for user in users:
            user_email = user.get("emailaddress", "")
            logger.info(f"  User: {user.get('name')} - emailaddress={user_email}")
            if user_email.lower() == email.lower():
                logger.info(f"Matched user: {user.get('id')} - {user.get('name')}")
                return user
    except Exception as e:
        logger.warning(f"Failed to find user by email: {e}")
    return None


async def create_ticket(
    summary: str,
    client_id: int,
    *,
    site_id: int | None = None,
    asset_id: int | None = None,
    user_email: str | None = None,
    ticket_type_id: int | None = None,
    team: str | None = None,
    template_id: int | None = None,
    related_ticket_id: int | None = None,
    match_id: str | None = None,
    initial_note: str | None = None,
    context_details: dict[str, Any] | None = None,
) -> dict:
    """
    Create a HaloPSA ticket with standard automation patterns.

    Features:
    - Idempotency via match_id (reuses existing open ticket)
    - Auto-matches user_email to HaloPSA user/agent
    - Adds initial note with workflow context
    - Execution link in all notes

    Args:
        summary: Ticket summary/title
        client_id: HaloPSA client ID
        site_id: Optional site ID
        asset_id: Optional asset/CI ID to link to the ticket
        user_email: Email to match to HaloPSA user (also checks if they're an agent)
        ticket_type_id: Ticket type ID (falls back to config 'psa_default_ticket_type')
        team: Team name to assign
        template_id: Ticket template ID
        related_ticket_id: Link to related ticket
        match_id: Unique ID for idempotency (reuses existing open ticket if found)
        initial_note: Custom text for initial note
        context_details: Key/value pairs to include in initial note

    Returns:
        Created or existing ticket dict with 'id', 'is_new' flag
    """
    # Match user/agent by email
    # User lookup is scoped to the target client_id so that provider/MSP
    # users (who belong to a different HaloPSA client) don't accidentally
    # override the ticket's client. If the submitter isn't a user under
    # the target client, only agent matching applies.
    matching_user = None
    matching_agent = None
    if user_email:
        matching_agent = await _find_agent_by_email(user_email)
        matching_user = await find_user_by_email(user_email, client_id=client_id)

    # Check for existing ticket via match_id
    ticket_id = None

    if match_id:
        try:
            existing = await tables.get(MATCH_TABLE, match_id)
            if existing and existing.data.get("ticket_id"):
                existing_ticket_id = existing.data["ticket_id"]
                # Verify ticket is still open
                try:
                    ticket = await halopsa.get_tickets(str(existing_ticket_id))
                    if ticket and not ticket.get("hasbeenclosed", False):
                        logger.info(f"Reusing existing ticket {existing_ticket_id} for match_id {match_id}")
                        # Still add initial note if requested (matches Rewst behavior)
                        if initial_note or context_details:
                            note_html = _build_initial_note_html(
                                workflow_name=context.workflow_name,
                                executed_by=context.name,
                                context_details=context_details,
                            )
                            if initial_note:
                                note_html = f"<p>{initial_note}</p>" + note_html
                            try:
                                await halopsa.create_actions([{
                                    "ticket_id": existing_ticket_id,
                                    "note_html": note_html,
                                    "outcome": "Workflow Progress",
                                    "hiddenfromuser": True,
                                }])
                            except Exception as e:
                                logger.warning(f"Failed to add note to existing ticket {existing_ticket_id}: {e}")
                        return {"id": existing_ticket_id, "is_new": False, **ticket}
                    else:
                        logger.info(f"Existing ticket {existing_ticket_id} is closed, creating new")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"No existing match found for {match_id}: {e}")

    # Get default ticket type from config if not provided
    if not ticket_type_id:
        ticket_type_id = await config.get("psa_default_ticket_type")

    # Build ticket payload
    ticket_data = {
        "summary": summary,
        "client_id": client_id,
    }

    if site_id:
        ticket_data["site_id"] = site_id
    if asset_id:
        ticket_data["asset_id"] = asset_id
    if ticket_type_id:
        ticket_data["tickettype_id"] = ticket_type_id
    if template_id:
        ticket_data["template_id"] = template_id
    if related_ticket_id:
        ticket_data["createdfrom_id"] = related_ticket_id
    if matching_user:
        ticket_data["user_id"] = matching_user.get("id")
    if matching_agent:
        ticket_data["agent_id"] = matching_agent.get("id")
        ticket_data["_forcereassign"] = True
        ticket_data["_agent01_ok"] = True
        ticket_data["_agent02_ok"] = True
        if not team:
            team = matching_agent.get("team")
    if team:
        ticket_data["team"] = team

    # Create the ticket
    logger.info(f"Creating ticket with data: {ticket_data}")
    try:
        result = await halopsa.create_tickets([ticket_data])
    except Exception as e:
        logger.error(f"HaloPSA create_tickets failed: {e}")
        raise UserError(f"Failed to create HaloPSA ticket: {e}")

    # Handle both list and dict responses
    if isinstance(result, list):
        if len(result) == 0:
            raise UserError("Failed to create HaloPSA ticket - empty response")
        ticket = result[0]
    elif isinstance(result, dict):
        ticket = result
    else:
        raise UserError(f"Failed to create HaloPSA ticket - unexpected response type: {type(result)}")

    ticket_id = ticket.get("id")

    if not ticket_id:
        raise UserError("HaloPSA ticket created but no ID returned")

    logger.info(f"Created HaloPSA ticket {ticket_id}")

    # Store match_id -> ticket_id mapping
    if match_id:
        try:
            await tables.upsert(
                MATCH_TABLE,
                match_id,
                {"ticket_id": ticket_id, "summary": summary},
            )
        except Exception as e:
            logger.warning(f"Failed to store match_id mapping: {e}")

    # Add initial note if requested
    if initial_note or context_details:
        note_html = _build_initial_note_html(
            workflow_name=context.workflow_name,
            executed_by=context.name,
            context_details=context_details,
        )
        if initial_note:
            note_html = f"<p>{initial_note}</p>" + note_html

        try:
            await halopsa.create_actions([{
                "ticket_id": ticket_id,
                "note_html": note_html,
                "outcome": "Started Workflow",
                "hiddenfromuser": True,
            }])
        except Exception as e:
            logger.warning(f"Failed to add initial note to ticket {ticket_id}: {e}")

    return {"id": ticket_id, "is_new": True, **ticket}


async def create_note(
    ticket_id: int,
    note: str | None = None,
    *,
    note_type: Literal["private", "public"] = "private",
    is_complete: bool = False,
    automation_log: list[str] | None = None,
    error_log: list[str] | None = None,
    close_ticket: bool = False,
    send_email: bool = False,
    email_template_id: int = 11,
) -> dict:
    """
    Add a note to a HaloPSA ticket.

    Features:
    - Formats automation/error logs as HTML lists
    - Includes execution link footer
    - Can close ticket in same operation
    - Can send email to the ticket's user via HaloPSA template

    Args:
        ticket_id: HaloPSA ticket ID
        note: Note text content
        note_type: "private" (hidden from user) or "public" (visible)
        is_complete: If True, marks outcome as "Workflow Complete"
        automation_log: Automation log entries
        error_log: Error log entries
        close_ticket: Close the ticket after adding note
        send_email: Send an email to the ticket's user via HaloPSA
        email_template_id: HaloPSA email template ID (default 11 = standard,
            -145 = denial, -160 = completion)

    Returns:
        Created action/note dict
    """
    # Build note HTML
    note_html = _build_note_html(
        note=note,
        automation_log=automation_log,
        error_log=error_log,
        is_complete=is_complete,
    )

    # Determine outcome
    if is_complete:
        outcome = "Workflow Complete"
    else:
        outcome = "Workflow Progress"

    # Build action payload
    action_data = {
        "ticket_id": ticket_id,
        "note_html": note_html,
        "outcome": outcome if note_type == "private" else "Public Note",
        "hiddenfromuser": note_type == "private",
    }

    action_data["who"] = f"🤖 Bifrost ({context.name})"

    # Create the note
    try:
        result = await halopsa.create_actions([action_data])
    except Exception as e:
        logger.error(f"HaloPSA create_actions failed: {e}")
        raise UserError(f"Failed to create HaloPSA note: {e}")

    # Handle both list and dict responses
    if isinstance(result, list):
        action = result[0] if result else {}
    elif isinstance(result, dict):
        action = result
    else:
        raise UserError(f"Failed to create HaloPSA note - unexpected response type: {type(result)}")
    logger.info(f"Added {note_type} note to ticket {ticket_id}")

    # Send email if requested
    if send_email:
        await _send_email_from_ticket(ticket_id, note_html=note, email_template_id=email_template_id)

    # Close ticket if requested
    if close_ticket:
        await close_ticket_impl(ticket_id, resolution_note=note)

    return action


async def _send_email_from_ticket(
    ticket_id: int,
    *,
    note_html: str | None = None,
    email_template_id: int = 11,
) -> None:
    """
    Send an email from a HaloPSA ticket to the ticket's user.

    Fetches the ticket to resolve the user's email address, then creates
    an action with sendemail=True.

    Args:
        ticket_id: HaloPSA ticket ID
        note_html: Optional HTML body for the email
        email_template_id: HaloPSA email template ID
    """
    # Fetch ticket to get user email
    ticket = await halopsa.get_tickets(str(ticket_id))
    t = ticket if isinstance(ticket, dict) else dict(ticket)

    # Extract email from embedded user object
    user = t.get("user", {})
    if not isinstance(user, dict):
        user = dict(user) if user else {}
    user_email = user.get("emailaddress") or user.get("email")

    if not user_email:
        logger.warning(f"No email found on ticket {ticket_id} user — skipping email send")
        return

    # Send email via HaloPSA action
    email_action = {
        "ticket_id": ticket_id,
        "note_html": note_html or "",
        "outcome": "Email From Automation",
        "hiddenfromuser": False,
        "sendemail": True,
        "emailto": user_email,
        "emailtemplate_id": email_template_id,
        "who": f"🤖 Bifrost ({context.name})",
    }

    try:
        await halopsa.create_actions([email_action])
        logger.info(f"Sent email to {user_email} from ticket {ticket_id}")
    except Exception as e:
        logger.error(f"Failed to send email from ticket {ticket_id}: {e}")
        raise UserError(f"Failed to send email: {e}")


async def close_ticket_impl(
    ticket_id: int,
    resolution_note: str | None = None,
) -> dict:
    """
    Close a HaloPSA ticket.

    Args:
        ticket_id: HaloPSA ticket ID
        resolution_note: Optional resolution note text

    Returns:
        Updated ticket dict
    """
    # Get ticket to verify it exists
    await halopsa.get_tickets(str(ticket_id))

    # Add resolution note if provided
    if resolution_note:
        note_html = _build_note_html(note=resolution_note, is_complete=True)
        try:
            await halopsa.create_actions([{
                "ticket_id": ticket_id,
                "note_html": note_html,
                "outcome": "Workflow Complete",
                "hiddenfromuser": True,
            }])
        except Exception as e:
            logger.warning(f"Failed to add resolution note to ticket {ticket_id}: {e}")

    # Close the ticket (status 9 is typically "Closed" in HaloPSA)
    closed_status = await config.get("psa_closed_status_id", default=9)

    try:
        result = await halopsa.create_tickets([{
            "id": ticket_id,
            "status_id": closed_status,
        }])
    except Exception as e:
        logger.error(f"Failed to close ticket {ticket_id}: {e}")
        raise UserError(f"Failed to close HaloPSA ticket: {e}")

    # Handle both list and dict responses
    if isinstance(result, list):
        ticket = result[0] if result else {}
    elif isinstance(result, dict):
        ticket = result
    else:
        ticket = {}

    logger.info(f"Closed HaloPSA ticket {ticket_id}")
    return ticket


# Alias for cleaner API
close_ticket = close_ticket_impl


async def create_opportunity(
    summary: str,
    client_id: int,
    *,
    site_id: int | None = None,
    opp_company_name: str | None = None,
    opp_email: str | None = None,
    opp_phone: str | None = None,
    opp_type: str | None = None,
    details: str | None = None,
    note: str | None = None,
    opp_value: float = 0.0,
    opp_conversion_probability: float = 50.0,
    target_date: str | None = None,
    pipeline_stage_id: int = 1,
    agent_id: int | None = None,
    match_id: str | None = None,
    asset_id: int | None = None,
    asset_ids: list[int] | None = None,
    ticket_type_id: int,
    team_id: int,
    opportunity_status_id: int,
) -> dict:
    """
    Create a HaloPSA opportunity.

    Uses create_ticket() for the initial ticket (gets idempotency via match_id),
    then upgrades it to ticket type 55 (Opportunity) via a second update call.
    This two-step approach is required due to API token restrictions on type 55 creation.

    Account manager is auto-assigned by HaloPSA (default_agent=-97 on ticket type 55).
    Status defaults to "Needs Scheduling". Conversion probability defaults to 50%.
    Target date defaults to end of current quarter.

    Args:
        summary: Opportunity title/name
        client_id: HaloPSA client ID
        site_id: Client site ID (optional)
        opp_company_name: Company name (defaults to client name if omitted)
        opp_email: Contact email address
        opp_phone: Contact phone number
        opp_type: Opportunity type (e.g. "Non-Profit", "Commercial")
        details: Opportunity description
        note: Initial note to add after creation
        opp_value: Expected deal value (default: 0)
        opp_conversion_probability: Win probability 0-100 (default: 50)
        target_date: Expected close date ISO 8601 (default: end of current quarter)
        pipeline_stage_id: Sales pipeline stage ID (default: 1)
        agent_id: Override agent assignment (default: client's account manager)
        match_id: Unique ID for idempotency (reuses existing opportunity if found)
        asset_id: Optional single asset/CI ID to link to the opportunity
        asset_ids: Optional list of asset/CI IDs to link multiple assets to the opportunity

    Returns:
        Created opportunity dict with id, summary, agent, client, and sales fields
    """
    # --- Step 1: Fetch client to validate account manager and get name ---
    logger.info(f"Fetching client {client_id} to resolve account manager...")
    try:
        client_result = await halopsa.get_client(str(client_id))
        client = normalize_halo_result(client_result)
    except Exception as e:
        raise UserError(f"Failed to fetch client {client_id}: {e}")

    client_name = client.get("name", "")
    account_manager_id = client.get("accountmanagertech")
    account_manager_name = client.get("accountmanagertech_name", "")

    if not account_manager_id and not agent_id:
        raise UserError(
            f"Client '{client_name}' has no account manager assigned in HaloPSA. "
            "Please assign one first, or pass agent_id explicitly."
        )

    # --- Step 2: Create initial ticket using extension helper ---
    # Gets idempotency (match_id) for free. No initial note — opportunity adds its own.
    ticket = await create_ticket(
        summary=summary,
        client_id=client_id,
        site_id=site_id,
        asset_id=asset_id,
        match_id=match_id,
    )
    ticket_id = ticket["id"]
    logger.info(f"Step 2 complete: ticket {ticket_id} (is_new={ticket.get('is_new')})")

    # --- Step 3: Upgrade to Opportunity type + set all fields in one update ---
    # Combining the type change and field setting into a single call.
    # Separately updating a type-55 ticket fails for this API token.
    update_payload: dict = {
        "id": ticket_id,
        "tickettype_id": ticket_type_id,
        "team_id": team_id,
        "oppvalue": opp_value,
        "oppconversionprobability": opp_conversion_probability,
        "targetdate": target_date,
        "pipeline_stage_id": pipeline_stage_id,
        "oppcompanyname": opp_company_name or client_name,
    }

    if asset_ids:
        update_payload["assets"] = [{"id": aid} for aid in asset_ids]
    elif asset_id:
        update_payload["asset_id"] = asset_id
    if details:
        update_payload["details"] = details
    if opp_email:
        update_payload["oppemailaddress"] = opp_email
    if opp_phone:
        update_payload["opptel"] = opp_phone
    if opp_type:
        update_payload["opptype"] = opp_type

    logger.info(f"Step 3: Upgrading ticket {ticket_id} to Opportunity type + setting team...")
    try:
        result2 = await halopsa.create_tickets([update_payload])
    except Exception as e:
        raise UserError(
            f"Ticket {ticket_id} was created but could not be configured as an Opportunity: {e}. "
            "Please update it manually in HaloPSA."
        )

    opp: dict = (
        result2[0] if isinstance(result2, list)
        else result2 if isinstance(result2, dict)
        else ticket
    )
    logger.info(f"Step 3 complete: ticket {ticket_id} upgraded to Opportunity type, team set to Sales")

    # --- Step 4: Set status + agent via action ---
    # The ticket type's statusaftertechupdate rule resets status on update,
    # so we apply the desired status through a separate action instead.
    # We also set new_agent here since step 4's agent assignment gets reset by these same rules.
    effective_agent_id = agent_id or account_manager_id
    step5_payload: dict = {
        "ticket_id": ticket_id,
        "new_status": opportunity_status_id,
        "hiddenfromuser": True,
        "outcome": "Status Change",
    }
    if effective_agent_id:
        step5_payload["new_agent"] = effective_agent_id
        step5_payload["_forcereassign"] = True
        step5_payload["_agent01_ok"] = True
        step5_payload["_agent02_ok"] = True
    try:
        await halopsa.create_actions([step5_payload])
        logger.info(f"Step 4 complete: status set to Needs Scheduling, agent set to {effective_agent_id}")
    except Exception as e:
        logger.warning(f"Could not set status/agent: {e}")

    # --- Step 5: Add note if provided ---
    if note:
        try:
            await halopsa.create_actions([{
                "ticket_id": ticket_id,
                "note": note,
                "outcome": "Note",
                "hiddenfromuser": False,
            }])
        except Exception as e:
            logger.warning(f"Opportunity created but note failed: {e}")

    # --- Step 6: Re-apply team + agent after status action ---
    # The status action triggers type rules that reset the team, and the team update
    # triggers rules that reset the agent. Setting both together in one call is the
    # last write, so both should stick.
    step6_payload: dict = {"id": ticket_id, "team_id": team_id}
    if effective_agent_id:
        step6_payload["agent_id"] = effective_agent_id
        step6_payload["_forcereassign"] = True
        step6_payload["_agent01_ok"] = True
        step6_payload["_agent02_ok"] = True
    try:
        await halopsa.create_tickets([step6_payload])
        logger.info(f"Step 6 complete: re-applied team_id={team_id} and agent_id={effective_agent_id} to opportunity {ticket_id}")
    except Exception as e:
        logger.warning(f"Could not re-apply team/agent to opportunity {ticket_id}: {e}")

    # --- Step 7: Fetch final state ---
    assigned_agent_id = agent_id or account_manager_id
    try:
        final = await halopsa.get_opportunities(str(ticket_id))
        opp = normalize_halo_result(final)
    except Exception as e:
        logger.warning(f"Could not fetch final opportunity state: {e}")

    agent_name = opp.get("agent_name") or account_manager_name or f"Agent {assigned_agent_id}"

    return {
        "id": ticket_id,
        "summary": opp.get("summary", summary),
        "client_id": client_id,
        "client_name": opp.get("client_name", client_name),
        "agent_id": opp.get("agent_id", assigned_agent_id),
        "agent_name": agent_name,
        "status_id": opp.get("status_id"),
        "status_name": opp.get("status_name"),
        "tickettype_id": opp.get("tickettype_id"),
        "tickettype_name": opp.get("tickettype_name"),
        "pipeline_stage_id": opp.get("pipeline_stage_id"),
        "oppvalue": opp.get("oppvalue", opp_value),
        "oppconversionprobability": opp.get("oppconversionprobability", opp_conversion_probability),
        "targetdate": opp.get("targetdate", target_date),
        "asset_id": opp.get("asset_id", asset_id),
        "team_id": opp.get("team_id", team_id),
        "team": opp.get("team", "Sales"),
        "web_url": opp.get("web_url"),
    }


def _cast_value(value: Any) -> Any:
    """Cast string values from HaloPSA SQL results to native Python types."""
    if not isinstance(value, str):
        return value

    # Booleans
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False

    # Integers
    try:
        int_val = int(value)
        if str(int_val) == value:  # Avoid matching "1.0" etc.
            return int_val
    except ValueError:
        pass

    # Floats
    try:
        float_val = float(value)
        if value.count(".") == 1:  # Only cast obvious decimals, not dates
            return float_val
    except ValueError:
        pass

    return value


def _cast_row(row: dict) -> dict:
    """Cast all string values in a row to native Python types."""
    return {k: _cast_value(v) for k, v in row.items()}


async def execute_sql(query: str, *, cast_types: bool = True) -> list[dict]:
    """
    Execute a SQL query against the HaloPSA reporting database.

    Uses POST /Report with _testonly and _loadreportonly flags.
    Response rows are at result.report.rows. All values come back as
    strings, so by default we cast them to native Python types
    (int, float, bool).

    Args:
        query: SQL query string (typically SELECT statements)
        cast_types: Cast string values to native types (default: True)

    Returns:
        List of result rows as dicts with cast values

    Example:
        users = await execute_sql(
            "SELECT TOP 5 uid as id, uusername as name FROM USERS WHERE uinactive = 0"
        )
        # [{"id": 1, "name": "John Doe"}, ...]
    """
    payload = [{"sql": query, "_testonly": True, "_loadreportonly": True}]

    try:
        result = await halopsa.create_report(data=payload)
    except Exception as e:
        logger.error(f"SQL query failed: {e}")
        raise UserError(f"Failed to execute HaloPSA SQL query: {e}")

    # Response is {"report": {"rows": [...]}, "loaded": true, ...}
    rows = []
    if isinstance(result, dict):
        report = result.get("report", {})
        if isinstance(report, dict):
            rows = report.get("rows", [])
        elif isinstance(report, list):
            rows = report

        # Check for SQL errors
        load_error = result.get("load_error", "")
        if load_error:
            raise UserError(f"HaloPSA SQL error: {load_error}")

    if cast_types and rows:
        rows = [_cast_row(r) for r in rows]

    return rows


# =============================================================================
# Generic Pagination
# =============================================================================


def _find_list_attr(result) -> tuple[list | None, str | None]:
    """Auto-detect the list attribute on a paginated HaloPSA response.

    Mirrors the PowerShell pattern: find the single array property on the
    response object. E.g. AreaView has 'clients', TicketView has 'tickets'.
    """
    if isinstance(result, dict):
        candidates = [(k, v) for k, v in result.items() if isinstance(v, list)]
    else:
        candidates = [
            (name, getattr(result, name))
            for name in dir(result)
            if not name.startswith("_")
            and isinstance(getattr(result, name, None), list)
        ]

    # Filter out metadata-like fields (e.g. 'columns')
    candidates = [(k, v) for k, v in candidates if v and k != "columns"]

    if len(candidates) == 1:
        return candidates[0][1], candidates[0][0]
    if len(candidates) > 1:
        # Multiple list attrs — pick the one that isn't 'columns'
        # Fall back to first
        return candidates[0][1], candidates[0][0]
    return None, None


async def paginate(method, *, page_size: int = 100, **kwargs) -> list:
    """Auto-paginate any halopsa.list_* call.

    Uses the same pattern as our PowerShell module: detect the single
    list attribute on the response, loop until record_count is reached.

    Args:
        method: An async halopsa.list_* method (e.g. halopsa.list_clients)
        page_size: Items per page (max 100 for most endpoints)
        **kwargs: Filters passed through to the API (e.g. toplevel_id=0)

    Returns:
        Flat list of all items across all pages.

    Example:
        clients = await paginate(halopsa.list_clients, toplevel_id=0)
    """
    all_items = []
    page = 1

    while True:
        result = await method(
            pageinate=True, page_no=page, page_size=page_size, **kwargs
        )

        items, key = _find_list_attr(result)
        if not items:
            break

        all_items.extend(items)

        total = getattr(result, "record_count", 0) or (
            result.get("record_count", 0) if isinstance(result, dict) else 0
        )
        if len(all_items) >= total:
            break

        page += 1

    return all_items


async def list_clients(*, include_inactive: bool = False) -> list:
    """List all HaloPSA clients with automatic pagination.

    Args:
        include_inactive: Include inactive clients (default: active only)

    Returns:
        List of client objects (AreaList dataclasses)
    """
    kwargs = {}
    if include_inactive:
        kwargs["includeinactive"] = True
    return await paginate(halopsa.list_clients, **kwargs)


# =============================================================================
# Reference Data Helpers
# =============================================================================


def _to_dict_list(result) -> list[dict]:
    """Normalize an SDK result to a list of dicts.

    Handles three shapes: plain list, object with a list attribute, or dict
    with a list value.
    """
    if isinstance(result, list):
        items = result
    else:
        items, _ = _find_list_attr(result)
        items = items or []
    return normalize_halo_list(items)


async def get_lookup(lookup_id: int) -> list[dict]:
    """Fetch a HaloPSA lookup table by ID, with caching.

    Args:
        lookup_id: The HaloPSA lookup ID (e.g. 12 = impact)

    Returns:
        List of lookup item dicts (id, name, value2, value3, etc.)
    """
    cache_key = f"lookup:{lookup_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    result = await halopsa.list_lookups(lookupid=lookup_id)
    items_list = _to_dict_list(result)
    _set_cached(cache_key, items_list)
    return items_list


async def list_priorities() -> list[dict]:
    """List all HaloPSA priorities, with caching.

    Returns:
        List of priority dicts (id, name, seriousness, colour, etc.)
    """
    cached = _get_cached("priorities")
    if cached is not None:
        return cached

    result = await halopsa.list_priorities()
    items_list = _to_dict_list(result)
    _set_cached("priorities", items_list)
    return items_list


async def list_ticket_types() -> list[dict]:
    """List all HaloPSA ticket types, with caching.

    Returns:
        List of ticket type dicts (id, name, etc.) — includes inactive.
    """
    cached = _get_cached("ticket_types")
    if cached is not None:
        return cached

    result = await halopsa.list_ticket_types()
    items_list = _to_dict_list(result)
    _set_cached("ticket_types", items_list)
    return items_list


async def list_categories(type_id: int | None = None) -> list[dict]:
    """List HaloPSA categories, optionally filtered by ticket type.

    Args:
        type_id: Optional ticket type ID to filter categories

    Returns:
        Flat list of category dicts, each with id and value (name).
    """
    cache_key = f"categories:{type_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    kwargs: dict[str, Any] = {"showall": True}
    if type_id is not None:
        kwargs["type_id"] = type_id

    result = await halopsa.list_categories(**kwargs)
    items_list = _to_dict_list(result)
    _set_cached(cache_key, items_list)
    return items_list


# --- Ticket type field introspection ---

# HaloPSA custom-field type codes
FIELD_TYPE_LABELS = {
    -1: "system",       # Built-in HaloPSA fields (priority, status, agent, etc.)
    0: "text",          # Single-line text input
    1: "textarea",      # Multi-line text
    2: "dropdown",      # Single-select dropdown (lookup-backed)
    3: "multiselect",   # Multi-select (lookup-backed)
    4: "date",          # Date / datetime picker
    5: "number",        # Numeric (rarely seen on tickets directly)
    6: "checkbox",      # Boolean toggle
    7: "table",         # Custom table (sub-rows)
    10: "richtext",     # Rich-text / HTML editor
}

# inputtype refinements (override display hint within type=0 text fields)
INPUT_TYPE_LABELS = {
    0: None,            # default
    1: "integer",       # numeric integer input
    2: "currency",      # currency / decimal input
    5: "url",           # URL / hyperlink
    6: "password",      # masked password input
}

# Usage-column flag meanings (technew / techdetail / endusernew / enduserdetail)
USAGE_FLAGS = {
    0: "hidden",
    1: "visible",
    2: "warn_if_empty",
    3: "required",
    4: "readonly",
}


async def get_ticket_type_fields(
    type_id: int,
    usage: Literal["technew", "techdetail", "endusernew", "enduserdetail"] = "technew",
    context: dict[str, Any] | None = None,
) -> list[dict]:
    """Return the form schema for a HaloPSA ticket type — the fields, their
    valid options, and where each value goes in the ``POST /Tickets`` payload.

    This is the single entry-point an LLM or automation needs to understand
    *what data* a ticket type expects before creating or updating a ticket.

    How it works
    ------------
    Calls ``GET /TicketType/{type_id}`` which returns the type's configured
    fields — both direct fields and field-group references.  Each group
    contains its own field list.  The method flattens both levels, filters
    by the ``usage`` visibility flag, and enriches each field with:

    * **api_field** — where to put the value in the ticket payload.
    * **options** — valid ``{id, name}`` pairs for dropdowns / selects.
    * **is_required / warn_if_empty / is_readonly** — validation hints.

    Visibility flags (per Halo admin "Edit Field" screen)::

        0 = Not Visible
        1 = Visible – Not Required
        2 = Visible – Warn if empty
        3 = Visible – Required
        4 = Visible – Read Only

    Option sources
    ~~~~~~~~~~~~~~
    Options are resolved from multiple backends depending on the field:

    * **Embedded values** — static lookup values baked into the field config.
    * **Lookup endpoint** — ``GET /Lookup?lookupid=X`` for lookup-table fields.
    * **System endpoints** — ``list_priorities()``, ``list_categories()`` for
      built-in system fields like priority and category.
    * **SQL lookups** — some fields have a ``sqllookup`` query with Halo
      variables like ``$userid``, ``$clientid``.  These are executed by
      Halo's internal engine and can't be run directly.  The field is
      returned with ``needs_context`` listing the required variable names
      so the caller knows what context is needed (e.g. to narrow results
      via a different approach, or to present the field as free-text).
    * **Dynamic (load_type=1)** — context-dependent fields whose options
      change based on runtime state.  Flagged with ``is_dynamic=True``.

    Building a ticket payload
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    Each field's ``api_field`` tells you where to place the value::

        api_field="summary"       →  payload["summary"] = "Printer offline"
        api_field="details"       →  payload["details"] = "Won't turn on..."
        api_field="priority_id"   →  payload["priority_id"] = 4
        api_field="category_2"    →  payload["category_2"] = 18
        api_field="team_id"       →  payload["team_id"] = 2
        api_field="agent_id"      →  payload["agent_id"] = 15
        api_field="impact"        →  payload["impact"] = 1
        api_field="urgency"       →  payload["urgency"] = 2
        api_field="customfields"  →  payload.setdefault("customfields", []).append(
                                         {"id": <fieldid>, "value": <val>})

    For ``customfields``, use the field's ``fieldid`` as the ``id`` and the
    selected option ``id`` (for dropdowns) or raw value (for text/date/etc.)
    as ``value``.

    Args:
        type_id: HaloPSA ticket type ID (e.g. 1=Incident, 43=Repurpose Computer).
        usage: Screen context — controls which visibility flag is read.
            ``"technew"`` = agent creating a new ticket (most common).
        context: Reserved for future use.  SQL-backed fields will report
            ``needs_context`` with the Halo variable names their query
            requires (e.g. ``["user_id", "client_id"]``).

    Returns:
        Ordered list of field descriptors.  Key fields on each dict:

        * ``fieldid`` (int) — HaloPSA field ID.
        * ``label`` (str) — display name.
        * ``field_type_label`` (str) — ``"text"``, ``"textarea"``, ``"dropdown"``,
          ``"multiselect"``, ``"checkbox"``, ``"date"``, ``"richtext"``, etc.
        * ``api_field`` (str) — where to put the value (see above).
        * ``is_required`` (bool) — must be filled to save.
        * ``warn_if_empty`` (bool, optional) — UI warns but allows save.
        * ``is_readonly`` (bool, optional) — displayed but not editable.
        * ``options`` (list[dict], optional) — ``[{"id": ..., "name": ...}]``
          for dropdown/multiselect fields.
        * ``is_dynamic`` (bool, optional) — options depend on runtime context.
        * ``needs_context`` (list[str], optional) — SQL variable names needed
          to resolve options (e.g. ``["user_id"]``).  Pass them via ``context``.
        * ``section`` (str) — field group / tab name.
        * ``sequence`` (int) — display order within section.
    """
    # Context-dependent results are not cached (options vary per context)
    if context is None:
        cache_key = f"ttf:{type_id}:{usage}"
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

    tt_raw = await halopsa.get_ticket_type(type_id)
    tt = tt_raw if isinstance(tt_raw, dict) else dict(tt_raw)

    # Flatten: direct fields + fields from embedded groups
    raw_records: list[tuple[dict, str]] = []  # (record, section_name)
    for f in tt.get("fields", []):
        fd = f if isinstance(f, dict) else dict(f)
        group = fd.get("group")
        if group:
            gd = group if isinstance(group, dict) else dict(group)
            section = gd.get("name") or gd.get("header") or "Fields"
            for gf in gd.get("fields", []):
                raw_records.append(
                    (gf if isinstance(gf, dict) else dict(gf), section))
        else:
            raw_records.append((fd, ""))

    seen: set[int] = set()
    seen_api: set[str] = set()  # dedupe system fields sharing the same api_field
    fields: list[dict] = []

    for rec, section in raw_records:
        fid = rec.get("fieldid")
        if fid is None or fid in seen:
            continue

        usage_flag = rec.get(usage, 0) or 0
        if usage_flag == 0:  # hidden
            continue

        fi = rec.get("fieldinfo") or {}
        if not isinstance(fi, dict):
            fi = dict(fi)

        label = fi.get("label") or fi.get("name")
        if not label:
            continue

        # Skip AI-populated fields — not user-inputtable
        faults_name = fi.get("faults_field_name", "")
        if faults_name.startswith("fai"):
            continue

        seen.add(fid)

        field_type = fi.get("type")
        field_type_label = FIELD_TYPE_LABELS.get(field_type, f"unknown({field_type})")
        input_type_code = fi.get("inputtype", 0) or 0
        input_hint = INPUT_TYPE_LABELS.get(input_type_code)

        is_required = usage_flag == 3 or bool(fi.get("mandatory"))
        is_warn = usage_flag == 2

        # --- API field location ---
        is_custom = fi.get("custom") == 1 and fid > 0
        if faults_name:
            api_field = _FAULTS_TO_API.get(faults_name, faults_name)
        elif is_custom:
            api_field = "customfields"
        elif fid < 0:
            api_field = _SYSTEM_FID_TO_API.get(fid) or _FAULTS_TO_API.get(
                fi.get("name", ""), fi.get("name", f"system_{fid}"))
        else:
            api_field = "customfields"

        # Dedupe system fields that resolve to the same api_field
        # (e.g. two Service Category fields both mapping to category_2)
        if api_field != "customfields":
            if api_field in seen_api:
                continue
            seen_api.add(api_field)

        # --- Options ---
        options = None
        needs_context: list[str] | None = None

        # 1. Embedded values (static lookups baked into fieldinfo)
        raw_values = fi.get("values")
        if raw_values and field_type in (2, 3):
            options = [
                {"id": (v if isinstance(v, dict) else dict(v)).get("id"),
                 "name": (v if isinstance(v, dict) else dict(v)).get("name")}
                for v in raw_values
            ]

        # 2. SQL lookup — field has a sqllookup query with $variables.
        #    These run inside Halo's engine so we can't execute them directly.
        #    Extract the required variable names so callers know what context
        #    is needed.
        sqllookup = fi.get("sqllookup") or ""
        if options is None and sqllookup.strip():
            needs_context = _extract_sql_context_vars(sqllookup)

        # 3. Lookup endpoint — static lookup table
        lookup_id = fi.get("lookup") if fi.get("lookup") and fi["lookup"] > 0 else None
        is_dynamic = bool(fi.get("load_type"))
        if options is None and not needs_context and lookup_id and field_type in (2, 3) and not is_dynamic:
            try:
                lkp_items = await get_lookup(lookup_id)
                if lkp_items:
                    options = [{"id": item.get("id"), "name": item.get("name")}
                               for item in lkp_items]
            except Exception:
                logger.debug("Failed to fetch lookup %s for field %s", lookup_id, fid)

        # 4. System fields with dedicated endpoints (field_type -1)
        #    and known system api_fields that need lookup resolution
        if not options and (field_type == -1 or api_field in _SYSTEM_FIELD_LOOKUP_IDS):
            options = await _get_system_field_options(api_field, type_id)

        desc: dict[str, Any] = {
            "fieldid": fid,
            "label": label,
            "field_type_label": input_hint or field_type_label,
            "is_required": is_required,
            "api_field": api_field,
            "section": section or fi.get("tab_name") or "",
            "sequence": rec.get("seq") or 999,
        }
        if is_warn:
            desc["warn_if_empty"] = True
        if usage_flag == 4:
            desc["is_readonly"] = True
        if options is not None:
            desc["options"] = options
        if needs_context:
            desc["needs_context"] = needs_context
        if is_dynamic:
            desc["is_dynamic"] = True
        if lookup_id:
            desc["lookup_id"] = lookup_id

        fields.append(desc)

    fields.sort(key=lambda f: (f.get("section") or "", f["sequence"]))

    if context is None:
        _set_cached(f"ttf:{type_id}:{usage}", fields)
    return fields


# Halo SQL variable name -> friendly context key
_SQL_VAR_MAP: dict[str, str] = {
    "$userid": "user_id",
    "$clientid": "client_id",
    "$siteid": "site_id",
    "$ticketid": "ticket_id",
    "$assetid": "asset_id",
}


def _extract_sql_context_vars(sql: str) -> list[str]:
    """Extract the context variable names a sqllookup query requires.

    Scans for Halo ``$variable`` patterns and maps them to friendly names.
    """
    sql_vars = set(re.findall(r"\$\w+", sql.lower()))
    return sorted({_SQL_VAR_MAP.get(var, var.lstrip("$")) for var in sql_vars})


# Lookup IDs for system fields that get their options from the Lookup API
# Lookup IDs for system fields that get their options from the Lookup API
_SYSTEM_FIELD_LOOKUP_IDS: dict[str, int] = {
    "impact": 12,
    "urgency": 27,
}

# Category API type_id for each category level
# (this is NOT the ticket type_id — it's the category type_id)
_CATEGORY_TYPE_IDS: dict[str, int] = {
    "category_1": 1,  # Service Category
    "category_2": 2,  # Resolution (unused)
    "category_3": 3,  # Billing Helper
    "category_4": 4,  # Change Category (unused right now)
}


async def _get_system_field_options(
    api_field: str, type_id: int,
) -> list[dict] | None:
    """Fetch options for a system field from the appropriate endpoint."""
    try:
        if api_field == "priority_id":
            items = await list_priorities()
            return [{"id": p.get("id"), "name": p.get("name")} for p in items]
        if api_field in _CATEGORY_TYPE_IDS:
            cat_type_id = _CATEGORY_TYPE_IDS[api_field]
            items = await list_categories(type_id=cat_type_id)
            return [{"id": c.get("id"), "name": c.get("value") or c.get("name")}
                    for c in items]
        if api_field in _SYSTEM_FIELD_LOOKUP_IDS:
            items = await get_lookup(_SYSTEM_FIELD_LOOKUP_IDS[api_field])
            return [{"id": i.get("id"), "name": i.get("name")} for i in items]
    except Exception:
        logger.debug("Failed to fetch system options for %s", api_field)
    return None


# Map faults_field_name / system field names -> clean API property names
_FAULTS_TO_API: dict[str, str] = {
    "symptom": "summary",
    "symptom2": "details",
    "impact": "impact",
    "urgency": "urgency",
    "seriousness": "priority_id",
    # HaloPSA faults names are offset by 1 from the ticket API fields:
    # category2 (Service Category) → category_1 in API
    # category3 (Resolution) → category_2 in API
    # category4 (Billing Helper) → category_3 in API
    # category5 (Change Category) → category_4 in API
    "category1": "category_1",
    "category2": "category_1",
    "category3": "category_2",
    "category4": "category_3",
    "category5": "category_4",
    "sectio_": "team_id",
    "assignedtoint": "agent_id",
    "assets": "assets",
    "ftickettags": "tags",
    "fixbydate": "fixbydate",
    "FOppTargetDate": "target_date",
    "FProjectStartDate": "start_date",
}

# System fields (negative fid) without faults_field_name — map by field ID
_SYSTEM_FID_TO_API: dict[int, str] = {
    -52: "followers",
    -101: "tags",
}


# --- Internal lookup builders for name resolution ---


async def _priority_lookup() -> dict[int, str]:
    """Build {priority_id: name} mapping using the numeric priorityid field."""
    priorities = await list_priorities()
    lookup: dict[int, str] = {}
    for p in priorities:
        pid = p.get("priorityid")
        if pid is not None and pid not in lookup:
            lookup[pid] = p.get("name", "")
    return lookup


async def _ticket_type_lookup() -> dict[int, str]:
    """Build {tickettype_id: name} mapping."""
    types = await list_ticket_types()
    return {t["id"]: t.get("name", "") for t in types if "id" in t}


async def _status_lookup() -> dict[int, str]:
    """Build {status_id: name} mapping."""
    cached = _get_cached("statuses")
    if cached is not None:
        statuses = cached
    else:
        result = await halopsa.list_statuses()
        statuses = _to_dict_list(result)
        _set_cached("statuses", statuses)
    return {s["id"]: s.get("name", "") for s in statuses if "id" in s}


# =============================================================================
# Pagination and Enrichment Helpers
# =============================================================================


async def paginate_tickets(
    *,
    page_size: int = 50,
    days_back: int | None = None,
    status_ids: list[int] | None = None,
    closed_only: bool = False,
    max_tickets: int | None = None,
    **kwargs,
) -> AsyncIterator[dict]:
    """
    Async generator that yields tickets with automatic pagination.

    Fetches tickets ordered by dateoccurred descending (most recent first).
    Stops when tickets are older than days_back threshold.

    Args:
        page_size: Number of tickets per page (max 100)
        days_back: Only yield tickets from the last N days (stops when older)
        status_ids: Filter by specific status IDs
        closed_only: Only return closed tickets (dateclosed is not null)
        max_tickets: Maximum number of tickets to yield
        **kwargs: Additional query parameters passed to list_tickets

    Yields:
        Individual ticket dicts from the paginated results

    Example:
        async for ticket in paginate_tickets(days_back=7, closed_only=True):
            print(ticket.id, ticket.summary)
    """
    from datetime import datetime, timedelta

    page_no = 1
    total_yielded = 0
    page_size = min(page_size, 100)  # HaloPSA max is 100

    # Calculate cutoff date if days_back specified
    cutoff_date = None
    if days_back is not None:
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        logger.info(f"Fetching tickets from last {days_back} days (cutoff: {cutoff_date})")

    # Build query parameters - order by dateoccurred descending
    params = {
        "pageinate": True,
        "page_size": page_size,
        "order": "dateoccurred",
        "orderdesc": True,
        **kwargs,
    }

    # Status filter
    if status_ids:
        params["status_id"] = ",".join(str(s) for s in status_ids)

    while True:
        params["page_no"] = page_no

        logger.debug(f"Fetching tickets page {page_no} (page_size={page_size})")

        try:
            result = await halopsa.list_tickets(**params)
        except Exception as e:
            logger.error(f"Failed to fetch tickets page {page_no}: {e}")
            raise

        # Extract tickets from response
        if hasattr(result, "tickets"):
            tickets = result.tickets or []
            record_count = getattr(result, "record_count", len(tickets))
        elif isinstance(result, dict):
            tickets = result.get("tickets", [])
            record_count = result.get("record_count", len(tickets))
        else:
            tickets = []
            record_count = 0

        if not tickets:
            break

        for ticket in tickets:
            # Convert to dict if needed
            ticket_dict = normalize_halo_result(ticket)

            # Get ticket date for filtering (just the date part)
            ticket_date_str = ticket_dict.get("dateoccurred", "")
            if ticket_date_str:
                ticket_date = ticket_date_str[:10]  # Extract YYYY-MM-DD
            else:
                ticket_date = None

            # Stop if we've gone past cutoff date (tickets are in desc order)
            if cutoff_date and ticket_date and ticket_date < cutoff_date:
                logger.info(f"Reached tickets before cutoff ({cutoff_date}), stopping")
                return

            # Skip open tickets if closed_only
            if closed_only and not ticket_dict.get("dateclosed"):
                continue

            yield ticket_dict
            total_yielded += 1

            # Check max_tickets limit
            if max_tickets and total_yielded >= max_tickets:
                logger.info(f"Reached max_tickets limit ({max_tickets})")
                return

        # Check if we've fetched all records
        fetched_so_far = page_no * page_size
        if fetched_so_far >= record_count:
            break

        page_no += 1

    logger.info(f"Pagination complete: yielded {total_yielded} tickets")


async def get_enriched_ticket(ticket_id: int) -> EnrichedTicket:
    """
    Fetch a ticket with full details and all associated notes/actions.

    Args:
        ticket_id: The HaloPSA ticket ID to fetch

    Returns:
        EnrichedTicket with full ticket data, actions, and extracted metadata

    Example:
        enriched = await get_enriched_ticket(409720)
        print(enriched.ticket.summary)
        print(f"Found {len(enriched.actions)} actions")
    """
    # Get full ticket details
    logger.debug(f"Fetching ticket {ticket_id}")
    ticket = await halopsa.get_tickets(str(ticket_id))
    ticket_dict = normalize_halo_result(ticket)

    # Resolve missing name fields using cached reference data
    await _resolve_names(ticket_dict)

    # Get all actions (notes) for this ticket
    actions_list = await _fetch_actions(ticket_id)

    # Extract metadata (now includes agents_involved from actions)
    metadata = extract_metadata(ticket_dict, actions_list)

    EnrichedTicket, _ = _get_ai_ticket_models()
    return EnrichedTicket(
        ticket=ticket_dict,
        actions=actions_list,
        metadata=metadata,
    )


# =============================================================================
# Utility Functions
# =============================================================================


def extract_agents_involved(actions: list[dict]) -> list[str]:
    """
    Extract unique agent names from ticket actions.

    Args:
        actions: List of action dicts from HaloPSA API

    Returns:
        List of unique agent names who touched the ticket
    """
    agents = set()
    for action in actions:
        who_agentid = action.get("who_agentid", 0)
        who = action.get("who", "")
        if who_agentid and who_agentid > 0 and who:
            agents.add(who)
    return list(agents)


def extract_metadata(ticket: dict, actions: list[dict] | None = None) -> TicketMetadata:
    """
    Extract and normalize metadata from a ticket for filtering.

    Args:
        ticket: Raw ticket dict from HaloPSA API
        actions: Optional list of actions to extract agents_involved

    Returns:
        TicketMetadata with normalized fields
    """
    # Parse SLA state
    sla_state = ticket.get("slastate")
    if sla_state == "I":
        sla_met = True
    elif sla_state == "O":
        sla_met = False
    else:
        sla_met = None

    # Extract agents from actions if provided
    agents_involved = extract_agents_involved(actions) if actions else None

    _, TicketMetadata = _get_ai_ticket_models()
    return TicketMetadata(
        ticket_id=ticket.get("id"),
        client_id=ticket.get("client_id"),
        client_name=ticket.get("client_name"),
        user_id=ticket.get("user_id"),
        user_name=ticket.get("user_name"),
        status_id=ticket.get("status_id"),
        status_name=ticket.get("status_name"),
        tickettype_id=ticket.get("tickettype_id"),
        tickettype_name=ticket.get("tickettype_name"),
        priority_id=ticket.get("priority_id"),
        priority_name=ticket.get("priority_name"),
        category_1=ticket.get("category_1"),
        category_2=ticket.get("category_2"),
        category_3=ticket.get("category_3"),
        category_4=ticket.get("category_4"),
        team_id=ticket.get("team_id"),
        team_name=ticket.get("team"),
        agent_id=ticket.get("agent_id"),
        agent_name=ticket.get("agent_name"),
        agents_involved=agents_involved,
        sla_id=ticket.get("sla_id"),
        sla_met=sla_met,
        site_id=ticket.get("site_id"),
        site_name=ticket.get("site_name"),
        timetaken=ticket.get("timetaken"),
        dateoccurred=ticket.get("dateoccurred"),
        dateclosed=ticket.get("dateclosed"),
    )


def clean_html(html: str) -> str:
    """
    Strip HTML tags and normalize whitespace.

    Args:
        html: HTML string to clean

    Returns:
        Plain text with normalized whitespace
    """
    if not html:
        return ""

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Normalize whitespace
    text = " ".join(text.split())
    return text.strip()


def format_actions_for_summary(actions: list[dict], max_chars: int = 3000) -> str:
    """
    Format ticket actions/notes for AI summarization.

    Args:
        actions: List of action dicts from HaloPSA
        max_chars: Maximum characters to include

    Returns:
        Formatted string with action summaries
    """
    if not actions:
        return ""

    lines = []
    total_chars = 0

    for action in actions:
        note = action.get("note") or action.get("note_html", "")
        outcome = action.get("outcome", "Note")
        who = action.get("who", "")

        if not note:
            continue

        clean_note = clean_html(note)
        if not clean_note:
            continue

        # Truncate individual notes
        if len(clean_note) > 500:
            clean_note = clean_note[:497] + "..."

        line = f"- [{outcome}] {who}: {clean_note}" if who else f"- [{outcome}] {clean_note}"

        if total_chars + len(line) > max_chars:
            break

        lines.append(line)
        total_chars += len(line)

    return "\n".join(lines)


# =============================================================================
# Shared Ticket Filtering (Step 1)
# =============================================================================

# Known ticket type IDs from HaloPSA
SERVICE_TICKET_TYPES = {1, 33}  # Incident, Service Request
ALERT_TICKET_TYPE = 21
NON_BILLABLE_TYPES = {"Automation", "Alert", "Triage", "Quick Time"}


def classify_ticket(ticket: dict, *, include_alerts: bool = False) -> str | None:
    """Returns None if ticket is a real service ticket, or a skip reason string.

    Consolidates filtering logic used across AI ticketing workflows.
    Validates: ticket type, auto-closed junk, empty/garbage summaries.
    """
    from datetime import datetime

    allowed_types = set(SERVICE_TICKET_TYPES)
    if include_alerts:
        allowed_types.add(ALERT_TICKET_TYPE)

    type_id = ticket.get("tickettype_id")
    if type_id is not None and int(type_id) not in allowed_types:
        return "wrong_type"

    opened = ticket.get("dateoccurred", "")
    closed = ticket.get("dateclosed", "")
    if opened and closed:
        try:
            dt_opened = datetime.fromisoformat(opened.replace("Z", "+00:00"))
            dt_closed = datetime.fromisoformat(closed.replace("Z", "+00:00"))
            duration = (dt_closed - dt_opened).total_seconds()
            time_logged = ticket.get("timetaken") or 0
            if duration < 60 and float(time_logged) == 0:
                return "auto_closed_junk"
        except (ValueError, TypeError):
            pass

    summary = (ticket.get("summary") or "").strip()
    if not summary:
        return "empty_summary"

    stripped = summary.upper()
    for prefix in ("RE:", "FW:", "FWD:"):
        stripped = stripped.replace(prefix, "").strip()
    if len(stripped) < 5:
        return "junk_summary"

    return None


# =============================================================================
# Shared Ticket-to-AI Formatting (Step 2)
# =============================================================================


def format_actions_bookend(
    actions: list[dict],
    max_chars: int = 3000,
    head: int = 3,
    tail: int = 3,
) -> str:
    """Format actions keeping first N and last N in full, summarizing middle."""
    if not actions:
        return ""

    # Filter to actions with actual content
    valid = []
    for action in actions:
        note = action.get("note") or action.get("note_html", "")
        if note and clean_html(note).strip():
            valid.append(action)

    if not valid:
        return ""

    def _fmt(action: dict) -> str:
        note = clean_html(action.get("note") or action.get("note_html", ""))
        outcome = action.get("outcome", "Note")
        who = action.get("who", "")
        if len(note) > 500:
            note = note[:497] + "..."
        return f"- [{outcome}] {who}: {note}" if who else f"- [{outcome}] {note}"

    if len(valid) <= head + tail:
        # All fit — format them all
        lines = [_fmt(a) for a in valid]
    else:
        head_actions = valid[:head]
        tail_actions = valid[-tail:]
        skipped = len(valid) - head - tail
        lines = [_fmt(a) for a in head_actions]
        lines.append(f"- ... ({skipped} actions omitted) ...")
        lines.extend(_fmt(a) for a in tail_actions)

    # Truncate to max_chars
    result_lines = []
    total = 0
    for line in lines:
        if total + len(line) > max_chars:
            break
        result_lines.append(line)
        total += len(line)

    return "\n".join(result_lines)


def prepare_ticket_for_ai(
    ticket: dict,
    actions: list[dict],
    *,
    detail_chars: int = 2000,
    action_chars: int = 3000,
    resolution_chars: int = 500,
    include_fields: set[str] | None = None,
    use_bookend_actions: bool = True,
) -> str:
    """Standard ticket-to-AI formatting. One function, consistent output.

    Default field set: summary, client, status, type, priority, categories,
    agent, team, time_logged, dates, details, resolution, actions.
    """
    categories = [ticket.get(f"category_{i}") for i in range(1, 5)]
    category_path = " > ".join(filter(None, categories)) or "Uncategorized"

    if use_bookend_actions:
        actions_text = format_actions_bookend(actions, max_chars=action_chars)
    else:
        actions_text = format_actions_for_summary(actions, max_chars=action_chars)

    details = clean_html(ticket.get("details", "")) or "No details provided"
    resolution = clean_html(
        ticket.get("clearance_note") or ticket.get("resolution") or ""
    ) or "No resolution documented"

    # Default fields
    header = f"""## Ticket #{ticket.get('id')}

- **Summary**: {ticket.get('summary', 'No summary')}
- **Client**: {ticket.get('client_name', 'Unknown')}
- **User**: {ticket.get('user_name', 'Unknown')}
- **Status**: {ticket.get('status_name', 'Unknown')}
- **Type**: {ticket.get('tickettype_name', 'Unknown')}
- **Priority**: {ticket.get('priority_name', 'Unknown')}
- **Categories**: {category_path}
- **Team**: {ticket.get('team', 'Unassigned')}
- **Agent**: {ticket.get('agent_name', 'Unassigned')}
- **Time Logged**: {ticket.get('timetaken', 0)} hours
- **Date Opened**: {ticket.get('dateoccurred', 'Unknown')}
- **Date Closed**: {ticket.get('dateclosed', 'Still Open')}"""

    return f"""{header}

### Details

{details[:detail_chars]}

### Resolution

{resolution[:resolution_chars]}

### Actions/Notes

{actions_text or 'No actions recorded'}
"""


# =============================================================================
# Enrichment Optimization (Step 3)
# =============================================================================


async def _fetch_actions(ticket_id: int) -> list[dict]:
    """Fetch actions/notes for a ticket. Extracted from get_enriched_ticket."""
    try:
        actions_result = await halopsa.list_actions(ticket_id=ticket_id)

        if hasattr(actions_result, "actions"):
            actions = actions_result.actions or []
        elif isinstance(actions_result, dict):
            actions = actions_result.get("actions", [])
        else:
            actions = []
    except Exception as e:
        logger.warning(f"Failed to fetch actions for ticket {ticket_id}: {e}")
        actions = []

    return normalize_halo_list(actions)


async def _resolve_names(ticket_dict: dict) -> None:
    """Resolve missing name fields using cached reference data. Mutates in place."""
    if not ticket_dict.get("priority_name") and ticket_dict.get("priority_id"):
        lookup = await _priority_lookup()
        ticket_dict["priority_name"] = lookup.get(ticket_dict["priority_id"], "")

    if not ticket_dict.get("tickettype_name") and ticket_dict.get("tickettype_id"):
        lookup = await _ticket_type_lookup()
        ticket_dict["tickettype_name"] = lookup.get(ticket_dict["tickettype_id"], "")

    if not ticket_dict.get("status_name") and ticket_dict.get("status_id"):
        lookup = await _status_lookup()
        ticket_dict["status_name"] = lookup.get(ticket_dict["status_id"], "")


async def enrich_from_paginated(ticket_dict: dict) -> EnrichedTicket:
    """Enrich an already-fetched ticket by only fetching actions.

    Use in batch flows where paginate_tickets() already provided the ticket.
    Skips the redundant get_tickets() call that get_enriched_ticket() makes.
    """
    ticket_id = ticket_dict["id"]

    # Resolve any missing name fields (uses cached lookups, no API call if warm)
    await _resolve_names(ticket_dict)

    # Fetch actions — the only API call needed
    actions = await _fetch_actions(ticket_id)
    metadata = extract_metadata(ticket_dict, actions)
    EnrichedTicket, _ = _get_ai_ticket_models()
    return EnrichedTicket(ticket=ticket_dict, actions=actions, metadata=metadata)


# =============================================================================
# Batch Processing Utility (Step 4)
# =============================================================================


async def process_tickets_batch(
    *,
    processor: Callable[[EnrichedTicket], Awaitable[dict]],
    days_back: int = 90,
    closed_only: bool = True,
    max_tickets: int | None = None,
    concurrency: int = 1,
    buffer_size: int = 25,
    on_flush: Callable[[list[dict]], Awaitable[None]] | None = None,
    filter_fn: Callable[[dict], str | None] | None = None,
    **paginate_kwargs,
) -> dict:
    """Stream tickets, enrich, process, flush in batches.

    Uses enrich_from_paginated() to avoid redundant fetches.
    Concurrency defaults to 1 (sequential) to be safe with the HaloPSA API.
    Returns stats dict with counts.
    """
    if filter_fn is None:
        filter_fn = classify_ticket

    total_seen = 0
    skipped_type = 0
    skipped_junk = 0
    processed = 0
    succeeded = 0
    failed = 0
    errors: list[dict] = []
    results_buffer: list[dict] = []

    async def _process_one(raw_ticket: dict) -> dict | None:
        """Enrich and process a single ticket. Returns result or None on failure."""
        tid = raw_ticket.get("id")
        try:
            enriched = await enrich_from_paginated(raw_ticket)
            return await processor(enriched)
        except Exception as e:
            logger.warning(f"Failed ticket {tid}: {e}")
            return None

    async def _flush(buffer: list[dict]) -> None:
        if not buffer or on_flush is None:
            return
        try:
            await on_flush(buffer)
        except Exception as e:
            logger.error(f"Batch flush failed: {e}")

    semaphore = asyncio.Semaphore(concurrency) if concurrency > 1 else None

    async def _collect_concurrent(tickets: list[dict]) -> None:
        """Process a batch of tickets concurrently and update stats."""
        nonlocal processed, succeeded, failed

        assert semaphore is not None

        async def _bounded(t: dict) -> tuple[dict, dict | None]:
            async with semaphore:
                return t, await _process_one(t)

        batch_results = await asyncio.gather(*[_bounded(t) for t in tickets])
        for t, result in batch_results:
            t_id = t.get("id")
            processed += 1
            if result and result.get("success", True):
                results_buffer.append(result)
                succeeded += 1
            else:
                failed += 1
                errors.append({"ticket_id": t_id, "error": (result or {}).get("error", "processing failed")})

    # Collect pending tasks for concurrent mode
    pending_tickets: list[dict] = []

    async for raw_ticket in paginate_tickets(
        days_back=days_back,
        closed_only=closed_only,
        **paginate_kwargs,
    ):
        total_seen += 1
        tid = raw_ticket.get("id")
        if not tid:
            continue

        skip_reason = filter_fn(raw_ticket)
        if skip_reason:
            if skip_reason == "wrong_type":
                skipped_type += 1
            else:
                skipped_junk += 1
            continue

        if concurrency <= 1:
            # Sequential mode
            result = await _process_one(raw_ticket)
            processed += 1
            if result and result.get("success", True):
                results_buffer.append(result)
                succeeded += 1
            else:
                failed += 1
                if result:
                    errors.append({"ticket_id": tid, "error": result.get("error", "unknown")})
                else:
                    errors.append({"ticket_id": tid, "error": "processing failed"})
        else:
            # Concurrent mode — collect and process in batches
            pending_tickets.append(raw_ticket)
            if len(pending_tickets) >= concurrency:
                await _collect_concurrent(pending_tickets)
                pending_tickets = []

        # Flush buffer
        if len(results_buffer) >= buffer_size:
            await _flush(results_buffer)
            results_buffer = []
            logger.info(
                f"Progress: {processed} processed ({succeeded} ok, {failed} err) | "
                f"{total_seen} seen, {skipped_type} wrong type, {skipped_junk} junk"
            )

        # Limit check
        if max_tickets and processed >= max_tickets:
            logger.info(f"Reached max_tickets limit ({max_tickets})")
            break

        if len(errors) > 100:
            errors = errors[-50:]

    # Process remaining concurrent tickets
    if pending_tickets and concurrency > 1:
        await _collect_concurrent(pending_tickets)

    # Final flush
    await _flush(results_buffer)

    logger.info(
        f"Batch complete: {processed} processed, {succeeded} ok, {failed} err | "
        f"{total_seen} seen, {skipped_type} wrong type, {skipped_junk} junk"
    )

    return {
        "success": True,
        "ticket_collection": {
            "total_seen": total_seen,
            "skipped_wrong_type": skipped_type,
            "skipped_junk": skipped_junk,
        },
        "processing": {
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
        },
        "errors": errors[:20],
    }


# =============================================================================
# HaloPSA /Control Integration Mapping Helpers
# =============================================================================


async def upsert_control_mapping(
    module_id: int,
    field_name: str,
    new_mapping: dict,
    match_key: str = "third_party_id",
) -> dict:
    """
    Upsert an integration mapping in HaloPSA's /Control blob.

    The /Control API requires posting the ENTIRE mappings array — you cannot
    do partial updates. This helper:
    1. GETs the current control blob for the given integration module
    2. Checks if a mapping with the same match_key value already exists
    3. If not, appends the new mapping to the array
    4. POSTs the entire updated array back

    Args:
        module_id: Integration module ID (234=NinjaRMM, 301=Pax8)
        field_name: The blob field name (e.g. "ninja_sitemappings", "pax8_client_mappings")
        new_mapping: The mapping object to add
        match_key: Field in existing mappings to check for duplicates (default: "third_party_id")

    Returns:
        {"action": "created"|"already_exists", "mapping": dict}
    """
    import uuid as uuid_mod

    # 1. Fetch current control blob
    control = await halopsa.list_controls(
        integrationmoduleid=module_id,
        includeintegrationsettings=True,
    )

    # Extract existing mappings array — control response varies in shape
    existing = []
    if isinstance(control, list):
        for item in control:
            val = item.get(field_name) if isinstance(item, dict) else getattr(item, field_name, None)
            if val is not None:
                existing = list(val)
                break
    elif isinstance(control, dict) and field_name in control:
        existing = list(control[field_name] or [])
    elif hasattr(control, field_name):
        existing = list(getattr(control, field_name) or [])

    # 2. Check if mapping already exists
    match_value = str(new_mapping.get(match_key, ""))
    for m in existing:
        m_val = m.get(match_key) if isinstance(m, dict) else getattr(m, match_key, None)
        if str(m_val) == match_value:
            logger.info(f"Control mapping already exists for {field_name}[{match_key}={match_value}]")
            return {"action": "already_exists", "mapping": m}

    # 3. Add _temp_id if not present (Halo convention for new mappings)
    if "_temp_id" not in new_mapping:
        new_mapping["_temp_id"] = str(uuid_mod.uuid4())

    existing.append(new_mapping)

    # 4. POST entire blob back
    payload = [
        {
            "id": 1,
            field_name: existing,
            "includeintegrationsettings": True,
            "integrationmoduleid": module_id,
            "_integrationid": module_id,
        }
    ]
    await halopsa.create_control(payload)
    logger.info(f"Created control mapping for {field_name}[{match_key}={match_value}]")

    return {"action": "created", "mapping": new_mapping}


async def create_ninja_site_mapping(
    halo_client_id: int,
    halo_client_name: str,
    halo_site_id: int,
    halo_site_name: str,
    ninja_org_id: int,
    ninja_location_id: int,
    ninja_location_name: str,
) -> dict:
    """
    Create a NinjaRMM site mapping in Halo's /Control blob and update client/site records.

    NinjaRMM uses integration module 234 with blob field 'ninja_sitemappings'.
    Also updates the client and site records with the ninjarmmid field.
    """
    mapping = {
        "organization": {"label": halo_client_name, "value": str(ninja_org_id)},
        "site": {"label": ninja_location_name, "value": str(ninja_location_id)},
        "halo_id": str(halo_site_id),
        "halo_name": halo_site_name,
        "halosite": {"id": str(halo_site_id)},
        "module_id": 234,
        "third_party_client_id": str(ninja_org_id),
        "third_party_client_name": halo_client_name,
        "third_party_id": str(ninja_location_id),
        "third_party_name": ninja_location_name,
    }
    result = await upsert_control_mapping(234, "ninja_sitemappings", mapping)

    # Update the client record with ninjarmmid
    await halopsa.create_client([{"id": halo_client_id, "ninjarmmid": ninja_org_id}])
    logger.info(f"Updated Halo client {halo_client_id} with ninjarmmid={ninja_org_id}")

    # Update the site record with ninjarmmid (location ID)
    await halopsa.create_site([{"id": halo_site_id, "ninjarmmid": ninja_location_id}])
    logger.info(f"Updated Halo site {halo_site_id} with ninjarmmid={ninja_location_id}")

    return result


async def upsert_contact(
    org_id: str,
    email: str,
    first_name: str,
    last_name: str,
    title: str = "",
    phone: str = "",
    site_id: int | None = None,
) -> dict:
    """
    Create or update a HaloPSA contact (user) for a given org.

    Searches for an existing contact by email, including inactive users, to
    avoid creating duplicates during reactivation scenarios.

    - Active match found  → update name, title, phone
    - Inactive match found → skip and log a warning (reactivation is intentional)
    - No match found       → create new contact linked to the org's HaloPSA client

    Args:
        org_id: Bifrost organization ID (used to resolve HaloPSA client_id)
        email: Contact email address
        first_name: First name
        last_name: Last name
        title: Job title (optional)
        phone: Phone number (optional)
        site_id: HaloPSA site ID to assign the contact to (optional)

    Returns:
        {"id": int, "created": bool, "skipped_inactive": bool}
    """
    display_name = f"{first_name} {last_name}"

    # Search including inactive users to catch potential duplicates
    try:
        result = await halopsa.list_users(search=email, includeinactive=True)
        all_users = result.get("users", []) if isinstance(result, dict) else []
    except Exception as e:
        logger.warning(f"Failed to search HaloPSA users for {email}: {e}")
        all_users = []

    match = next(
        (u for u in all_users if u.get("emailaddress", "").lower() == email.lower()),
        None,
    )

    if match:
        if match.get("inactive"):
            logger.warning(
                f"Inactive HaloPSA contact found for {email} (ID: {match['id']}) — skipping to avoid unintended reactivation"
            )
            return {"id": match["id"], "created": False, "skipped_inactive": True}

        # Update existing active contact
        payload = {"id": match["id"], "name": display_name}
        if title:
            payload["jobtitle"] = title
        if phone:
            payload["phone"] = phone
        try:
            await halopsa.create_users([payload])
            logger.info(f"Updated HaloPSA contact {match['id']} for {email}")
        except Exception as e:
            logger.warning(f"Failed to update HaloPSA contact {match['id']}: {e}")
        return {"id": match["id"], "created": False, "skipped_inactive": False}

    # Create new contact linked to the org's HaloPSA client
    client_id = await resolve_client_id(org_id)
    payload = {
        "name": display_name,
        "firstname": first_name,
        "surname": last_name,
        "emailaddress": email,
        "client_id": client_id,
    }
    if title:
        payload["jobtitle"] = title
    if phone:
        payload["phone"] = phone
    if site_id:
        payload["site_id"] = site_id

    result = await halopsa.create_users([payload])
    if isinstance(result, list) and result:
        contact_id = result[0].get("id")
    elif isinstance(result, dict):
        contact_id = result.get("id")
    else:
        contact_id = None

    logger.info(f"Created HaloPSA contact {contact_id} for {email}")
    return {"id": contact_id, "created": True, "skipped_inactive": False}


async def create_pax8_company_mapping(
    halo_client_id: int,
    halo_client_name: str,
    pax8_company_id: str,
    pax8_company_name: str,
) -> dict:
    """
    Create a Pax8 company mapping in Halo's /Control blob.

    Pax8 uses integration module 301 with blob field 'pax8_client_mappings'.
    """
    mapping = {
        "pax8Client": {"id": pax8_company_id, "name": pax8_company_name},
        "haloClient": {"id": str(halo_client_id)},
        "halo_id": str(halo_client_id),
        "halo_desc": halo_client_name,
        "third_party_id": pax8_company_id,
        "third_party_desc": pax8_company_name,
        "third_party_url": f"https://app.pax8.com/companies/{pax8_company_id}?activeTab=Details",
        "table_id": 2,
        "module_id": 301,
    }
    return await upsert_control_mapping(301, "pax8_client_mappings", mapping)
