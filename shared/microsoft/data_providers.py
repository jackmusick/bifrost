"""
Microsoft Data Providers

Data providers for Microsoft-related form dropdowns.
"""

import logging

from bifrost import data_provider

logger = logging.getLogger(__name__)


@data_provider(
    name="microsoft_customers",
    description="List Microsoft CSP customers from Partner Center",
    category="Microsoft",
    cache_ttl_seconds=300,
)
async def microsoft_customers() -> list[dict]:
    """
    Return list of Microsoft CSP customers for dropdown selection.

    Returns:
        List of options with tenantId as value and companyName as label.
    """
    from modules.microsoft import create_csp_client

    logger.debug("Fetching Microsoft customers for data provider")

    csp = await create_csp_client()
    customers = csp.list_customers()

    options = []
    for customer in customers:
        company_profile = customer.get("companyProfile", {})
        tenant_id = company_profile.get("tenantId")
        company_name = company_profile.get("companyName")
        domain = company_profile.get("domain")

        if not tenant_id or not company_name:
            continue

        options.append({
            "label": company_name,
            "value": tenant_id,
            "metadata": {
                "domain": domain,
                "customer_id": customer.get("id"),
                "relationship": customer.get("relationshipToPartner"),
            },
        })

    # Sort alphabetically by company name
    options.sort(key=lambda x: x["label"].lower())

    logger.debug(f"Returning {len(options)} Microsoft customers")
    return options
