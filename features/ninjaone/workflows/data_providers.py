"""
NinjaOne data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import ninjaone


@data_provider(
    name="NinjaOne: List Organizations",
    description="Returns NinjaOne organizations for org mapping picker.",
    category="NinjaOne",
    tags=["ninjaone", "data-provider"],
)
async def list_ninjaone_organizations() -> list[dict]:
    """Return NinjaOne organizations as {value, label} options for org mapping."""
    client = await ninjaone.get_client(scope="global")
    try:
        organizations = await client.list_organizations()
    finally:
        await client.close()

    options = []
    for organization in organizations:
        normalized = ninjaone.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
