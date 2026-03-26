"""
Microsoft Graph API Client

Generic Python client for Microsoft Graph API.
Designed to be flexible - can call any Graph endpoint without pre-built methods.

Documentation: https://learn.microsoft.com/en-us/graph/api/overview

Usage:
    from modules.microsoft import create_graph_client

    # Create client for a Bifrost org (uses client credentials by default)
    graph = await create_graph_client(org_id="org-uuid")

    # Or for a specific tenant
    graph = await create_graph_client(tenant_id="customer-tenant-id")

    # Use delegated permissions (GDAP token exchange)
    graph = await create_graph_client(org_id="org-uuid", use_delegated=True)

    # Make requests
    users = graph.paginate("/users", params={"$select": "displayName,mail"})
    user = graph.get(f"/users/{user_id}")
    new_user = graph.post("/users", {"displayName": "John", ...})
    graph.patch(f"/users/{user_id}", {"jobTitle": "Manager"})
    graph.delete(f"/users/{user_id}")
"""

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def graph_error_detail(e: Exception) -> str:
    """Extract error detail from a Graph API exception."""
    if hasattr(e, "response") and e.response is not None:
        try:
            body = e.response.json()
            err = body.get("error", {})
            code = err.get("code", "")
            msg = err.get("message", "")
            return f"{e.response.status_code} {code}: {msg}" if code else str(e)
        except Exception:
            return f"{e.response.status_code}: {e.response.text[:200]}"
    return str(e)


