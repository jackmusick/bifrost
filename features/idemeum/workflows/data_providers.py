"""
Idemeum data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.idemeum import IdemeumClient


@data_provider(
    name="Idemeum: List Customers",
    description="Returns Idemeum customers for org mapping picker.",
    category="Idemeum",
    tags=["idemeum", "data-provider"],
)
async def list_idemeum_customers() -> list[dict]:
    """Return Idemeum customers as {value, label} options for org mapping."""
    from modules.idemeum import get_client

    client = await get_client(scope="global")
    try:
        customers = await client.list_customers()
    finally:
        await client.close()

    options = []
    for customer in customers:
        normalized = IdemeumClient.normalize_customer(customer)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
