"""
Cove data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.cove import CoveClient


@data_provider(
    name="Cove Data Protection: List Customers",
    description="Returns Cove EndCustomer partners for org mapping picker.",
    category="Cove Data Protection",
    tags=["cove", "data-provider"],
)
async def list_cove_customers() -> list[dict]:
    """Return Cove customers as {value, label} options for org mapping."""
    from modules.cove import get_client

    client = await get_client(scope="global")
    try:
        partners = await client.enumerate_partners()
    finally:
        await client.close()

    options = []
    for partner in partners:
        normalized = CoveClient.normalize_partner(partner)
        if normalized["level"] != "EndCustomer":
            continue
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
