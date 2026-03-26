"""
DNSFilter data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.dnsfilter import DNSFilterClient


@data_provider(
    name="DNSFilter: List Networks",
    description="Returns DNSFilter networks for org mapping picker.",
    category="DNSFilter",
    tags=["dnsfilter", "data-provider"],
)
async def list_dnsfilter_networks() -> list[dict]:
    """Return DNSFilter networks as {value, label} options for org mapping."""
    from modules.dnsfilter import get_client

    client = await get_client(scope="global")
    try:
        networks = await client.list_networks()
    finally:
        await client.close()

    options = []
    for network in networks:
        normalized = DNSFilterClient.normalize_network(network)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())

