"""
ConnectSecure data providers for org mapping UI.
"""

from modules.connectsecure import ConnectSecureClient


async def list_connectsecure_companies() -> list[dict]:
    """Return ConnectSecure companies as {value, label} options for org mapping."""
    from modules.connectsecure import get_client

    client = await get_client(scope="global")
    try:
        companies = await client.list_companies()
    finally:
        await client.close()

    options = []
    for company in companies:
        normalized = ConnectSecureClient.normalize_company(company)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())

