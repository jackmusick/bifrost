"""
Pax8 API Client

Python client for interacting with the Pax8 Partner API.
Documentation: https://devx.pax8.com/reference

Authentication uses OAuth2 via Bifrost's OAuth SDK.
"""

from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum
import requests


class BillingTerm(str, Enum):
    """Valid billing terms for Pax8 subscriptions and orders."""
    MONTHLY = "Monthly"
    ANNUAL = "Annual"
    TWO_YEAR = "2-Year"
    THREE_YEAR = "3-Year"
    ONE_TIME = "1-Time"
    TRIAL = "Trial"


@dataclass
class Address:
    """Company address structure."""
    street: str
    city: str
    state_or_province: str
    postal_code: str
    country: str
    street2: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            "street": self.street,
            "city": self.city,
            "stateOrProvince": self.state_or_province,
            "postalCode": self.postal_code,
            "country": self.country,
        }
        if self.street2:
            result["street2"] = self.street2
        return result


@dataclass
class OrderLineItem:
    """Line item for creating orders."""
    product_id: str
    quantity: int
    billing_term: BillingTerm
    provision_start_date: str  # Format: YYYY-MM-DD
    line_item_number: int = 1
    commitment_term_id: Optional[str] = None
    provisioning_details: Optional[list[dict]] = None
    parent_line_item_number: Optional[int] = None
    parent_subscription_id: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            "productId": self.product_id,
            "quantity": self.quantity,
            "billingTerm": self.billing_term.value if isinstance(self.billing_term, BillingTerm) else self.billing_term,
            "provisionStartDate": self.provision_start_date,
            "lineItemNumber": self.line_item_number,
        }
        if self.commitment_term_id:
            result["commitmentTermId"] = self.commitment_term_id
        if self.provisioning_details:
            result["provisioningDetails"] = self.provisioning_details
        if self.parent_line_item_number:
            result["parentLineItemNumber"] = self.parent_line_item_number
        if self.parent_subscription_id:
            result["parentSubscriptionId"] = self.parent_subscription_id
        return result


