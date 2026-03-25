"""
VIPRE data providers for org mapping UI.
"""

from modules.vipre import VipreClient


async def list_vipre_sites() -> list[dict]:
    """Return inferred VIPRE sites as {value, label} options for org mapping."""
    from modules.vipre import get_client

    client = await get_client(scope="global")
    try:
        sites = await client.infer_sites_from_devices()
    finally:
        await client.close()

    options = []
    for site in sites:
        site_id = site.get("id", "")
        site_name = site.get("name") or site_id
        if site_id:
            options.append(
                {
                    "value": site_id,
                    "label": site_name,
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())

