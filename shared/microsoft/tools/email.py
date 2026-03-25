"""
Shared Microsoft Graph Email Tools

Reusable email tools that work for any Bifrost org with a Microsoft integration.
Auto-resolves the caller from execution context to determine which mailbox to query.

For the provider org, uses the global Microsoft integration.
For customer orgs, uses their org-scoped Microsoft integration mapping.

Graph API reference: https://learn.microsoft.com/en-us/graph/api/user-list-messages
"""

import logging
from typing import Optional

from bifrost import tool, context, UserError
from modules.microsoft import create_graph_client

logger = logging.getLogger(__name__)

# Configure with your Bifrost platform/provider organization ID
PLATFORM_ORG_ID = ""  # e.g., "00000000-0000-0000-0000-000000000002"


async def _get_graph_and_email() -> tuple:
    """Get a Graph client and the caller's email address.

    Uses the execution context to determine the org and caller.
    Returns (GraphClient, email_address).
    """
    email = getattr(context, "email", None)
    if not email:
        raise UserError("Could not determine your email from the execution context.")

    org_id = getattr(context, "org_id", None) or PLATFORM_ORG_ID

    try:
        graph = await create_graph_client(org_id=org_id)
    except Exception as e:
        raise UserError(f"Failed to create Graph client: {e}")

    return graph, email


def _format_email(msg: dict) -> dict:
    """Extract compact email metadata for display. No body content."""
    from_addr = msg.get("from", {}).get("emailAddress", {})
    to_list = [
        r.get("emailAddress", {}).get("address", "")
        for r in msg.get("toRecipients", [])
    ]
    cc_list = [
        r.get("emailAddress", {}).get("address", "")
        for r in msg.get("ccRecipients", [])
    ]

    return {
        "id": msg.get("id"),
        "subject": msg.get("subject", ""),
        "from_name": from_addr.get("name", ""),
        "from_email": from_addr.get("address", ""),
        "to": to_list,
        "cc": cc_list if cc_list else None,
        "received": msg.get("receivedDateTime", ""),
        "sent": msg.get("sentDateTime", ""),
        "is_read": msg.get("isRead"),
        "has_attachments": msg.get("hasAttachments", False),
        "importance": msg.get("importance", "normal"),
        "conversation_id": msg.get("conversationId"),
    }


@tool(
    description=(
        "List emails from your mailbox. Searches inbox by default, or sent items, "
        "or all folders. Filter by date range, sender, or search query. Returns "
        "email metadata only (subject, from, to, timestamps) without message bodies "
        "to keep responses compact. Use get_email with a message ID to read the full "
        "content. The caller's mailbox is resolved automatically from your login. "
        "Works for any Bifrost org with a Microsoft integration."
    ),
)
async def list_emails(
    folder: str = "inbox",
    after: Optional[str] = None,
    before: Optional[str] = None,
    sender: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 15,
) -> dict:
    """List emails from the caller's mailbox.

    Args:
        folder: Which folder to search. "inbox", "sent", or "all". Default "inbox".
        after: Only emails after this ISO datetime, e.g. "2026-03-19T00:00:00Z".
        before: Only emails before this ISO datetime.
        sender: Filter by sender email address (partial match).
        search: Free text search across subject and body.
        limit: Max emails to return (capped at 50). Default 15.
    """
    graph, email = await _get_graph_and_email()
    limit = min(limit, 50)

    params = {
        "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,isRead,hasAttachments,importance,conversationId",
        "$top": limit,
        "$orderby": "receivedDateTime desc",
    }

    # Build filter clauses
    filters = []
    if after:
        filters.append(f"receivedDateTime ge {after}")
    if before:
        filters.append(f"receivedDateTime le {before}")
    if sender:
        filters.append(f"from/emailAddress/address eq '{sender}'")

    if filters:
        params["$filter"] = " and ".join(filters)

    if search:
        params["$search"] = f'"{search}"'
        # Graph API doesn't allow $orderby with $search
        del params["$orderby"]

    # Determine endpoint based on folder
    if folder == "sent":
        endpoint = f"/users/{email}/mailFolders/sentitems/messages"
    elif folder == "all":
        endpoint = f"/users/{email}/messages"
    else:
        endpoint = f"/users/{email}/mailFolders/inbox/messages"

    try:
        result = graph.get(endpoint, params=params)
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "Authorization" in error_str:
            raise UserError(
                "Mail access denied. The Microsoft integration may not have "
                "Mail.Read permissions for this tenant."
            )
        raise UserError(f"Failed to fetch emails: {e}")

    messages = result.get("value", [])

    return {
        "email": email,
        "folder": folder,
        "emails": [_format_email(m) for m in messages],
        "count": len(messages),
    }


