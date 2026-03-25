"""
Microsoft Integration Module

Python clients for Microsoft Graph, Exchange Online, and Partner Center APIs.
Uses GDAP (Granular Delegated Admin Privileges) for multi-tenant access.

Usage:
    from modules.microsoft import create_graph_client, create_csp_client

    # Graph API (for user/group management in customer tenant)
    graph = await create_graph_client()  # Uses current org's tenant
    users = graph.paginate("/users")

    # Partner Center (for listing customers, managing consents)
    csp = await create_csp_client()
    customers = csp.list_customers()

    # Work with specific customer tenant
    graph = await create_graph_client(tenant_id="customer-tenant-id")
    users = graph.paginate("/users")
"""

from .graph import GraphClient, create_graph_client
from .csp import PartnerCenterClient, create_csp_client, build_consent_grants, ENTERPRISE_APP_IDS
from .auth import (
    GDAPCredentials,
    get_gdap_credentials,
    exchange_for_token,
    get_partner_center_token,
    get_graph_token,
    get_exchange_token,
    get_current_org_tenant_id,
)

__all__ = [
    # Graph API
    "GraphClient",
    "create_graph_client",
    # Partner Center / CSP
    "PartnerCenterClient",
    "create_csp_client",
    "build_consent_grants",
    "ENTERPRISE_APP_IDS",
    # Authentication helpers
    "GDAPCredentials",
    "get_gdap_credentials",
    "exchange_for_token",
    "get_partner_center_token",
    "get_graph_token",
    "get_exchange_token",
    "get_current_org_tenant_id",
]
