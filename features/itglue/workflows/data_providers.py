"""
IT Glue data providers for org mapping UI.
"""

from modules import itglue


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
