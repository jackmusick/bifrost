"""
Microsoft Exchange Online Client

Python client for Exchange Online REST API (PowerShell cmdlets via REST).
Uses the Exchange Admin API to run PowerShell commands like Get-Mailbox, Set-Mailbox, etc.

Uses GDAP delegated permissions (token exchange) for authentication. Application
permissions (client credentials) are not supported because Exchange requires
the service principal to have an Entra ID directory role (Exchange Administrator),
which requires Privileged Role Administrator GDAP role to assign.

Documentation: https://learn.microsoft.com/en-us/powershell/exchange/exchange-online-powershell-v2

Usage:
    from modules.microsoft import create_exchange_client

    # Create client for a Bifrost org
    exchange = await create_exchange_client(org_id="org-uuid")

    # Or for a specific tenant
    exchange = await create_exchange_client(tenant_id="customer-tenant-id")

    # Run PowerShell cmdlets
    mailboxes = exchange.invoke("Get-Mailbox", ResultSize="Unlimited")
    mailbox = exchange.invoke("Get-Mailbox", Identity="user@domain.com")
    exchange.invoke("Set-Mailbox", Identity="user@domain.com", DisplayName="New Name")
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ExchangeClient:
    """
    Client for Exchange Online REST API.

    Runs PowerShell cmdlets via the Exchange Admin REST API.
    """

    BASE_URL = "https://outlook.office365.com/adminapi/beta"

    def __init__(self, access_token: str, tenant_id: str):
        """
        Initialize Exchange Online client.

        Args:
            access_token: OAuth2 access token with Exchange.Manage scope
            tenant_id: Target tenant ID
        """
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def invoke(
        self,
        cmdlet: str,
        anchor_mailbox: str | None = None,
        **parameters: Any,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        Invoke an Exchange PowerShell cmdlet via REST API.

        Args:
            cmdlet: PowerShell cmdlet name (e.g., "Get-Mailbox", "Set-Mailbox")
            anchor_mailbox: Optional UPN to set as X-AnchorMailbox header.
                If not provided, uses the Identity parameter when present.
                This routes the request to the correct Exchange backend server.
            **parameters: Cmdlet parameters as keyword arguments

        Returns:
            Cmdlet output - typically a list of objects for Get- commands,
            single object or None for Set- commands.

        Raises:
            ExchangeError: If the API call or cmdlet fails

        Examples:
            mailboxes = exchange.invoke("Get-Mailbox", ResultSize="Unlimited")
            mailbox = exchange.invoke("Get-Mailbox", Identity="user@domain.com")
            exchange.invoke("Set-Mailbox", Identity="user@domain.com", DisplayName="New Name")
        """
        url = f"{self.BASE_URL}/{self.tenant_id}/InvokeCommand"

        body: dict[str, Any] = {
            "CmdletInput": {
                "CmdletName": cmdlet,
                "Parameters": {},
            }
        }

        for key, value in parameters.items():
            if value is not None:
                body["CmdletInput"]["Parameters"][key] = value

        # Set X-AnchorMailbox header to route to the correct Exchange backend.
        # Without this, cross-server cmdlets (e.g., Add-MailboxPermission on a
        # mailbox hosted on a different server) fail with "Cmdlet needs proxy".
        anchor = anchor_mailbox or parameters.get("Identity")
        headers = {}
        if anchor and isinstance(anchor, str) and "@" in anchor:
            headers["X-AnchorMailbox"] = f"UPN:{anchor}"

        logger.debug(
            "Invoking Exchange cmdlet",
            extra={"cmdlet": cmdlet, "tenant_id": self.tenant_id}
        )

        response = self.session.post(url, json=body, headers=headers, timeout=120)

        if response.status_code != 200:
            error_msg = self._parse_error(response)
            logger.error(
                "Exchange cmdlet failed",
                extra={
                    "cmdlet": cmdlet,
                    "status_code": response.status_code,
                    "error": error_msg,
                }
            )
            raise ExchangeError(
                cmdlet=cmdlet,
                error_code=str(response.status_code),
                message=error_msg or f"{response.status_code} {response.reason}",
            )

        data = response.json()

        # Check for cmdlet-level errors in response
        value = data.get("value", [])
        if value and isinstance(value[0], dict) and "Error" in value[0]:
            error = value[0].get("Error", {})
            raise ExchangeError(
                cmdlet=cmdlet,
                error_code=error.get("Code", "Unknown"),
                message=error.get("Message", "Unknown error"),
            )

        if len(value) == 1:
            return value[0]
        elif len(value) == 0:
            return None
        else:
            return value

    def _parse_error(self, response: requests.Response) -> str:
        """Parse error message from response."""
        try:
            data = response.json()
            if "error" in data:
                return data["error"].get("message", str(data["error"]))
            return response.text
        except Exception:
            return response.text

    def get_mailboxes(
        self,
        result_size: int | str = 100,
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get mailboxes from the tenant.

        Args:
            result_size: Max results ("Unlimited" for all)
            filter_expr: Optional filter expression

        Returns:
            List of mailbox objects
        """
        params: dict[str, Any] = {"ResultSize": result_size}
        if filter_expr:
            params["Filter"] = filter_expr

        result = self.invoke("Get-Mailbox", **params)
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        return result

    def get_mailbox(self, identity: str) -> dict[str, Any] | None:
        """
        Get a specific mailbox by identity.

        Args:
            identity: Email address, alias, or mailbox GUID

        Returns:
            Mailbox object or None if not found
        """
        try:
            result = self.invoke("Get-Mailbox", Identity=identity)
            if isinstance(result, dict):
                return result
            return None
        except ExchangeError as e:
            if e.error_code == "404":
                return None
            raise


class ExchangeError(Exception):
    """Error returned by Exchange cmdlet."""

    def __init__(self, cmdlet: str, error_code: str, message: str):
        self.cmdlet = cmdlet
        self.error_code = error_code
        self.message = message
        super().__init__(f"{cmdlet} failed: [{error_code}] {message}")


async def create_exchange_client(
    tenant_id: str | None = None,
    org_id: str | None = None,
) -> ExchangeClient:
    """
    Create an Exchange Online client.

    Factory function that handles token acquisition automatically.
    Uses GDAP delegated permissions (token exchange) via the Microsoft CSP integration.

    Note: Application permissions (client credentials) are not supported for Exchange
    because it requires the service principal to have an Entra ID directory role
    (Exchange Administrator), which needs Privileged Role Administrator to assign.

    Args:
        tenant_id: Customer tenant ID. Required if org_id not provided.
        org_id: Bifrost organization ID. If provided, looks up tenant_id
               from IntegrationMapping.

    Returns:
        Configured ExchangeClient instance

    Raises:
        ValueError: If neither tenant_id nor org_id is provided
        UserError: If integration not configured or tenant not linked

    Usage:
        from modules.microsoft import create_exchange_client

        # For a Bifrost org (looks up tenant from IntegrationMapping)
        exchange = await create_exchange_client(org_id="org-uuid")
        mailboxes = exchange.get_mailboxes()

        # For a specific tenant
        exchange = await create_exchange_client(tenant_id="abc123-...")
        mailbox = exchange.get_mailbox("user@domain.com")
    """
    from bifrost import integrations, UserError
    from .auth import get_exchange_token

    if not tenant_id and not org_id:
        raise ValueError("Either tenant_id or org_id must be provided")

    if not tenant_id:
        # Look up tenant from Microsoft integration mapping
        integration = await integrations.get("Microsoft", scope=org_id)
        if integration and integration.entity_id:
            tenant_id = integration.entity_id
        else:
            raise UserError(
                "No tenant linked to org. "
                "Use the Microsoft CSP app to link this organization."
            )

    access_token = await get_exchange_token(tenant_id)
    return ExchangeClient(access_token, tenant_id)
