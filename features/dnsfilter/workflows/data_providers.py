"""
DNSFilter data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.dnsfilter import DNSFilterClient


@data_provider(
    name="DNSFilter: List Organizations",
    description="Returns DNSFilter organizations for org mapping picker.",
    category="DNSFilter",
    tags=["dnsfilter", "data-provider"],
)
async def list_dnsfilter_networks() -> list[dict]:
    """
    Return DNSFilter organizations as {value, label} options for org mapping.

    The function name is kept stable to avoid forcing a new registration path,
    but the entity surface is now DNSFilter organizations rather than networks.
    """
    from modules.dnsfilter import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.list_organizations()
    finally:
        await client.close()

    options = []
    for organization in organizations:
        normalized = DNSFilterClient.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            label = normalized["name"]
            network_count = len(normalized["network_ids"])
            if network_count:
                label = f"{label} [{network_count} network{'s' if network_count != 1 else ''}]"
            options.append(
                {
                    "value": normalized["id"],
                    "label": label,
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
