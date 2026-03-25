"""
AutoElevate Agent Tools

Tools for the AutoElevate Approval Agent. Each tool bundles multiple
operations so the agent makes fewer decisions.
"""

from __future__ import annotations

import logging

from bifrost import workflow, config

logger = logging.getLogger(__name__)

# Email template IDs for HaloPSA notifications — configure to match your templates
APPROVAL_EMAIL_TEMPLATE = config.get("autoelevate_approval_email_template_id", -148)
DENIAL_EMAIL_TEMPLATE = config.get("autoelevate_denial_email_template_id", -145)


@workflow(
    category="AutoElevate",
    tags=["autoelevate", "agent"],
    is_tool=True,
    tool_description=(
        "Fetch the current AutoElevate approval policy. "
        "Returns the full policy document including approved vendors, "
        "approved software lists, and review guidelines. Call this before "
        "making any approval decision."
    ),
)
async def get_approval_policy() -> dict:
    """Fetch the approval policy from Bifrost config.

    Set the 'autoelevate_approval_policy' config value with your organization's
    approval policy text (approved vendors, software lists, review guidelines).
    """
    policy_text = config.get("autoelevate_approval_policy", "")
    if not policy_text:
        return {
            "error": (
                "No approval policy configured. Set 'autoelevate_approval_policy' "
                "in your Bifrost config with your organization's approval policy."
            )
        }
    return {"title": "AutoElevate Approval Policy", "policy": policy_text}


async def _match_user_and_update_ticket(ticket_id: int, ae_request: dict) -> dict | None:
    """
    Match the AutoElevate user to a HaloPSA user and update the ticket.

    AutoElevate provides a username (e.g., "araya.jones"). We match it against
    HaloPSA users for the ticket's client by comparing against:
    - emailaddress prefix (before @)
    - firstname + surname concatenation

    If matched, updates the ticket's user_id so emails can be sent.
    Returns the matched user dict or None.
    """
    from modules import halopsa
    from modules.extensions.halopsa import normalize_halo_result

    # Extract AE username from request
    event = ae_request.get("event", {})
    event_data = event.get("data", {}) if isinstance(event, dict) else {}
    ae_user = event_data.get("user", {})
    username = (ae_user.get("name") or "").lower() if isinstance(ae_user, dict) else ""

    if not username:
        logger.warning("No username found in AutoElevate request")
        return None

    # Get the ticket to find the client_id
    ticket = await halopsa.get_tickets(str(ticket_id))
    t = ticket if isinstance(ticket, dict) else dict(ticket)
    client_id = t.get("client_id")

    if not client_id:
        logger.warning(f"No client_id on ticket {ticket_id}")
        return None

    # List users for this client
    result = await halopsa.list_users(client_id=client_id, includeactive=True, includeinactive=False)
    users = result.get("users", []) if isinstance(result, dict) else []

    # Match by email prefix or firstname+surname
    matched_user = None
    for user in users:
        u = normalize_halo_result(user)
        email = (u.get("emailaddress") or "").lower()
        email_prefix = email.split("@")[0] if email else ""
        fullname = ((u.get("firstname") or "") + (u.get("surname") or "")).lower()

        if username == email_prefix or username == fullname:
            matched_user = u
            break

    if not matched_user:
        logger.warning(f"Could not match AE user '{username}' to HaloPSA user for client {client_id}")
        return None

    logger.info(f"Matched AE user '{username}' -> HaloPSA user {matched_user.get('id')} ({matched_user.get('name')})")

    # Update the ticket with the matched user
    await halopsa.create_tickets([{
        "id": ticket_id,
        "user_id": matched_user["id"],
    }])
    logger.info(f"Updated ticket {ticket_id} with user_id {matched_user['id']}")

    return matched_user


@workflow(
    category="AutoElevate",
    tags=["autoelevate", "agent"],
    is_tool=True,
    tool_description=(
        "Look up the AutoElevate elevation request linked to a HaloPSA ticket. "
        "Returns the full request details including file info, certificates, "
        "virus scan results, user info, and approval state. Call this first "
        "to get the request_id and details you need to make a decision."
    ),
)
async def get_elevation_request(ticket_id: int) -> dict:
    """
    Find the AutoElevate request matching a HaloPSA ticket ID.

    Args:
        ticket_id: HaloPSA ticket ID
    """
    from modules import autoelevate

    requests = await autoelevate.list_requests(take=500)
    for req in requests:
        r = req if isinstance(req, dict) else dict(req)
        ticketing_info = r.get("ticketingSystemInfo")
        if isinstance(ticketing_info, dict):
            ae_ticket_id = ticketing_info.get("ticketId") or ticketing_info.get("ticket_id")
            if ae_ticket_id is not None and int(ae_ticket_id) == ticket_id:
                # Fetch full details (single-get has more data than list)
                full = await autoelevate.get_request(r["id"])
                return full if full else r

    return {"error": f"No AutoElevate request found matching ticket #{ticket_id}"}


