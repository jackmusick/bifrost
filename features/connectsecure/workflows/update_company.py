"""
ConnectSecure: Update Company
"""

from bifrost import workflow
from modules.connectsecure import ConnectSecureClient


@workflow(
    name="ConnectSecure: Update Company",
    description="Update a ConnectSecure company name.",
    category="ConnectSecure",
    tags=["connectsecure", "update"],
)
async def update_connectsecure_company(
    company_id: str,
    name: str,
) -> dict:
    from modules.connectsecure import get_client

    client = await get_client(scope="global")
    try:
        company = await client.update_company(company_id=company_id, name=name)
    finally:
        await client.close()

    normalized = ConnectSecureClient.normalize_company(company)
    return {
        "company": {
            "id": normalized["id"],
            "name": normalized["name"],
        }
    }
