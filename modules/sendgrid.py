"""
SendGrid Email API Client

Authentication: API Key
Docs: https://docs.sendgrid.com/api-reference

Required Secrets (global, not per-org):
- sendgrid_api_key: SendGrid API key with mail send permissions

Note: Simple wrapper focused on sending emails. For full API coverage,
consider using the official sendgrid-python package.
"""

from __future__ import annotations

import httpx
from typing import Any


class SendGridClient:
    """
    SendGrid API client for sending emails.

    Usage:
        client = SendGridClient(api_key="...")

        await client.send_email(
            to="recipient@example.com",
            from_email="sender@example.com",
            subject="Hello",
            html_content="<p>World</p>",
        )
    """

    BASE_URL = "https://api.sendgrid.com/v3"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        """Make a request to the SendGrid API."""
        client = await self._get_client()

        url = f"{self.BASE_URL}/{path.lstrip('/')}"

        response = await client.request(method, url, params=params, json=json)
        response.raise_for_status()

        if response.content:
            return response.json()
        return None

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # -------------------------------------------------------------------------
    # Email Sending
    # -------------------------------------------------------------------------

    async def send_email(
        self,
        to: str | list[str],
        from_email: str,
        subject: str,
        *,
        from_name: str | None = None,
        html_content: str | None = None,
        text_content: str | None = None,
        reply_to: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        attachments: list[dict] | None = None,
        template_id: str | None = None,
        dynamic_template_data: dict | None = None,
        categories: list[str] | None = None,
        custom_args: dict | None = None,
    ) -> dict | None:
        """
        Send an email via SendGrid.

        Args:
            to: Recipient email(s)
            from_email: Sender email address
            subject: Email subject
            from_name: Optional sender name
            html_content: HTML body (required if no template_id)
            text_content: Plain text body
            reply_to: Reply-to address
            cc: CC recipient(s)
            bcc: BCC recipient(s)
            attachments: List of attachment dicts with content, filename, type
            template_id: SendGrid dynamic template ID
            dynamic_template_data: Data for dynamic template
            categories: Email categories for tracking
            custom_args: Custom tracking arguments

        Returns:
            Response data (usually None for successful sends - 202 Accepted)
        """
        # Build recipient list
        def to_recipient_list(emails):
            if isinstance(emails, str):
                emails = [emails]
            return [{"email": email} for email in emails]

        personalizations = [{"to": to_recipient_list(to)}]

        if cc:
            personalizations[0]["cc"] = to_recipient_list(cc)
        if bcc:
            personalizations[0]["bcc"] = to_recipient_list(bcc)
        if dynamic_template_data:
            personalizations[0]["dynamic_template_data"] = dynamic_template_data

        # Build from address
        from_addr = {"email": from_email}
        if from_name:
            from_addr["name"] = from_name

        # Build payload
        payload = {
            "personalizations": personalizations,
            "from": from_addr,
            "subject": subject,
        }

        if reply_to:
            payload["reply_to"] = {"email": reply_to}

        if template_id:
            payload["template_id"] = template_id
        else:
            content = []
            if text_content:
                content.append({"type": "text/plain", "value": text_content})
            if html_content:
                content.append({"type": "text/html", "value": html_content})
            if content:
                payload["content"] = content

        if attachments:
            payload["attachments"] = attachments

        if categories:
            payload["categories"] = categories

        if custom_args:
            payload["custom_args"] = custom_args

        return await self._request("POST", "/mail/send", json=payload)

    async def send_template_email(
        self,
        to: str | list[str],
        from_email: str,
        template_id: str,
        template_data: dict,
        *,
        from_name: str | None = None,
        reply_to: str | None = None,
    ) -> dict | None:
        """
        Send an email using a SendGrid dynamic template.

        Args:
            to: Recipient email(s)
            from_email: Sender email address
            template_id: SendGrid dynamic template ID
            template_data: Data to populate the template
            from_name: Optional sender name
            reply_to: Reply-to address
        """
        return await self.send_email(
            to=to,
            from_email=from_email,
            subject="",  # Subject comes from template
            from_name=from_name,
            reply_to=reply_to,
            template_id=template_id,
            dynamic_template_data=template_data,
        )

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    async def validate_email(self, email: str) -> dict:
        """
        Validate an email address.

        Requires Email Validation API access (paid feature).
        """
        return await self._request(
            "POST",
            "/validations/email",
            json={"email": email},
        )


# Convenience function for use with Bifrost SDK
async def get_client() -> SendGridClient:
    """
    Get a SendGrid client configured from Bifrost secrets.

    Usage:
        from modules.sendgrid import get_client

        client = await get_client()
        await client.send_email(
            to="user@example.com",
            from_email="noreply@example.com",
            subject="Test",
            html_content="<p>Hello</p>",
        )
    """
    from bifrost import secrets

    return SendGridClient(
        api_key=await secrets.get("sendgrid_api_key"),
    )
