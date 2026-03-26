"""
List CSP Tenants

Lists all Microsoft CSP customer tenants from Partner Center,
merged with their current status from the Bifrost database.
"""

import logging
from datetime import datetime, timezone

from bifrost import workflow, tables, organizations, context

logger = logging.getLogger(__name__)

STATUS_TABLE = "csp_tenant_status"


@workflow(
    category="Microsoft CSP",
    tags=["microsoft", "csp", "tenants"],
)
async def list_csp_tenants() -> dict:
    """
    List all CSP tenants with their current status.

    Fetches customers from Partner Center API and merges with
    stored status data (org links, consent status).

    Returns:
        dict with tenants list and metadata
    """
    from modules.microsoft import create_csp_client

    # Get provider org ID from context
    provider_org_id = context.org_id

    logger.info("Fetching CSP tenants from Partner Center")

    # Fetch customers from Partner Center
    csp = await create_csp_client()
    customers = csp.list_customers()

    logger.info(f"Found {len(customers)} customers in Partner Center")

    # Get all stored statuses (table may not exist yet)
    try:
        status_result = await tables.query(STATUS_TABLE, scope=provider_org_id, limit=1000)
        status_by_tenant = {
            doc.data.get("tenant_id"): doc.data
            for doc in status_result.documents
        }
    except Exception as e:
        # Table doesn't exist yet - that's fine, we'll create it on first link/consent
        logger.debug(f"Status table not found (will be created on first write): {e}")
        status_by_tenant = {}

    # Get all Bifrost organizations for the dropdown
    all_orgs = await organizations.list()
    org_options = [
        {"value": org.id, "label": org.name}
        for org in all_orgs
    ]

    # Merge Partner Center data with stored status
    tenants = []
    for customer in customers:
        company_profile = customer.get("companyProfile", {})
        tenant_id = company_profile.get("tenantId")

        if not tenant_id:
            continue

        tenant_name = company_profile.get("companyName", "Unknown")
        domain = company_profile.get("domain", "")
        customer_id = customer.get("id", "")

        # Get stored status or defaults
        status = status_by_tenant.get(tenant_id, {})

        tenants.append({
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "domain": domain,
            "customer_id": customer_id,
            "bifrost_org_id": status.get("bifrost_org_id"),
            "bifrost_org_name": status.get("bifrost_org_name"),
            "consent_status": status.get("consent_status", "none"),
            "consent_error": status.get("consent_error"),
            "consent_execution_id": status.get("consent_execution_id"),
            "consented_at": status.get("consented_at"),
            "updated_at": status.get("updated_at"),
        })

    # Sort by tenant name
    tenants.sort(key=lambda t: t["tenant_name"].lower())

    return {
        "tenants": tenants,
        "tenant_count": len(tenants),
        "organizations": org_options,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
