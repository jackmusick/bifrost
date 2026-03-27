"""
Autotask data providers for org mapping UI.
"""

from bifrost import data_provider
from modules.autotask import AutotaskClient


@data_provider(
    name="Autotask: List Companies",
    description="Returns active Autotask customer companies for org mapping.",
    category="Autotask",
    tags=["autotask", "data-provider"],
)
async def list_autotask_companies() -> list[dict]:
    """Return active Autotask customer companies as {value, label} options."""
    from modules.autotask import get_client

    client = await get_client(scope="global")
    try:
        companies = await client.list_active_companies()
    finally:
        await client.close()

    options = []
    for company in companies:
        normalized = AutotaskClient.normalize_company(company)
        if normalized["id"] and normalized["name"]:
            options.append(
                {
                    "value": normalized["id"],
                    "label": normalized["name"],
                }
            )

    return sorted(options, key=lambda item: item["label"].lower())
