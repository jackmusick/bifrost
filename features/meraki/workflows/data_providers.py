"""
Meraki data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.meraki import MerakiClient


@data_provider(
    name="Meraki: List Organizations",
    description="Returns Meraki organizations for org mapping picker.",
    category="Meraki",
    tags=["meraki", "data-provider"],
)
async def list_meraki_organizations() -> list[dict]:
    """Return Meraki organizations as {value, label} options for org mapping."""
    from modules.meraki import get_client

    client = await get_client(scope="global")
    try:
        organizations = await client.list_organizations()
    finally:
        await client.close()

    options = []
    for organization in organizations:
        normalized = MerakiClient.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())

