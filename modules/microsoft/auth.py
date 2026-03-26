"""
Microsoft Authentication Helpers

Handles GDAP refresh token exchange for tenant-specific access tokens.
Uses fresh token exchange each time (no caching) for simplicity and guaranteed freshness.

Token Exchange Flow:
1. Get GDAP OAuth credentials from integrations.get("Microsoft CSP")
2. Exchange refresh token for tenant-specific access token via OAuth2 token endpoint

Supported Token Types:
- Partner Center: scope=https://api.partnercenter.microsoft.com/.default
- Microsoft Graph: scope=https://graph.microsoft.com/.default
- Exchange Online: scope=https://outlook.office365.com/.default
"""

import logging
from typing import Any

import requests

from bifrost import config, integrations, UserError

logger = logging.getLogger(__name__)

# Integration names as configured in Bifrost
CSP_INTEGRATION_NAME = "Microsoft CSP"
MICROSOFT_INTEGRATION_NAME = "Microsoft"


class GDAPCredentials:
    """GDAP OAuth credentials for token exchange."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token


async def get_gdap_credentials() -> GDAPCredentials:
    """
    Get full GDAP OAuth credentials from Bifrost integrations (Microsoft CSP).

    Returns:
        GDAPCredentials: Object containing client_id, client_secret, and refresh_token

    Raises:
        UserError: If Microsoft CSP integration is not configured or missing required fields
    """
    integration = await integrations.get(CSP_INTEGRATION_NAME)
    if not integration:
        raise UserError(
            f"Microsoft CSP integration not configured. "
            f"Please set up the '{CSP_INTEGRATION_NAME}' integration in Settings."
        )

    oauth_data = integration.oauth
    if not oauth_data:
        raise UserError(
            f"Microsoft CSP integration is missing OAuth configuration. "
            f"Please complete the OAuth setup for '{CSP_INTEGRATION_NAME}'."
        )

    client_id = oauth_data.client_id
    client_secret = oauth_data.client_secret
    refresh_token = oauth_data.refresh_token

    if not client_id:
        raise UserError(
            "Microsoft CSP OAuth is missing client_id. "
            "Please check the integration configuration."
        )
    if not client_secret:
        raise UserError(
            "Microsoft CSP OAuth is missing client_secret. "
            "Please check the integration configuration."
        )
    if not refresh_token:
        raise UserError(
            "Microsoft CSP OAuth is missing refresh_token. "
            "Please re-authenticate the integration."
        )

    return GDAPCredentials(client_id, client_secret, refresh_token)


class MicrosoftAppCredentials:
    """Microsoft app credentials for client credentials flow."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret


async def get_microsoft_app_credentials() -> MicrosoftAppCredentials:
    """
    Get Microsoft app credentials from Bifrost integrations.

    This is the separate "Bifrost Microsoft" app used for client credentials
    access to customer tenants. Different from CSP app which uses delegated flow.

    Returns:
        MicrosoftAppCredentials: Object containing client_id and client_secret

    Raises:
        UserError: If Microsoft integration is not configured or missing required fields
    """
    integration = await integrations.get(MICROSOFT_INTEGRATION_NAME, scope="global")
    if not integration:
        raise UserError(
            f"Microsoft integration not configured. "
            f"Please set up the '{MICROSOFT_INTEGRATION_NAME}' integration in Settings."
        )

    oauth_data = integration.oauth
    if not oauth_data:
        raise UserError(
            f"Microsoft integration is missing OAuth configuration. "
            f"Please complete the OAuth setup for '{MICROSOFT_INTEGRATION_NAME}'."
        )

    client_id = oauth_data.client_id
    client_secret = oauth_data.client_secret

    if not client_id:
        raise UserError(
            "Microsoft OAuth is missing client_id. "
            "Please check the integration configuration."
        )
    if not client_secret:
        raise UserError(
            "Microsoft OAuth is missing client_secret. "
            "Please check the integration configuration."
        )

    return MicrosoftAppCredentials(client_id, client_secret)


