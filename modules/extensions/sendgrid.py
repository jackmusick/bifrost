"""
SendGrid Extension

Higher-level helpers built on top of the auto-generated SendGrid module.
Pulls credentials from the 'SendGrid' integration config (api_key, default_sender_address)
and exposes a simple send_email function for use across workflows.
"""

from __future__ import annotations

import logging
from modules.sendgrid import SendGridClient

logger = logging.getLogger(__name__)

INTEGRATION_NAME = "SendGrid"


async def _get_client() -> tuple[SendGridClient, str]:
    """
    Build a SendGridClient from the Bifrost integration config.

    Returns:
        Tuple of (SendGridClient, default_sender_address)

    Raises:
        RuntimeError: If the integration is missing or misconfigured
    """
    from bifrost import integrations

    integration = await integrations.get(INTEGRATION_NAME)
    if not integration:
        raise RuntimeError(
            f"'{INTEGRATION_NAME}' integration not found. "
            "Set it up in Settings with api_key and default_sender_address."
        )

    cfg = integration.config or {}

    api_key = cfg.get("api_key")
    if not api_key:
        raise RuntimeError(
            f"'{INTEGRATION_NAME}' integration is missing api_key in config."
        )

    default_sender = cfg.get("default_sender_address", "")

    return SendGridClient(api_key=api_key), default_sender


async def send_email(
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    *,
    from_email: str | None = None,
    from_name: str | None = None,
    reply_to: str | None = None,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
) -> dict | None:
    """
    Send an email via SendGrid using the platform integration.

    Uses the integration's default_sender_address if from_email is not provided.
    Sends plain text body, and optionally an HTML version.

    Args:
        recipient: Recipient email address
        subject: Email subject line
        body: Plain text body (always sent)
        html_body: Optional HTML body (sent alongside plain text if provided)
        from_email: Sender address (falls back to integration default)
        from_name: Optional display name for the sender
        reply_to: Optional reply-to address
        cc: Optional CC recipient(s)
        bcc: Optional BCC recipient(s)

    Returns:
        SendGrid API response (typically None on success - 202 Accepted)

    Raises:
        RuntimeError: If integration is not configured
        httpx.HTTPStatusError: If SendGrid rejects the request
    """
    client, default_sender = await _get_client()

    sender = from_email or default_sender
    if not sender:
        raise RuntimeError(
            f"No sender address provided and '{INTEGRATION_NAME}' integration "
            "has no default_sender_address configured."
        )

    logger.info(f"Sending email to {recipient} | subject: {subject!r} | from: {sender}")

    try:
        result = await client.send_email(
            to=recipient,
            from_email=sender,
            subject=subject,
            from_name=from_name,
            text_content=body,
            html_content=html_body,
            reply_to=reply_to,
            cc=cc,
            bcc=bcc,
        )
        logger.info(f"Email sent successfully to {recipient}")
        return result
    finally:
        await client.close()