@tool(
    description=(
        "Get the full content of a specific email by message ID. Use this after "
        "list_emails to read the body of a specific message. Returns the full "
        "email including body text, all recipients, and attachment names."
    ),
)
async def get_email(
    message_id: str,
) -> dict:
    """Fetch a single email's full content.

    Args:
        message_id: The Graph message ID (from list_emails results).
    """
    graph, email = await _get_graph_and_email()

    try:
        msg = graph.get(
            f"/users/{email}/messages/{message_id}",
            params={
                "$select": "id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,sentDateTime,body,bodyPreview,hasAttachments,attachments,importance,conversationId,isRead",
            },
        )
    except Exception as e:
        raise UserError(f"Failed to fetch email: {e}")

    from_addr = msg.get("from", {}).get("emailAddress", {})
    to_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("toRecipients", [])]
    cc_list = [r.get("emailAddress", {}).get("address", "") for r in msg.get("ccRecipients", [])]

    # Extract body as plain text preview to avoid HTML noise
    body = msg.get("bodyPreview", "") or ""
    body_full = msg.get("body", {})
    if body_full.get("contentType") == "text":
        body = body_full.get("content", body)

    # Attachment names only (no content)
    attachments = []
    for att in msg.get("attachments", []):
        attachments.append({
            "name": att.get("name", ""),
            "size": att.get("size", 0),
            "content_type": att.get("contentType", ""),
        })

    return {
        "id": msg.get("id"),
        "subject": msg.get("subject", ""),
        "from_name": from_addr.get("name", ""),
        "from_email": from_addr.get("address", ""),
        "to": to_list,
        "cc": cc_list if cc_list else None,
        "received": msg.get("receivedDateTime", ""),
        "sent": msg.get("sentDateTime", ""),
        "body": body,
        "attachments": attachments if attachments else None,
        "is_read": msg.get("isRead"),
        "importance": msg.get("importance", "normal"),
    }


@tool(
    description=(
        "Send an email from your Microsoft 365 mailbox via Graph API. Sends as "
        "the calling user (resolved from your login). Works for any Bifrost org "
        "with a Microsoft integration that has Mail.Send permissions. "
        "Supports to, cc, bcc recipients, HTML body, and importance."
    ),
)
async def send_outlook_email(
    to: list[str],
    subject: str,
    body: str,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    importance: str = "normal",
    save_to_sent: bool = True,
) -> dict:
    """Send an email from the caller's mailbox.

    Args:
        to: List of recipient email addresses.
        subject: Email subject line.
        body: Email body (HTML supported).
        cc: Optional list of CC recipient email addresses.
        bcc: Optional list of BCC recipient email addresses.
        importance: "low", "normal", or "high". Default "normal".
        save_to_sent: If True (default), saves a copy in Sent Items.
    """
    if not to:
        raise UserError("At least one recipient is required.")
    if not subject.strip():
        raise UserError("Subject is required.")
    if not body.strip():
        raise UserError("Body is required.")

    graph, email = await _get_graph_and_email()

    def _recipient(addr: str) -> dict:
        return {"emailAddress": {"address": addr}}

    message = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body,
        },
        "toRecipients": [_recipient(a) for a in to],
        "importance": importance,
    }

    if cc:
        message["ccRecipients"] = [_recipient(a) for a in cc]
    if bcc:
        message["bccRecipients"] = [_recipient(a) for a in bcc]

    payload = {
        "message": message,
        "saveToSentItems": save_to_sent,
    }

    try:
        graph.post(f"/users/{email}/sendMail", payload)
    except Exception as e:
        error_str = str(e)
        if "403" in error_str or "Authorization" in error_str:
            raise UserError(
                "Mail send denied. The Microsoft integration may not have "
                "Mail.Send permissions for this tenant."
            )
        raise UserError(f"Failed to send email: {e}")

    return {
        "sent": True,
        "from": email,
        "to": to,
        "cc": cc,
        "subject": subject,
    }
