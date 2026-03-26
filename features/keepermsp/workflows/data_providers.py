"""
Keeper MSP data providers for org mapping UI.
"""

from bifrost import data_provider
from modules import keeper


@data_provider(
    name="Keeper MSP: List Managed Companies",
    description="Returns Keeper managed companies for org mapping picker.",
    category="Keeper MSP",
    tags=["keeper", "msp", "data-provider"],
)
async def list_keeper_managed_companies() -> list[dict]:
    """Return Keeper managed companies as {value, label} options for org mapping."""
    client = await keeper.get_client(scope="global")
    try:
        companies = await client.list_managed_companies()
    finally:
        await client.close()

    options = []
    for company in companies:
        normalized = keeper.KeeperMSPClient.normalize_managed_company(company)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
