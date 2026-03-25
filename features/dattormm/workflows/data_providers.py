"""
Datto RMM data providers for org mapping UI.
"""

from modules import dattormm


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
