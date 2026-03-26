"""
Autotask entity data providers for Bifrost integration UI.
"""

import httpx
from bifrost import data_provider, integrations


@data_provider(
    name="Autotask: List Companies",
    description="Returns active Autotask customer companies for org mapping",
    category="Autotask",
)
async def list_autotask_companies() -> list[dict]:
    """Returns active Autotask customer companies as entity picker options."""
    at = await integrations.get("Autotask", scope="global")
    if not at:
        return []

    headers = {
        "ApiIntegrationCode": at.config["api_integration_code"],
        "UserName": at.config["username"],
        "Secret": at.config["secret"],
        "Content-Type": "application/json",
    }
    base_url = at.config["base_url"]

    companies: list[dict] = []
    next_url: str | None = f"{base_url}/V1.0/Companies/query"
    query = {
        "maxRecords": 500,
        "includeFields": ["id", "companyName", "companyType", "isActive"],
        "filter": [
            {
                "op": "and", "field": "", "value": None, "udf": False,
                "items": [
                    {"op": "eq", "field": "companyType", "value": 1, "udf": False, "items": []},
                    {"op": "eq", "field": "isActive",    "value": True, "udf": False, "items": []},
                ],
            }
        ],
    }

    async with httpx.AsyncClient(verify=False) as client:
        while next_url:
            resp = await client.post(next_url, headers=headers, json=query)
            resp.raise_for_status()
            data = resp.json()
            companies.extend(data["items"])
            next_url = data["pageDetails"].get("nextPageUrl")

    return [
        {"value": str(c["id"]), "label": c["companyName"]}
        for c in sorted(companies, key=lambda c: c["companyName"])
    ]
