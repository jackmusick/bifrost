"""
Huntress data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import huntress


@data_provider(
    name="Huntress: List Organizations",
    description="Returns Huntress organizations for org mapping picker.",
    category="Huntress",
    tags=["huntress", "data-provider"],
)
async def list_huntress_organizations() -> list[dict]:
    """Return Huntress organizations as {value, label} options for org mapping."""
    client = await huntress.get_client(scope="global")
    try:
        organizations = await client.list_organizations()
    finally:
        await client.close()

    options = []
    for organization in organizations:
        normalized = huntress.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
