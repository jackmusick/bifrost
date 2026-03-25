"""
NinjaOne data providers for org mapping UI.
"""

from modules import ninjaone


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