class Pax8Client:
    """Client for Pax8 Partner API."""

    BASE_URL = "https://api.pax8.com/v1"

    def __init__(self, access_token: str):
        """
        Initialize Pax8 API client.

        Args:
            access_token: OAuth2 access token for authentication.
                         Use Bifrost's oauth.get_token("pax8") to obtain this.
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
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """Make an API request."""
        url = f"{self.BASE_URL}{path}"
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            body = ""
            if e.response is not None:
                try:
                    body = e.response.json()
                except Exception:
                    body = e.response.text[:1000]
            raise requests.exceptions.HTTPError(
                f"HTTP {e.response.status_code} {method} {path}: {body}",
                response=e.response,
            ) from e
        if response.content:
            return response.json()
        return {}

    def _paginate(
        self,
        path: str,
        params: Optional[dict] = None,
        page_size: int = 100,
        max_pages: Optional[int] = None,
    ) -> list[dict]:
        """Paginate through a list endpoint."""
        params = params or {}
        params["size"] = page_size
        all_results = []
        page = 0

        while True:
            params["page"] = page
            response = self._request("GET", path, params=params)

            # Handle paginated response structure
            content = response.get("content", [])
            if not content:
                break

            all_results.extend(content)

            # Check if there are more pages
            total_pages = response.get("totalPages", 1)
            page += 1

            if page >= total_pages:
                break
            if max_pages and page >= max_pages:
                break

        return all_results

    # =========================================================================
    # Companies
    # =========================================================================

    def list_companies(
        self,
        *,
        city: Optional[str] = None,
        country: Optional[str] = None,
        state_or_province: Optional[str] = None,
        postal_code: Optional[str] = None,
        self_service_allowed: Optional[bool] = None,
        bill_on_behalf_of_enabled: Optional[bool] = None,
        order_approval_required: Optional[bool] = None,
        status: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List all companies.

        Args:
            city: Filter by city
            country: Filter by country
            state_or_province: Filter by state/province
            postal_code: Filter by postal code
            self_service_allowed: Filter by self-service allowed
            bill_on_behalf_of_enabled: Filter by bill-on-behalf-of enabled
            order_approval_required: Filter by order approval required
            status: Filter by status (e.g., 'Active', 'Inactive')
            paginate: If True, fetch all pages; if False, fetch first page only
        """
        params = {}
        if city:
            params["city"] = city
        if country:
            params["country"] = country
        if state_or_province:
            params["stateOrProvince"] = state_or_province
        if postal_code:
            params["postalCode"] = postal_code
        if self_service_allowed is not None:
            params["selfServiceAllowed"] = str(self_service_allowed).lower()
        if bill_on_behalf_of_enabled is not None:
            params["billOnBehalfOfEnabled"] = str(bill_on_behalf_of_enabled).lower()
        if order_approval_required is not None:
            params["orderApprovalRequired"] = str(order_approval_required).lower()
        if status:
            params["status"] = status

        if paginate:
            return self._paginate("/companies", params)
        return self._request("GET", "/companies", params=params).get("content", [])

    def get_company(self, company_id: str) -> dict:
        """Get a company by ID."""
        return self._request("GET", f"/companies/{company_id}")

    def create_company(
        self,
        *,
        name: str,
        phone: str,
        address: Address,
        website: str,
        self_service_allowed: bool,
        bill_on_behalf_of_enabled: bool,
        order_approval_required: bool,
        external_id: Optional[str] = None,
    ) -> dict:
        """
        Create a new company.

        Note: Company will be 'Inactive' until contacts are added.

        Args:
            name: Company name
            phone: Phone number
            address: Company address
            website: Company website
            self_service_allowed: Allow self-service privileges
            bill_on_behalf_of_enabled: True if Pax8 handles billing, False if partner handles
            order_approval_required: Require approval for self-service orders
            external_id: External reference ID
        """
        body = {
            "name": name,
            "phone": phone,
            "address": address.to_dict() if isinstance(address, Address) else address,
            "website": website,
            "selfServiceAllowed": self_service_allowed,
            "billOnBehalfOfEnabled": bill_on_behalf_of_enabled,
            "orderApprovalRequired": order_approval_required,
        }
        if external_id:
            body["externalId"] = external_id
        return self._request("POST", "/companies", json_body=body)

    def update_company(self, company_id: str, **updates: Any) -> dict:
        """
        Update a company.

        Args:
            company_id: Company ID to update
            **updates: Fields to update (name, phone, address, website, etc.)
        """
        # Convert snake_case to camelCase for known fields
        field_map = {
            "external_id": "externalId",
            "self_service_allowed": "selfServiceAllowed",
            "bill_on_behalf_of_enabled": "billOnBehalfOfEnabled",
            "order_approval_required": "orderApprovalRequired",
        }
        body = {}
        for key, value in updates.items():
            api_key = field_map.get(key, key)
            if isinstance(value, Address):
                value = value.to_dict()
            body[api_key] = value
        return self._request("PUT", f"/companies/{company_id}", json_body=body)

    # =========================================================================
    # Contacts
    # =========================================================================

    def list_contacts(self, company_id: str) -> list[dict]:
        """List contacts for a company."""
        result = self._request("GET", f"/companies/{company_id}/contacts")
        # Handle both list and paginated response formats
        if isinstance(result, list):
            return result
        return result.get("content", [])

    def get_contact(self, company_id: str, contact_id: str) -> dict:
        """Get a contact by ID."""
        return self._request("GET", f"/companies/{company_id}/contacts/{contact_id}")

    def create_contact(
        self,
        company_id: str,
        *,
        first_name: str,
        last_name: str,
        email: str,
        phone: Optional[str] = None,
        types: Optional[list[str]] = None,
    ) -> dict:
        """
        Create a contact for a company.

        Args:
            company_id: Company ID
            first_name: First name
            last_name: Last name
            email: Email address
            phone: Phone number
            types: Contact type names (e.g., ['Admin', 'Billing', 'Technical']).
                   Each is set as primary. Pax8 API expects objects with type + primary fields.
        """
        body: dict[str, Any] = {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
        }
        if phone:
            body["phone"] = phone
        if types:
            body["types"] = [{"type": t, "primary": True} for t in types]
        return self._request("POST", f"/companies/{company_id}/contacts", json_body=body)

    def update_contact(
        self,
        company_id: str,
        contact_id: str,
        **updates: Any,
    ) -> dict:
        """Update a contact."""
        field_map = {
            "first_name": "firstName",
            "last_name": "lastName",
        }
        body = {}
        for key, value in updates.items():
            api_key = field_map.get(key, key)
            body[api_key] = value
        return self._request("PUT", f"/companies/{company_id}/contacts/{contact_id}", json_body=body)

    def delete_contact(self, company_id: str, contact_id: str) -> None:
        """Delete a contact."""
        self._request("DELETE", f"/companies/{company_id}/contacts/{contact_id}")

    # =========================================================================
    # Products
    # =========================================================================

    def list_products(
        self,
        *,
        vendor_name: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List available products.

        Args:
            vendor_name: Filter by vendor name
            paginate: If True, fetch all pages
        """
        params = {}
        if vendor_name:
            params["vendorName"] = vendor_name

        if paginate:
            return self._paginate("/products", params)
        return self._request("GET", "/products", params=params).get("content", [])

    def get_product(self, product_id: str) -> dict:
        """Get a product by ID."""
        return self._request("GET", f"/products/{product_id}")

    def get_product_provisioning_details(self, product_id: str) -> dict:
        """Get provisioning details for a product."""
        return self._request("GET", f"/products/{product_id}/provision-details")

    def get_product_dependencies(self, product_id: str) -> dict:
        """Get dependencies for a product."""
        return self._request("GET", f"/products/{product_id}/dependencies")

    def get_product_pricing(self, product_id: str) -> dict:
        """Get pricing for a product."""
        return self._request("GET", f"/products/{product_id}/pricing")

    # =========================================================================
    # Orders
    # =========================================================================

    def list_orders(
        self,
        *,
        company_id: Optional[str] = None,
        status: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List orders.

        Args:
            company_id: Filter by company ID
            status: Filter by order status
            paginate: If True, fetch all pages
        """
        params = {}
        if company_id:
            params["companyId"] = company_id
        if status:
            params["status"] = status

        if paginate:
            return self._paginate("/orders", params)
        return self._request("GET", "/orders", params=params).get("content", [])

    def get_order(self, order_id: str) -> dict:
        """Get an order by ID."""
        return self._request("GET", f"/orders/{order_id}")

    def create_order(
        self,
        *,
        company_id: str,
        line_items: list[OrderLineItem],
        ordered_by: Optional[str] = None,
        ordered_by_user_email: Optional[str] = None,
    ) -> dict:
        """
        Create a new order.

        Note: Currently NOT supported for scheduled orders.

        Args:
            company_id: Company ID for the order
            line_items: List of order line items
            ordered_by: Type of user who created the order
            ordered_by_user_email: Email of user who created the order
        """
        body = {
            "companyId": company_id,
            "lineItems": [
                item.to_dict() if isinstance(item, OrderLineItem) else item
                for item in line_items
            ],
        }
        if ordered_by:
            body["orderedBy"] = ordered_by
        if ordered_by_user_email:
            body["orderedByUserEmail"] = ordered_by_user_email
        return self._request("POST", "/orders", json_body=body)

    # =========================================================================
    # Subscriptions
    # =========================================================================

    def list_subscriptions(
        self,
        *,
        company_id: Optional[str] = None,
        product_id: Optional[str] = None,
        status: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List subscriptions.

        Args:
            company_id: Filter by company ID
            product_id: Filter by product ID
            status: Filter by status (e.g., 'Active', 'Cancelled')
            paginate: If True, fetch all pages
        """
        params = {}
        if company_id:
            params["companyId"] = company_id
        if product_id:
            params["productId"] = product_id
        if status:
            params["status"] = status

        if paginate:
            return self._paginate("/subscriptions", params)
        return self._request("GET", "/subscriptions", params=params).get("content", [])

    def get_subscription(self, subscription_id: str) -> dict:
        """Get a subscription by ID."""
        return self._request("GET", f"/subscriptions/{subscription_id}")

    def get_subscription_history(self, subscription_id: str) -> list[dict]:
        """Get history for a subscription."""
        result = self._request("GET", f"/subscriptions/{subscription_id}/history")
        if isinstance(result, list):
            return result
        return result.get("content", [])

    def update_subscription(
        self,
        subscription_id: str,
        *,
        quantity: Optional[int] = None,
        billing_term: Optional[BillingTerm] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        price: Optional[float] = None,
        partner_cost: Optional[float] = None,
        currency_code: Optional[str] = None,
        provisioning_details: Optional[list[dict]] = None,
    ) -> dict:
        """
        Update a subscription.

        Note: Currently NOT supported for subscriptions with a future date.

        Args:
            subscription_id: Subscription ID to update
            quantity: New quantity
            billing_term: New billing term
            start_date: New start date (YYYY-MM-DD)
            end_date: New end date (YYYY-MM-DD)
            price: New price
            partner_cost: New partner cost
            currency_code: Currency ISO 4217 code
            provisioning_details: Provisioning details
        """
        body = {}
        if quantity is not None:
            body["quantity"] = quantity
        if billing_term:
            body["billingTerm"] = billing_term.value if isinstance(billing_term, BillingTerm) else billing_term
        if start_date:
            body["startDate"] = start_date
        if end_date:
            body["endDate"] = end_date
        if price is not None:
            body["price"] = price
        if partner_cost is not None:
            body["partnerCost"] = partner_cost
        if currency_code:
            body["currencyCode"] = currency_code
        if provisioning_details:
            body["provisioningDetails"] = provisioning_details
        return self._request("PUT", f"/subscriptions/{subscription_id}", json_body=body)

    def cancel_subscription(self, subscription_id: str) -> dict:
        """Cancel a subscription."""
        return self._request("DELETE", f"/subscriptions/{subscription_id}")

    # =========================================================================
    # Invoices
    # =========================================================================

    def list_invoices(
        self,
        *,
        status: Optional[str] = None,
        invoice_date_start: Optional[str] = None,
        invoice_date_end: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List invoices.

        Args:
            status: Filter by status
            invoice_date_start: Filter by start date (YYYY-MM-DD)
            invoice_date_end: Filter by end date (YYYY-MM-DD)
            paginate: If True, fetch all pages
        """
        params = {}
        if status:
            params["status"] = status
        if invoice_date_start:
            params["invoiceDateStart"] = invoice_date_start
        if invoice_date_end:
            params["invoiceDateEnd"] = invoice_date_end

        if paginate:
            return self._paginate("/invoices", params)
        return self._request("GET", "/invoices", params=params).get("content", [])

    def get_invoice(self, invoice_id: str) -> dict:
        """Get an invoice by ID."""
        return self._request("GET", f"/invoices/{invoice_id}")

    def list_invoice_items(self, invoice_id: str) -> list[dict]:
        """List items for an invoice."""
        result = self._request("GET", f"/invoices/{invoice_id}/items")
        if isinstance(result, list):
            return result
        return result.get("content", [])

    # =========================================================================
    # Usage Summaries
    # =========================================================================

    def list_usage_summaries(
        self,
        *,
        company_id: Optional[str] = None,
        product_id: Optional[str] = None,
        resource_group: Optional[str] = None,
        paginate: bool = True,
    ) -> list[dict]:
        """
        List usage summaries.

        Args:
            company_id: Filter by company ID
            product_id: Filter by product ID
            resource_group: Filter by resource group
            paginate: If True, fetch all pages
        """
        params = {}
        if company_id:
            params["companyId"] = company_id
        if product_id:
            params["productId"] = product_id
        if resource_group:
            params["resourceGroup"] = resource_group

        if paginate:
            return self._paginate("/usage-summaries", params)
        return self._request("GET", "/usage-summaries", params=params).get("content", [])

    def get_usage_summary(self, usage_summary_id: str) -> dict:
        """Get a usage summary by ID."""
        return self._request("GET", f"/usage-summaries/{usage_summary_id}")

    def list_usage_lines(
        self,
        usage_summary_id: str,
        paginate: bool = True,
    ) -> list[dict]:
        """List usage lines for a usage summary."""
        if paginate:
            return self._paginate(f"/usage-summaries/{usage_summary_id}/usage-lines")
        result = self._request("GET", f"/usage-summaries/{usage_summary_id}/usage-lines")
        if isinstance(result, list):
            return result
        return result.get("content", [])

    # =========================================================================
    # Generic Request (for endpoints not yet implemented)
    # =========================================================================

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict:
        """
        Make a generic API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API path (e.g., '/companies')
            params: Query parameters
            json_body: JSON body for POST/PUT requests
        """
        return self._request(method, path, params=params, json_body=json_body)


def create_client(access_token: str) -> Pax8Client:
    """
    Create a Pax8 client.

    Usage:
        from modules.pax8 import create_client

        token = await oauth.get("pax8")
        client = create_client(token["access_token"])
        companies = client.list_companies()

    Args:
        access_token: OAuth2 access token

    Returns:
        Configured Pax8Client instance
    """
    return Pax8Client(access_token)


# =============================================================================
# Lazy Client (Bifrost Integration)
# =============================================================================

class _LazyClient:
    """
    Module-level proxy that auto-initializes from Bifrost integration.
    Pulls OAuth access token from integration.oauth on every call (no caching).
    On 401, calls oauth.refresh() and retries once.
    """

    _integration_name: str = "Pax8"

    async def _get_integration(self):
        from bifrost import integrations

        integration = await integrations.get(self._integration_name)
        if not integration:
            raise RuntimeError(f"Integration '{self._integration_name}' not found. Is the Pax8 integration configured?")
        if not integration.oauth or not integration.oauth.access_token:
            raise RuntimeError("Pax8 integration is missing an OAuth access token. Check the integration setup.")
        return integration

    def __getattr__(self, name: str):
        """Proxy attribute access to a real Pax8Client instance."""
        async def _wrapper(*args, **kwargs):
            integration = await self._get_integration()
            client = Pax8Client(integration.oauth.access_token)
            try:
                return getattr(client, name)(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    # Token expired early — refresh and retry once
                    await integration.oauth.refresh()
                    client = Pax8Client(integration.oauth.access_token)
                    return getattr(client, name)(*args, **kwargs)
                raise
        return _wrapper


# Module-level lazy client — use like: await pax8.list_companies()
_lazy = _LazyClient()


def __getattr__(name: str):
    """Enable top-level module attribute access via the lazy client."""
    return getattr(_lazy, name)
