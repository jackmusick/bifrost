"""
Datto Networking data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import dattonetworking


@data_provider(
    name="Datto Networking: List Networks",
    description="Returns Datto Networking networks for org mapping picker.",
    category="Datto Networking",
    tags=["datto", "networking", "data-provider"],
)
async def list_dattonetworking_networks() -> list[dict]:
    """Return Datto Networking networks as {value, label} options for org mapping."""
    client = await dattonetworking.get_client(scope="global")
    try:
        networks = await client.list_networks()
    finally:
        await client.close()

    options = []
    for network in networks:
        normalized = dattonetworking.DattoNetworkingClient.normalize_network(network)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