@workflow(
    category="AutoElevate",
    tags=["autoelevate", "agent"],
    is_tool=True,
    tool_description=(
        "Approve an AutoElevate elevation request. Optionally creates a rule "
        "to auto-approve future identical requests at the specified scope. "
        "Matches the AutoElevate user to HaloPSA, updates the ticket contact, "
        "adds a note, sends an approval email, and closes the ticket."
    ),
)
async def approve_request(
    request_id: str,
    explanation: str,
    create_rule: bool = False,
    rule_level: str = "none",
    ticket_id: int | None = None,
) -> dict:
    """
    Approve an elevation request and record the decision.

    Args:
        request_id: AutoElevate request ID
        explanation: Your reasoning for approving (shown to techs in ticket note)
        create_rule: Whether to create a rule for future identical requests
        rule_level: Rule scope — "msp" (global), "company", or "computer". Ignored if create_rule is False.
        ticket_id: HaloPSA ticket ID to add a note to (if known)
    """
    from modules import autoelevate
    from modules.extensions.halopsa import create_note

    # Get the full request so we can match the user
    ae_request = await autoelevate.get_request(request_id)

    # Match user and update ticket before doing anything else
    if ticket_id and ae_request:
        await _match_user_and_update_ticket(ticket_id, ae_request)

    # Approve in AutoElevate
    json_body = {
        "createRule": create_rule,
        "ruleLevel": rule_level if create_rule and rule_level != "none" else None,
        "elevationType": "user",
    }
    result = await autoelevate.approve_request(request_id, json_body=json_body)
    logger.info(f"Approved request {request_id} (create_rule={create_rule}, rule_level={rule_level})")

    # Update rule notes if a rule was created
    rule_id = None
    if create_rule and isinstance(result, dict):
        rule_id = result.get("ruleId") or result.get("rule_id")
        if rule_id:
            note_text = f"Ticket #{ticket_id}\n\n{explanation}" if ticket_id else explanation
            await autoelevate.update_rule(rule_id, json_body={"notes": note_text})
            logger.info(f"Updated rule {rule_id} notes")

    # Add ticket note + send approval email + close
    if ticket_id:
        rule_link = f'<br><a href="https://msp.autoelevate.com/elevation-rules/{rule_id}/edit">View Rule</a>' if rule_id else ""
        note_html = (
            f"This request has been <b>approved</b>.<br><br>"
            f"<p>{explanation}</p>"
            f"{rule_link}"
        )
        await create_note(
            ticket_id, note_html,
            is_complete=True,
            close_ticket=True,
            send_email=True,
            email_template_id=APPROVAL_EMAIL_TEMPLATE,
        )

    return {
        "approved": True,
        "request_id": request_id,
        "rule_created": create_rule,
        "rule_level": rule_level if create_rule else None,
        "rule_id": rule_id,
        "ticket_id": ticket_id,
    }


@workflow(
    category="AutoElevate",
    tags=["autoelevate", "agent"],
    is_tool=True,
    tool_description=(
        "Deny (escalate) an AutoElevate elevation request. This does NOT "
        "call the AutoElevate deny API — instead it leaves the request pending "
        "for a human tech to review. Matches the user to HaloPSA, updates the "
        "ticket contact, adds a note, and sends a denial email. The ticket is "
        "left open for dispatch."
    ),
)
async def deny_request(
    request_id: str,
    explanation: str,
    ticket_id: int | None = None,
) -> dict:
    """
    Deny/escalate an elevation request for human review.

    Does NOT call the AutoElevate deny API. Leaves the request pending so a
    tech can manually approve or deny it. Sends the user an email and adds
    a note for the tech.

    Args:
        request_id: AutoElevate request ID
        explanation: Your reasoning for denying (shown to techs in ticket note)
        ticket_id: HaloPSA ticket ID to add a note to and send email from (if known)
    """
    from modules import autoelevate
    from modules.extensions.halopsa import create_note

    # Get the full request so we can match the user
    ae_request = await autoelevate.get_request(request_id)

    # Match user and update ticket before doing anything else
    if ticket_id and ae_request:
        await _match_user_and_update_ticket(ticket_id, ae_request)

    logger.info(f"Denied/escalated request {request_id}")

    # Add ticket note + send denial email (ticket stays open)
    if ticket_id:
        ae_link = f'https://msp.autoelevate.com/elevation-requests/{request_id}'
        note_html = (
            f"This request has been <b>denied</b> by automated review.<br><br>"
            f"<p>{explanation}</p><br>"
            f"<p>Since this request was not approved, no automatic action was taken. "
            f"A tech should reach out to the user to learn more about their request, "
            f'or take manual action <a href="{ae_link}">here</a>.</p>'
        )
        await create_note(
            ticket_id, note_html,
            is_complete=True,
            close_ticket=False,
            send_email=True,
            email_template_id=DENIAL_EMAIL_TEMPLATE,
        )

    return {
        "approved": False,
        "request_id": request_id,
        "ticket_id": ticket_id,
        "escalated": True,
    }
