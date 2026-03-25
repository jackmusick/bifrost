"""
Datto Networking data providers for org mapping UI.
"""

from modules import dattonetworking


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
