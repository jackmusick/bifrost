"""
IT Glue data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import itglue


@data_provider(
    name="IT Glue: List Organizations",
    description="Returns IT Glue organizations for org mapping picker.",
    category="IT Glue",
    tags=["itglue", "data-provider"],
)
async def list_itglue_organizations() -> list[dict]:
    """Return IT Glue organizations as {value, label} options for org mapping."""
    client = await itglue.get_client(scope="global")
    organizations = client.list_organizations()

    options = []
    for organization in organizations:
        normalized = itglue.ITGlueClient.normalize_organization(organization)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