class GraphClient:
    """
    Generic client for Microsoft Graph API.

    Provides flexible methods to call any Graph endpoint.
    Handles pagination automatically via @odata.nextLink.
    """

    BASE_URL = "https://graph.microsoft.com/v1.0"
    BETA_URL = "https://graph.microsoft.com/beta"

    def __init__(self, access_token: str, tenant_id: str | None = None):
        """
        Initialize Graph API client.

        Args:
            access_token: OAuth2 access token for Graph API.
                         Use create_graph_client() to obtain a configured client.
            tenant_id: Optional tenant ID for context/logging purposes.
        """
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        beta: bool = False,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """
        Make a request to any Graph API endpoint.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.)
            endpoint: API endpoint (e.g., "/users", "/groups/{id}/members")
            params: Query parameters (e.g., {"$select": "displayName", "$top": 100})
            json_body: Request body for POST/PATCH requests
            headers: Additional headers to include
            beta: Use beta API endpoint instead of v1.0
            timeout: Request timeout in seconds

        Returns:
            Response JSON as dictionary (empty dict for 204 No Content)

        Raises:
            requests.HTTPError: If request fails
        """
        base = self.BETA_URL if beta else self.BASE_URL

        # Handle full URLs (e.g., from @odata.nextLink)
        if endpoint.startswith("http"):
            url = endpoint
        else:
            # Ensure endpoint starts with /
            if not endpoint.startswith("/"):
                endpoint = f"/{endpoint}"
            url = f"{base}{endpoint}"

        # Merge additional headers
        request_headers = dict(self.session.headers)
        if headers:
            request_headers.update(headers)

        max_retries = 3
        for attempt in range(max_retries + 1):
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=request_headers,
                timeout=timeout,
            )

            if response.status_code == 429 and attempt < max_retries:
                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(f"Graph API 429 throttled, retrying in {retry_after}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_after)
                continue

            if response.status_code >= 500 and attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"Graph API {response.status_code}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

            break

        response.raise_for_status()

        # Handle 204 No Content
        if response.status_code == 204 or not response.content:
            return {}

        return response.json()

    def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make a GET request.

        Args:
            endpoint: API endpoint (e.g., "/users/{id}")
            params: Query parameters
            **kwargs: Additional arguments passed to request()

        Returns:
            Response JSON
        """
        return self.request("GET", endpoint, params=params, **kwargs)

    def post(
        self,
        endpoint: str,
        body: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make a POST request.

        Args:
            endpoint: API endpoint (e.g., "/users")
            body: Request body
            params: Query parameters
            **kwargs: Additional arguments passed to request()

        Returns:
            Response JSON (created object)
        """
        return self.request("POST", endpoint, params=params, json_body=body, **kwargs)

    def patch(
        self,
        endpoint: str,
        body: dict[str, Any],
        *,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make a PATCH request.

        Args:
            endpoint: API endpoint (e.g., "/users/{id}")
            body: Fields to update
            params: Query parameters
            **kwargs: Additional arguments passed to request()

        Returns:
            Response JSON (may be empty for some endpoints)
        """
        return self.request("PATCH", endpoint, params=params, json_body=body, **kwargs)

    def delete(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Make a DELETE request.

        Args:
            endpoint: API endpoint (e.g., "/users/{id}")
            params: Query parameters
            **kwargs: Additional arguments passed to request()
        """
        self.request("DELETE", endpoint, params=params, **kwargs)

    def paginate(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        max_pages: int | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Paginate through a list endpoint automatically.

        Handles @odata.nextLink for automatic pagination through all results.

        Args:
            endpoint: API endpoint that returns a list (e.g., "/users", "/groups")
            params: Query parameters (e.g., {"$select": "displayName", "$top": 100})
            max_pages: Maximum number of pages to fetch (None for all)
            **kwargs: Additional arguments passed to request()

        Returns:
            Combined list of all items from all pages

        Example:
            # Get all users with specific fields
            users = graph.paginate("/users", params={"$select": "id,displayName,mail"})

            # Get first 500 users max (5 pages of 100)
            users = graph.paginate("/users", params={"$top": 100}, max_pages=5)
        """
        params = params or {}
        all_results: list[dict[str, Any]] = []
        page_count = 0
        next_link: str | None = None

        while True:
            if next_link:
                # Use full next link URL
                data = self.get(next_link, **kwargs)
            else:
                # First page
                data = self.get(endpoint, params=params, **kwargs)

            # Extract items from response
            items = data.get("value", [])
            all_results.extend(items)

            # Check for next page
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break

            page_count += 1
            if max_pages and page_count >= max_pages:
                logger.debug(
                    "Pagination stopped at max_pages",
                    extra={"max_pages": max_pages, "total_items": len(all_results)}
                )
                break

        return all_results

    def batch(
        self,
        requests_list: list[dict[str, Any]],
        *,
        beta: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Execute a batch of requests in a single API call.

        Graph API supports up to 20 requests per batch.

        Args:
            requests_list: List of request objects, each with:
                - id: Unique identifier for the request
                - method: HTTP method
                - url: Relative URL (e.g., "/users/123")
                - body: Optional request body
                - headers: Optional additional headers
            beta: Use beta API endpoint

        Returns:
            List of response objects with id, status, headers, body

        Example:
            responses = graph.batch([
                {"id": "1", "method": "GET", "url": "/users/user1@domain.com"},
                {"id": "2", "method": "GET", "url": "/users/user2@domain.com"},
            ])
        """
        base = self.BETA_URL if beta else self.BASE_URL
        batch_endpoint = f"{base}/$batch"

        body = {"requests": requests_list}

        response = self.session.post(
            batch_endpoint,
            json=body,
            timeout=120,  # Batch requests can take longer
        )
        response.raise_for_status()

        return response.json().get("responses", [])


async def create_graph_client(
    tenant_id: str | None = None,
    org_id: str | None = None,
    use_delegated: bool = False,
) -> GraphClient:
    """
    Create a Microsoft Graph client.

    Factory function that handles token acquisition automatically.

    By default, uses client credentials (application permissions) via the
    "Microsoft" integration. Set use_delegated=True to use GDAP token
    exchange (delegated permissions) via the "Microsoft CSP" integration.

    Args:
        tenant_id: Customer tenant ID. Required if org_id not provided.
        org_id: Bifrost organization ID. If provided, looks up tenant_id
               from IntegrationMapping and uses that org's credentials.
        use_delegated: If True, use GDAP delegated token exchange instead
                      of client credentials. Useful before app permissions
                      are granted or for user-context operations.

    Returns:
        Configured GraphClient instance

    Raises:
        ValueError: If neither tenant_id nor org_id is provided
        UserError: If integration not configured or tenant not linked

    Usage:
        from modules.microsoft import create_graph_client

        # Application permissions (default) - for a Bifrost org
        graph = await create_graph_client(org_id="org-uuid")
        users = graph.paginate("/users")

        # Application permissions - for specific tenant
        graph = await create_graph_client(tenant_id="abc123-...")
        org = graph.get("/organization")

        # Delegated permissions (GDAP) - when app permissions not yet granted
        graph = await create_graph_client(org_id="org-uuid", use_delegated=True)
    """
    from bifrost import integrations, UserError

    if not tenant_id and not org_id:
        raise ValueError("Either tenant_id or org_id must be provided")

    if use_delegated:
        # Use GDAP token exchange (delegated permissions)
        from .auth import get_graph_token, get_current_org_tenant_id

        if not tenant_id:
            if org_id:
                # Look up tenant from Microsoft integration mapping
                integration = await integrations.get("Microsoft", scope=org_id)
                if integration and integration.entity_id:
                    tenant_id = integration.entity_id
                else:
                    # Fall back to config-based lookup
                    tenant_id = await get_current_org_tenant_id()
            else:
                tenant_id = await get_current_org_tenant_id()

        access_token = await get_graph_token(tenant_id)
        return GraphClient(access_token, tenant_id)

    else:
        # Use client credentials (application permissions) - default
        if org_id:
            # Get token via Microsoft integration with org scope
            integration = await integrations.get("Microsoft", scope=org_id)
            if not integration:
                raise UserError("Microsoft integration not found")
            if not integration.oauth or not integration.oauth.access_token:
                raise UserError(
                    "Microsoft integration not configured for client credentials. "
                    "Check that the integration has client_id and client_secret set."
                )
            if not integration.entity_id:
                raise UserError(
                    "No tenant linked to org. "
                    "Use the Microsoft CSP app to link this organization."
                )
            return GraphClient(integration.oauth.access_token, integration.entity_id)

        elif tenant_id:
            # Get token via Microsoft integration with global scope + specific tenant
            # This requires the token URL to have {entity_id} templating
            integration = await integrations.get("Microsoft", scope="global")
            if not integration:
                raise UserError("Microsoft integration not found")
            if not integration.oauth or not integration.oauth.access_token:
                raise UserError(
                    "Microsoft integration not configured for client credentials."
                )
            return GraphClient(integration.oauth.access_token, tenant_id)

        else:
            raise ValueError("Either tenant_id or org_id must be provided")
