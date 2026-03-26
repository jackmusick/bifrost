"""
Google Workspace Reseller data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import googleworkspace


@data_provider(
    name="Google Workspace Reseller: List Customers",
    description="Returns reseller-visible Google Workspace customers for org mapping picker.",
    category="Google Workspace Reseller",
    tags=["google", "workspace", "reseller", "data-provider"],
)
async def list_google_workspace_reseller_customers() -> list[dict]:
    """Return reseller-visible Google Workspace customers as {value, label}."""
    client = await googleworkspace.get_reseller_client(scope="global")
    try:
        customers = await client.list_customers()
    finally:
        await client.close()

    options = []
    for customer in customers:
        normalized = googleworkspace.GoogleWorkspaceResellerClient.normalize_customer(customer)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
