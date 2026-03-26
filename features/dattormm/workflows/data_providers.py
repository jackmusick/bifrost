"""
Datto RMM data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import dattormm


@data_provider(
    name="Datto RMM: List Sites",
    description="Returns Datto RMM sites for org mapping picker.",
    category="Datto RMM",
    tags=["datto", "rmm", "data-provider"],
)
async def list_dattormm_sites() -> list[dict]:
    """Return Datto RMM sites as {value, label} options for org mapping."""
    client = await dattormm.get_client(scope="global")
    try:
        sites = await client.list_sites()
    finally:
        await client.close()

    options = []
    for site in sites:
        normalized = dattormm.DattoRMMClient.normalize_site(site)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
