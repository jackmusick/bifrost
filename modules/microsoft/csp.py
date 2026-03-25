"""
Microsoft Partner Center API Client

Python client for the Microsoft Partner Center API (CSP).
Used for listing customers, managing subscriptions, and granting application consents.

Documentation: https://learn.microsoft.com/en-us/partner-center/developer/partner-center-rest-api-reference

Enterprise Application IDs for Consent:
- Microsoft Graph: 00000003-0000-0000-c000-000000000000
- Exchange Online: 00000002-0000-0ff1-ce00-000000000000
- SharePoint Online: 00000003-0000-0ff1-ce00-000000000000
- Microsoft Defender ATP: fc780465-2017-40d4-a0c5-307022471b92
"""

import logging
from typing import Any

import requests

from bifrost import UserError

from .auth import get_partner_center_token

logger = logging.getLogger(__name__)


# Well-known Enterprise Application IDs
ENTERPRISE_APP_IDS = {
    "graph": "00000003-0000-0000-c000-000000000000",
    "exchange": "00000002-0000-0ff1-ce00-000000000000",
    "sharepoint": "00000003-0000-0ff1-ce00-000000000000",
    "defender": "fc780465-2017-40d4-a0c5-307022471b92",
}


class PartnerCenterClient:
    """
    Client for Microsoft Partner Center API.

    Used for managing customer tenants, subscriptions, and CPV consents.
    """

    BASE_URL = "https://api.partnercenter.microsoft.com/v1"

    def __init__(self, access_token: str):
        """
        Initialize Partner Center API client.

        Args:
            access_token: OAuth2 access token for Partner Center API.
                         Use create_csp_client() to obtain a configured client.
        """
        self.access_token = access_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request to Partner Center."""
        url = f"{self.BASE_URL}{path}"
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            timeout=60,
        )

        # Handle common error cases
        if response.status_code == 404:
            raise UserError(
                "No GDAP relationship found with this tenant. "
                "Please establish a GDAP relationship in Partner Center first."
            )
        if response.status_code == 403:
            raise UserError(
                "Insufficient GDAP permissions. "
                "Ensure your GDAP relationship includes required admin roles."
            )

        response.raise_for_status()

        if response.content:
            return response.json()
        return {}

    def _paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Paginate through a Partner Center list endpoint.

        Partner Center uses 'items' key and continuation tokens.
        """
        params = params or {}
        all_results: list[dict[str, Any]] = []
        page_count = 0

        while True:
            response = self._request("GET", path, params=params)

            items = response.get("items", [])
            all_results.extend(items)

            # Check for continuation
            links = response.get("links", {})
            next_link = links.get("next")

            if not next_link:
                break

            page_count += 1
            if max_pages and page_count >= max_pages:
                break

            # Extract continuation token from next link
            # Partner Center uses ?seek= parameter for continuation
            if "seek=" in str(next_link):
                seek_token = str(next_link).split("seek=")[-1].split("&")[0]
                params["seek"] = seek_token
            else:
                break

        return all_results

    # =========================================================================
    # Customers
    # =========================================================================

    def list_customers(self, max_pages: int | None = None) -> list[dict[str, Any]]:
        """
        List all customer tenants.

        Returns:
            List of customer objects with id, companyProfile, etc.
        """
        return self._paginate("/customers", max_pages=max_pages)

    def get_customer(self, tenant_id: str) -> dict[str, Any]:
        """
        Get customer details by tenant ID.

        Args:
            tenant_id: The customer's Entra tenant ID

        Returns:
            Customer object with id, companyProfile, billingProfile, etc.
        """
        return self._request("GET", f"/customers/{tenant_id}")

    # =========================================================================
    # Subscriptions
    # =========================================================================

    def list_subscriptions(
        self,
        tenant_id: str,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List subscriptions for a customer.

        Args:
            tenant_id: The customer's Entra tenant ID

        Returns:
            List of subscription objects
        """
        return self._paginate(f"/customers/{tenant_id}/subscriptions", max_pages=max_pages)

    def get_subscription(
        self,
        tenant_id: str,
        subscription_id: str,
    ) -> dict[str, Any]:
        """
        Get subscription details.

        Args:
            tenant_id: The customer's Entra tenant ID
            subscription_id: The subscription ID

        Returns:
            Subscription object
        """
        return self._request("GET", f"/customers/{tenant_id}/subscriptions/{subscription_id}")

    # =========================================================================
    # Application Consents (CPV)
    # =========================================================================



    def grant_consent(
        self,
        tenant_id: str,
        application_id: str,
        grants: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Grant application consent to a customer tenant via CPV.

        This installs your partner application's service principal in the customer
        tenant and grants the specified delegated permissions.

        Args:
            tenant_id: The customer's Entra tenant ID
            application_id: Your partner application ID (client_id)
            grants: List of permission grants, each with:
                - enterpriseApplicationId: The target resource app ID (e.g., Graph)
                - scope: Comma-separated scopes (e.g., "User.Read.All,Group.Read.All")

        Returns:
            The created consent object

        Raises:
            UserError: If consent already exists (409) or GDAP issues (403/404)

        Example:
            csp.grant_consent(
                tenant_id="customer-tenant-id",
                application_id="your-partner-app-client-id",
                grants=[
                    {
                        "enterpriseApplicationId": "00000003-0000-0000-c000-000000000000",
                        "scope": "Directory.Read.All,User.Read.All"
                    }
                ]
            )
        """
        body = {
            "applicationId": application_id,
            "applicationGrants": grants,
        }

        try:
            return self._request("POST", f"/customers/{tenant_id}/applicationconsents", json_body=body)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 409:
                # Consent already exists - this is not an error, just means it was already granted
                logger.info(
                    "Consent already exists",
                    extra={"tenant_id": tenant_id, "application_id": application_id}
                )
                return {"status": "already_exists"}
            raise



def build_consent_grants(
    *,
    graph_scopes: str | None = None,
    exchange_scopes: str | None = None,
    sharepoint_scopes: str | None = None,
    defender_scopes: str | None = None,
) -> list[dict[str, str]]:
    """
    Build consent grants list from scope strings.

    Helper function to construct the grants array for grant_consent().

    Args:
        graph_scopes: Comma-separated Graph API scopes (e.g., "User.Read.All,Group.Read.All")
        exchange_scopes: Comma-separated Exchange scopes (e.g., "Exchange.Manage")
        sharepoint_scopes: Comma-separated SharePoint scopes
        defender_scopes: Comma-separated Defender scopes

    Returns:
        List of grant dictionaries for grant_consent()

    Example:
        grants = build_consent_grants(
            graph_scopes="Directory.Read.All,User.Read.All",
            exchange_scopes="Exchange.Manage"
        )
    """
    grants: list[dict[str, str]] = []

    if graph_scopes:
        grants.append({
            "enterpriseApplicationId": ENTERPRISE_APP_IDS["graph"],
            "scope": graph_scopes.strip(),
        })

    if exchange_scopes:
        grants.append({
            "enterpriseApplicationId": ENTERPRISE_APP_IDS["exchange"],
            "scope": exchange_scopes.strip(),
        })

    if sharepoint_scopes:
        grants.append({
            "enterpriseApplicationId": ENTERPRISE_APP_IDS["sharepoint"],
            "scope": sharepoint_scopes.strip(),
        })

    if defender_scopes:
        grants.append({
            "enterpriseApplicationId": ENTERPRISE_APP_IDS["defender"],
            "scope": defender_scopes.strip(),
        })

    return grants


async def create_csp_client() -> PartnerCenterClient:
    """
    Create a Partner Center client.

    Factory function that handles token acquisition automatically.

    Usage:
        from modules.microsoft import create_csp_client

        csp = await create_csp_client()
        customers = csp.list_customers()

    Returns:
        Configured PartnerCenterClient instance
    """
    access_token = await get_partner_center_token()
    return PartnerCenterClient(access_token)
