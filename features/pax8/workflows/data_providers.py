"""
Pax8 data providers for org mapping UI.
"""

from modules.pax8 import Pax8Client


async def list_pax8_companies() -> list[dict]:
    """Return Pax8 companies as {value, label} options for org mapping."""
    from modules.pax8 import get_client

    client = await get_client(scope="global")
    try:
        companies = await client.list_companies()
    finally:
        await client.close()

    options = []
    for company in companies:
        normalized = Pax8Client.normalize_company(company)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