async def exchange_for_token(tenant_id: str, scope: str) -> str:
    """
    Exchange GDAP refresh token for a tenant-specific access token.

    Performs fresh token exchange every time (no caching).

    Args:
        tenant_id: The target tenant ID (customer tenant or 'common' for Partner Center)
        scope: The OAuth scope to request (e.g., "https://graph.microsoft.com/.default")

    Returns:
        str: Access token for the requested scope and tenant

    Raises:
        UserError: If GDAP or partner app is not configured
        requests.HTTPError: If token exchange fails
    """
    creds = await get_gdap_credentials()

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    logger.debug(
        "Exchanging GDAP token",
        extra={"tenant_id": tenant_id, "scope": scope}
    )

    try:
        response = requests.post(
            token_url,
            data={
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": creds.refresh_token,
                "scope": scope,
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.HTTPError as e:
        # Log full error details for debugging
        error_data = None
        if e.response is not None:
            error_data = _parse_oauth_error(e.response)
            logger.error(
                "Token exchange failed",
                extra={
                    "tenant_id": tenant_id,
                    "scope": scope,
                    "status_code": e.response.status_code,
                    "error_data": error_data,
                }
            )

        if error_data:
            error_code = error_data.get("error", "")
            error_desc = error_data.get("error_description", "")
            correlation_id = error_data.get("correlation_id", "")

            # Always include full error details
            detail_msg = f"\n\nError: {error_code}\nDescription: {error_desc}"
            if correlation_id:
                detail_msg += f"\nCorrelation ID: {correlation_id}"

            if "invalid_grant" in error_code:
                raise UserError(
                    f"GDAP refresh token error. {detail_msg}"
                ) from e
            if "unauthorized_client" in error_code:
                raise UserError(
                    f"Partner app authorization error. {detail_msg}"
                ) from e

            # Generic OAuth error with full details
            raise UserError(f"Token exchange failed. {detail_msg}") from e

        raise

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        raise UserError(
            "Token exchange succeeded but no access_token returned.")

    return access_token


def _parse_oauth_error(response: requests.Response) -> dict[str, Any] | None:
    """Parse OAuth error response."""
    try:
        return response.json()
    except (ValueError, requests.JSONDecodeError):
        return None


async def get_partner_center_token() -> str:
    """
    Get access token for Partner Center API.

    Returns:
        str: Access token for Partner Center API
    """
    return await exchange_for_token(
        tenant_id="common",
        scope="https://api.partnercenter.microsoft.com/.default"
    )


async def get_graph_token(tenant_id: str) -> str:
    """
    Get access token for Microsoft Graph API for a specific tenant.

    Args:
        tenant_id: The customer's Entra tenant ID

    Returns:
        str: Access token for Graph API in the specified tenant
    """
    return await exchange_for_token(
        tenant_id=tenant_id,
        scope="https://graph.microsoft.com/.default"
    )


async def get_exchange_token(tenant_id: str) -> str:
    """
    Get access token for Exchange Online for a specific tenant.

    Args:
        tenant_id: The customer's Entra tenant ID

    Returns:
        str: Access token for Exchange Online in the specified tenant
    """
    return await exchange_for_token(
        tenant_id=tenant_id,
        scope="https://outlook.office365.com/.default"
    )


async def get_current_org_tenant_id() -> str:
    """
    Get the Entra tenant ID for the current Bifrost organization.

    Reads from config.get("entra_tenant_id") for the current org context.

    Returns:
        str: The linked Entra tenant ID

    Raises:
        UserError: If no tenant is linked to the current organization
    """
    tenant_id = await config.get("entra_tenant_id")
    if not tenant_id:
        raise UserError(
            "No Entra tenant linked to this organization. "
            "Use the Microsoft CSP app to link your organization."
        )
    return tenant_id
