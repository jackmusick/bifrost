"""
Email SDK for Bifrost.

Provides async Python API for sending emails via the platform's
configured email workflow.

Usage:
    from bifrost import email

    result = await email.send(
        recipient="user@example.com",
        subject="Welcome!",
        body="Hello from Bifrost",
    )
"""

from .client import get_client, raise_for_status_with_detail
from ._context import resolve_scope


class email:
    """
    Email sending operations (async).

    Sends emails via the platform's configured email workflow.
    The email workflow must be configured by a platform admin
    in Settings > Email.
    """

    @staticmethod
    async def send(
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> dict:
        """
        Send an email via the configured email workflow.

        Args:
            recipient: Email address of the recipient
            subject: Email subject line
            body: Plain text email body
            html_body: Optional HTML email body

        Returns:
            dict with keys: success (bool), execution_id (str | None), error (str | None)

        Example:
            >>> from bifrost import email
            >>> result = await email.send(
            ...     recipient="user@example.com",
            ...     subject="Invoice Ready",
            ...     body="Your invoice is ready for download.",
            ... )
            >>> if not result["success"]:
            ...     print(f"Failed: {result['error']}")
        """
        client = get_client()
        scope = resolve_scope(None)
        response = await client.post(
            "/api/email/send",
            json={
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "scope": scope,
            },
        )
        raise_for_status_with_detail(response)
        return response.json()
